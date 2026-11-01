/*
 * 富文本（ProseMirror）里的扩展语法写入
 * ---------------------------------------------------------------------------
 * toast-ui 的 exec 命令只认识它自己的 block 类型，`> [!NOTE]`、`::: code-group`
 * 这些扩展语法没有对应命令；直接 insertText 会把 `>` 写成正文并留下转义字符。
 *
 * 因此这里直接操作 ProseMirror 文档：
 *   - 提示框：构造 / 复用真正的 blockQuote（标记段 + 正文）
 *   - 公式：写入纯文本（行内 `$…$` / 块级 `$$…$$`）
 *
 * 统一的编辑语义（笔记与日记编辑器共用）：
 *   - 选区在提示框内、点的又是同一种类型 → **取消**提示框（还原成普通正文）
 *   - 选区在提示框内、点的是另一种类型 → **改类型**（只改标记段，不嵌套）
 *   - 不在提示框内 → 有选区就**包裹**选中内容，无选区就插入占位提示框
 *
 * 任何路径都不允许丢弃选中的正文：用户很容易先 Ctrl+A 再点按钮。
 *
 * 返回值表示是否写入成功，调用方据此决定是否提示"编辑器未准备好"。
 * 本模块不导入任何 Vue / Element Plus 代码。
 */

import { TextSelection } from 'prosemirror-state'
import { liftTarget } from 'prosemirror-transform'

const CALLOUT_MARKER_RE = /^\[!([A-Za-z][\w-]*)\](?:[ \t]+(.*))?$/

/**
 * 找到选区"涉及"的 blockQuote。
 *
 * 不能只看 `$from` 的祖先链：用户按 Ctrl+A 时 `$from` 落在文档开头，
 * 根本不在提示框里，但意图显然是要动提示框。
 *
 * 判断顺序：
 *   1. 光标起点在某个提示框内 → 就是它（最常见的真实路径）
 *   2. 否则选区终点在某个提示框内 → 就是它（从后往前选中）
 *   3. 否则取选区覆盖到的**第一个**提示框
 *
 * 第 3 条刻意宁可"动第一个"也不返回 null：返回 null 会让调用方把整段
 * （本来就含提示框）再包一层，也就是用户最反感的嵌套。取消 / 改类型
 * 都不会丢正文，误操作代价远小于嵌套一层引用。
 */
export const findCalloutAncestor = (state) => {
  const { doc, selection } = state
  const { $from, $to, from, to } = selection

  const ancestorOf = ($pos) => {
    for (let depth = $pos.depth; depth >= 1; depth -= 1) {
      const node = $pos.node(depth)
      if (node.type.name === 'blockQuote') {
        return { node, pos: $pos.before(depth), depth }
      }
    }
    return null
  }

  const fromAncestor = ancestorOf($from)
  if (fromAncestor) {
    return fromAncestor
  }

  const toAncestor = ancestorOf($to)
  if (toAncestor) {
    return toAncestor
  }

  let first = null
  doc.nodesBetween(from, to, (node, pos) => {
    if (first) {
      return false
    }
    if (node.type.name === 'blockQuote') {
      first = { node, pos, depth: 1 }
      return false
    }
    return true
  })

  return first
}

/** 读取提示框的标记段：返回 { type, title, paragraph, text }。 */
export const readCalloutMarker = (blockQuote) => {
  const paragraph = blockQuote?.firstChild
  if (!paragraph || paragraph.type.name !== 'paragraph' || !paragraph.textContent) {
    return null
  }

  const match = paragraph.textContent.match(CALLOUT_MARKER_RE)
  if (!match) {
    return null
  }

  return {
    type: match[1].toUpperCase(),
    title: (match[2] || '').trim(),
    paragraph,
    text: paragraph.textContent,
  }
}

/**
 * 决定实际写入范围。
 * 行内写法（wrapSelection）保留选区以便包裹；块级写法一律折叠到选区末尾。
 */
const resolveInsertRange = (selection, options) => {
  const { from, to } = selection
  const wrapsSelection = Boolean(options.wrapSelection) && from !== to

  return wrapsSelection
    ? { from, to, wrapsSelection: true }
    : { from: to, to, wrapsSelection: false }
}

/** 在光标处写入纯文本；块级写入不吞掉选中内容。 */
export const insertWysiwygText = (view, text, options = {}) => {
  if (!view || !text) {
    return false
  }

  const { state } = view
  const { from, to, wrapsSelection } = resolveInsertRange(state.selection, options)
  const selected = wrapsSelection ? state.doc.textBetween(from, to, '\n') : ''
  const content = wrapsSelection ? `${options.before ?? ''}${selected}${options.after ?? ''}` : text

  const tr = state.tr.insertText(content, from, to)
  const caret = from + content.length

  if (wrapsSelection) {
    tr.setSelection(TextSelection.create(tr.doc, caret, caret))
  } else if (Number.isFinite(options.selectOffset) && options.selectLength > 0) {
    const start = Math.min(from + options.selectOffset, tr.doc.content.size)
    const end = Math.min(start + options.selectLength, tr.doc.content.size)
    if (end > start) {
      tr.setSelection(TextSelection.create(tr.doc, start, end))
    }
  }

  tr.scrollIntoView()
  view.dispatch(tr)
  return true
}

/** 取消提示框：删掉标记段，再把剩余内容从 blockQuote 里提出来。 */
const unwrapCallout = (view, found) => {
  const { state } = view
  const { pos, node, depth } = found
  const marker = readCalloutMarker(node)

  if (!marker) {
    return false
  }

  const tr = state.tr
  // 标记段相对 blockQuote 内容的偏移是 0，绝对位置为 pos + 1
  tr.delete(pos + 1, pos + 1 + marker.paragraph.nodeSize)

  const lifted = tr.doc.nodeAt(pos)
  if (lifted && lifted.type.name === 'blockQuote') {
    // 标记段删掉后只剩正文，尝试整体 lift 出引用块
    const $pos = tr.doc.resolve(pos + 1)
    const range = $pos.blockRange(tr.doc.resolve(pos + lifted.nodeSize - 1), (n) => n.type.name === 'blockQuote')
    const target = range ? liftTarget(range) : null

    if (range && target !== null) {
      tr.lift(range, target)
    }
  }

  if (!tr.docChanged) {
    return false
  }

  const caret = Math.min(pos, tr.doc.content.size)
  tr.setSelection(TextSelection.near(tr.doc.resolve(caret)))
  tr.scrollIntoView()
  view.dispatch(tr)
  return true
}

/** 改类型：只替换标记段的类型词，保留自定义标题、正文与已有格式。 */
const retypeCallout = (view, found, kind, title) => {
  const { state } = view
  const { pos } = found
  const marker = readCalloutMarker(found.node)

  if (!marker) {
    return false
  }

  // 没显式给标题时沿用原有标题：改类型不应该顺手删掉用户写的标题
  const nextTitle = title || marker.title
  const nextText = nextTitle ? `[!${kind}] ${nextTitle}` : `[!${kind}]`
  if (marker.text === nextText) {
    return false
  }

  const paragraphStart = pos + 1
  const paragraphEnd = paragraphStart + marker.paragraph.nodeSize
  const tr = state.tr.insertText(nextText, paragraphStart + 1, paragraphEnd - 1)

  tr.scrollIntoView()
  view.dispatch(tr)
  return true
}

/**
 * 应用提示框。
 *
 * - 选区已在同类型提示框内 → 取消
 * - 选区在另一种提示框内 → 改类型（不嵌套）
 * - 其它情况 → 有选区就包裹，无选区就插入占位提示框
 *
 * @param {object} view ProseMirror EditorView
 * @param {{ kind?: string, title?: string }} options
 */
export const applyWysiwygCallout = (view, options = {}) => {
  if (!view) {
    return false
  }

  const { state } = view
  const { schema } = state
  const blockQuoteType = schema.nodes.blockQuote
  const paragraphType = schema.nodes.paragraph
  const selection = state.selection

  if (!blockQuoteType || !paragraphType || !selection?.$from) {
    return false
  }

  const kind = String(options.kind || 'note').toUpperCase()
  const title = String(options.title || '').trim()

  // ① 已经在一个提示框里：同类型取消、异类型改类型
  const existing = findCalloutAncestor(state)
  if (existing) {
    const marker = readCalloutMarker(existing.node)
    if (marker) {
      return marker.type === kind
        ? unwrapCallout(view, existing)
        : retypeCallout(view, existing, kind, title)
    }
  }

  const marker = title ? `[!${kind}] ${title}` : `[!${kind}]`
  const placeholder = '提示内容'
  const markerParagraph = (text) => paragraphType.create(null, schema.text(text))

  // ② 有选区：把选中的 blocks 包进 blockQuote，标记段放最前面
  if (!selection.empty) {
    const range = selection.$from.blockRange(selection.$to)
    const tr = state.tr

    if (range) {
      tr.wrap(range, [{ type: blockQuoteType }])
    }

    if (tr.docChanged) {
      tr.insert(range.start + 1, markerParagraph(marker))

      const caret = Math.min(tr.mapping.map(selection.to), tr.doc.content.size)
      tr.setSelection(TextSelection.create(tr.doc, caret))
      tr.scrollIntoView()
      view.dispatch(tr)
      return true
    }
  }

  // ③ 无选区：插入新提示框；光标在空段落时整块替换，避免留下空行
  const quote = blockQuoteType.create(null, [
    markerParagraph(marker),
    markerParagraph(placeholder),
  ])

  const tr = state.tr
  const $from = selection.$from
  let insertPos = selection.to
  let replacedBlock = false

  if ($from.depth >= 1) {
    const blockStart = $from.before(1)
    const block = $from.node(1)
    if (block.type === paragraphType && block.content.size === 0 && selection.empty) {
      tr.replaceWith(blockStart, blockStart + block.nodeSize, quote)
      insertPos = blockStart
      replacedBlock = true
    }
  }

  if (!replacedBlock) {
    tr.insert(selection.to, quote)
  }

  // 正文段落起点：quote 开口 1 + 标记段 nodeSize(marker + 2) + 正文段开口 1
  const bodyFrom = Math.min(insertPos + marker.length + 4, tr.doc.content.size)
  const bodyTo = Math.min(bodyFrom + placeholder.length, tr.doc.content.size)

  if (bodyTo > bodyFrom) {
    tr.setSelection(TextSelection.create(tr.doc, bodyFrom, bodyTo))
  }
  tr.scrollIntoView()

  view.dispatch(tr)
  return true
}

/** 选区当前所处的提示框类型（大写），不在提示框内返回空串。 */
export const getActiveCalloutType = (state) => {
  const existing = findCalloutAncestor(state)
  return existing ? readCalloutMarker(existing.node)?.type || '' : ''
}
