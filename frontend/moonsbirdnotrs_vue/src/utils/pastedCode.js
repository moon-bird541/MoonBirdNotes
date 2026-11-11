/*
 * 粘贴代码块修复
 * ---------------------------------------------------------------------------
 * 从部分站点 / AI 对话页复制代码时，剪贴板 HTML 会把「一行代码」包成独立的
 * <pre>（或 <pre><div>行</div>…</pre>）。ProseMirror 会把每个 <pre> 解析成一个
 * codeBlock 节点，于是整段代码被拆成「一行一个代码块」，且语言一律为空，
 * 编辑器里就是一堆带 "text" 标签的单行代码块。
 *
 * 这里在粘贴进入编辑器之前把这类 HTML 还原成单个 <pre>：
 *   1. <pre> 内是逐行包裹的块级子节点 → 按行拼回带换行的文本；
 *   2. 连续出现 3 个以上「单行 <pre>」→ 合并成一个多行代码块。
 * 只有能确定是「被拆开的一段代码」时才改写，其它粘贴保持 toast-ui 原行为。
 */

/** 会被当成「一行」的块级包装标签 */
const LINE_WRAPPER_TAGS = new Set(['DIV', 'P', 'LI', 'TR'])

/** 少于这个数量的连续单行 <pre> 视为用户本来就要的多段代码，不合并 */
const MIN_SPLIT_RUN = 3

const singleLineText = (node) => node.textContent.replace(/\n+$/, '')

/** <pre><div>行1</div><div>行2</div></pre> → <pre>行1\n行2</pre> */
const flattenLineWrappedPre = (pre) => {
  const container = pre.querySelector(':scope > code') || pre
  const children = Array.from(container.children)

  if (children.length < 2) {
    return false
  }
  if (!children.every((child) => LINE_WRAPPER_TAGS.has(child.tagName))) {
    return false
  }
  // 行包装里还有真正的块级结构时，可能是正常内容而不是逐行代码
  if (children.some((child) => child.querySelector('pre, ul, ol, table'))) {
    return false
  }

  container.textContent = children.map(singleLineText).join('\n')
  return true
}

/** 把紧挨着的、各自只有一行的若干个 <pre> 合并成一个多行代码块 */
const mergeSplitPreRun = (pre) => {
  if (singleLineText(pre).includes('\n')) {
    return false
  }

  const group = [pre]
  let cursor = pre.nextSibling

  while (cursor) {
    // 只允许空白文本节点夹在 <pre> 之间
    if (cursor.nodeType === 3 && !cursor.textContent.trim()) {
      cursor = cursor.nextSibling
      continue
    }
    if (cursor.nodeType !== 1 || cursor.tagName !== 'PRE') {
      break
    }
    if (singleLineText(cursor).includes('\n')) {
      break
    }
    group.push(cursor)
    cursor = cursor.nextSibling
  }

  if (group.length < MIN_SPLIT_RUN) {
    return false
  }

  // 保留第一个代码宿主的 <code class="language-…">，语言信息不丢
  const container = pre.querySelector(':scope > code') || pre
  container.textContent = group.map(singleLineText).join('\n')
  group.slice(1).forEach((node) => node.remove())
  return true
}

/**
 * 归一化剪贴板里的代码 HTML。
 * @param {string} html
 * @returns {string | null} 需要改写时返回新的 HTML，否则返回 null
 */
export const normalizePastedCodeHtml = (html) => {
  if (!html || !/<pre[\s>]/i.test(html)) {
    return null
  }

  const doc = new DOMParser().parseFromString(html, 'text/html')
  let changed = false

  doc.querySelectorAll('pre').forEach((pre) => {
    if (flattenLineWrappedPre(pre)) {
      changed = true
    }
  })

  doc.querySelectorAll('pre').forEach((pre) => {
    if (pre.isConnected && mergeSplitPreRun(pre)) {
      changed = true
    }
  })

  return changed ? doc.body.innerHTML : null
}

/**
 * 生成 toast-ui 插件：粘贴时修复被拆成「一行一个代码块」的代码。
 *
 * toast-ui 自己的 handlePaste 只处理表格粘贴（非表格返回 false），
 * 因此这里的 handlePaste 仍会被调用；返回 true 表示已由我们接管。
 * 归一化后的 HTML 直接交给 ProseMirror 的 pasteHTML，插入行为与原生粘贴一致
 * （选区、列表上下文、撤销记录都由编辑器自己处理）。
 */
export const createCodePasteFix = () => (context) => {
  const { Plugin } = context.pmState

  // 防止 view.pasteHTML 再次触发本插件、造成重复插入
  let repairing = false

  return {
    wysiwygPlugins: [
      () =>
        new Plugin({
          props: {
            handlePaste(view, event) {
              if (repairing) {
                return false
              }

              const html = event.clipboardData?.getData?.('text/html')
              if (!html) {
                return false
              }

              const normalized = normalizePastedCodeHtml(html)
              if (!normalized) {
                return false
              }

              repairing = true
              try {
                // 不传原事件：否则 pasteHTML 内部再次回调本插件会读到未修复的剪贴板。
                // 测试环境（jsdom）没有 ClipboardEvent，用一个最小事件对象兜底。
                const pasteEvent =
                  typeof ClipboardEvent === 'function'
                    ? new ClipboardEvent('paste')
                    : { type: 'paste', clipboardData: null }
                view.pasteHTML(normalized, pasteEvent)
                return true
              } catch (error) {
                // 修复失败时回退到 toast-ui 的默认粘贴
                console.warn('[editor] 粘贴代码块归一化失败，回退默认粘贴：', error)
                return false
              } finally {
                repairing = false
              }
            },
          },
        }),
    ],
  }
}
