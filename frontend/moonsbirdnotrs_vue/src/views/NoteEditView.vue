<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Back,
  Check,
  Clock,
  Close,
  Document,
  MagicStick,
  Minus,
  Plus,
  RefreshRight,
  Tickets,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import Editor from '@toast-ui/editor'
import { wrapIn } from 'prosemirror-commands'
import { TextSelection } from 'prosemirror-state'
import { liftTarget } from 'prosemirror-transform'

import '@toast-ui/editor/dist/toastui-editor.css'

import WorkspaceShell from '../components/WorkspaceShell.vue'
import api from '../services/api'
import '../styles/markdown.css'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const saving = ref(false)
const restoringVersionId = ref(null)
const editorReady = ref(false)
const tagOptions = ref([])
const versions = ref([])
const versionsLoading = ref(false)
const versionDrawerVisible = ref(false)
const tagInputVisible = ref(false)
const tagInputValue = ref('')
const tagInput = ref(null)
const editorRoot = ref(null)
const floatingToolbar = ref(null)
const selectionRange = ref(null)
const toolbarVisible = ref(false)
const floatingPreviewVisible = ref(false)
const hoverBlockHintVisible = ref(false)
const toolbarPosition = reactive({
  top: -9999,
  left: -9999,
})
const hoverBlockHint = reactive({
  label: '',
  top: -9999,
  left: -9999,
})

const form = reactive({
  title: '',
  tag_names: [],
})

const autoSaveConfig = {
  interval: 5000,  // 5秒自动保存
}

let autoSaveTimer = null
let lastSavedContent = ''

const versionPreview = reactive({
  visible: false,
  version: null,
})

const toPlainTextForCount = (markdownContent = '') =>
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

const headingOptions = [
  { label: 'H1', value: 1 },
  { label: 'H2', value: 2 },
  { label: 'H3', value: 3 },
]

const createToolbarToggleState = () => ({
  active: false,
  full: false,
})

const toolbarState = reactive({
  strong: createToolbarToggleState(),
  italic: createToolbarToggleState(),
  strike: createToolbarToggleState(),
  code: createToolbarToggleState(),
  blockQuote: createToolbarToggleState(),
  codeBlock: createToolbarToggleState(),
  horizontalRule: createToolbarToggleState(),
  headings: headingOptions.reduce((map, option) => {
    map[option.value] = createToolbarToggleState()
    return map
  }, {}),
})

const previewHtml = ref('')
const floatingPreviewBodyHtml = ref('')
const currentMarkdown = ref('')
const floatingPreviewMode = ref('body')

let editorInstance = null
let activeCodeLanguageInput = null
let activeCodeLanguageChip = null
let floatingPreviewTimer = null
let cleanupEditorSelectionListeners = null
let toolbarSyncFrame = null
let cleanupEditorHoverListeners = null

const wordCount = computed(() => toPlainTextForCount(currentMarkdown.value).replace(/\s+/g, '').length)
const versionCountText = computed(() => `${versions.value.length} / 5`)

const hideToolbar = () => {
  toolbarVisible.value = false
  selectionRange.value = null
  resetToolbarState()
}

const hideHoverBlockHint = () => {
  hoverBlockHintVisible.value = false
  hoverBlockHint.label = ''
  hoverBlockHint.top = -9999
  hoverBlockHint.left = -9999
}

const cancelToolbarSync = () => {
  if (toolbarSyncFrame !== null) {
    window.cancelAnimationFrame(toolbarSyncFrame)
    toolbarSyncFrame = null
  }
}

const scheduleToolbarSync = () => {
  if (toolbarSyncFrame !== null) {
    return
  }

  toolbarSyncFrame = window.requestAnimationFrame(() => {
    toolbarSyncFrame = null
    syncToolbarPosition()
  })
}

const isRectInViewport = (rect) =>
  rect.bottom > 0 &&
  rect.top < window.innerHeight &&
  rect.right > 0 &&
  rect.left < window.innerWidth

const resolveHoverBlockLabel = (element) => {
  if (!element) {
    return ''
  }

  if (element.closest('.toastui-editor-ww-code-block')) {
    return '代码块'
  }

  const tagName = element.tagName?.toLowerCase()
  if (!tagName) {
    return ''
  }

  if (tagName === 'blockquote') {
    return '引用'
  }

  if (tagName === 'li') {
    return '列表项'
  }

  if (tagName === 'h1') {
    return '一级标题'
  }

  if (tagName === 'h2') {
    return '二级标题'
  }

  if (tagName === 'h3') {
    return '三级标题'
  }

  if (tagName === 'h4') {
    return '四级标题'
  }

  if (tagName === 'h5') {
    return '五级标题'
  }

  if (tagName === 'h6') {
    return '六级标题'
  }

  if (tagName === 'pre') {
    return '代码块'
  }

  if (tagName === 'table') {
    return '表格'
  }

  if (tagName === 'hr') {
    return '分隔线'
  }

  if (tagName === 'p') {
    return '正文'
  }

  return ''
}

const getHoverBlockElement = (target, editorContents) => {
  if (!(target instanceof Node) || !editorContents?.contains(target)) {
    return null
  }

  const baseElement = target.nodeType === Node.ELEMENT_NODE ? target : target.parentElement
  return baseElement?.closest?.(
    '.toastui-editor-ww-code-block, h1, h2, h3, h4, h5, h6, p, li, blockquote, pre, table, hr'
  )
}

const getNodeFromPoint = (x, y) => {
  try {
    if (typeof document.caretRangeFromPoint === 'function') {
      const range = document.caretRangeFromPoint(x, y)
      if (range?.startContainer) {
        return range.startContainer
      }
    }

    if (typeof document.caretPositionFromPoint === 'function') {
      const position = document.caretPositionFromPoint(x, y)
      if (position?.offsetNode) {
        return position.offsetNode
      }
    }
  } catch {
    // Fallback below.
  }

  return document.elementFromPoint(x, y)
}

const updateHoverBlockHint = (event) => {
  if (toolbarVisible.value) {
    hideHoverBlockHint()
    return
  }

  const pointerNode = getNodeFromPoint(event.clientX, event.clientY)
  if (!(pointerNode instanceof Node)) {
    hideHoverBlockHint()
    return
  }

  const pointerElement =
    pointerNode.nodeType === Node.ELEMENT_NODE ? pointerNode : pointerNode.parentElement
  if (!pointerElement) {
    hideHoverBlockHint()
    return
  }

  const editorContents = pointerElement.closest?.('.toastui-editor-contents')
  if (!editorContents || !editorRoot.value?.contains(editorContents)) {
    hideHoverBlockHint()
    return
  }

  const blockElement = getHoverBlockElement(pointerNode, editorContents)
  const label = resolveHoverBlockLabel(blockElement)
  if (!blockElement || !label) {
    hideHoverBlockHint()
    return
  }

  const rect = blockElement.getBoundingClientRect()
  if (!isRectInViewport(rect)) {
    hideHoverBlockHint()
    return
  }

  const hintWidth = 112
  hoverBlockHint.label = label
  hoverBlockHint.top = Math.max(event.clientY - 34, 8)
  hoverBlockHint.left = Math.min(
    Math.max(event.clientX + 12, 12),
    Math.max(12, window.innerWidth - hintWidth - 12)
  )
  hoverBlockHintVisible.value = true
}

const hideFloatingPreview = () => {
  floatingPreviewVisible.value = false

  if (floatingPreviewTimer) {
    clearTimeout(floatingPreviewTimer)
    floatingPreviewTimer = null
  }
}

const showFloatingPreview = () => {
  if (!editorReady.value) {
    return
  }

  floatingPreviewVisible.value = true

  if (floatingPreviewTimer) {
    clearTimeout(floatingPreviewTimer)
  }

  floatingPreviewTimer = window.setTimeout(() => {
    floatingPreviewVisible.value = false
    floatingPreviewTimer = null
  }, 1800)
}

const getEditorSelection = () => {
  const view = getWysiwygView()
  const stateSelection = view?.state?.selection
  if (!view || !stateSelection || stateSelection.empty) {
    return null
  }

  return [stateSelection.from, stateSelection.to]
}

const isSameSelectionRange = (rangeA, rangeB) =>
  Boolean(rangeA && rangeB && rangeA[0] === rangeB[0] && rangeA[1] === rangeB[1])

const resetToolbarState = () => {
  toolbarState.strong.active = false
  toolbarState.strong.full = false
  toolbarState.italic.active = false
  toolbarState.italic.full = false
  toolbarState.strike.active = false
  toolbarState.strike.full = false
  toolbarState.code.active = false
  toolbarState.code.full = false
  toolbarState.blockQuote.active = false
  toolbarState.blockQuote.full = false
  toolbarState.codeBlock.active = false
  toolbarState.codeBlock.full = false
  toolbarState.horizontalRule.active = false
  toolbarState.horizontalRule.full = false

  headingOptions.forEach((option) => {
    toolbarState.headings[option.value].active = false
    toolbarState.headings[option.value].full = false
  })
}

const getTrailingHorizontalRuleInfo = (selection) => {
  if (!selection || selection.$to.depth < 1) {
    return null
  }

  const rootBlockDepth = 1
  const rootBlock = selection.$to.node(rootBlockDepth)
  const insertPos = selection.$to.after(rootBlockDepth)
  const $insertPos = selection.$to.doc.resolve(insertPos)
  const nextNodeInfo = $insertPos.nodeAfter
    ? {
        node: $insertPos.nodeAfter,
        pos: insertPos,
      }
    : null
  const nextNode = nextNodeInfo?.node || null

  return {
    rootBlock,
    insertPos,
    nextNode,
    nextNodePos: nextNodeInfo?.pos ?? null,
  }
}

const getSelectionTextSegments = (view) => {
  const selection = view?.state?.selection
  if (!view || !selection || selection.empty) {
    return []
  }

  const { from, to } = selection
  const segments = []

  view.state.doc.nodesBetween(from, to, (node, pos) => {
    if (!node.isText) {
      return
    }

    const start = Math.max(pos, from)
    const end = Math.min(pos + node.nodeSize, to)
    if (start >= end) {
      return
    }

    const $pos = view.state.doc.resolve(start)
    const ancestors = []

    for (let depth = 0; depth <= $pos.depth; depth += 1) {
      ancestors.push($pos.node(depth))
    }

    segments.push({
      node,
      start,
      end,
      parentType: $pos.parent.type.name,
      parentAttrs: $pos.parent.attrs || {},
      ancestors,
    })
  })

  return segments
}

const setToolbarToggleState = (target, active, full) => {
  target.active = active
  target.full = full
}

const updateToolbarState = () => {
  resetToolbarState()

  const view = getWysiwygView()
  const selection = view?.state?.selection
  if (!view || !selection || selection.empty) {
    return
  }

  const segments = getSelectionTextSegments(view)
  if (!segments.length) {
    return
  }

  const markDefinitions = [
    ['strong', 'strong'],
    ['italic', 'emph'],
    ['strike', 'strike'],
    ['code', 'code'],
  ]

  markDefinitions.forEach(([stateKey, markName]) => {
    const markType = view.state.schema.marks[markName]
    if (!markType) {
      return
    }

    const hasAny = segments.some((segment) => markType.isInSet(segment.node.marks))
    const hasFull = segments.every((segment) => markType.isInSet(segment.node.marks))
    setToolbarToggleState(toolbarState[stateKey], hasAny, hasFull)
  })

  const isInsideBlockType = (segment, typeName) =>
    segment.parentType === typeName || segment.ancestors.some((node) => node.type?.name === typeName)

  setToolbarToggleState(
    toolbarState.blockQuote,
    segments.some((segment) => isInsideBlockType(segment, 'blockQuote')),
    segments.every((segment) => isInsideBlockType(segment, 'blockQuote'))
  )

  setToolbarToggleState(
    toolbarState.codeBlock,
    segments.some((segment) => isInsideBlockType(segment, 'codeBlock')),
    segments.every((segment) => isInsideBlockType(segment, 'codeBlock'))
  )

  const trailingHorizontalRule = getTrailingHorizontalRuleInfo(selection)
  const hasTrailingHorizontalRule = trailingHorizontalRule?.nextNode?.type?.name === 'thematicBreak'
  setToolbarToggleState(toolbarState.horizontalRule, hasTrailingHorizontalRule, hasTrailingHorizontalRule)

  headingOptions.forEach((option) => {
    const isHeading = (segment) =>
      segment.parentType === 'heading' && Number(segment.parentAttrs.level) === option.value

    setToolbarToggleState(
      toolbarState.headings[option.value],
      segments.some(isHeading),
      segments.every(isHeading)
    )
  })
}

const escapeHtml = (value = '') =>
  value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')

const buildTitlePreviewHtml = () => {
  const title = form.title.trim() || '未命名笔记'
  return `<h1>${escapeHtml(title)}</h1>`
}

const buildTagPreviewHtml = () => {
  if (!form.tag_names.length) {
    return '<p>当前没有标签</p>'
  }

  const tags = form.tag_names
    .map((tagName) => `<span class="floating-preview-inline-tag">${escapeHtml(tagName)}</span>`)
    .join('')

  return `<div class="floating-preview-inline-tags">${tags}</div>`
}

const resolveFloatingPreviewTitle = () => {
  if (floatingPreviewMode.value === 'title') {
    return '标题预览'
  }

  if (floatingPreviewMode.value === 'tags') {
    return '标签预览'
  }

  return '预览'
}

const getEditorSelectionRect = () => {
  const view = getWysiwygView()
  const stateSelection = view?.state?.selection
  if (!view || !stateSelection || stateSelection.empty) {
    return null
  }

  try {
    const browserSelection = window.getSelection()
    const browserRange = browserSelection?.rangeCount ? browserSelection.getRangeAt(0) : null
    if (browserRange && editorRoot.value?.contains(browserRange.commonAncestorContainer)) {
      const browserRects = Array.from(browserRange.getClientRects()).filter((r) => r.width > 0 || r.height > 0)
      if (browserRects.length) {
        const topRect = browserRects.reduce((best, r) => (r.top < best.top ? r : best), browserRects[0])
        return topRect
      }
    }

    const from = Math.min(stateSelection.from, stateSelection.to)
    const to = Math.max(stateSelection.from, stateSelection.to)
    const startRect = view.coordsAtPos(from)
    const nextRect = view.coordsAtPos(Math.min(from + 1, to))
    const sameLine = Math.abs(startRect.top - nextRect.top) < 2

    return {
      top: startRect.top,
      bottom: startRect.bottom,
      left: startRect.left,
      right: sameLine
        ? Math.max(startRect.right ?? startRect.left, nextRect.left, startRect.left + 1)
        : Math.max(startRect.right ?? startRect.left, startRect.left + 1),
      width: Math.max(
        (sameLine
          ? Math.max(startRect.right ?? startRect.left, nextRect.left, startRect.left + 1)
          : Math.max(startRect.right ?? startRect.left, startRect.left + 1)) - startRect.left,
        1
      ),
      height: Math.max(startRect.bottom - startRect.top, 1),
    }
  } catch {
    return null
  }
}

const getWysiwygView = () => editorInstance?.wwEditor?.view || null

const bindEditorSelectionListeners = () => {
  cleanupEditorSelectionListeners?.()

  const editorContents = editorRoot.value?.querySelector('.toastui-editor-contents')
  if (!editorContents) {
    cleanupEditorSelectionListeners = null
    return
  }

  const handleSelectionCommit = () => {
    nextTick(() => {
      scheduleToolbarSync()
    })
  }

  const handlePointerDown = () => {
    hideToolbar()
    hideHoverBlockHint()
  }

  editorContents.addEventListener('mouseup', handleSelectionCommit)
  editorContents.addEventListener('keyup', handleSelectionCommit)
  editorContents.addEventListener('touchend', handleSelectionCommit)
  editorContents.addEventListener('mousedown', handlePointerDown)

  cleanupEditorSelectionListeners = () => {
    editorContents.removeEventListener('mouseup', handleSelectionCommit)
    editorContents.removeEventListener('keyup', handleSelectionCommit)
    editorContents.removeEventListener('touchend', handleSelectionCommit)
    editorContents.removeEventListener('mousedown', handlePointerDown)
  }
}

const bindEditorHoverListeners = () => {
  cleanupEditorHoverListeners?.()

  if (!editorRoot.value) {
    cleanupEditorHoverListeners = null
    return
  }

  const handleMouseMove = (event) => {
    updateHoverBlockHint(event)
  }

  document.addEventListener('mousemove', handleMouseMove, true)

  cleanupEditorHoverListeners = () => {
    document.removeEventListener('mousemove', handleMouseMove, true)
  }
}

const resolveCodeBlockPos = (view, rawPos) => {
  const doc = view.state.doc
  const candidates = [rawPos, rawPos - 1, rawPos + 1].filter(
    (pos) => Number.isInteger(pos) && pos >= 0 && pos <= doc.content.size
  )

  for (const pos of candidates) {
    const node = doc.nodeAt(pos)
    if (node?.type?.name === 'codeBlock') {
      return pos
    }
  }

  try {
    const safePos = Math.max(0, Math.min(rawPos, doc.content.size))
    const $pos = doc.resolve(safePos)

    for (let depth = $pos.depth; depth >= 0; depth -= 1) {
      if ($pos.node(depth)?.type?.name === 'codeBlock') {
        return depth === 0 ? 0 : $pos.before(depth)
      }
    }
  } catch {
    return null
  }

  return null
}

const getCodeBlockPos = (codeBlockElement) => {
  const view = getWysiwygView()
  if (!view || !codeBlockElement) {
    return null
  }

  const candidates = [
    codeBlockElement,
    codeBlockElement.querySelector('pre'),
    codeBlockElement.querySelector('code'),
  ].filter(Boolean)

  for (const candidate of candidates) {
    try {
      const rawPos = view.posAtDOM(candidate, 0)
      const pos = resolveCodeBlockPos(view, rawPos)
      if (pos !== null) {
        return pos
      }
    } catch {
      continue
    }
  }

  return null
}

const getCodeBlockLanguageLabel = (codeBlockElement) => {
  const language =
    codeBlockElement?.getAttribute('data-language') ||
    codeBlockElement?.querySelector('code')?.getAttribute('data-language') ||
    ''

  return language || 'text'
}

const syncCodeBlockLanguageChip = (codeBlockElement) => {
  const chip = codeBlockElement?.querySelector('.inline-code-language-chip')
  if (!chip) {
    return
  }

  const label = getCodeBlockLanguageLabel(codeBlockElement)
  chip.dataset.language = label
  chip.textContent = label
}

const updateCodeBlockLanguage = (codeBlockElement, value) => {
  const view = getWysiwygView()
  const pos = getCodeBlockPos(codeBlockElement)
  if (!view || pos === null) {
    return
  }

  const node = view.state.doc.nodeAt(pos)
  if (!node || node.type?.name !== 'codeBlock') {
    return
  }

  const nextLanguage = value.trim()
  if ((node.attrs.language || '') === nextLanguage) {
    syncCodeBlockLanguageChip(codeBlockElement)
    return
  }

  const tr = view.state.tr.setNodeMarkup(pos, null, {
    ...node.attrs,
    language: nextLanguage,
  })

  view.dispatch(tr)
  updatePreviewFromEditor()
}

const finishInlineCodeLanguageEdit = (save = true) => {
  if (!activeCodeLanguageInput) {
    return
  }

  const input = activeCodeLanguageInput
  const chip = activeCodeLanguageChip
  const codeBlockElement = input.closest('.toastui-editor-ww-code-block')
  const nextValue = input.value

  activeCodeLanguageInput = null
  activeCodeLanguageChip = null
  input.remove()

  if (chip) {
    chip.hidden = false
  }

  if (save && codeBlockElement) {
    updateCodeBlockLanguage(codeBlockElement, nextValue)
  } else if (codeBlockElement) {
    syncCodeBlockLanguageChip(codeBlockElement)
  }
}

const openInlineCodeLanguageEditor = (codeBlockElement) => {
  const chip = codeBlockElement?.querySelector('.inline-code-language-chip')
  if (!chip) {
    return
  }

  if (activeCodeLanguageInput?.closest('.toastui-editor-ww-code-block') === codeBlockElement) {
    activeCodeLanguageInput.focus()
    activeCodeLanguageInput.select()
    return
  }

  finishInlineCodeLanguageEdit(true)

  const input = document.createElement('input')
  input.type = 'text'
  input.className = 'inline-code-language-input'
  input.value =
    codeBlockElement.getAttribute('data-language') === 'text'
      ? ''
      : codeBlockElement.getAttribute('data-language') || ''
  input.placeholder = 'text'
  input.setAttribute('aria-label', '代码块语言')

  const finish = (save) => {
    finishInlineCodeLanguageEdit(save)
  }

  input.addEventListener('blur', () => finish(true), { once: true })
  input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault()
      finish(true)
    }

    if (event.key === 'Escape') {
      event.preventDefault()
      finish(false)
    }
  })

  chip.hidden = true
  codeBlockElement.appendChild(input)
  activeCodeLanguageInput = input
  activeCodeLanguageChip = chip

  window.requestAnimationFrame(() => {
    input.focus()
    input.select()
  })
}

const decorateCodeBlocks = () => {
  const codeBlocks = editorRoot.value?.querySelectorAll('.toastui-editor-ww-code-block')
  if (!codeBlocks?.length) {
    return
  }

  codeBlocks.forEach((codeBlockElement) => {
    let chip = codeBlockElement.querySelector('.inline-code-language-chip')

    if (!chip) {
      chip = document.createElement('button')
      chip.type = 'button'
      chip.className = 'inline-code-language-chip'
      chip.title = '修改代码块语言'
      chip.addEventListener('mousedown', (event) => {
        event.preventDefault()
      })
      chip.addEventListener('click', (event) => {
        event.preventDefault()
        event.stopPropagation()
        openInlineCodeLanguageEditor(codeBlockElement)
      })
      codeBlockElement.appendChild(chip)
    }

    syncCodeBlockLanguageChip(codeBlockElement)
  })
}

const updatePreviewFromEditor = () => {
  if (!editorInstance) {
    return
  }

  currentMarkdown.value = editorInstance.getMarkdown()
  previewHtml.value = editorInstance.getHTML()
  floatingPreviewMode.value = 'body'
  floatingPreviewBodyHtml.value = ''
  hideFloatingPreview()

  window.requestAnimationFrame(() => {
    decorateCodeBlocks()
  })
}

const syncToolbarPosition = () => {
  if (!editorInstance || !floatingToolbar.value) {
    return
  }

  const editorSelection = getEditorSelection()
  if (!editorSelection) {
    hideToolbar()
    return
  }

  hideHoverBlockHint()

  const rect = getEditorSelectionRect()
  if (!rect) {
    hideToolbar()
    return
  }

  if (!isRectInViewport(rect)) {
    hideToolbar()
    return
  }

  if (!toolbarVisible.value) {
    toolbarVisible.value = true

    nextTick(() => {
      scheduleToolbarSync()
    })
    return
  }

  const toolbarRect = floatingToolbar.value.getBoundingClientRect()
  if (toolbarRect.width === 0 || toolbarRect.height === 0) {
    return
  }

  const horizontalPadding = 12
  const desiredTop = rect.top - toolbarRect.height - 10
  const minTop = 8
  const desiredLeft = rect.left + rect.width / 2 - toolbarRect.width / 2
  const maxLeft = window.innerWidth - toolbarRect.width - horizontalPadding
  const keepCurrentLeft = toolbarVisible.value && isSameSelectionRange(selectionRange.value, editorSelection)
  const nextLeft = keepCurrentLeft ? toolbarPosition.left : desiredLeft

  selectionRange.value = editorSelection
  toolbarPosition.top = Math.max(desiredTop, minTop)
  toolbarPosition.left = Math.min(Math.max(nextLeft, horizontalPadding), Math.max(horizontalPadding, maxLeft))
  updateToolbarState()
}

const restoreSelection = () => {
  if (!editorInstance || !selectionRange.value) {
    return
  }

  try {
    const [start, end] = selectionRange.value
    editorInstance.focus()
    editorInstance.setSelection(start, end)
  } catch {
    hideToolbar()
  }
}

const applyInlineMark = (stateKey, markName) => {
  const view = getWysiwygView()
  const selection = view?.state?.selection
  const markType = view?.state?.schema?.marks?.[markName]

  if (!view || !selection || selection.empty || !markType) {
    return
  }

  const shouldRemove = toolbarState[stateKey].full
  const tr = shouldRemove
    ? view.state.tr.removeMark(selection.from, selection.to, markType)
    : view.state.tr.addMark(selection.from, selection.to, markType.create())

  view.dispatch(tr.scrollIntoView())
}

const runEditorCommand = (command, payload) => {
  if (!editorInstance) {
    return
  }

  restoreSelection()

  if (command === 'strong') {
    applyInlineMark('strong', 'strong')
  } else if (command === 'italic') {
    applyInlineMark('italic', 'emph')
  } else if (command === 'strike') {
    applyInlineMark('strike', 'strike')
  } else if (command === 'code') {
    applyInlineMark('code', 'code')
  } else {
    editorInstance.exec(command, payload)
  }

  updatePreviewFromEditor()
  updateToolbarState()

  nextTick(() => {
    scheduleToolbarSync()
  })
}

const applyHeading = (level) => {
  if (!editorInstance) {
    return
  }

  restoreSelection()
  const view = getWysiwygView()
  const selection = view?.state?.selection
  const paragraphType = view?.state?.schema?.nodes?.paragraph
  const headingType = view?.state?.schema?.nodes?.heading

  if (!view || !selection || selection.empty || !paragraphType || !headingType) {
    return
  }

  const shouldResetToParagraph = toolbarState.headings[level].full
  const tr = shouldResetToParagraph
    ? view.state.tr.setBlockType(selection.from, selection.to, paragraphType)
    : view.state.tr.setBlockType(selection.from, selection.to, headingType, { level })

  view.dispatch(tr.scrollIntoView())
  updatePreviewFromEditor()
  updateToolbarState()

  nextTick(() => {
    scheduleToolbarSync()
  })
}

const applyBlockQuote = () => {
  if (!editorInstance) {
    return
  }

  restoreSelection()

  const view = getWysiwygView()
  const selection = view?.state?.selection
  const blockQuoteType = view?.state?.schema?.nodes?.blockQuote

  if (!view || !selection || selection.empty || !blockQuoteType) {
    return
  }

  if (toolbarState.blockQuote.full) {
    const range = selection.$from.blockRange(selection.$to, (node) => node.type === blockQuoteType)
    const target = range ? liftTarget(range) : null

    if (range && target !== null) {
      view.dispatch(view.state.tr.lift(range, target).scrollIntoView())
    }
  } else {
    wrapIn(blockQuoteType)(view.state, view.dispatch, view)
  }

  updatePreviewFromEditor()
  updateToolbarState()

  nextTick(() => {
    scheduleToolbarSync()
  })
}

const applyCodeBlock = () => {
  if (!editorInstance) {
    return
  }

  restoreSelection()

  const view = getWysiwygView()
  const selection = view?.state?.selection
  const paragraphType = view?.state?.schema?.nodes?.paragraph
  const codeBlockType = view?.state?.schema?.nodes?.codeBlock

  if (!view || !selection || selection.empty || !paragraphType || !codeBlockType) {
    return
  }

  if (toolbarState.codeBlock.full) {
    const tr = view.state.tr.setBlockType(selection.from, selection.to, paragraphType)
    view.dispatch(tr.scrollIntoView())
  } else {
    const selectedText = view.state.doc.textBetween(selection.from, selection.to, '\n')
    const codeBlockNode = codeBlockType.create(null, view.state.schema.text(selectedText))
    const tr = view.state.tr.replaceSelectionWith(codeBlockNode, false)
    const textStart = Math.min(selection.from + 1, tr.doc.content.size)
    const textEnd = textStart + selectedText.length
    tr.setSelection(TextSelection.create(tr.doc, textStart, textEnd)).scrollIntoView()
    view.dispatch(tr)
  }

  updatePreviewFromEditor()
  updateToolbarState()

  nextTick(() => {
    scheduleToolbarSync()
  })
}

const normalizeCodeIndent = (code) => {
  const normalizedLines = code.replace(/\r\n?/g, '\n').replace(/\t/g, '  ').split('\n')
  const firstContentIndex = normalizedLines.findIndex((line) => line.trim())
  const lastContentIndex = normalizedLines.findLastIndex((line) => line.trim())

  if (firstContentIndex === -1 || lastContentIndex === -1) {
    return ''
  }

  const contentLines = normalizedLines.slice(firstContentIndex, lastContentIndex + 1)
  const minIndent = contentLines
    .filter((line) => line.trim())
    .reduce((min, line) => {
      const indent = line.match(/^\s*/)?.[0].length || 0
      return Math.min(min, indent)
    }, Number.POSITIVE_INFINITY)

  return contentLines.map((line) => line.slice(Number.isFinite(minIndent) ? minIndent : 0)).join('\n')
}

const formatJsonCode = (code) => {
  try {
    return JSON.stringify(JSON.parse(code), null, 2)
  } catch {
    return null
  }
}

const getIndentDelta = (line) => {
  let delta = 0
  let quote = ''
  let escaped = false

  for (const char of line) {
    if (escaped) {
      escaped = false
      continue
    }

    if (char === '\\') {
      escaped = true
      continue
    }

    if (quote) {
      if (char === quote) {
        quote = ''
      }
      continue
    }

    if (char === '"' || char === "'" || char === '`') {
      quote = char
      continue
    }

    if (char === '{' || char === '[' || char === '(') {
      delta += 1
    } else if (char === '}' || char === ']' || char === ')') {
      delta -= 1
    }
  }

  return delta
}

const formatBracketIndentedCode = (code) => {
  let indentLevel = 0
  const indentUnit = '  '

  return code
    .split('\n')
    .map((line) => {
      const trimmed = line.trim()

      if (!trimmed) {
        return ''
      }

      const startsWithClosingToken = /^[}\])]/.test(trimmed)
      const effectiveIndentLevel = startsWithClosingToken ? Math.max(indentLevel - 1, 0) : indentLevel

      const formattedLine = `${indentUnit.repeat(effectiveIndentLevel)}${trimmed}`
      const delta = getIndentDelta(trimmed)

      if (startsWithClosingToken) {
        indentLevel = effectiveIndentLevel
      }

      if (delta > 0) {
        indentLevel += delta
      } else if (delta < 0 && !startsWithClosingToken) {
        indentLevel = Math.max(indentLevel + delta, 0)
      }

      return formattedLine
    })
    .join('\n')
}

const formatCodeBlockContent = (code, language = '') => {
  const normalizedCode = normalizeCodeIndent(code)
  const normalizedLanguage = language.toLowerCase()
  const jsonCode = formatJsonCode(normalizedCode)

  if (jsonCode && (!normalizedLanguage || normalizedLanguage === 'json')) {
    return jsonCode
  }

  return formatBracketIndentedCode(normalizedCode)
}

const getSelectedCodeBlockInfo = (view) => {
  const selection = view?.state?.selection
  if (!view || !selection || selection.empty) {
    return null
  }

  for (let depth = selection.$from.depth; depth >= 0; depth -= 1) {
    const node = selection.$from.node(depth)
    if (node?.type?.name === 'codeBlock') {
      const pos = depth === 0 ? 0 : selection.$from.before(depth)
      return { node, pos }
    }
  }

  return null
}

const applyCodeBlockAutoFormat = () => {
  if (!editorInstance || !toolbarState.codeBlock.full) {
    return
  }

  restoreSelection()

  const view = getWysiwygView()
  const codeBlockInfo = getSelectedCodeBlockInfo(view)
  if (!view || !codeBlockInfo) {
    return
  }

  const { node, pos } = codeBlockInfo
  const formattedCode = formatCodeBlockContent(node.textContent || '', node.attrs?.language || '')

  if (formattedCode === node.textContent) {
    updateToolbarState()
    return
  }

  const contentStart = pos + 1
  const contentEnd = contentStart + node.content.size
  const tr = view.state.tr.insertText(formattedCode, contentStart, contentEnd)
  const selectionEnd = contentStart + formattedCode.length

  tr.setSelection(TextSelection.create(tr.doc, contentStart, selectionEnd)).scrollIntoView()
  view.dispatch(tr)
  updatePreviewFromEditor()
  updateToolbarState()

  nextTick(() => {
    scheduleToolbarSync()
  })
}

const applyHorizontalRule = () => {
  if (!editorInstance) {
    return
  }

  restoreSelection()

  const view = getWysiwygView()
  const selection = view?.state?.selection
  const thematicBreakType = view?.state?.schema?.nodes?.thematicBreak
  const paragraphType = view?.state?.schema?.nodes?.paragraph

  if (!view || !selection || !thematicBreakType || !paragraphType || selection.$to.depth < 1) {
    return
  }

  const trailingHorizontalRule = getTrailingHorizontalRuleInfo(selection)
  if (!trailingHorizontalRule) {
    return
  }

  const { insertPos, nextNode, nextNodePos, rootBlock } = trailingHorizontalRule

  if (toolbarState.horizontalRule.full && nextNode?.type === thematicBreakType && nextNodePos !== null) {
    const tr = view.state.tr.delete(nextNodePos, nextNodePos + nextNode.nodeSize)
    view.dispatch(tr.scrollIntoView())
    updatePreviewFromEditor()
    updateToolbarState()

    nextTick(() => {
      scheduleToolbarSync()
    })
    return
  }

  if (nextNode?.type === thematicBreakType) {
    updateToolbarState()
    nextTick(() => {
      scheduleToolbarSync()
    })
    return
  }

  const isLastBlock = view.state.doc.child(view.state.doc.childCount - 1) === rootBlock
  const shouldAppendParagraph = isLastBlock
  const tr = view.state.tr.insert(insertPos, thematicBreakType.create())

  if (shouldAppendParagraph) {
    tr.insert(insertPos + 1, paragraphType.create())
  }

  view.dispatch(tr.scrollIntoView())
  updatePreviewFromEditor()
  updateToolbarState()

  nextTick(() => {
    scheduleToolbarSync()
  })
}

const buildEditor = () => {
  if (!editorRoot.value) {
    return
  }

  editorInstance = new Editor({
    el: editorRoot.value,
    height: 'auto',
    minHeight: '560px',
    initialEditType: 'wysiwyg',
    initialValue: currentMarkdown.value,
    previewStyle: 'tab',
    hideModeSwitch: true,
    usageStatistics: false,
    toolbarItems: [],
    autofocus: false,
    placeholder: '在这里直接编辑笔记正文',
    events: {
      change: () => {
        updatePreviewFromEditor()
      },
      caretChange: () => {
        nextTick(() => {
          scheduleToolbarSync()
        })
      },
      focus: () => {
        nextTick(() => {
          scheduleToolbarSync()
        })
      },
      blur: () => {
        window.setTimeout(() => {
          const active = document.activeElement
          if (floatingToolbar.value?.contains(active)) {
            return
          }
          hideToolbar()
        }, 120)
      },
    },
  })

  editorReady.value = true
  updatePreviewFromEditor()
  nextTick(() => {
    bindEditorSelectionListeners()
    bindEditorHoverListeners()
  })
}

const setFormFromNote = (note) => {
  form.title = note.title || ''
  form.tag_names = note.tags?.map((tag) => tag.name) || []
  currentMarkdown.value = note.markdown_content || ''
  previewHtml.value = note.rendered_html || ''

  // 初始化 lastSavedContent，避免第一次自动保存触发
  lastSavedContent = note.markdown_content || ''

  if (editorInstance) {
    editorInstance.setMarkdown(currentMarkdown.value)
    updatePreviewFromEditor()
  }
}

const fetchNote = async () => {
  const { data } = await api.get(`/notes/${route.params.id}/`)
  setFormFromNote(data)
}

const fetchTagOptions = async () => {
  const { data } = await api.get('/notes/tags/')
  tagOptions.value = data.map((tag) => tag.name)
}

const fetchVersions = async () => {
  versionsLoading.value = true

  try {
    const { data } = await api.get(`/notes/${route.params.id}/versions/`)
    versions.value = data
  } finally {
    versionsLoading.value = false
  }
}

const fetchPageData = async () => {
  loading.value = true

  try {
    await fetchNote()
  } catch (error) {
    const detail = error.response?.data?.detail || '加载笔记失败，请稍后重试。'
    ElMessage.error(detail)
  } finally {
    loading.value = false
  }

  const [tagResult, versionResult] = await Promise.allSettled([
    fetchTagOptions(),
    fetchVersions(),
  ])

  if (tagResult.status === 'rejected') {
    ElMessage.warning('标签列表加载失败，当前仍可继续编辑正文。')
  }

  if (versionResult.status === 'rejected') {
    versionsLoading.value = false
    ElMessage.warning('历史版本暂时加载失败，不影响当前笔记编辑。')
  }
}

const handleTagChange = (value) => {
  const normalized = [...new Set(value.map((item) => item.trim()).filter(Boolean))]

  if (normalized.length > 4) {
    ElMessage.warning('每篇笔记最多只能选择四个标签。')
    form.tag_names = normalized.slice(0, 4)
    return
  }

  form.tag_names = normalized
}

// 移除标签
const handleTagRemove = (tag) => {
  form.tag_names = form.tag_names.filter(t => t !== tag)
}

// 显示标签输入框
const showTagInput = () => {
  if (form.tag_names.length >= 4) {
    ElMessage.warning('每篇笔记最多只能选择四个标签。')
    return
  }
  tagInputVisible.value = true
  nextTick(() => {
    tagInput.value?.focus()
  })
}

// 取消标签输入
const cancelTagInput = () => {
  tagInputVisible.value = false
  tagInputValue.value = ''
}

// 确认添加标签
const handleTagInputConfirm = () => {
  const value = tagInputValue.value.trim()
  if (value) {
    if (form.tag_names.includes(value)) {
      ElMessage.warning('该标签已存在。')
    } else if (form.tag_names.length >= 4) {
      ElMessage.warning('每篇笔记最多只能选择四个标签。')
    } else {
      form.tag_names.push(value)
      // 如果是新标签，添加到选项列表
      if (!tagOptions.value.includes(value)) {
        tagOptions.value.push(value)
      }
    }
  }
  tagInputVisible.value = false
  tagInputValue.value = ''
}

const saveNote = async () => {
  if (!form.title.trim()) {
    ElMessage.warning('请填写笔记标题。')
    return
  }

  if (!form.tag_names.length) {
    ElMessage.warning('请至少填写一个标签。')
    return
  }

  if (!editorInstance) {
    ElMessage.warning('编辑器尚未准备好，请稍后重试。')
    return
  }

  // 保存当前滚动位置
  const editorContainer = document.querySelector('.cherry-editor')
  const scrollTop = editorContainer?.scrollTop || 0

  // 提示用户输入版本备注
  try {
    const { value: versionNote } = await ElMessageBox.prompt(
      '请输入版本备注：',
      '创建版本',
      {
        confirmButtonText: '创建',
        cancelButtonText: '取消',
        inputPattern: /.+/,
        inputErrorMessage: '请输入版本备注',
      }
    )

    saving.value = true

    const markdownContent = editorInstance.getMarkdown()
    const { data } = await api.put(`/notes/${route.params.id}/edit/`, {
      title: form.title,
      markdown_content: markdownContent,
      tag_names: form.tag_names,
      create_version: true,
      version_note: versionNote,
    })

    // 更新表单数据，但不重置编辑器内容（避免滚动位置丢失）
    form.title = data.title || ''
    form.tag_names = data.tags?.map((tag) => tag.name) || []
    currentMarkdown.value = data.markdown_content || ''
    previewHtml.value = data.rendered_html || ''

    tagOptions.value = [...new Set([...tagOptions.value, ...form.tag_names])].sort()

    lastSavedContent = markdownContent

    // 恢复滚动位置
    await nextTick()
    if (editorContainer) {
      editorContainer.scrollTop = scrollTop
    }

    ElMessage.success('已创建新版本，旧内容已进入版本记录。')

    try {
      await fetchVersions()
    } catch {
      ElMessage.warning('版本已创建，但历史版本列表刷新失败。')
    }
  } catch (error) {
    if (error === 'cancel') {
      // 用户取消
      return
    }
    const detail =
      error.response?.data?.title?.[0] ||
      error.response?.data?.tag_names?.[0] ||
      error.response?.data?.detail ||
      '创建版本失败，请稍后重试。'
    ElMessage.error(detail)
  } finally {
    saving.value = false
  }
}

const goToDetail = () => {
  router.push({ name: 'note-detail', params: { id: route.params.id } })
}

const formatDateTime = (value) => {
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

// 自动保存（每5秒）
const autoSave = async () => {
  if (!editorInstance) return

  const currentContent = editorInstance.getMarkdown()

  // 内容无变化，跳过
  if (currentContent === lastSavedContent) {
    return
  }

  try {
    // 自动保存不生成版本
    await api.put(`/notes/${route.params.id}/edit/`, {
      title: form.title,
      tag_names: form.tag_names,
      markdown_content: currentContent,
      create_version: false,
    })

    lastSavedContent = currentContent
  } catch (error) {
    console.error('自动保存失败', error)
  }
}

// 启动自动保存
const startAutoSave = () => {
  autoSaveTimer = setInterval(() => {
    autoSave()
  }, autoSaveConfig.interval)
}

// 停止自动保存
const stopAutoSave = () => {
  if (autoSaveTimer) {
    clearInterval(autoSaveTimer)
    autoSaveTimer = null
  }
}

// 手动保存（Ctrl+S）
const handleManualSave = async () => {
  if (!editorInstance) return

  const currentContent = editorInstance.getMarkdown()

  // 内容无变化，跳过
  if (currentContent === lastSavedContent) {
    ElMessage.info('内容未修改，无需保存')
    return
  }

  try {
    // 手动保存不生成版本
    await api.put(`/notes/${route.params.id}/edit/`, {
      title: form.title,
      tag_names: form.tag_names,
      markdown_content: currentContent,
      create_version: false,
    })

    lastSavedContent = currentContent
    ElMessage.success('保存成功')
  } catch (error) {
    const detail =
      error.response?.data?.title?.[0] ||
      error.response?.data?.tag_names?.[0] ||
      error.response?.data?.detail ||
      '保存失败，请稍后重试。'
    ElMessage.error(detail)
  }
}

// 处理键盘快捷键
const handleKeyboardShortcut = (event) => {
  // Ctrl+S 或 Cmd+S 保存
  if ((event.ctrlKey || event.metaKey) && event.key === 's') {
    event.preventDefault()
    handleManualSave()
  }
}

// 查看版本预览
const previewVersion = (version) => {
  versionPreview.visible = true
  versionPreview.version = version
}

// 关闭版本预览
const closeVersionPreview = () => {
  versionPreview.visible = false
  versionPreview.version = null
}

// 切换版本抽屉
const toggleVersionDrawer = () => {
  versionDrawerVisible.value = !versionDrawerVisible.value
}

// 关闭版本抽屉
const closeVersionDrawer = () => {
  versionDrawerVisible.value = false
}

// 恢复版本
const restoreVersion = async (version) => {
  closeVersionPreview()

  // 询问是否保存当前内容
  try {
    await ElMessageBox.confirm(
      '恢复此版本将覆盖当前编辑内容。是否先保存当前内容为新版本？',
      '恢复版本',
      {
        confirmButtonText: '保存并恢复',
        cancelButtonText: '直接恢复',
        distinguishCancelAndClose: true,
        type: 'warning',
      }
    )

    // 用户选择保存当前内容
    const { value: versionNote } = await ElMessageBox.prompt(
      '请输入当前版本的备注：',
      '版本备注',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /.+/,
        inputErrorMessage: '请输入版本备注',
      }
    )

    await restoreVersionWithSave(version, versionNote)
  } catch (action) {
    if (action === 'cancel') {
      // 用户选择不保存，直接恢复
      await restoreVersionDirectly(version)
    }
    // action === 'close' 用户取消操作，什么都不做
  }
}

// 保存当前内容后恢复版本
const restoreVersionWithSave = async (version, versionNote) => {
  try {
    const { data } = await api.post(
      `/notes/${route.params.id}/versions/${version.id}/restore/`,
      {
        save_current: true,
        version_note: versionNote,
      }
    )

    setFormFromNote(data)
    if (editorInstance) {
      editorInstance.setMarkdown(data.markdown_content)
      updatePreviewFromEditor()
    }
    lastSavedContent = data.markdown_content

    ElMessage.success('已保存当前内容并恢复到选定版本')
    await fetchVersions()
  } catch (error) {
    ElMessage.error('恢复版本失败')
  }
}

// 直接恢复版本（不保存当前内容）
const restoreVersionDirectly = async (version) => {
  try {
    const { data } = await api.post(
      `/notes/${route.params.id}/versions/${version.id}/restore/`,
      {
        save_current: false,
      }
    )

    setFormFromNote(data)
    if (editorInstance) {
      editorInstance.setMarkdown(data.markdown_content)
      updatePreviewFromEditor()
    }
    lastSavedContent = data.markdown_content

    ElMessage.success('已恢复到选定版本')
    await fetchVersions()
  } catch (error) {
    ElMessage.error('恢复版本失败')
  }
}

const handleDocumentSelection = () => {
  nextTick(() => {
    scheduleToolbarSync()
  })
}

watch(
  () => form.title,
  () => {
    floatingPreviewMode.value = 'title'
    floatingPreviewBodyHtml.value = buildTitlePreviewHtml()
    showFloatingPreview()
  }
)

watch(
  () => form.tag_names.join('|'),
  () => {
    floatingPreviewMode.value = 'tags'
    floatingPreviewBodyHtml.value = buildTagPreviewHtml()
    showFloatingPreview()
  }
)

// 编辑器内容变化时的防抖保存已移除，改为定时自动保存

onMounted(async () => {
  await fetchPageData()
  await nextTick()
  buildEditor()

  // 启动自动保存
  startAutoSave()

  // 添加键盘快捷键监听
  document.addEventListener('keydown', handleKeyboardShortcut)

  document.addEventListener('selectionchange', handleDocumentSelection)
  window.addEventListener('resize', hideToolbar)
  window.addEventListener('scroll', scheduleToolbarSync, true)
  document.addEventListener('scroll', scheduleToolbarSync, true)
})

onBeforeUnmount(() => {
  // 清理定时器
  stopAutoSave()

  // 移除键盘快捷键监听
  document.removeEventListener('keydown', handleKeyboardShortcut)

  document.removeEventListener('selectionchange', handleDocumentSelection)
  window.removeEventListener('resize', hideToolbar)
  window.removeEventListener('scroll', scheduleToolbarSync, true)
  document.removeEventListener('scroll', scheduleToolbarSync, true)
  cancelToolbarSync()
  cleanupEditorSelectionListeners?.()
  cleanupEditorSelectionListeners = null
  cleanupEditorHoverListeners?.()
  cleanupEditorHoverListeners = null
  hideHoverBlockHint()
  hideFloatingPreview()
  finishInlineCodeLanguageEdit(false)
  editorInstance?.destroy()
  editorInstance = null
})
</script>

<template>
  <main class="edit-page page-shell">
    <WorkspaceShell>
      <section class="edit-stage" v-loading="loading">
        <header class="edit-header fade-rise-enter">
          <button class="back-button" type="button" @click="goToDetail">
            <el-icon><Back /></el-icon>
            <span>返回详情</span>
          </button>

          <div class="auto-save-badge">
            <el-icon><Clock /></el-icon>
            <span>自动保存已启用</span>
          </div>

          <el-button class="save-button" type="primary" :loading="saving" @click="saveNote">
            <el-icon><Check /></el-icon>
            <span>创建版本</span>
          </el-button>
        </header>

        <section class="editor-layout fade-rise-enter-delay">
          <article class="editor-main">
            <section class="editor-panel">
              <div class="editor-meta">
                <input
                  v-model="form.title"
                  class="title-input"
                  type="text"
                  placeholder="无标题"
                  maxlength="255"
                />
                <div class="title-count">{{ form.title.length }}/255</div>
              </div>

              <div class="editor-meta tags-section">
                <div class="tags-list">
                  <div
                    v-for="tag in form.tag_names"
                    :key="tag"
                    class="tag-pill"
                  >
                    <span class="tag-icon">#</span>
                    <span class="tag-text">{{ tag }}</span>
                    <button
                      type="button"
                      class="tag-remove"
                      @click="handleTagRemove(tag)"
                      aria-label="移除标签"
                    >
                      <el-icon><Close /></el-icon>
                    </button>
                  </div>

                  <div v-if="tagInputVisible" class="tag-input-wrapper">
                    <span class="tag-icon">#</span>
                    <input
                      ref="tagInput"
                      v-model="tagInputValue"
                      class="tag-input-field"
                      type="text"
                      placeholder="输入标签名"
                      maxlength="20"
                      @keyup.enter="handleTagInputConfirm"
                      @blur="handleTagInputConfirm"
                      @keyup.esc="cancelTagInput"
                    />
                  </div>

                  <button
                    v-else
                    type="button"
                    class="tag-add-btn"
                    @click="showTagInput"
                  >
                    <el-icon><Plus /></el-icon>
                    <span>添加标签</span>
                  </button>
                </div>
              </div>

              <div class="editor-divider"></div>

              <div class="editor-stats">
                <span>{{ wordCount }} 字</span>
              </div>

              <div class="editor-shell">
                <div ref="editorRoot" class="wysiwyg-editor"></div>
              </div>
            </section>
          </article>

          <Teleport to="body">
            <div
              v-show="toolbarVisible"
              ref="floatingToolbar"
              class="floating-toolbar"
              :style="{
                top: `${toolbarPosition.top}px`,
                left: `${toolbarPosition.left}px`,
              }"
            >
              <div class="toolbar-group">
                <el-tooltip content="加粗" placement="top" :show-after="120">
                  <button
                    type="button"
                    class="toolbar-button"
                    :class="{
                      'is-active': toolbarState.strong.active,
                      'is-full': toolbarState.strong.full,
                    }"
                    @mousedown.prevent
                    @click="runEditorCommand('strong')"
                  >
                    <strong>B</strong>
                  </button>
                </el-tooltip>
                <el-tooltip content="斜体" placement="top" :show-after="120">
                  <button
                    type="button"
                    class="toolbar-button"
                    :class="{
                      'is-active': toolbarState.italic.active,
                      'is-full': toolbarState.italic.full,
                    }"
                    @mousedown.prevent
                    @click="runEditorCommand('italic')"
                  >
                    <em>I</em>
                  </button>
                </el-tooltip>
                <el-tooltip content="删除线" placement="top" :show-after="120">
                  <button
                    type="button"
                    class="toolbar-button"
                    :class="{
                      'is-active': toolbarState.strike.active,
                      'is-full': toolbarState.strike.full,
                    }"
                    @mousedown.prevent
                    @click="runEditorCommand('strike')"
                  >
                    <span class="toolbar-strike">S</span>
                  </button>
                </el-tooltip>
                <el-tooltip content="行内代码" placement="top" :show-after="120">
                  <button
                    type="button"
                    class="toolbar-button"
                    :class="{
                      'is-active': toolbarState.code.active,
                      'is-full': toolbarState.code.full,
                    }"
                    @mousedown.prevent
                    @click="runEditorCommand('code')"
                  >
                    <span class="toolbar-code">&lt;/&gt;</span>
                  </button>
                </el-tooltip>
              </div>

              <div class="toolbar-divider"></div>

              <div class="toolbar-group heading-group">
                <el-tooltip
                  v-for="option in headingOptions"
                  :key="option.value"
                  :content="`标题 ${option.label}`"
                  placement="top"
                  :show-after="120"
                >
                  <button
                    type="button"
                    class="toolbar-chip"
                    :class="{
                      'is-active': toolbarState.headings[option.value].active,
                      'is-full': toolbarState.headings[option.value].full,
                    }"
                    @mousedown.prevent
                    @click="applyHeading(option.value)"
                  >
                    {{ option.label }}
                  </button>
                </el-tooltip>
              </div>

              <div class="toolbar-divider"></div>

              <div class="toolbar-group">
                <el-tooltip content="引用" placement="top" :show-after="120">
                  <button
                    type="button"
                    class="toolbar-button with-icon"
                    :class="{
                      'is-active': toolbarState.blockQuote.active,
                      'is-full': toolbarState.blockQuote.full,
                    }"
                    @mousedown.prevent
                    @click="applyBlockQuote"
                  >
                    <el-icon><Tickets /></el-icon>
                  </button>
                </el-tooltip>
                <el-tooltip content="代码块" placement="top" :show-after="120">
                  <button
                    type="button"
                    class="toolbar-button with-icon"
                    :class="{
                      'is-active': toolbarState.codeBlock.active,
                      'is-full': toolbarState.codeBlock.full,
                    }"
                    @mousedown.prevent
                    @click="applyCodeBlock"
                  >
                    <el-icon><Document /></el-icon>
                  </button>
                </el-tooltip>
                <el-tooltip
                  v-if="toolbarState.codeBlock.full"
                  content="AI 自动排版代码块"
                  placement="top"
                  :show-after="120"
                >
                  <button
                    type="button"
                    class="toolbar-button with-icon ai-format-button"
                    @mousedown.prevent
                    @click="applyCodeBlockAutoFormat"
                  >
                    <el-icon><MagicStick /></el-icon>
                  </button>
                </el-tooltip>
                <el-tooltip content="分割线" placement="top" :show-after="120">
                  <button
                    type="button"
                    class="toolbar-button with-icon"
                    :class="{
                      'is-active': toolbarState.horizontalRule.active,
                      'is-full': toolbarState.horizontalRule.full,
                    }"
                    @mousedown.prevent
                    @click="applyHorizontalRule"
                  >
                    <el-icon><Minus /></el-icon>
                  </button>
                </el-tooltip>
              </div>
            </div>
          </Teleport>

          <Teleport to="body">
            <div
              v-show="hoverBlockHintVisible"
              class="hover-block-hint"
              :style="{
                top: `${hoverBlockHint.top}px`,
                left: `${hoverBlockHint.left}px`,
              }"
            >
              {{ hoverBlockHint.label }}
            </div>
          </Teleport>
        </section>

        <!-- 版本抽屉遮罩 -->
        <transition name="drawer-mask">
          <div v-show="versionDrawerVisible" class="drawer-mask" @click="closeVersionDrawer"></div>
        </transition>

        <!-- 版本抽屉 -->
        <transition name="drawer-slide">
          <aside v-show="versionDrawerVisible" class="version-drawer">
            <div class="version-drawer-header">
              <div>
                <p>Versions</p>
                <h2>历史版本</h2>
              </div>
              <button class="drawer-close-btn" @click="closeVersionDrawer">
                <el-icon><Close /></el-icon>
              </button>
            </div>

            <div class="version-drawer-body">
              <div v-if="versions.length" class="version-list">
                <article
                  v-for="version in versions"
                  :key="version.id"
                  class="version-item"
                  @click="previewVersion(version)"
                >
                  <div class="version-icon">
                    <el-icon><Clock /></el-icon>
                  </div>
                  <div class="version-copy">
                    <strong>{{ version.title }}</strong>
                    <span>{{ formatDateTime(version.created_at) }} / {{ version.word_count }} 字</span>
                    <p v-if="version.note_text" class="version-note">{{ version.note_text }}</p>
                    <p v-if="version.tag_names?.length">{{ version.tag_names.join(' / ') }}</p>
                  </div>
                </article>
              </div>

              <div v-else class="version-empty">
                <p>还没有历史版本。</p>
                <span>点击"创建版本"后，当前内容会进入版本记录。</span>
              </div>
            </div>
          </aside>
        </transition>

        <!-- 浮动版本按钮 -->
        <button class="floating-version-button" @click="toggleVersionDrawer">
          <el-icon><Document /></el-icon>
          <span class="button-label">版本</span>
          <span v-if="versions.length" class="version-count">{{ versions.length }}</span>
        </button>

        <transition name="preview-float">
          <aside v-show="floatingPreviewVisible" class="floating-preview">
            <div class="floating-preview-head">
              <div>
                <p>Preview</p>
                <strong>{{ resolveFloatingPreviewTitle() }}</strong>
              </div>
              <span>{{ editorReady ? '实时更新' : '加载中' }}</span>
            </div>
            <div
              v-if="floatingPreviewBodyHtml"
              class="floating-preview-body markdown-body"
              v-html="floatingPreviewBodyHtml"
            ></div>
            <div v-else class="floating-preview-empty">
              <strong>预览会在编辑时出现</strong>
            </div>
          </aside>
        </transition>
      </section>
    </WorkspaceShell>

    <!-- 版本预览对话框 -->
    <el-dialog
      v-model="versionPreview.visible"
      title="版本预览"
      width="80%"
      :close-on-click-modal="false"
    >
      <template v-if="versionPreview.version">
        <div class="version-preview-header">
          <h3>{{ versionPreview.version.title }}</h3>
          <p>
            <span>{{ formatDateTime(versionPreview.version.created_at) }}</span>
            <span>{{ versionPreview.version.word_count }} 字</span>
          </p>
          <p v-if="versionPreview.version.note_text" class="preview-note">
            备注：{{ versionPreview.version.note_text }}
          </p>
        </div>
        <div
          class="version-preview-content markdown-body"
          v-html="versionPreview.version.rendered_html"
        ></div>
      </template>
      <template #footer>
        <el-button @click="closeVersionPreview">关闭</el-button>
        <el-button type="primary" @click="restoreVersion(versionPreview.version)">
          <el-icon><RefreshRight /></el-icon>
          恢复此版本
        </el-button>
      </template>
    </el-dialog>
  </main>
</template>

<style scoped>
.edit-page {
  padding: 20px;
}

.edit-stage {
  min-height: calc(100vh - 20px);
  min-height: calc(100svh - 20px);
  margin-top: 20px;
}

.edit-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 20px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.82);
  box-shadow: var(--shadow-soft);
}

.back-button {
  display: inline-flex;
  width: fit-content;
  align-items: center;
  gap: 8px;
  min-height: 42px;
  padding: 0 14px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.82);
  color: var(--brand-navy);
  cursor: pointer;
  transition:
    transform 0.2s ease,
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.back-button:hover {
  transform: translateY(-1px);
  border-color: rgba(37, 99, 235, 0.24);
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.08);
}

.auto-save-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.08);
  color: var(--brand-blue);
  font-size: 0.9rem;
  font-weight: 600;
}

.auto-save-badge :deep(.el-icon) {
  font-size: 1rem;
}

.save-button {
  min-height: 44px;
  padding-inline: 20px;
  border: none;
  border-radius: 14px;
  background: linear-gradient(135deg, #1d4ed8 0%, #2563eb 46%, #f59e0b 160%);
  box-shadow: 0 18px 36px rgba(37, 99, 235, 0.24);
}

.editor-layout {
  display: grid;
  grid-template-columns: 1fr;
  gap: 26px;
  align-items: start;
  margin-top: 34px;
}

.editor-main,
.version-panel {
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 30px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.9), rgba(255, 255, 255, 0.72)),
    rgba(255, 255, 255, 0.72);
  box-shadow: var(--shadow-soft);
}

.editor-main {
  display: grid;
  gap: 22px;
  min-width: 0;
  padding: 30px;
}

.editor-panel {
  display: grid;
  gap: 0;
  padding: 30px 32px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.76);
}

.editor-meta {
  position: relative;
  margin-bottom: 16px;
}

.title-input {
  width: 100%;
  padding: 12px 0;
  border: none;
  background: transparent;
  color: var(--brand-navy);
  font-size: 2.2rem;
  font-weight: 700;
  line-height: 1.2;
  outline: none;
  transition: color 0.2s ease;
}

.title-input::placeholder {
  color: rgba(100, 116, 139, 0.3);
}

.title-input:focus {
  color: var(--brand-blue);
}

.title-count {
  position: absolute;
  right: 0;
  bottom: 8px;
  color: var(--ink-soft);
  font-size: 0.75rem;
  opacity: 0;
  transition: opacity 0.2s ease;
}

.title-input:focus + .title-count {
  opacity: 1;
}

/* 标签区域 */
.tags-section {
  margin-bottom: 16px;
}

.tags-list {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.tag-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border: 1px solid rgba(37, 99, 235, 0.2);
  border-radius: 999px;
  background: linear-gradient(135deg, rgba(37, 99, 235, 0.08), rgba(245, 158, 11, 0.06));
  color: var(--brand-blue);
  font-size: 0.95rem;
  font-weight: 600;
  transition: all 0.2s ease;
}

.tag-pill:hover {
  border-color: rgba(37, 99, 235, 0.3);
  background: linear-gradient(135deg, rgba(37, 99, 235, 0.12), rgba(245, 158, 11, 0.08));
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.15);
}

.tag-icon {
  color: var(--brand-blue);
  font-size: 1rem;
  font-weight: 700;
  opacity: 0.7;
}

.tag-text {
  color: var(--brand-navy);
}

.tag-remove {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: rgba(37, 99, 235, 0.12);
  color: var(--brand-blue);
  cursor: pointer;
  transition: all 0.2s ease;
}

.tag-remove:hover {
  background: rgba(239, 68, 68, 0.15);
  color: #dc2626;
  transform: scale(1.1);
}

.tag-remove :deep(.el-icon) {
  font-size: 12px;
}

.tag-input-wrapper {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border: 1px solid var(--brand-blue);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.95);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
}

.tag-input-field {
  width: 120px;
  border: none;
  background: transparent;
  color: var(--brand-navy);
  font-size: 0.95rem;
  font-weight: 600;
  outline: none;
}

.tag-input-field::placeholder {
  color: rgba(100, 116, 139, 0.5);
}

.tag-add-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border: 1px dashed rgba(148, 163, 184, 0.3);
  border-radius: 999px;
  background: rgba(248, 250, 252, 0.5);
  color: var(--ink-soft);
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.tag-add-btn:hover {
  border-color: var(--brand-blue);
  border-style: solid;
  background: rgba(37, 99, 235, 0.06);
  color: var(--brand-blue);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.1);
}

.tag-add-btn :deep(.el-icon) {
  font-size: 14px;
}

.editor-divider {
  height: 1px;
  margin: 24px 0 16px;
  background: linear-gradient(
    90deg,
    transparent,
    rgba(148, 163, 184, 0.2) 20%,
    rgba(148, 163, 184, 0.2) 80%,
    transparent
  );
}

.editor-stats {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 16px;
}

.editor-stats span {
  color: var(--ink-soft);
  font-size: 0.9rem;
  font-weight: 600;
}

.editor-shell {
  position: relative;
}

.wysiwyg-editor {
  min-height: 560px;
}

.wysiwyg-editor :deep(.toastui-editor-defaultUI) {
  height: auto !important;
  border: none;
  background: transparent;
}

.wysiwyg-editor :deep(.toastui-editor-mode-switch) {
  display: none;
}

.wysiwyg-editor :deep(.toastui-editor-toolbar) {
  display: none;
}

.wysiwyg-editor :deep(.toastui-editor-main) {
  overflow: visible;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.9);
}

.wysiwyg-editor :deep(.toastui-editor-main-container) {
  height: auto !important;
  overflow: visible !important;
  font-family: 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.wysiwyg-editor :deep(.toastui-editor-ww-container) {
  height: auto !important;
  overflow: visible !important;
  background: transparent;
}

.wysiwyg-editor :deep(.toastui-editor-contents) {
  min-height: 520px;
  padding: 22px 24px;
  color: var(--brand-navy);
  font-size: 1rem;
  line-height: 1.95;
  font-family: inherit;
}

.wysiwyg-editor :deep(.toastui-editor-contents pre),
.wysiwyg-editor :deep(.toastui-editor-contents code),
.wysiwyg-editor :deep(.toastui-editor-contents .toastui-editor-ww-code-block),
.wysiwyg-editor :deep(.toastui-editor-contents .toastui-editor-ww-code-block code) {
  font-family: 'Cascadia Code', 'Consolas', monospace;
}

.wysiwyg-editor :deep(.toastui-editor-contents p),
.wysiwyg-editor :deep(.toastui-editor-contents li),
.wysiwyg-editor :deep(.toastui-editor-contents blockquote) {
  color: var(--brand-navy);
}

.wysiwyg-editor :deep(.toastui-editor-contents h1),
.wysiwyg-editor :deep(.toastui-editor-contents h2),
.wysiwyg-editor :deep(.toastui-editor-contents h3),
.wysiwyg-editor :deep(.toastui-editor-contents h4),
.wysiwyg-editor :deep(.toastui-editor-contents h5),
.wysiwyg-editor :deep(.toastui-editor-contents h6) {
  border-bottom: none;
  padding-bottom: 0;
}

.wysiwyg-editor :deep(.toastui-editor-contents em),
.wysiwyg-editor :deep(.toastui-editor-contents i) {
  display: inline-block;
  font-style: oblique 12deg;
  transform: skewX(-8deg);
  transform-origin: center bottom;
}

.wysiwyg-editor :deep(.toastui-editor-contents blockquote) {
  border-left-color: var(--brand-blue);
}

.wysiwyg-editor :deep(.toastui-editor-contents .toastui-editor-ww-code-block) {
  position: relative;
  margin: 18px 0 14px;
  border-radius: 20px;
}

.wysiwyg-editor :deep(.toastui-editor-contents .toastui-editor-ww-code-block pre) {
  border-radius: 20px;
}

.wysiwyg-editor :deep(.toastui-editor-contents .toastui-editor-ww-code-block:after) {
  display: none;
}

.wysiwyg-editor :deep(.toastui-editor-ww-code-block-language) {
  display: none !important;
}

.wysiwyg-editor :deep(.inline-code-language-chip),
.wysiwyg-editor :deep(.inline-code-language-input) {
  position: absolute;
  top: 14px;
  right: 14px;
  box-sizing: border-box;
  min-width: 74px;
  max-width: min(132px, calc(100% - 28px));
  height: 30px;
  padding: 0 12px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 12px 24px rgba(15, 23, 42, 0.08);
  color: var(--brand-navy);
  font-size: 0.78rem;
  font-weight: 700;
  line-height: 30px;
  text-align: center;
  letter-spacing: 0.01em;
}

.wysiwyg-editor :deep(.inline-code-language-chip) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border: 1px solid rgba(148, 163, 184, 0.18);
  cursor: text;
  transition:
    border-color 0.18s ease,
    box-shadow 0.18s ease,
    background-color 0.18s ease;
}

.wysiwyg-editor :deep(.inline-code-language-chip:hover) {
  border-color: rgba(37, 99, 235, 0.28);
  background: rgba(255, 255, 255, 0.98);
  box-shadow:
    0 12px 24px rgba(15, 23, 42, 0.08),
    0 0 0 3px rgba(37, 99, 235, 0.08);
}

.wysiwyg-editor :deep(.inline-code-language-input) {
  outline: none;
  cursor: text;
}

.wysiwyg-editor :deep(.inline-code-language-input:focus) {
  border-color: rgba(37, 99, 235, 0.34);
  background: #ffffff;
  box-shadow:
    0 12px 24px rgba(15, 23, 42, 0.08),
    0 0 0 3px rgba(37, 99, 235, 0.12);
}

.floating-toolbar {
  position: fixed;
  z-index: 200;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 11px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 20px;
  background:
    radial-gradient(circle at top right, rgba(37, 99, 235, 0.12), transparent 34%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 250, 252, 0.94)),
    rgba(255, 255, 255, 0.94);
  box-shadow:
    0 22px 48px rgba(15, 23, 42, 0.14),
    0 6px 18px rgba(37, 99, 235, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(16px);
}

.hover-block-hint {
  position: fixed;
  z-index: 199;
  min-height: 26px;
  padding: 0 10px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.14);
  color: var(--brand-navy);
  font-size: 0.75rem;
  font-weight: 700;
  line-height: 24px;
  pointer-events: none;
  white-space: nowrap;
  backdrop-filter: blur(10px);
}

.toolbar-group {
  display: flex;
  align-items: center;
  gap: 6px;
}

.toolbar-divider {
  width: 1px;
  height: 28px;
  background: linear-gradient(180deg, rgba(148, 163, 184, 0), rgba(148, 163, 184, 0.32), rgba(148, 163, 184, 0));
}

.toolbar-button,
.toolbar-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 36px;
  height: 36px;
  padding: 0 11px;
  border: 1px solid rgba(148, 163, 184, 0.1);
  border-radius: 13px;
  background: rgba(255, 255, 255, 0.68);
  color: var(--brand-navy);
  cursor: pointer;
  transition:
    transform 0.18s ease,
    background-color 0.18s ease,
    border-color 0.18s ease,
    color 0.18s ease,
    box-shadow 0.18s ease;
}

.toolbar-button:hover,
.toolbar-chip:hover {
  transform: translateY(-1px);
  border-color: rgba(37, 99, 235, 0.2);
  background: linear-gradient(180deg, rgba(37, 99, 235, 0.12), rgba(255, 255, 255, 0.82));
  color: var(--brand-blue);
  box-shadow:
    0 10px 20px rgba(15, 23, 42, 0.1),
    inset 0 1px 0 rgba(255, 255, 255, 0.72);
}

.toolbar-button:active,
.toolbar-chip:active {
  transform: translateY(0);
  background: rgba(37, 99, 235, 0.14);
  border-color: rgba(37, 99, 235, 0.24);
  color: var(--brand-blue);
}

.toolbar-button.is-active,
.toolbar-chip.is-active {
  border-color: rgba(37, 99, 235, 0.18);
  background: linear-gradient(180deg, rgba(37, 99, 235, 0.09), rgba(255, 255, 255, 0.82));
  color: var(--brand-blue);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.72);
}

.toolbar-button.is-full,
.toolbar-chip.is-full {
  border-color: rgba(37, 99, 235, 0.24);
  background: linear-gradient(180deg, rgba(37, 99, 235, 0.16), rgba(255, 255, 255, 0.88));
  color: var(--brand-blue);
  box-shadow:
    0 10px 22px rgba(37, 99, 235, 0.12),
    inset 0 1px 0 rgba(255, 255, 255, 0.82);
}

.toolbar-chip {
  min-width: 44px;
  font-size: 0.76rem;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.toolbar-strike {
  text-decoration: line-through;
}

.toolbar-code {
  font-size: 0.78rem;
  font-family: 'Cascadia Code', 'Consolas', monospace;
}

.with-icon :deep(.el-icon) {
  font-size: 0.95rem;
}

.version-panel {
  position: sticky;
  top: 22px;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 18px;
  max-height: calc(100vh - 44px);
  padding: 24px;
  overflow: hidden;
}

.version-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
}

.version-head p {
  margin: 0 0 8px;
  color: var(--brand-blue);
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.version-head h2 {
  margin: 0;
  color: var(--brand-navy);
  font-size: 1.5rem;
  letter-spacing: -0.04em;
}

.version-head > span {
  color: var(--ink-soft);
  font-weight: 700;
}

.version-list {
  display: grid;
  gap: 12px;
  overflow-y: auto;
  overflow-x: hidden;
  padding-right: 4px;
}

.version-item {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 12px;
  padding: 14px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.72);
  cursor: pointer;
  transition: all 180ms ease;
}

.version-item:hover {
  border-color: var(--brand-blue);
  background: rgba(37, 99, 235, 0.04);
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.08);
}

.version-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 12px;
  background: rgba(37, 99, 235, 0.08);
  color: var(--brand-blue);
}

.version-copy {
  min-width: 0;
}

.version-copy strong {
  display: block;
  color: var(--brand-navy);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.version-copy span,
.version-copy p {
  color: var(--ink-soft);
  font-size: 0.86rem;
}

.version-copy span {
  display: block;
  margin-top: 6px;
}

.version-copy p {
  margin: 8px 0 0;
}

.restore-button {
  grid-column: 2;
  width: fit-content;
  min-height: 36px;
  border-radius: 12px;
}

.version-empty {
  display: grid;
  gap: 6px;
  padding: 8px 0;
}

.version-empty p {
  margin: 0;
  color: var(--brand-navy);
  font-weight: 700;
}

.version-empty span {
  color: var(--ink-soft);
  line-height: 1.7;
}

.floating-preview {
  position: fixed;
  right: 28px;
  bottom: 28px;
  z-index: 198;
  display: grid;
  gap: 12px;
  width: min(380px, calc(100vw - 32px));
  max-height: min(360px, 48vh);
  padding: 16px;
  overflow: hidden;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 22px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 250, 252, 0.94)),
    rgba(255, 255, 255, 0.94);
  box-shadow:
    0 24px 64px rgba(15, 23, 42, 0.16),
    0 8px 24px rgba(37, 99, 235, 0.08);
  backdrop-filter: blur(18px);
}

.floating-preview-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.floating-preview-head p {
  margin: 0 0 6px;
  color: var(--brand-blue);
  font-size: 0.76rem;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.floating-preview-head strong {
  display: block;
  color: var(--brand-navy);
  font-size: 1rem;
  line-height: 1.35;
}

.floating-preview-head span {
  color: var(--ink-soft);
  font-size: 0.8rem;
  white-space: nowrap;
}

.floating-preview-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.floating-preview-tag {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.08);
  color: var(--brand-blue);
  font-size: 0.78rem;
  font-weight: 600;
}

.floating-preview-body {
  min-height: 0;
  overflow: auto;
  padding-right: 4px;
}

.floating-preview-body :deep(*) {
  font-size: 0.92rem;
}

.floating-preview-body :deep(h1),
.floating-preview-body :deep(h2),
.floating-preview-body :deep(h3) {
  margin-top: 0;
}

.floating-preview-body :deep(.floating-preview-inline-tags) {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.floating-preview-body :deep(.floating-preview-inline-tag) {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.08);
  color: var(--brand-blue);
  font-size: 0.78rem;
  font-weight: 600;
}

.floating-preview-empty {
  color: var(--ink-soft);
}

.floating-preview-empty strong {
  color: var(--brand-navy);
  font-size: 0.94rem;
}

.preview-float-enter-active,
.preview-float-leave-active {
  transition:
    opacity 0.18s ease,
    transform 0.18s ease;
}

.preview-float-enter-from,
.preview-float-leave-to {
  opacity: 0;
  transform: translateY(10px);
}

@media (max-width: 1380px) {
  .editor-layout {
    grid-template-columns: 1fr;
  }

  .version-panel {
    position: static;
  }
}

@media (max-width: 980px) {
  .edit-page {
    padding: 16px;
  }

  .edit-stage {
    min-height: auto;
    margin-top: 0;
  }
}

@media (max-width: 720px) {
  .edit-header {
    flex-wrap: wrap;
    padding: 14px 16px;
  }

  .back-button {
    order: 1;
  }

  .auto-save-badge {
    order: 3;
    width: 100%;
    justify-content: center;
    font-size: 0.85rem;
  }

  .save-button {
    order: 2;
    margin-left: auto;
  }

  .editor-main {
    padding: 22px;
  }

  .editor-panel {
    padding: 24px 20px;
    border-radius: 20px;
  }

  .title-input {
    font-size: 1.8rem;
    padding: 10px 0;
  }

  .editor-divider {
    margin: 20px 0 14px;
  }

  .floating-toolbar {
    gap: 8px;
    flex-wrap: wrap;
    width: min(320px, calc(100vw - 32px));
  }

  .heading-group {
    flex-wrap: wrap;
  }

  .floating-preview {
    right: 16px;
    bottom: 16px;
    width: min(340px, calc(100vw - 24px));
  }

  .wysiwyg-editor :deep(.inline-code-language-chip),
  .wysiwyg-editor :deep(.inline-code-language-input) {
    right: 12px;
    min-width: 68px;
  }
}

@media (max-width: 520px) {
  .editor-main,
  .version-panel {
    padding: 18px 16px;
    border-radius: 20px;
  }

  .editor-panel {
    padding: 16px;
    border-radius: 18px;
  }

  .editor-head,
  .version-head {
    align-items: flex-start;
    flex-direction: column;
  }

  .wysiwyg-editor :deep(.toastui-editor-contents) {
    min-height: 420px;
    padding: 18px 16px;
  }

  .version-item {
    grid-template-columns: 1fr;
  }

  .version-icon {
    display: none;
  }

  .restore-button {
    grid-column: auto;
    width: 100%;
  }

  .floating-preview {
    right: 12px;
    bottom: 12px;
    width: calc(100vw - 24px);
    max-height: 42vh;
    padding: 14px;
    border-radius: 18px;
  }

  .version-drawer {
    width: 100vw;
  }

  .floating-version-button {
    right: 16px;
    bottom: 16px;
    min-width: 64px;
    padding: 12px 10px;
  }

  .floating-version-button :deep(.el-icon) {
    font-size: 22px;
  }

  .floating-version-button .button-label {
    font-size: 0.8rem;
  }
}

/* 版本预览对话框样式 */
.version-note {
  margin-top: 6px;
  padding: 6px 10px;
  border-radius: 8px;
  background: rgba(37, 99, 235, 0.08);
  color: var(--brand-blue);
  font-size: 0.85rem;
  font-style: italic;
}

.version-preview-header {
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.2);
}

.version-preview-header h3 {
  margin: 0 0 8px;
  color: var(--brand-navy);
  font-size: 1.5rem;
}

.version-preview-header p {
  margin: 4px 0;
  color: var(--ink-soft);
  font-size: 0.9rem;
}

.version-preview-header p span {
  margin-right: 16px;
}

.version-preview-header .preview-note {
  margin-top: 12px;
  padding: 10px 14px;
  border-radius: 8px;
  background: rgba(37, 99, 235, 0.08);
  color: var(--brand-blue);
  font-size: 0.95rem;
  font-style: normal;
}

.version-preview-content {
  max-height: 60vh;
  overflow-y: auto;
  padding: 20px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 12px;
  background: rgba(248, 250, 252, 0.5);
}

/* 版本抽屉遮罩 */
.drawer-mask {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 100;
  background: rgba(15, 23, 42, 0.5);
  backdrop-filter: blur(4px);
}

.drawer-mask-enter-active,
.drawer-mask-leave-active {
  transition: all 0.3s ease;
}

.drawer-mask-enter-from,
.drawer-mask-leave-to {
  opacity: 0;
}

/* 版本抽屉 */
.version-drawer {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 101;
  width: min(420px, 85vw);
  display: flex;
  flex-direction: column;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(255, 255, 255, 0.96));
  backdrop-filter: blur(20px);
  box-shadow: -8px 0 48px rgba(15, 23, 42, 0.15);
}

.drawer-slide-enter-active,
.drawer-slide-leave-active {
  transition: transform 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}

.drawer-slide-enter-from,
.drawer-slide-leave-to {
  transform: translateX(100%);
}

.version-drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 28px 26px 22px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.16);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.9), transparent);
}

.version-drawer-header p {
  margin: 0 0 8px;
  color: var(--brand-blue);
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.version-drawer-header h2 {
  margin: 0;
  color: var(--brand-navy);
  font-size: 1.8rem;
  font-weight: 800;
  letter-spacing: -0.04em;
}

.drawer-close-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.8);
  color: var(--brand-navy);
  cursor: pointer;
  transition: all 0.2s ease;
}

.drawer-close-btn:hover {
  border-color: rgba(37, 99, 235, 0.3);
  background: rgba(255, 255, 255, 1);
  transform: scale(1.05);
}

.version-drawer-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px 26px 30px;
}

/* 浮动版本按钮 */
.floating-version-button {
  position: fixed;
  right: 28px;
  bottom: 28px;
  z-index: 198;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  min-width: 72px;
  padding: 14px 12px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 18px;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.96), rgba(248, 250, 252, 0.94));
  box-shadow:
    0 12px 32px rgba(15, 23, 42, 0.12),
    0 4px 12px rgba(37, 99, 235, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.9);
  color: var(--brand-blue);
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  backdrop-filter: blur(12px);
}

.floating-version-button:hover {
  transform: translateY(-3px);
  border-color: rgba(37, 99, 235, 0.3);
  box-shadow:
    0 18px 48px rgba(15, 23, 42, 0.18),
    0 8px 20px rgba(37, 99, 235, 0.16),
    inset 0 1px 0 rgba(255, 255, 255, 1);
}

.floating-version-button :deep(.el-icon) {
  font-size: 26px;
}

.floating-version-button .button-label {
  font-size: 0.85rem;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.floating-version-button .version-count {
  position: absolute;
  top: 8px;
  right: 8px;
  min-width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 6px;
  border-radius: 999px;
  background: linear-gradient(135deg, #1d4ed8, #2563eb);
  color: #ffffff;
  font-size: 0.75rem;
  font-weight: 700;
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.4);
}
</style>
