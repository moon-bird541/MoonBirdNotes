export const headingOptions = [
  { label: 'H1', value: 1 },
  { label: 'H2', value: 2 },
  { label: 'H3', value: 3 },
]

export const createToolbarToggleState = () => ({
  active: false,
  full: false,
})

export const toPlainTextForCount = (markdownContent = '') =>
  markdownContent
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/`([^`]*)`/g, '$1')
    .replace(/!\[[^\]]*\]\([^)]+\)/g, ' ')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/^\s{0,3}#{1,6}\s*/gm, '')
    .replace(/^\s*[-*+]\s+/gm, '')
    .replace(/^\s*\d+\.\s+/gm, '')
    .replace(/[*_~>#-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()

export const escapeHtml = (value = '') =>
  value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')

export const buildTitlePreviewHtml = (titleValue) => {
  const title = titleValue.trim() || '未命名笔记'
  return `<h1>${escapeHtml(title)}</h1>`
}

export const buildTagPreviewHtml = (tagNames = []) => {
  if (!tagNames.length) {
    return '<p>当前没有标签</p>'
  }

  const tags = tagNames
    .map((tagName) => `<span class="floating-preview-inline-tag">${escapeHtml(tagName)}</span>`)
    .join('')

  return `<div class="floating-preview-inline-tags">${tags}</div>`
}

export const resolveFloatingPreviewTitle = (mode) => {
  if (mode === 'title') {
    return '标题预览'
  }

  if (mode === 'tags') {
    return '标签预览'
  }

  return '预览'
}

export const formatEditorDateTime = (value) => {
  if (!value) {
    return '-'
  }

  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}
