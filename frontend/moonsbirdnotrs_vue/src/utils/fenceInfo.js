/*
 * 代码块 info-string 解析与 HTML 生成（Firefly / Expressive Code 风格）
 * ---------------------------------------------------------------------------
 * 形如：
 *   ```js title="app.js" {1,3-5} ins={6} del={"2":7-8} showLineNumbers startLineNumber=5
 *       collapse={1-4} wrap=false frame=none
 *
 * 这份实现与后端 `backend/notes/markdown_extensions.py` 一一对应：
 * 同一段 Markdown 在阅读端、编辑器预览、导出 HTML 三处必须产出相同结构，
 * 样式与交互只写一次。改动任何一侧都要同步另一侧。
 */

const TERMINAL_LANGUAGES = new Set([
  'bash',
  'bat',
  'cmd',
  'console',
  'fish',
  'nu',
  'powershell',
  'ps',
  'ps1',
  'sh',
  'shell',
  'shellsession',
  'terminal',
  'zsh',
])

const QUOTES = new Set(['"', "'"])
const KNOWN_FLAG = /^(showLineNumbers|wrap|preserveIndent|frame|title|startLineNumber|collapse|lang|mark|ins|del)(=|$)/
const RANGE_RE = /^(\d+)(?:\s*-\s*(\d+))?$/
const LABELLED_RE = /^(["'])(.*?)\1\s*:\s*(.+)$/
const MARK_WEIGHT = { mark: 1, ins: 2, del: 3 }

export const EMOJI_SHORTCODES = {
  package: '📦',
  yarn: '🧶',
  npm: '📦',
  pnpm: '📦',
  rocket: '🚀',
  fire: '🔥',
  star: '⭐',
  bulb: '💡',
  warning: '⚠️',
  gear: '⚙️',
  hammer: '🔨',
  book: '📖',
  memo: '📝',
  link: '🔗',
}

export const escapeHtml = (value = '') =>
  String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')

/** 按空白拆分 info-string，保留引号 / 花括号 / 正则内部的空白。 */
export const splitInfoTokens = (info = '') => {
  const source = String(info || '')
  const tokens = []
  let current = ''
  let quote = ''
  let braceDepth = 0
  let inRegex = false

  for (let index = 0; index < source.length; index += 1) {
    const char = source[index]
    const previous = index ? source[index - 1] : ''

    if (quote) {
      current += char
      if (char === quote && previous !== '\\') {
        quote = ''
      }
      continue
    }

    if (inRegex) {
      current += char
      if (char === '/' && previous !== '\\') {
        inRegex = false
      }
      continue
    }

    if (char === '{') {
      braceDepth += 1
      current += char
      continue
    }

    if (char === '}') {
      braceDepth = Math.max(0, braceDepth - 1)
      current += char
      continue
    }

    if (braceDepth === 0 && QUOTES.has(char)) {
      quote = char
      current += char
      continue
    }

    if (braceDepth === 0 && char === '/' && !current) {
      inRegex = true
      current += char
      continue
    }

    if (braceDepth === 0 && /\s/.test(char)) {
      if (current) {
        tokens.push(current)
        current = ''
      }
      continue
    }

    current += char
  }

  if (current) {
    tokens.push(current)
  }

  return tokens
}

/** 解析 `{1,3-5}` / `{"说明":7-8, 12}`。 */
export const parseLineRanges = (spec = '') => {
  let source = String(spec || '').trim()
  if (source.startsWith('{')) {
    source = source.slice(1)
  }
  if (source.endsWith('}')) {
    source = source.slice(0, -1)
  }

  const ranges = []
  source.split(',').forEach((chunk) => {
    const piece = chunk.trim()
    if (!piece) {
      return
    }

    let label = ''
    let rest = piece
    const labelled = piece.match(LABELLED_RE)
    if (labelled) {
      label = labelled[2]
      rest = labelled[3]
    }

    rest.trim().split(/\s+/).forEach((part) => {
      const match = part.match(RANGE_RE)
      if (!match) {
        return
      }
      const start = Number(match[1])
      const end = match[2] ? Number(match[2]) : start
      if (!Number.isFinite(start) || start < 1) {
        return
      }
      ranges.push({ start, end: Math.max(start, end), label })
    })
  })

  return ranges
}

const parseMarkValue = (raw) => {
  const value = String(raw || '').trim()
  if (!value) {
    return null
  }

  if (value.startsWith('{')) {
    const ranges = parseLineRanges(value)
    return ranges.length ? { kind: 'lines', ranges } : null
  }

  if (value.startsWith('/') && value.endsWith('/') && value.length > 2) {
    return { kind: 'regex', regex: value.slice(1, -1) }
  }

  if (QUOTES.has(value[0]) && value.endsWith(value[0]) && value.length > 1) {
    const text = value.slice(1, -1)
    return text ? { kind: 'text', text } : null
  }

  return null
}

const parseBoolean = (value, fallback = true) => {
  if (value === undefined) {
    return fallback
  }
  const normalized = String(value).trim().toLowerCase()
  if (['false', 'no', '0', 'off'].includes(normalized)) {
    return false
  }
  if (['true', 'yes', '1', 'on'].includes(normalized)) {
    return true
  }
  return fallback
}

const unquote = (value = '') => {
  const trimmed = String(value).trim()
  if (trimmed.length > 1 && QUOTES.has(trimmed[0]) && trimmed.endsWith(trimmed[0])) {
    return trimmed.slice(1, -1)
  }
  return trimmed
}

/** 解析完整 fence info-string。 */
export const parseFenceInfo = (info = '') => {
  const tokens = splitInfoTokens(info)
  const result = {
    lang: '',
    title: '',
    frame: 'auto',
    wrap: true,
    preserveIndent: true,
    showLineNumbers: false,
    startLineNumber: 1,
    collapse: [],
    marks: [],
    rest: '',
  }
  const leftovers = []

  tokens.forEach((token, index) => {
    const assignment = token.match(/^([A-Za-z][\w-]*)=(.*)$/)
    const key = assignment ? assignment[1] : ''
    const value = assignment ? assignment[2] : ''

    if (!assignment && index === 0 && !KNOWN_FLAG.test(token) && !token.startsWith('{')) {
      const markValue = parseMarkValue(token)
      if (markValue && markValue.kind === 'lines') {
        result.marks.push({ type: 'mark', kind: 'lines', ranges: markValue.ranges })
        return
      }
      result.lang = token.replace(/^\./, '')
      return
    }

    if (!assignment) {
      if (token.startsWith('{')) {
        const ranges = parseLineRanges(token)
        if (ranges.length) {
          result.marks.push({ type: 'mark', kind: 'lines', ranges })
          return
        }
      }
      const markValue = parseMarkValue(token)
      if (markValue) {
        result.marks.push({ type: 'mark', ...markValue })
        return
      }
      if (token === 'showLineNumbers') {
        result.showLineNumbers = true
        return
      }
      if (token === 'wrap') {
        result.wrap = true
        return
      }
      if (token === 'preserveIndent') {
        result.preserveIndent = true
        return
      }
      leftovers.push(token)
      return
    }

    switch (key) {
      case 'lang':
        result.lang = unquote(value).replace(/^\./, '')
        break
      case 'title':
        result.title = unquote(value)
        break
      case 'frame': {
        const frame = unquote(value)
        result.frame = ['code', 'terminal', 'none', 'auto'].includes(frame) ? frame : 'auto'
        break
      }
      case 'wrap':
        result.wrap = parseBoolean(value, true)
        break
      case 'preserveIndent':
        result.preserveIndent = parseBoolean(value, true)
        break
      case 'showLineNumbers':
        result.showLineNumbers = parseBoolean(value, true)
        break
      case 'startLineNumber': {
        const parsed = Number.parseInt(unquote(value), 10)
        result.startLineNumber = Number.isFinite(parsed) && parsed > 0 ? parsed : 1
        break
      }
      case 'collapse':
        result.collapse = parseLineRanges(value)
        break
      case 'mark':
      case 'ins':
      case 'del': {
        const markValue = parseMarkValue(value)
        if (markValue) {
          result.marks.push({ type: key, ...markValue })
        }
        break
      }
      default:
        leftovers.push(token)
    }
  })

  result.rest = leftovers.join(' ')
  return result
}

/** 把 marks 展开成 行号 -> { type, label }，优先级 del > ins > mark。 */
export const buildLineMarkMap = (marks = [], lines = []) => {
  const markMap = new Map()

  const setMark = (lineNumber, type, label = '') => {
    if (!Number.isFinite(lineNumber) || lineNumber < 1) {
      return
    }
    const existing = markMap.get(lineNumber)
    if (existing && MARK_WEIGHT[type] <= MARK_WEIGHT[existing.type]) {
      return
    }
    markMap.set(lineNumber, { type, label })
  }

  marks.forEach((mark) => {
    if (mark.kind === 'lines') {
      (mark.ranges || []).forEach((range) => {
        for (let line = range.start; line <= range.end; line += 1) {
          setMark(line, mark.type, range.label || '')
        }
      })
      return
    }

    if (mark.kind === 'text' && mark.text) {
      lines.forEach((line, index) => {
        if (line.includes(mark.text)) {
          setMark(index + 1, mark.type)
        }
      })
      return
    }

    if (mark.kind === 'regex' && mark.regex) {
      let pattern = null
      try {
        pattern = new RegExp(mark.regex)
      } catch {
        return
      }
      lines.forEach((line, index) => {
        if (pattern.test(line)) {
          setMark(index + 1, mark.type)
        }
      })
    }
  })

  return markMap
}

const detectFrame = (info) => {
  if (info.frame !== 'auto') {
    return info.frame
  }
  return TERMINAL_LANGUAGES.has(String(info.lang || '').toLowerCase()) ? 'terminal' : 'code'
}

const diffMarks = (lines) => {
  const marks = []
  lines.forEach((line, index) => {
    if (line.startsWith('+') && !line.startsWith('+++')) {
      marks.push({ type: 'ins', kind: 'lines', ranges: [{ start: index + 1, end: index + 1, label: '' }] })
    } else if (line.startsWith('-') && !line.startsWith('---')) {
      marks.push({ type: 'del', kind: 'lines', ranges: [{ start: index + 1, end: index + 1, label: '' }] })
    }
  })
  return marks
}

const inlineMarkup = (line, marks) => {
  for (const mark of marks) {
    let span = null

    if (mark.kind === 'text' && mark.text) {
      const index = line.indexOf(mark.text)
      if (index >= 0) {
        span = [index, index + mark.text.length]
      }
    } else if (mark.kind === 'regex' && mark.regex) {
      let match = null
      try {
        match = new RegExp(mark.regex).exec(line)
      } catch {
        match = null
      }
      if (match) {
        span = [match.index, match.index + match[0].length]
      }
    }

    if (span) {
      const [start, end] = span
      return `${escapeHtml(line.slice(0, start))}<span class="moonbird-code-mark">${escapeHtml(
        line.slice(start, end)
      )}</span>${escapeHtml(line.slice(end))}`
    }
  }

  return escapeHtml(line)
}

const collapseSpec = (collapse = []) => collapse.map((range) => `${range.start}-${range.end}`).join(',')

/**
 * 生成规范化代码块 HTML（与后端 `build_code_block_html` 结构完全一致）。
 * @param {string} code 原始代码文本
 * @param {object} info parseFenceInfo 结果
 */
export const buildCodeBlockHtml = (code = '', info = null) => {
  const parsed = info || parseFenceInfo('')
  let codeText = String(code ?? '')
  if (codeText.endsWith('\n')) {
    codeText = codeText.slice(0, -1)
  }
  const lines = codeText.split('\n')

  const marks = [...(parsed.marks || [])]
  const lang = parsed.lang || ''
  if (lang.toLowerCase() === 'diff' && !marks.some((mark) => mark.type !== 'mark')) {
    marks.push(...diffMarks(lines))
  }

  const collapse = parsed.collapse || []
  const markMap = buildLineMarkMap(marks, lines)
  const frame = detectFrame(parsed)
  const start = parsed.startLineNumber || 1

  const classes = ['moonbird-code']
  if (parsed.showLineNumbers) {
    classes.push('has-line-numbers')
  }
  if (frame !== 'none') {
    classes.push(`is-frame-${frame}`)
  }
  if (!parsed.wrap) {
    classes.push('is-no-wrap')
  }
  if (collapse.length) {
    classes.push('has-collapse')
  }

  const attrs = [`class="${classes.join(' ')}"`]
  if (lang) {
    attrs.push(`data-mb-lang="${escapeHtml(lang)}"`)
  }
  if (parsed.title) {
    attrs.push(`data-mb-title="${escapeHtml(parsed.title)}"`)
  }
  if (collapse.length) {
    attrs.push(`data-mb-collapse="${escapeHtml(collapseSpec(collapse))}"`)
  }
  if (start > 1) {
    attrs.push(`data-mb-start="${start}"`)
  }

  const parts = []
  if (frame !== 'none') {
    const dots = frame === 'terminal' ? '<span class="moonbird-code-dots" aria-hidden="true"></span>' : ''
    const title = parsed.title ? `<span class="moonbird-code-title">${escapeHtml(parsed.title)}</span>` : ''
    parts.push(
      `<div class="moonbird-code-head">${dots}<span class="moonbird-code-lang">${escapeHtml(
        lang || 'text'
      )}</span>${title}</div>`
    )
  }

  const lineParts = lines.map((line, index) => {
    const lineNumber = index + 1
    const mark = markMap.get(lineNumber)
    const lineClasses = ['moonbird-code-line']
    if (mark) {
      lineClasses.push(`is-${mark.type}`)
    }
    if (collapse.some((range) => range.start <= lineNumber && lineNumber <= range.end)) {
      lineClasses.push('is-collapsed')
    }
    const numberHtml = parsed.showLineNumbers
      ? `<span class="moonbird-code-lineno">${start + lineNumber - 1}</span>`
      : ''
    const noteHtml = mark && mark.label ? `<span class="moonbird-code-note">${escapeHtml(mark.label)}</span>` : ''
    return (
      `<span class="${lineClasses.join(' ')}">${numberHtml}` +
      `<span class="moonbird-code-text">${inlineMarkup(line, marks)}</span>${noteHtml}</span>`
    )
  })

  const preClass = parsed.showLineNumbers ? 'moonbird-code-pre has-line-numbers' : 'moonbird-code-pre'
  const codeClass = lang ? ` class="language-${escapeHtml(lang)}"` : ''
  parts.push(`<pre class="${preClass}"><code${codeClass}>${lineParts.join('')}</code></pre>`)

  return `<div ${attrs.join(' ')}>${parts.join('')}</div>`
}

/** 把 `:package:` 这类 emoji 短代码换成真实 emoji。 */
export const replaceEmojiShortcodes = (label = '') =>
  String(label || '').replace(/:([a-z0-9_+-]+):/g, (raw, name) => EMOJI_SHORTCODES[name] || raw)

/** 代码组标签：支持 `:package:` 这类 emoji 短代码。 */
export const parseCodeGroupLabels = (rest = '', count = 0) => {
  const match = String(rest || '').match(/labels=\[([^\]]*)\]/)
  const labels = []

  if (match) {
    match[1].split(',').forEach((chunk) => {
      const label = chunk.trim().replace(/^["']|["']$/g, '').trim()
      if (label) {
        labels.push(replaceEmojiShortcodes(label))
      }
    })
  }

  while (labels.length < count) {
    labels.push(`Tab ${labels.length + 1}`)
  }

  return count > 0 ? labels.slice(0, count) : labels
}

/** 生成代码组 HTML。panels: [{ label, html }] */
export const buildCodeGroupHtml = (panels = []) => {
  if (!panels.length) {
    return ''
  }

  const tabs = panels
    .map((panel, index) => {
      const active = index === 0 ? ' is-active' : ''
      const selected = index === 0 ? 'true' : 'false'
      return `<span class="moonbird-code-tab${active}" role="tab" tabindex="0" aria-selected="${selected}">${escapeHtml(
        panel.label
      )}</span>`
    })
    .join('')

  const bodies = panels
    .map((panel, index) => `<div class="moonbird-code-panel${index === 0 ? ' is-active' : ''}">${panel.html}</div>`)
    .join('')

  return `<div class="moonbird-code-group"><div class="moonbird-code-tabs" role="tablist">${tabs}</div><div class="moonbird-code-panels">${bodies}</div></div>`
}

/** 只要语言本身（编辑器语言芯片用）。 */
export const getFenceLanguage = (info = '') => parseFenceInfo(info).lang || 'text'

const quoteIfNeeded = (value = '') => {
  const text = String(value ?? '')
  if (!text) {
    return ''
  }
  return `"${text.replace(/"/g, '\\"')}"`
}

const formatRanges = (ranges = []) =>
  ranges
    .filter((range) => range && Number.isFinite(range.start))
    .map((range) => {
      const end = range.end && range.end > range.start ? range.end : range.start
      return end > range.start ? `${range.start}-${end}` : `${range.start}`
    })
    .join(',')

/**
 * 把结构化参数还原成 fence info-string（编辑器参数面板用）。
 * 与 parseFenceInfo 互逆：parseFenceInfo(buildFenceInfo(x)) 得到同一组参数。
 * @param {object} options
 * @returns {string}
 */
export const buildFenceInfo = (options = {}) => {
  const tokens = []
  const lang = String(options.lang || '').trim()

  if (lang) {
    tokens.push(lang)
  }
  if (options.title && String(options.title).trim()) {
    tokens.push(`title=${quoteIfNeeded(String(options.title).trim())}`)
  }

  const highlight = formatRanges(options.highlight)
  if (highlight) {
    tokens.push(`{${highlight}}`)
  }

  const ins = formatRanges(options.ins)
  if (ins) {
    tokens.push(`ins={${ins}}`)
  }

  const del = formatRanges(options.del)
  if (del) {
    tokens.push(`del={${del}}`)
  }

  if (options.showLineNumbers) {
    tokens.push('showLineNumbers')
  }

  const startLine = Number.parseInt(options.startLineNumber, 10)
  if (Number.isFinite(startLine) && startLine > 1) {
    tokens.push(`startLineNumber=${startLine}`)
  }

  const collapse = formatRanges(options.collapse)
  if (collapse) {
    tokens.push(`collapse={${collapse}}`)
  }

  if (options.wrap === false) {
    tokens.push('wrap=false')
  }

  const frame = String(options.frame || '').trim()
  if (frame && ['code', 'terminal', 'none'].includes(frame)) {
    tokens.push(`frame=${frame}`)
  }

  return tokens.join(' ')
}

/** 只替换语言，保留 title / 行标记 / 行号等其余参数（编辑器改语言时用）。 */
export const replaceFenceLanguage = (info = '', language = '') => {
  const tokens = splitInfoTokens(info)
  const nextLanguage = String(language || '').trim()

  if (!tokens.length) {
    return nextLanguage
  }

  const [first, ...rest] = tokens
  const isLanguageToken = !first.includes('=') && !first.startsWith('{') && !KNOWN_FLAG.test(first)
  return isLanguageToken
    ? [nextLanguage, ...rest].filter(Boolean).join(' ')
    : [nextLanguage, ...tokens].filter(Boolean).join(' ')
}
