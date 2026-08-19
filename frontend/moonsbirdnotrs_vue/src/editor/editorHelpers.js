export const headingOptions = [
  { label: 'H1', value: 1 },
  { label: 'H2', value: 2 },
  { label: 'H3', value: 3 },
]

export const createToolbarToggleState = () => ({
  active: false,
  full: false,
})

export const createFixedToolbarState = () => ({
  strong: createToolbarToggleState(),
  italic: createToolbarToggleState(),
  strike: createToolbarToggleState(),
  code: createToolbarToggleState(),
  link: createToolbarToggleState(),
  blockQuote: createToolbarToggleState(),
  bulletList: createToolbarToggleState(),
  orderedList: createToolbarToggleState(),
  taskList: createToolbarToggleState(),
  codeBlock: createToolbarToggleState(),
  headings: headingOptions.reduce((map, option) => {
    map[option.value] = createToolbarToggleState()
    return map
  }, {}),
})

const createToggleFromContexts = (contexts, predicate) => ({
  active: contexts.some(predicate),
  full: contexts.length > 0 && contexts.every(predicate),
})

const getResolvedPositionAncestors = ($position) => {
  const ancestors = []

  for (let depth = 0; depth <= $position.depth; depth += 1) {
    ancestors.push($position.node(depth))
  }

  return ancestors
}

const collectSelectionContexts = (view) => {
  const { doc, selection } = view.state

  if (selection.empty) {
    return [
      {
        marks: view.state.storedMarks || selection.$from.marks(),
        ancestors: getResolvedPositionAncestors(selection.$from),
      },
    ]
  }

  const contexts = []
  doc.nodesBetween(selection.from, selection.to, (node, position) => {
    if (!node.isText) {
      return true
    }

    const resolvedPosition = doc.resolve(Math.min(position + 1, doc.content.size))
    contexts.push({
      marks: node.marks,
      ancestors: getResolvedPositionAncestors(resolvedPosition),
    })
    return false
  })

  if (!contexts.length) {
    contexts.push({
      marks: selection.$from.marks(),
      ancestors: getResolvedPositionAncestors(selection.$from),
    })
  }

  return contexts
}

const contextHasMark = (context, markName) =>
  context.marks.some((mark) => mark.type.name === markName)

const contextHasAncestor = (context, nodeName, predicate = () => true) =>
  context.ancestors.some((node) => node.type.name === nodeName && predicate(node))

const contextIsTaskList = (context) =>
  contextHasAncestor(context, 'listItem', (node) => Boolean(node.attrs?.task))

export const getFixedToolbarSnapshot = (view) => {
  const emptySnapshot = {
    range: null,
    selectedText: '',
    state: createFixedToolbarState(),
  }

  if (!view?.state?.selection) {
    return emptySnapshot
  }

  const { doc, selection } = view.state
  const contexts = collectSelectionContexts(view)
  const state = createFixedToolbarState()

  const markDefinitions = [
    ['strong', 'strong'],
    ['italic', 'emph'],
    ['strike', 'strike'],
    ['code', 'code'],
    ['link', 'link'],
  ]

  markDefinitions.forEach(([stateKey, markName]) => {
    state[stateKey] = createToggleFromContexts(contexts, (context) => contextHasMark(context, markName))
  })

  state.blockQuote = createToggleFromContexts(contexts, (context) =>
    contextHasAncestor(context, 'blockQuote')
  )
  state.orderedList = createToggleFromContexts(contexts, (context) =>
    contextHasAncestor(context, 'orderedList')
  )
  state.taskList = createToggleFromContexts(contexts, contextIsTaskList)
  state.bulletList = createToggleFromContexts(
    contexts,
    (context) => contextHasAncestor(context, 'bulletList') && !contextIsTaskList(context)
  )
  state.codeBlock = createToggleFromContexts(contexts, (context) =>
    contextHasAncestor(context, 'codeBlock')
  )

  headingOptions.forEach(({ value }) => {
    state.headings[value] = createToggleFromContexts(contexts, (context) =>
      contextHasAncestor(context, 'heading', (node) => node.attrs?.level === value)
    )
  })

  return {
    range: [selection.from, selection.to],
    selectedText: selection.empty ? '' : doc.textBetween(selection.from, selection.to, '\n'),
    state,
  }
}

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
