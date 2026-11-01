/*
 * `:::` 容器语法展开（阅读端）
 * ---------------------------------------------------------------------------
 * Docusaurus / VitePress 风格的容器写法在 toast-ui Viewer 里没有对应语义，
 * 因此阅读 Markdown 之前先把它展开成 Viewer 认识的结构：
 *   - 提示框容器 `:::tip[标题] … :::` → `> [!TIP] 标题` 引用块（复用现有提示框增强器）
 *   - 代码组容器 `::: code-group labels=[…] … :::` → 占位注释 + 预生成的代码组 HTML
 *
 * 代码组的 HTML 需要原始 Markdown 才能生成，所以展开结果和面板内容一起返回，
 * 由 utils/viewerRenderer.js 在渲染占位注释时取用。
 *
 * 后端 `notes/markdown_extensions.py` 实现了同一套语义，两端结构保持一致。
 */

import { buildCodeBlockHtml, buildCodeGroupHtml, parseFenceInfo, replaceEmojiShortcodes } from './fenceInfo'

const COMBINABLE = new Set([
  'note', 'abstract', 'summary', 'tldr', 'info', 'todo',
  'tip', 'hint', 'important', 'success', 'check', 'done',
  'question', 'help', 'faq', 'warning', 'caution', 'attention',
  'danger', 'error', 'failure', 'fail', 'missing', 'bug',
  'example', 'quote', 'cite',
])

const ALIASES = {
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

const OPEN_RE = /^(?::{3,})\s*([A-Za-z][\w-]*)\s*(.*)$/
const PLACEHOLDER_PREFIX = 'moonbird-code-group:'

const resolveContainerType = (name = '') => {
  const key = String(name).toLowerCase()
  const canonical = ALIASES[key] || key
  return COMBINABLE.has(key) || COMBINABLE.has(canonical) ? canonical.toUpperCase() : ''
}

const splitFenceSegments = (lines) => {
  const segments = []
  let buffer = []
  let index = 0

  const flushText = () => {
    if (buffer.some((line) => line.trim())) {
      segments.push({ kind: 'text', lines: buffer })
    }
    buffer = []
  }

  while (index < lines.length) {
    const fence = lines[index].match(/^(`{3,}|~{3,})\s*(.*)$/)
    if (!fence) {
      buffer.push(lines[index])
      index += 1
      continue
    }

    const marker = fence[1]
    const closer = new RegExp(`^${marker[0]}{${marker.length},}\\s*$`)
    const code = []
    let cursor = index + 1
    while (cursor < lines.length && !closer.test(lines[cursor])) {
      code.push(lines[cursor])
      cursor += 1
    }

    if (cursor >= lines.length) {
      buffer.push(lines[index])
      index += 1
      continue
    }

    flushText()
    segments.push({ kind: 'code', info: fence[2], code: code.join('\n') })
    index = cursor + 1
  }

  flushText()
  return segments
}

const buildGroupPanels = (innerLines, labels) => {
  const segments = splitFenceSegments(innerLines)
  if (!segments.length) {
    return []
  }

  const resolvedLabels = [...labels]
  while (resolvedLabels.length < segments.length) {
    resolvedLabels.push(`Tab ${resolvedLabels.length + 1}`)
  }

  return segments.map((segment, index) => ({
    label: resolvedLabels[index],
    html:
      segment.kind === 'code'
        ? buildCodeBlockHtml(segment.code, parseFenceInfo(segment.info))
        : // 代码组里的普通文本按段落输出，保持与代码块一致的间距
          segment.lines
            .filter((line) => line.trim())
            .map((line) => `<p>${line.replace(/[&<>]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[char]))}</p>`)
            .join(''),
  }))
}

const parseLabels = (rest = '') => {
  const match = String(rest || '').match(/labels=\[([^\]]*)\]/)
  if (!match) {
    return []
  }
  return match[1]
    .split(',')
    .map((chunk) => replaceEmojiShortcodes(chunk.trim().replace(/^["']|["']$/g, '').trim()))
    .filter(Boolean)
}

/**
 * 展开 `:::` 容器语法。
 * @param {string} markdown
 * @returns {{ markdown: string, groups: Array<Array<{label: string, html: string}>> }}
 */
export const expandDirectives = (markdown = '') => {
  const source = String(markdown || '')
  if (!source.includes(':::')) {
    return { markdown: source, groups: [] }
  }

  const lines = source.split('\n')
  const output = []
  const groups = []
  let index = 0

  while (index < lines.length) {
    const match = lines[index].match(OPEN_RE)
    const type = match ? resolveContainerType(match[1]) : ''
    const isCodeGroup = Boolean(match) && match[1].toLowerCase() === 'code-group'

    if (!match || (!type && !isCodeGroup)) {
      output.push(lines[index])
      index += 1
      continue
    }

    const fence = lines[index].match(/^:{3,}/)[0]
    const closer = new RegExp(`^${fence}[ \\t]*$`)
    const inner = []
    let cursor = index + 1
    while (cursor < lines.length && !closer.test(lines[cursor])) {
      inner.push(lines[cursor])
      cursor += 1
    }

    if (cursor >= lines.length) {
      // 未闭合：按普通文本回退，避免吞掉后文
      output.push(lines[index])
      index += 1
      continue
    }

    if (isCodeGroup) {
      const panels = buildGroupPanels(inner, parseLabels(match[2]))
      if (panels.length) {
        const groupIndex = groups.push(panels) - 1
        output.push(`<!--${PLACEHOLDER_PREFIX}${groupIndex}-->`)
        output.push('')
      }
    } else {
      const title = String(match[2] || '').trim().replace(/^\[(.*)\]$/, '$1').trim()
      output.push(`> [!${type}]${title ? ` ${title}` : ''}`)
      inner.forEach((line) => output.push(line.trim() ? `> ${line}` : '>'))
      output.push('')
    }

    index = cursor + 1
  }

  return { markdown: output.join('\n'), groups }
}

/** 判断一段 HTML 是否是代码组占位注释，并取出下标。 */
export const matchGroupPlaceholder = (html = '') => {
  const match = String(html || '').match(new RegExp(`<!--${PLACEHOLDER_PREFIX}(\\d+)-->`))
  return match ? Number(match[1]) : null
}

/** 用面板内容生成代码组 HTML。 */
export const renderGroupPlaceholder = (groups, index) => {
  const panels = groups?.[index]
  return panels?.length ? buildCodeGroupHtml(panels) : ''
}
