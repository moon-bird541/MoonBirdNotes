/*
 * 富文本（WYSIWYG）内的扩展语法即时预览
 * ---------------------------------------------------------------------------
 * toast-ui 的富文本面板只把 Markdown 转成普通 blockquote / codeBlock，
 * `> [!NOTE] 标题` 和 ```js title="…" {1}``` 在写作时看着就是一堆参数文本。
 *
 * 这里用 ProseMirror 的 decoration 把已有节点「就地」换成最终外观：
 *   - 提示框：给 blockquote 加配色类，隐藏 `[!TYPE]` 标记，行首插入标题
 *   - 代码块：在代码块上方插入一条信息栏（语言 / 标题 / 徽标 / 设置入口）
 *
 * 为什么必须是 decoration 而不是手写 DOM：ProseMirror 每次事务都会按文档重建
 * 节点视图，任何手动 append 到节点里的元素都会被移除；只有 decoration 归编辑器
 * 自己维护，能稳定跟随文档变化。
 *
 * 插件工厂的 context 由 toast-ui 注入，Plugin / Decoration 必须从 context 取，
 * 否则会与编辑器内部的 prosemirror 副本产生类身份不一致。
 *
 * 交互按钮通过 eventEmitter 把事件抛给宿主视图，插件本身不持有编辑器实例，
 * 也不直接改文档。
 */

import { parseFenceInfo } from './fenceInfo'

const CALLOUT_TYPES = {
  note: { family: 'note', label: '注意', icon: 'ℹ' },
  abstract: { family: 'note', label: '摘要', icon: '📋' },
  info: { family: 'note', label: '信息', icon: 'ℹ' },
  todo: { family: 'note', label: '待办', icon: '☐' },
  tip: { family: 'tip', label: '提示', icon: '✦' },
  success: { family: 'tip', label: '成功', icon: '✔' },
  question: { family: 'tip', label: '问题', icon: '❓' },
  important: { family: 'important', label: '重要', icon: '❢' },
  example: { family: 'important', label: '示例', icon: '🧪' },
  warning: { family: 'warning', label: '警告', icon: '⚠' },
  caution: { family: 'danger', label: '小心', icon: '⛔' },
  danger: { family: 'danger', label: '危险', icon: '⛔' },
  failure: { family: 'danger', label: '失败', icon: '✖' },
  bug: { family: 'danger', label: '缺陷', icon: '🐞' },
  quote: { family: 'note', label: '引用', icon: '❝' },
}

const CALLOUT_ALIASES = {
  summary: 'abstract',
  tldr: 'abstract',
  hint: 'tip',
  check: 'success',
  done: 'success',
  help: 'question',
  faq: 'question',
  attention: 'caution',
  error: 'danger',
  fail: 'failure',
  missing: 'failure',
  cite: 'quote',
}

const MARKER_RE = /^\[!([A-Za-z][\w-]*)\][ \t]*(.*)$/
const HIDDEN_CLASS = 'mb-source-hidden'

const resolveCallout = (name = '') => {
  const key = CALLOUT_ALIASES[String(name).toLowerCase()] || String(name).toLowerCase()
  return CALLOUT_TYPES[key] ? { canonical: key, ...CALLOUT_TYPES[key] } : null
}

/** 取段落第一行的文本（softbreak 用 \n 连接）。 */
const firstLineOf = (paragraph) =>
  paragraph.textBetween(0, paragraph.content.size, '\n').split('\n')[0] || ''

const stopPointer = (event) => {
  event.preventDefault()
  event.stopPropagation()
}

const createCalloutTitle = (icon, label) => {
  const element = document.createElement('span')
  element.className = 'mb-callout-preview-title'
  element.setAttribute('contenteditable', 'false')
  element.textContent = `${icon} ${label}`
  return element
}

const describeBadges = (info) => {
  const badges = []
  if (info.showLineNumbers) {
    badges.push(info.startLineNumber > 1 ? `行号 ${info.startLineNumber}+` : '行号')
  }
  if (info.marks.length) {
    badges.push('行标记')
  }
  if (info.collapse.length) {
    badges.push('折叠')
  }
  if (info.frame !== 'auto') {
    badges.push(`frame=${info.frame}`)
  }
  return badges
}

/** 代码块信息栏：语言胶囊 + 标题 + 参数徽标 + 设置按钮。 */
const createCodeHead = (info, handlers) => {
  const head = document.createElement('div')
  head.className = 'mb-code-preview-head'
  head.setAttribute('contenteditable', 'false')

  const language = document.createElement('button')
  language.type = 'button'
  language.className = 'mb-code-preview-lang'
  language.textContent = info.lang || 'text'
  language.title = '修改代码块语言'
  language.addEventListener('mousedown', stopPointer)
  language.addEventListener('click', (event) => {
    stopPointer(event)
    handlers.editLanguage()
  })
  head.appendChild(language)

  if (info.title) {
    const title = document.createElement('span')
    title.className = 'mb-code-preview-title'
    title.textContent = info.title
    head.appendChild(title)
  }

  const badges = describeBadges(info)
  if (badges.length) {
    const badge = document.createElement('span')
    badge.className = 'mb-code-preview-badges'
    badge.textContent = badges.join(' · ')
    head.appendChild(badge)
  }

  const options = document.createElement('button')
  options.type = 'button'
  options.className = 'mb-code-preview-options'
  options.textContent = '⋯'
  options.title = '代码块设置（标题 / 行号 / 标记 / 折叠）'
  options.setAttribute('aria-label', '代码块设置')
  options.addEventListener('mousedown', stopPointer)
  options.addEventListener('click', (event) => {
    stopPointer(event)
    handlers.editOptions()
  })
  head.appendChild(options)

  return head
}

/**
 * 生成 toast-ui 插件：为富文本面板提供扩展语法即时预览。
 *
 * toast-ui 的 eventEmitter 只允许内置事件类型，自定义事件会在 listen 时抛错，
 * 因此交互回调通过闭包传入，插件本身不持有编辑器实例、也不直接改文档。
 *
 * @param {{ onEditLanguage?: (pos:number)=>void, onEditOptions?: (pos:number)=>void }} handlers
 * @returns {(context: object) => { wysiwygPlugins: Function[] }}
 */
export const createRichBlockPreview = (handlers = {}) => (context) => {
  const { Plugin } = context.pmState
  const { Decoration, DecorationSet } = context.pmView

  return {
    wysiwygPlugins: [
      () =>
        new Plugin({
          props: {
            decorations(state) {
              const decorations = []

              state.doc.descendants((node, pos) => {
                if (node.type.name === 'blockQuote') {
                  const paragraph = node.firstChild
                  if (!paragraph || paragraph.type.name !== 'paragraph') {
                    return
                  }

                  const firstLine = firstLineOf(paragraph)
                  const marker = firstLine.match(MARKER_RE)
                  const meta = marker ? resolveCallout(marker[1]) : null
                  if (!meta) {
                    return
                  }

                  decorations.push(
                    Decoration.node(pos, pos + node.nodeSize, {
                      class: `moonbird-callout moonbird-callout-${meta.family} moonbird-callout-${meta.canonical} is-callout-preview`,
                    })
                  )

                  // 光标停在标记行上且编辑器有焦点时保留原文，否则无法修改类型与标题
                  const lineStart = pos + 2
                  const lineEnd = lineStart + firstLine.length
                  const caretOnMarker =
                    state.selection.from >= lineStart && state.selection.from <= lineEnd
                  const editingMarker = caretOnMarker && handlers.isEditorFocused?.()

                  if (editingMarker) {
                    return
                  }

                  // 隐藏 `[!TYPE] 标题` 整行，改由 widget 展示标题
                  if (firstLine.length) {
                    decorations.push(
                      Decoration.inline(lineStart, lineEnd, {
                        class: HIDDEN_CLASS,
                      })
                    )
                  }

                  decorations.push(
                    Decoration.widget(
                      lineStart,
                      () => createCalloutTitle(meta.icon, marker[2].trim() || meta.label),
                      { side: -1 }
                    )
                  )
                  return
                }

                // `::: code-group …` / `:::` 这类容器行在富文本里只是普通段落，
                // 用弱化样式标出来，避免误以为是正文
                if (node.type.name === 'paragraph') {
                  const text = node.textBetween(0, node.content.size, '\n').trim()
                  if (text.startsWith(':::')) {
                    decorations.push(
                      Decoration.node(pos, pos + node.nodeSize, { class: 'mb-directive-preview' })
                    )
                  }
                  return
                }

                if (node.type.name !== 'codeBlock') {
                  return
                }

                // 每次重算 decoration 都会新建 widget，闭包里的 pos 因而始终是最新的
                const info = parseFenceInfo(node.attrs?.language || '')
                decorations.push(
                  Decoration.node(pos, pos + node.nodeSize, { class: 'mb-code-preview' })
                )
                decorations.push(
                  Decoration.widget(
                    pos,
                    () =>
                      createCodeHead(info, {
                        editLanguage: () => handlers.onEditLanguage?.(pos),
                        editOptions: () => handlers.onEditOptions?.(pos),
                      }),
                    { side: -1 }
                  )
                )
              })

              return DecorationSet.create(state.doc, decorations)
            },
          },
        }),
    ],
  }
}
