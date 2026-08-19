<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import Editor from '@toast-ui/editor'
import '@toast-ui/editor/dist/i18n/zh-cn'
import { wrapIn } from 'prosemirror-commands'
import { Selection, TextSelection } from 'prosemirror-state'
import { liftTarget } from 'prosemirror-transform'

import '@toast-ui/editor/dist/toastui-editor.css'

import WorkspaceShell from '../components/WorkspaceShell.vue'
import EditorTableOverlays from '../editor/components/EditorTableOverlays.vue'
import FixedEditorToolbar from '../editor/components/FixedEditorToolbar.vue'
import FloatingFormatToolbar from '../editor/components/FloatingFormatToolbar.vue'
import FloatingPreview from '../editor/components/FloatingPreview.vue'
import NoteEditorPanel from '../editor/components/NoteEditorPanel.vue'
import NoteEditHeader from '../editor/components/NoteEditHeader.vue'
import SideTableToolbar from '../editor/components/SideTableToolbar.vue'
import TableActionPanel from '../editor/components/TableActionPanel.vue'
import VersionHistoryDrawer from '../editor/components/VersionHistoryDrawer.vue'
import VersionPreviewDialog from '../editor/components/VersionPreviewDialog.vue'
import {
  buildTagPreviewHtml,
  buildTitlePreviewHtml,
  createFixedToolbarState,
  createToolbarToggleState,
  formatEditorDateTime,
  getFixedToolbarSnapshot,
  headingOptions,
  resolveFloatingPreviewTitle,
  toPlainTextForCount,
} from '../editor/editorHelpers'
import api from '../services/api'
import {
  EDITOR_SETTINGS_CHANGE_EVENT,
  EDITOR_TOOLBAR_MODES,
  getEditorSettings,
} from '../utils/editorSettings'
import {
  MIN_TABLE_COLUMN_WIDTH,
  MIN_TABLE_ROW_HEIGHT,
  MAX_TABLE_COLUMN_COUNT,
  MAX_TABLE_ROW_COUNT,
  applyTableAlignment,
  applyTableLayoutsToTables,
  extractTableLayoutMetadata,
  fitTableLayoutToMaxWidth,
  getAvailableTableWidth,
  getTableColumnCount,
  getTableColumnWidths,
  getTableRowCount,
  getTableRowHeights,
  normalizeTableLayout,
  serializeMarkdownWithTableLayouts,
  setTableInlineLimit,
  syncTableColgroup,
} from '../utils/tableLayout'
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
const editorRoot = ref(null)
const imageInsertInput = ref(null)
const imageReplaceInput = ref(null)
const floatingToolbar = ref(null)
const selectionRange = ref(null)
const toolbarVisible = ref(false)
const toolbarSelectionInTable = ref(false)
const tableMultiCellSelectionActive = ref(false)
const sideTablePickerVisible = ref(false)
const tableActionPanelVisible = ref(false)
const tableHoverControlVisible = ref(false)
const tableResizeHandleVisible = ref(false)
const tableResizeHandleDragging = ref(false)
const activeTableInfo = ref(null)
const floatingPreviewVisible = ref(false)
const hoverBlockHintVisible = ref(false)
const editorSettings = ref(getEditorSettings())
const editorPlaceholder = '在这里直接编辑笔记正文'
const toolbarPosition = reactive({
  top: -9999,
  left: -9999,
})
const hoverBlockHint = reactive({
  label: '',
  top: -9999,
  left: -9999,
})
const tableActionPanelPosition = reactive({
  top: -9999,
  left: -9999,
})
const tableHoverControlPosition = reactive({
  top: -9999,
  left: -9999,
})
const tableResizeHandle = reactive({
  top: -9999,
  left: -9999,
  width: 14,
  height: 0,
  kind: 'column',
  columnIndex: -1,
  rowIndex: -1,
})
const tableResizeSizeHint = reactive({
  visible: false,
  top: -9999,
  left: -9999,
  text: '',
})
const tableSelectionOverlay = reactive({
  visible: false,
  top: -9999,
  left: -9999,
  width: 0,
  height: 0,
})

const form = reactive({
  title: '',
  tag_names: [],
})

let autoSaveTimer = null
let lastSavedContent = ''

const versionPreview = reactive({
  visible: false,
  version: null,
})

const toolbarState = reactive({
  strong: createToolbarToggleState(),
  italic: createToolbarToggleState(),
  strike: createToolbarToggleState(),
  code: createToolbarToggleState(),
  cellAlignLeft: createToolbarToggleState(),
  cellAlignCenter: createToolbarToggleState(),
  cellAlignRight: createToolbarToggleState(),
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
const imageToolbarVisible = ref(false)
const activeEditorImage = ref(null)
const imageToolbarPosition = reactive({
  top: -9999,
  left: -9999,
})
const fixedToolbarState = reactive(createFixedToolbarState())
const fixedToolbarSelectedText = ref('')

let editorInstance = null
let activeCodeLanguageInput = null
let activeCodeLanguageChip = null
let floatingPreviewTimer = null
let cleanupEditorSelectionListeners = null
let toolbarSyncFrame = null
let cleanupEditorHoverListeners = null
let lastEditorSelectionRange = null
let toastContextMenuFrame = null
let nativeSelectedTableCellElements = new Set()
let nativeTableCellSelectionAnchor = null
let nativeTableCellSelectionAnchorPosition = null
let nativeTableCellSelectionDragging = false
let nativeTableCellSelectionMoved = false
let nativeTableCellSelectionRect = null
let nativeTableCellSelectionStyleElement = null
let tableHoverControlCellElement = null
let tableHoverControlTableInfo = null
let tableResizeHandleTableElement = null
let tableResizeDragState = null
let suppressNextTableEditorClick = false
let editorRootIdSeed = 0
let tableLayoutMetadata = []
let tableLayoutStyleElement = null
const tableAlignmentRevision = ref(0)

const wordCount = computed(() => toPlainTextForCount(currentMarkdown.value).replace(/\s+/g, '').length)
const versionCountText = computed(() => `${versions.value.length} / 5`)
const editorFontSizeStyle = computed(() => ({
  '--editor-font-size': `${editorSettings.value.fontSizePx}px`,
}))
const autoSaveStatusText = computed(() => {
  if (!editorSettings.value.autoSaveEnabled) {
    return '自动保存已关闭'
  }

  return `自动保存：${Math.round(editorSettings.value.autoSaveIntervalMs / 1000)} 秒`
})
const isFixedToolbarMode = computed(
  () => editorSettings.value.toolbarMode === EDITOR_TOOLBAR_MODES.FIXED
)
const canDeleteSelectedTableRow = computed(
  () => Boolean(activeTableInfo.value) && activeTableInfo.value.rowIndex > 0 && activeTableInfo.value.rowCount > 2
)
const canDeleteSelectedTableColumn = computed(
  () => Boolean(activeTableInfo.value) && activeTableInfo.value.columnCount > 1
)
const canAddSelectedTableRow = computed(
  () => Boolean(activeTableInfo.value) && activeTableInfo.value.rowCount < MAX_TABLE_ROW_COUNT
)
const canAddSelectedTableColumn = computed(
  () => Boolean(activeTableInfo.value) && activeTableInfo.value.columnCount < MAX_TABLE_COLUMN_COUNT
)
const activeTableAlignment = computed(() => {
  tableAlignmentRevision.value
  if (!activeTableInfo.value) {
    return 'left'
  }

  const view = getWysiwygView()
  const tableIndex = view ? getTableIndexFromTablePos(view, activeTableInfo.value.tablePos) : -1
  return tableIndex >= 0 ? tableLayoutMetadata[tableIndex]?.align || 'left' : 'left'
})
const canMergeSelectedTableCells = computed(() => {
  tableMultiCellSelectionActive.value
  tableActionPanelVisible.value
  return Boolean(getMergeTableCellSelectionInfo(false))
})
const canSplitSelectedTableCell = computed(() => {
  activeTableInfo.value
  tableActionPanelVisible.value
  return Boolean(getSplitTableCellInfo(false))
})

const hideToolbar = () => {
  toolbarVisible.value = false
  selectionRange.value = null
  resetToolbarState()
}

const hideTableActionPanel = () => {
  tableActionPanelVisible.value = false
  activeTableInfo.value = null
  tableActionPanelPosition.top = -9999
  tableActionPanelPosition.left = -9999
}

const hideTableHoverControl = () => {
  tableHoverControlVisible.value = false
  tableHoverControlCellElement = null
  tableHoverControlTableInfo = null
  tableHoverControlPosition.top = -9999
  tableHoverControlPosition.left = -9999
}

const hideTableResizeHandle = () => {
  if (tableResizeHandleDragging.value) {
    return
  }

  tableResizeHandleVisible.value = false
  tableResizeHandleTableElement = null
  tableResizeHandle.top = -9999
  tableResizeHandle.left = -9999
  tableResizeHandle.width = 14
  tableResizeHandle.height = 0
  tableResizeHandle.kind = 'column'
  tableResizeHandle.columnIndex = -1
  tableResizeHandle.rowIndex = -1
  hideTableResizeSizeHint()
}

const hideTableResizeSizeHint = () => {
  tableResizeSizeHint.visible = false
  tableResizeSizeHint.top = -9999
  tableResizeSizeHint.left = -9999
  tableResizeSizeHint.text = ''
}

const showTableResizeSizeHint = (text, anchorRect, kind = 'column') => {
  if (!text || !anchorRect) {
    hideTableResizeSizeHint()
    return
  }

  const hintWidth = 82
  const hintHeight = 30
  const gap = 10
  const desiredLeft =
    kind === 'column'
      ? anchorRect.left - hintWidth / 2
      : anchorRect.left + anchorRect.width / 2 - hintWidth / 2
  const desiredTop =
    kind === 'column'
      ? anchorRect.top - hintHeight - gap
      : anchorRect.top - hintHeight - gap

  tableResizeSizeHint.text = text
  tableResizeSizeHint.left = Math.min(
    Math.max(desiredLeft, 8),
    Math.max(8, window.innerWidth - hintWidth - 8)
  )
  tableResizeSizeHint.top = Math.max(8, Math.min(desiredTop, Math.max(8, window.innerHeight - hintHeight - 8)))
  tableResizeSizeHint.visible = true
}

const trimTableLayoutMetadata = (layouts) => {
  const normalizedLayouts = Array.isArray(layouts) ? [...layouts] : []
  while (normalizedLayouts.length && !normalizedLayouts[normalizedLayouts.length - 1]) {
    normalizedLayouts.pop()
  }
  return normalizedLayouts
}

const getDomTableCellSpan = (cellElement, attrName) => {
  const span = Number(cellElement?.getAttribute?.(attrName))
  return Number.isFinite(span) && span > 1 ? span : 1
}

const ensureTableLayoutStyleElement = () => {
  if (!tableLayoutStyleElement) {
    tableLayoutStyleElement = document.createElement('style')
    tableLayoutStyleElement.setAttribute('data-moonbird-table-layouts', 'true')
    document.head.appendChild(tableLayoutStyleElement)
  }

  return tableLayoutStyleElement
}

const getTableRowCssSelector = (tableSelector, tableElement, rowElement) => {
  const rowParent = rowElement.parentElement
  if (!rowParent || rowParent === tableElement) {
    const rowIndex = Array.from(tableElement.children).filter((element) => element.tagName === 'TR').indexOf(rowElement)
    return rowIndex >= 0 ? `${tableSelector} > tr:nth-of-type(${rowIndex + 1})` : ''
  }

  const sectionTagName = rowParent.tagName.toLowerCase()
  const sectionIndex = Array.from(tableElement.children)
    .filter((element) => element.tagName === rowParent.tagName)
    .indexOf(rowParent)
  const rowIndex = Array.from(rowParent.children).filter((element) => element.tagName === 'TR').indexOf(rowElement)

  if (sectionIndex < 0 || rowIndex < 0) {
    return ''
  }

  return `${tableSelector} > ${sectionTagName}:nth-of-type(${sectionIndex + 1}) > tr:nth-of-type(${rowIndex + 1})`
}

const syncEditorTableLayoutTargets = (tableElements) => {
  getEditorTableElements().forEach((tableElement) => {
    delete tableElement.dataset.moonbirdLayoutTableIndex
  })

  tableElements.forEach((tableElement, tableIndex) => {
    tableElement.dataset.moonbirdLayoutTableIndex = String(tableIndex)
  })
}

const applyEditorTableLayoutToDom = (tableElement, layout) => {
  const columnCount = getTableColumnCount(tableElement)
  const rowCount = getTableRowCount(tableElement)
  const normalizedLayout = normalizeTableLayout(
    layout,
    columnCount,
    tableElement?.getBoundingClientRect?.().width,
    rowCount,
    tableElement?.getBoundingClientRect?.().height
  )

  if (!tableElement || !normalizedLayout) {
    return null
  }

  const fittedLayout = fitTableLayoutToMaxWidth(normalizedLayout, getAvailableTableWidth(tableElement))

  setTableInlineLimit(tableElement, fittedLayout.width)
  applyTableAlignment(tableElement, fittedLayout.align)
  syncTableColgroup(tableElement, fittedLayout.columns, { minColumnWidth: 0 })

  if (fittedLayout.rows?.length) {
    tableElement.style.height = `${fittedLayout.height}px`
    tableElement.style.minHeight = `${rowCount * MIN_TABLE_ROW_HEIGHT}px`
  }

  Array.from(tableElement.rows).forEach((rowElement, rowIndex) => {
    let columnIndex = 0
    const rowHeight = fittedLayout.rows?.[rowIndex]

    if (rowHeight) {
      rowElement.style.height = `${rowHeight}px`
      rowElement.style.boxSizing = 'border-box'
    }

    Array.from(rowElement.cells).forEach((cellElement) => {
      if (cellElement.hasAttribute('extended')) {
        return
      }

      const colSpan = getDomTableCellSpan(cellElement, 'colspan')
      const cellWidth = fittedLayout.columns
        .slice(columnIndex, columnIndex + colSpan)
        .reduce((sum, width) => sum + width, 0)

      if (cellWidth > 0) {
        cellElement.style.width = `${Math.round(cellWidth)}px`
      }
      cellElement.style.maxWidth = '0'
      cellElement.style.minWidth = '0'
      cellElement.style.overflowWrap = 'anywhere'
      cellElement.style.wordBreak = 'break-word'

      if (rowHeight) {
        cellElement.style.height = `${rowHeight}px`
      }

      cellElement.style.boxSizing = 'border-box'
      columnIndex += colSpan
    })
  })

  return fittedLayout
}

const getEditorTableCssSelector = (tableElement, tableIndex) => {
  const editorId = ensureEditorRootSelectionId()
  const tablePath = getElementPathFromEditorRoot(tableElement)

  if (editorId && tablePath) {
    return `[data-moonbird-editor-id="${editorId}"] > ${tablePath}`
  }

  return `.wysiwyg-editor .toastui-editor-ww-container .toastui-editor-contents table[data-moonbird-layout-table-index="${tableIndex}"]`
}

const getTableAlignmentCss = (align = 'left') => {
  if (align === 'center') {
    return 'margin-left:auto !important;margin-right:auto !important;'
  }
  if (align === 'right') {
    return 'margin-left:auto !important;margin-right:0 !important;'
  }
  return 'margin-left:0 !important;margin-right:auto !important;'
}

const buildEditorTableLayoutCss = (tableElement, tableIndex, layout) => {
  const columnCount = getTableColumnCount(tableElement)
  const rowCount = getTableRowCount(tableElement)
  const normalizedLayout = normalizeTableLayout(
    layout,
    columnCount,
    tableElement.getBoundingClientRect().width,
    rowCount,
    tableElement.getBoundingClientRect().height
  )

  if (!normalizedLayout) {
    return { layout: null, css: '' }
  }

  const fittedLayout = fitTableLayoutToMaxWidth(normalizedLayout, getAvailableTableWidth(tableElement))
  const tableSelector = getEditorTableCssSelector(tableElement, tableIndex)
  const tableHeightRule = fittedLayout.rows?.length
    ? `height:${fittedLayout.height}px !important;min-height:${rowCount * MIN_TABLE_ROW_HEIGHT}px !important;`
    : ''
  const rules = [
    `${tableSelector}{width:min(${fittedLayout.width}px,100%) !important;inline-size:min(${fittedLayout.width}px,100%) !important;max-width:100% !important;max-inline-size:100% !important;min-width:0 !important;min-inline-size:0 !important;overflow:hidden !important;${getTableAlignmentCss(fittedLayout.align)}${tableHeightRule}table-layout:fixed !important;box-sizing:border-box !important;}`,
  ]

  Array.from(tableElement.rows).forEach((rowElement, rowIndex) => {
    const rowSelector = getTableRowCssSelector(tableSelector, tableElement, rowElement)
    if (!rowSelector) {
      return
    }

    const rowHeight = fittedLayout.rows?.[rowIndex]
    if (rowHeight) {
      rules.push(`${rowSelector}{height:${rowHeight}px !important;box-sizing:border-box !important;}`)
    }

    let columnIndex = 0
    Array.from(rowElement.cells).forEach((cellElement) => {
      if (cellElement.hasAttribute('extended')) {
        return
      }

      const cellIndex = Array.from(rowElement.children).indexOf(cellElement)
      const colSpan = getDomTableCellSpan(cellElement, 'colspan')
      const cellWidth = fittedLayout.columns
        .slice(columnIndex, columnIndex + colSpan)
        .reduce((sum, width) => sum + width, 0)
      const cellHeightRule = rowHeight ? `height:${rowHeight}px !important;` : ''

      if (cellIndex >= 0 && cellWidth > 0) {
        rules.push(
          `${rowSelector} > *:nth-child(${cellIndex + 1}){width:${Math.round(cellWidth)}px !important;max-width:0 !important;min-width:0 !important;overflow-wrap:anywhere !important;word-break:break-word !important;${cellHeightRule}box-sizing:border-box !important;}`
        )
      }

      columnIndex += colSpan
    })
  })

  return {
    layout: fittedLayout,
    css: rules.join('\n'),
  }
}

const updateEditorTableLayoutStyles = () => {
  const tableElements = getEditorLayoutTableElements()
  const nextLayouts = [...tableLayoutMetadata]
  const cssRules = []

  syncEditorTableLayoutTargets(tableElements)

  tableElements.forEach((tableElement, tableIndex) => {
    const layout = tableLayoutMetadata[tableIndex]
    if (!layout) {
      return
    }

    const result = buildEditorTableLayoutCss(tableElement, tableIndex, layout)
    nextLayouts[tableIndex] = result.layout
    if (result.layout) {
      applyEditorTableLayoutToDom(tableElement, result.layout)
    }
    if (result.css) {
      cssRules.push(result.css)
    }
  })

  tableLayoutMetadata = trimTableLayoutMetadata(nextLayouts)

  if (!cssRules.length) {
    if (tableLayoutStyleElement) {
      tableLayoutStyleElement.textContent = ''
    }
    return
  }

  ensureTableLayoutStyleElement().textContent = cssRules.join('\n')
}

const applyStoredTableLayoutsToEditor = () => {
  updateEditorTableLayoutStyles()
}

const getCurrentMarkdownWithTableLayouts = () => {
  if (!editorInstance) {
    return currentMarkdown.value || ''
  }

  updateEditorTableLayoutStyles()
  return serializeMarkdownWithTableLayouts(editorInstance.getMarkdown(), tableLayoutMetadata)
}

const setEditorMarkdownFromStoredContent = (markdownContent = '') => {
  const parsed = extractTableLayoutMetadata(markdownContent)
  tableLayoutMetadata = parsed.layouts

  if (editorInstance) {
    editorInstance.setMarkdown(parsed.markdown)
    nextTick(() => {
      applyStoredTableLayoutsToEditor()
      updatePreviewFromEditor()
    })
  }

  return parsed.markdown
}

const isMultiCellSelectionActive = () => {
  const selection = getWysiwygView()?.state?.selection
  return Boolean(selection?.isCellSelection && (selection.ranges?.length || 0) > 1)
}

const removeNativeTableCellVisualSelectionClasses = () => {
  nativeSelectedTableCellElements.forEach((cellElement) => {
    cellElement.classList.remove('moonbird-native-cell-selected')
  })
  nativeSelectedTableCellElements = new Set()
  hideTableSelectionOverlay()

  if (nativeTableCellSelectionStyleElement) {
    nativeTableCellSelectionStyleElement.textContent = ''
  }
}

const applyNativeTableCellVisualStyle = (cellElement) => {
  cellElement.classList.add('moonbird-native-cell-selected')
}

const isNativeTableCellVisuallySelected = (cellElement) =>
  cellElement.classList.contains('moonbird-native-cell-selected') ||
  window.getComputedStyle(cellElement).backgroundColor === 'rgba(147, 197, 253, 0.22)'

const ensureNativeTableCellSelectionStyleElement = () => {
  if (!nativeTableCellSelectionStyleElement) {
    nativeTableCellSelectionStyleElement = document.createElement('style')
    nativeTableCellSelectionStyleElement.setAttribute('data-moonbird-table-selection', 'true')
    document.head.appendChild(nativeTableCellSelectionStyleElement)
  }

  return nativeTableCellSelectionStyleElement
}

const hideTableSelectionOverlay = () => {
  tableSelectionOverlay.visible = false
  tableSelectionOverlay.top = -9999
  tableSelectionOverlay.left = -9999
  tableSelectionOverlay.width = 0
  tableSelectionOverlay.height = 0
}

const updateTableSelectionOverlay = (selectedCells) => {
  if (!Array.isArray(selectedCells) || selectedCells.length < 2) {
    hideTableSelectionOverlay()
    return
  }

  const rect = getElementsBoundingRect(selectedCells)
  if (!rect || !isRectInViewport(rect)) {
    hideTableSelectionOverlay()
    return
  }

  const inset = 2
  tableSelectionOverlay.top = Math.max(0, rect.top - inset)
  tableSelectionOverlay.left = Math.max(0, rect.left - inset)
  tableSelectionOverlay.width = rect.width + inset * 2
  tableSelectionOverlay.height = rect.height + inset * 2
  tableSelectionOverlay.visible = true
}

const refreshTableSelectionOverlay = () => {
  const selectedCells = Array.from(nativeSelectedTableCellElements).filter(
    (cellElement) => cellElement.isConnected && editorRoot.value?.contains(cellElement)
  )

  if (selectedCells.length > 1) {
    updateTableSelectionOverlay(selectedCells)
    return
  }

  if (nativeTableCellSelectionRect) {
    updateTableSelectionOverlay(getTableCellsFromSelectionRect(nativeTableCellSelectionRect))
    return
  }

  hideTableSelectionOverlay()
}

const ensureEditorRootSelectionId = () => {
  if (!editorRoot.value) {
    return ''
  }

  if (!editorRoot.value.dataset.moonbirdEditorId) {
    editorRootIdSeed += 1
    editorRoot.value.dataset.moonbirdEditorId = `moonbird-editor-${Date.now()}-${editorRootIdSeed}`
  }

  return editorRoot.value.dataset.moonbirdEditorId
}

const getElementPathFromEditorRoot = (element) => {
  const rootElement = editorRoot.value
  const parts = []
  let current = element

  while (current && current !== rootElement) {
    const parent = current.parentElement
    if (!parent) {
      return ''
    }

    const tagName = current.tagName.toLowerCase()
    const index =
      Array.from(parent.children).filter((sibling) => sibling.tagName === current.tagName).indexOf(current) + 1

    parts.unshift(`${tagName}:nth-of-type(${index})`)
    current = parent
  }

  return current === rootElement ? parts.join(' > ') : ''
}

const renderNativeTableCellSelectionStyle = (selectedCells) => {
  const editorId = ensureEditorRootSelectionId()
  const styleElement = ensureNativeTableCellSelectionStyleElement()

  if (!editorId || selectedCells.length < 2) {
    styleElement.textContent = ''
    return
  }

  const selectors = selectedCells
    .map((cellElement) => getElementPathFromEditorRoot(cellElement))
    .filter(Boolean)
    .map((path) => `[data-moonbird-editor-id="${editorId}"] > ${path}`)

  styleElement.textContent = selectors.length
    ? `${selectors.join(',\n')} {
  background-color: rgba(147, 197, 253, 0.22) !important;
  border-color: rgba(37, 99, 235, 0.44) !important;
  box-shadow: inset 0 0 0 9999px rgba(147, 197, 253, 0.18), inset 0 0 0 1px rgba(37, 99, 235, 0.34) !important;
  caret-color: transparent !important;
}
${selectors.map((selector) => `${selector} > *`).join(',\n')} {
  background: transparent !important;
}`
    : ''

  updateTableSelectionOverlay(selectedCells)
}

const clearNativeTableCellVisualSelection = () => {
  removeNativeTableCellVisualSelectionClasses()
  nativeTableCellSelectionRect = null
  tableMultiCellSelectionActive.value = isMultiCellSelectionActive()
}

const isNodeInsideEditor = (node) => {
  const element = node instanceof Element ? node : node?.parentElement
  return Boolean(element && editorRoot.value?.contains(element))
}

const doRectsIntersect = (rectA, rectB) =>
  rectA.left < rectB.right &&
  rectA.right > rectB.left &&
  rectA.top < rectB.bottom &&
  rectA.bottom > rectB.top

const getDomTableCellPosition = (cellElement) => {
  const tableElement = cellElement?.closest?.('table')
  const rowElement = cellElement?.closest?.('tr')

  if (!tableElement || !rowElement) {
    return null
  }

  const rowIndex = Array.from(tableElement.rows).indexOf(rowElement)
  const columnIndex = Array.from(rowElement.cells).indexOf(cellElement)

  if (rowIndex < 0 || columnIndex < 0) {
    return null
  }

  return {
    tableElement,
    tableIndex: getEditorTableElements().indexOf(tableElement),
    rowIndex,
    columnIndex,
  }
}

const getEditorTableElements = () => {
  const wysiwygTableElements = Array.from(
    editorRoot.value?.querySelectorAll('.toastui-editor-ww-container .toastui-editor-contents table') || []
  )

  if (wysiwygTableElements.length) {
    return wysiwygTableElements
  }

  return Array.from(editorRoot.value?.querySelectorAll('.toastui-editor-contents table') || [])
}

const getVisibleEditorTableElements = () =>
  getEditorTableElements().filter((tableElement) => {
    const rect = tableElement.getBoundingClientRect()
    return rect.width > 0 && rect.height > 0
  })

const getEditorLayoutTableElements = () => {
  const visibleTableElements = getVisibleEditorTableElements()
  return visibleTableElements.length ? visibleTableElements : getEditorTableElements()
}

const getEditorContentsElements = () =>
  Array.from(editorRoot.value?.querySelectorAll('.toastui-editor-contents') || [])

const buildTableCellSelectionRect = (anchorPosition, focusPosition) => {
  if (
    !anchorPosition ||
    !focusPosition ||
    anchorPosition.tableIndex < 0 ||
    focusPosition.tableIndex < 0 ||
    anchorPosition.tableIndex !== focusPosition.tableIndex
  ) {
    return null
  }

  return {
    tableIndex: anchorPosition.tableIndex,
    minRow: Math.min(anchorPosition.rowIndex, focusPosition.rowIndex),
    maxRow: Math.max(anchorPosition.rowIndex, focusPosition.rowIndex),
    minColumn: Math.min(anchorPosition.columnIndex, focusPosition.columnIndex),
    maxColumn: Math.max(anchorPosition.columnIndex, focusPosition.columnIndex),
  }
}

const getTableCellsFromSelectionRect = (selectionRect) => {
  if (!selectionRect) {
    return []
  }

  const tableElement = getEditorTableElements()[selectionRect.tableIndex]
  if (!tableElement) {
    return []
  }

  const selectedCells = []

  for (let rowIndex = selectionRect.minRow; rowIndex <= selectionRect.maxRow; rowIndex += 1) {
    const rowElement = tableElement.rows[rowIndex]
    for (let columnIndex = selectionRect.minColumn; columnIndex <= selectionRect.maxColumn; columnIndex += 1) {
      const cellElement = rowElement?.cells?.[columnIndex]
      if (cellElement) {
        selectedCells.push(cellElement)
      }
    }
  }

  return selectedCells
}

const markNativeTableCellVisualSelection = (selectedCells, selectionRect = nativeTableCellSelectionRect) => {
  removeNativeTableCellVisualSelectionClasses()

  if (selectedCells.length < 2) {
    return false
  }

  selectedCells.forEach((cellElement) => {
    applyNativeTableCellVisualStyle(cellElement)
    nativeSelectedTableCellElements.add(cellElement)
  })

  renderNativeTableCellSelectionStyle(selectedCells)
  nativeTableCellSelectionRect = selectionRect
  tableMultiCellSelectionActive.value = true
  return true
}

const reapplyStoredNativeTableCellVisualSelection = () => {
  if (!nativeTableCellSelectionRect) {
    return false
  }

  return markNativeTableCellVisualSelection(
    getTableCellsFromSelectionRect(nativeTableCellSelectionRect),
    nativeTableCellSelectionRect
  )
}

const expandTableCellsToRect = (cellElements) => {
  const tableSelections = new Map()

  cellElements.forEach((cellElement) => {
    const position = getDomTableCellPosition(cellElement)
    if (!position) {
      return
    }

    const selectionInfo = tableSelections.get(position.tableElement) || {
      minRow: position.rowIndex,
      maxRow: position.rowIndex,
      minColumn: position.columnIndex,
      maxColumn: position.columnIndex,
    }

    selectionInfo.minRow = Math.min(selectionInfo.minRow, position.rowIndex)
    selectionInfo.maxRow = Math.max(selectionInfo.maxRow, position.rowIndex)
    selectionInfo.minColumn = Math.min(selectionInfo.minColumn, position.columnIndex)
    selectionInfo.maxColumn = Math.max(selectionInfo.maxColumn, position.columnIndex)
    tableSelections.set(position.tableElement, selectionInfo)
  })

  const expandedCells = []

  tableSelections.forEach((selectionInfo, tableElement) => {
    for (let rowIndex = selectionInfo.minRow; rowIndex <= selectionInfo.maxRow; rowIndex += 1) {
      const rowElement = tableElement.rows[rowIndex]
      for (let columnIndex = selectionInfo.minColumn; columnIndex <= selectionInfo.maxColumn; columnIndex += 1) {
        const cellElement = rowElement?.cells?.[columnIndex]
        if (cellElement) {
          expandedCells.push(cellElement)
        }
      }
    }
  })

  return expandedCells
}

const applyTableCellRectVisualSelection = (anchorCell, focusCell) => {
  const anchorPosition = anchorCell?.tableIndex >= 0 ? anchorCell : getDomTableCellPosition(anchorCell)
  const focusPosition = focusCell?.tableIndex >= 0 ? focusCell : getDomTableCellPosition(focusCell)
  const selectionRect = buildTableCellSelectionRect(anchorPosition, focusPosition)

  if (!selectionRect) {
    return false
  }

  return markNativeTableCellVisualSelection(getTableCellsFromSelectionRect(selectionRect), selectionRect)
}

const getTableCellFromPoint = (x, y) => {
  const elements = document.elementsFromPoint?.(x, y) || []

  for (const element of elements) {
    const cellElement = element.closest?.('td, th')
    if (cellElement && editorRoot.value?.contains(cellElement)) {
      return cellElement
    }
  }

  return null
}

const isElementInsideEditorContents = (element, editorContents = null) => {
  const editorContentElements = Array.isArray(editorContents)
    ? editorContents
    : editorContents
      ? [editorContents]
      : getEditorContentsElements()

  return editorContentElements.some((editorContentElement) => editorContentElement.contains(element))
}

const getTableCellFromEvent = (event, editorContents) => {
  if (Number.isFinite(event.clientX) && Number.isFinite(event.clientY)) {
    const pointCell = getTableCellFromPoint(event.clientX, event.clientY)
    if (pointCell && isElementInsideEditorContents(pointCell, editorContents)) {
      return pointCell
    }
  }

  const target = event.target instanceof Element ? event.target : null
  const targetCell = target?.closest?.('td, th')

  if (targetCell && isElementInsideEditorContents(targetCell, editorContents)) {
    return targetCell
  }

  return null
}

const getTableElementFromPoint = (x, y) => {
  const elements = document.elementsFromPoint?.(x, y) || []

  for (const element of elements) {
    if (!(element instanceof Element)) {
      continue
    }

    if (element.closest?.('.table-resize-handle, .table-action-panel, .table-hover-control')) {
      return null
    }

    const tableElement = element.closest?.('.toastui-editor-contents table')
    if (tableElement && editorRoot.value?.contains(tableElement)) {
      return tableElement
    }
  }

  return null
}

const getTableElementNearPoint = (x, y, tolerance = 8) =>
  getEditorTableElements().find((tableElement) => {
    const rect = tableElement.getBoundingClientRect()
    return (
      y >= rect.top - tolerance &&
      y <= rect.bottom + tolerance &&
      x >= rect.left - tolerance &&
      x <= rect.right + tolerance
    )
  }) || null

const isTableResizeIgnoredElement = (element) =>
  Boolean(
    element?.closest?.(
      '.table-action-panel, .table-hover-control, .floating-toolbar, .editor-side-toolbar, .side-table-picker-popover'
    )
  )

const getTableResizeHitInfo = (event, allowPressedPointer = false) => {
  const eventTarget = event.target instanceof Element ? event.target : null
  if (isTableResizeIgnoredElement(eventTarget)) {
    return null
  }

  if (
    tableResizeHandleDragging.value ||
    (!allowPressedPointer && event.buttons > 0) ||
    !Number.isFinite(event.clientX) ||
    !Number.isFinite(event.clientY)
  ) {
    return null
  }

  const pointerElement = document.elementFromPoint(event.clientX, event.clientY)
  if (isTableResizeIgnoredElement(pointerElement)) {
    return null
  }

  if (
    tableResizeHandleVisible.value &&
    pointerElement?.closest?.('.table-resize-handle') &&
    tableResizeHandleTableElement &&
    (tableResizeHandle.kind === 'table' ||
      tableResizeHandle.kind === 'table-height' ||
      tableResizeHandle.columnIndex >= 0)
  ) {
    return {
      kind: tableResizeHandle.kind,
      tableElement: tableResizeHandleTableElement,
      columnIndex: tableResizeHandle.columnIndex,
      rowIndex: tableResizeHandle.rowIndex,
      left: tableResizeHandle.left,
      top: tableResizeHandle.top,
      width: tableResizeHandle.width,
      height: tableResizeHandle.height,
    }
  }

  const tableEdgeTolerance = 24
  const columnEdgeTolerance = 9
  const tableElement =
    getTableElementFromPoint(event.clientX, event.clientY) ||
    getTableElementNearPoint(event.clientX, event.clientY, tableEdgeTolerance)
  if (!tableElement) {
    return null
  }

  const tableRect = tableElement.getBoundingClientRect()
  const columnCount = getTableColumnCount(tableElement)
  const rowCount = getTableRowCount(tableElement)
  if (
    columnCount < 1 ||
    rowCount < 1 ||
    event.clientY < tableRect.top - tableEdgeTolerance ||
    event.clientY > tableRect.bottom + tableEdgeTolerance ||
    event.clientX < tableRect.left - tableEdgeTolerance ||
    event.clientX > tableRect.right + tableEdgeTolerance
  ) {
    return null
  }

  const isNearRightEdge =
    Math.abs(event.clientX - tableRect.right) <= tableEdgeTolerance &&
    event.clientY >= tableRect.top - tableEdgeTolerance &&
    event.clientY <= tableRect.bottom + tableEdgeTolerance
  const isNearBottomEdge =
    Math.abs(event.clientY - tableRect.bottom) <= tableEdgeTolerance &&
    event.clientX >= tableRect.left - tableEdgeTolerance &&
    event.clientX <= tableRect.right + tableEdgeTolerance

  if (isNearRightEdge) {
    return {
      kind: 'table',
      tableElement,
      columnIndex: columnCount - 1,
      left: tableRect.right,
      top: tableRect.top,
      width: 22,
      height: tableRect.height,
    }
  }

  const rowEdgeTolerance = 10
  const rowBoundaries = getTableRowBoundaryPositions(tableElement)
  for (let rowIndex = 0; rowIndex < rowBoundaries.length; rowIndex += 1) {
    const boundaryTop = rowBoundaries[rowIndex]
    if (
      Number.isFinite(boundaryTop) &&
      Math.abs(event.clientY - boundaryTop) <= rowEdgeTolerance &&
      event.clientX >= tableRect.left - columnEdgeTolerance &&
      event.clientX <= tableRect.right + columnEdgeTolerance
    ) {
      return {
        kind: 'row',
        tableElement,
        columnIndex: -1,
        rowIndex,
        left: tableRect.left,
        top: boundaryTop,
        width: tableRect.width,
        height: 18,
      }
    }
  }

  if (isNearBottomEdge) {
    return {
      kind: 'table-height',
      tableElement,
      columnIndex: -1,
      rowIndex: -1,
      left: tableRect.left,
      top: tableRect.bottom,
      width: tableRect.width,
      height: 22,
    }
  }

  const columnBoundaries = getTableColumnBoundaryPositions(tableElement)
  for (let boundaryIndex = 0; boundaryIndex < columnBoundaries.length; boundaryIndex += 1) {
    const boundaryLeft = columnBoundaries[boundaryIndex]
    if (Number.isFinite(boundaryLeft) && Math.abs(event.clientX - boundaryLeft) <= columnEdgeTolerance) {
      return {
        kind: 'column',
        tableElement,
        columnIndex: boundaryIndex,
        rowIndex: -1,
        left: boundaryLeft,
        top: tableRect.top,
        width: 18,
        height: tableRect.height,
      }
    }
  }

  return null
}

const showTableResizeHandle = (hitInfo) => {
  if (hasActiveEditorTextSelection()) {
    hideTableResizeHandle()
    return
  }

  tableResizeHandleTableElement = hitInfo.tableElement
  tableResizeHandleVisible.value = true
  tableResizeHandle.kind = hitInfo.kind
  tableResizeHandle.columnIndex = hitInfo.columnIndex
  tableResizeHandle.rowIndex = Number.isInteger(hitInfo.rowIndex) ? hitInfo.rowIndex : -1
  tableResizeHandle.top = Math.max(0, hitInfo.top)
  tableResizeHandle.left = hitInfo.left
  tableResizeHandle.width = Math.max(14, hitInfo.width || 14)
  tableResizeHandle.height =
    hitInfo.kind === 'table-height' || hitInfo.kind === 'row'
      ? Math.max(14, hitInfo.height || 14)
      : Math.max(28, hitInfo.height)
}

const updateTableResizeHandle = (event) => {
  if (tableResizeHandleDragging.value) {
    return
  }

  if (event.buttons > 0) {
    hideTableResizeHandle()
    return
  }

  if (hasActiveEditorTextSelection()) {
    hideTableResizeHandle()
    return
  }

  const target = event.target instanceof Element ? event.target : null
  if (isTableResizeIgnoredElement(target)) {
    hideTableResizeHandle()
    return
  }

  const hitInfo = getTableResizeHitInfo(event)
  if (!hitInfo) {
    hideTableResizeHandle()
    return
  }

  hideHoverBlockHint()
  showTableResizeHandle(hitInfo)
}

const getEditorContentsWidthForTable = (tableElement) => {
  const contentsElement = tableElement?.closest?.('.toastui-editor-contents')
  return contentsElement?.getBoundingClientRect().width || tableElement?.getBoundingClientRect().width || 0
}

const getDefaultTableColumnWidth = (tableElement = null) =>
  Math.max(
    MIN_TABLE_COLUMN_WIDTH,
    Math.floor((getAvailableTableWidth(tableElement) || getEditorContentsWidthForTable(tableElement) || MAX_TABLE_COLUMN_COUNT * MIN_TABLE_COLUMN_WIDTH) / MAX_TABLE_COLUMN_COUNT)
  )

const getDefaultTableRowHeight = () => MIN_TABLE_ROW_HEIGHT

const createDefaultTableLayout = (tableElement, rowCount, columnCount) => {
  const columnWidth = getDefaultTableColumnWidth(tableElement)
  const rowHeight = getDefaultTableRowHeight(tableElement)
  const columns = Array.from({ length: columnCount }, () => columnWidth)
  const rows = Array.from({ length: rowCount }, () => rowHeight)

  return {
    width: columns.reduce((sum, width) => sum + width, 0),
    columns,
    align: 'left',
    height: rows.reduce((sum, height) => sum + height, 0),
    rows,
  }
}

const getTableLayoutForMutation = (tableInfo) => {
  const view = getWysiwygView()
  const tableIndex = view ? getTableIndexFromTablePos(view, tableInfo?.tablePos) : -1
  const tableElement = tableIndex >= 0 ? getEditorLayoutTableElements()[tableIndex] : null
  const rowCount = tableInfo?.rowCount || getTableRowCount(tableElement)
  const columnCount = tableInfo?.columnCount || getTableColumnCount(tableElement)
  const fallbackLayout = createDefaultTableLayout(tableElement, rowCount, columnCount)
  const normalizedLayout = normalizeTableLayout(
    tableIndex >= 0 && tableLayoutMetadata[tableIndex] ? tableLayoutMetadata[tableIndex] : fallbackLayout,
    columnCount,
    fallbackLayout.width,
    rowCount,
    fallbackLayout.height
  )
  const layout = normalizedLayout || fallbackLayout
  if (!layout.rows?.length) {
    layout.rows = fallbackLayout.rows
    layout.height = fallbackLayout.height
  }

  return {
    tableIndex,
    tableElement,
    layout,
  }
}

const sumLayoutSizes = (sizes = []) => sizes.reduce((sum, size) => sum + size, 0)

const applyActiveTableAlignment = (align = 'left') => {
  const tableInfo = getFreshActiveTableInfo()
  if (!tableInfo) {
    return
  }

  const { tableIndex, tableElement, layout } = getTableLayoutForMutation(tableInfo)
  if (tableIndex < 0) {
    return
  }

  const nextLayouts = [...tableLayoutMetadata]
  while (nextLayouts.length <= tableIndex) {
    nextLayouts.push(null)
  }
  nextLayouts[tableIndex] = {
    ...layout,
    align,
  }
  tableLayoutMetadata = trimTableLayoutMetadata(nextLayouts)
  tableAlignmentRevision.value += 1
  applyTableAlignment(tableElement, align)
  updateEditorTableLayoutStyles()
  updatePreviewFromEditor()
}

const getTableColumnBoundaryPositions = (tableElement) => {
  const columnCount = getTableColumnCount(tableElement)
  if (!tableElement || columnCount < 2) {
    return []
  }

  const boundaryGroups = Array.from({ length: columnCount - 1 }, () => [])

  Array.from(tableElement.rows || []).forEach((rowElement) => {
    let columnIndex = 0

    Array.from(rowElement.cells || []).forEach((cellElement) => {
      if (cellElement.hasAttribute('extended')) {
        return
      }

      const span = getDomTableCellSpan(cellElement, 'colspan')
      const rect = cellElement.getBoundingClientRect()
      const widthPerColumn = rect.width / span

      if (rect.width > 0 && Number.isFinite(widthPerColumn)) {
        for (let offset = 0; offset < span; offset += 1) {
          const boundaryIndex = columnIndex + offset
          if (boundaryIndex < columnCount - 1) {
            boundaryGroups[boundaryIndex].push(rect.left + widthPerColumn * (offset + 1))
          }
        }
      }

      columnIndex += span
    })
  })

  return boundaryGroups.map((positions) => {
    if (!positions.length) {
      return null
    }

    const sortedPositions = [...positions].sort((left, right) => left - right)
    return sortedPositions[Math.floor(sortedPositions.length / 2)]
  })
}

const getTableRowBoundaryPositions = (tableElement) =>
  Array.from(tableElement?.rows || []).map((rowElement) => rowElement.getBoundingClientRect().bottom)

const normalizeResizeColumns = (columns, totalWidth, minColumnWidth = MIN_TABLE_COLUMN_WIDTH) => {
  const safeMinColumnWidth = Math.max(0, Math.round(minColumnWidth))
  const safeTotalWidth = Math.max(Math.round(totalWidth), safeMinColumnWidth * columns.length)
  const currentColumns = columns.map((width) => Math.max(Math.round(width), safeMinColumnWidth))
  const flexibleWidths = currentColumns.map((width) => Math.max(width - safeMinColumnWidth, 0))
  const flexibleTotal = flexibleWidths.reduce((sum, width) => sum + width, 0)
  const extraWidth = safeTotalWidth - safeMinColumnWidth * currentColumns.length

  if (!currentColumns.length) {
    return Array.from({ length: columns.length }, () => safeMinColumnWidth)
  }

  const safeColumns = currentColumns.map((width, index) =>
    safeMinColumnWidth + Math.round(flexibleTotal ? (flexibleWidths[index] / flexibleTotal) * extraWidth : extraWidth / currentColumns.length)
  )
  let diff = safeTotalWidth - safeColumns.reduce((sum, width) => sum + width, 0)
  for (let index = safeColumns.length - 1; index >= 0 && diff !== 0; index -= 1) {
    if (diff > 0) {
      safeColumns[index] += diff
      diff = 0
    } else {
      const reducibleWidth = Math.min(safeColumns[index] - safeMinColumnWidth, Math.abs(diff))
      safeColumns[index] -= reducibleWidth
      diff += reducibleWidth
    }
  }
  return safeColumns
}

const normalizeResizeRows = (rows, totalHeight) => {
  const safeRows = rows.map((height) => Math.max(Math.round(height), MIN_TABLE_ROW_HEIGHT))
  const currentTotal = safeRows.reduce((sum, height) => sum + height, 0)

  if (!currentTotal || Math.abs(currentTotal - totalHeight) < 1) {
    return safeRows
  }

  const diff = Math.round(totalHeight - currentTotal)
  safeRows[safeRows.length - 1] = Math.max(
    MIN_TABLE_ROW_HEIGHT,
    safeRows[safeRows.length - 1] + diff
  )
  return safeRows
}

const setEditorTableLayoutMetadata = (tableElement, tableIndex, layout) => {
  const resolvedTableIndex =
    Number.isInteger(tableIndex) && tableIndex >= 0
      ? tableIndex
      : getEditorLayoutTableElements().indexOf(tableElement)
  const columnCount = getTableColumnCount(tableElement)
  const rowCount = getTableRowCount(tableElement)
  const normalizedLayout = normalizeTableLayout(
    {
      ...layout,
      align: layout?.align || tableLayoutMetadata[resolvedTableIndex]?.align || 'left',
    },
    columnCount,
    tableElement?.getBoundingClientRect?.().width,
    rowCount,
    tableElement?.getBoundingClientRect?.().height
  )

  if (resolvedTableIndex < 0 || !normalizedLayout) {
    return null
  }

  const fittedLayout = fitTableLayoutToMaxWidth(normalizedLayout, getAvailableTableWidth(tableElement))
  const nextLayouts = [...tableLayoutMetadata]
  while (nextLayouts.length <= resolvedTableIndex) {
    nextLayouts.push(null)
  }
  nextLayouts[resolvedTableIndex] = fittedLayout
  tableLayoutMetadata = trimTableLayoutMetadata(nextLayouts)
  updateEditorTableLayoutStyles()
  return fittedLayout
}

const clearEditorTableLayoutDom = (tableElement) => {
  if (!tableElement) {
    return
  }

  Array.from(tableElement.children || [])
    .filter((element) => element.tagName === 'COLGROUP')
    .forEach((element) => element.remove())

  tableElement.style.width = ''
  tableElement.style.maxWidth = ''
  tableElement.style.minWidth = ''
  tableElement.style.inlineSize = ''
  tableElement.style.maxInlineSize = ''
  tableElement.style.minInlineSize = ''
  tableElement.style.height = ''
  tableElement.style.minHeight = ''
  tableElement.style.tableLayout = ''
  tableElement.style.boxSizing = ''
  tableElement.style.overflow = ''
  tableElement.style.marginLeft = ''
  tableElement.style.marginRight = ''
  delete tableElement.dataset.moonbirdLayoutCustomized

  Array.from(tableElement.rows || []).forEach((rowElement) => {
    rowElement.style.height = ''
    rowElement.style.boxSizing = ''

    Array.from(rowElement.cells || []).forEach((cellElement) => {
      cellElement.style.width = ''
      cellElement.style.maxWidth = ''
      cellElement.style.minWidth = ''
      cellElement.style.height = ''
      cellElement.style.boxSizing = ''
      cellElement.style.overflowWrap = ''
      cellElement.style.wordBreak = ''
    })
  })
}

const getTableIndexFromTablePos = (view, tablePos) => {
  if (!view || !Number.isInteger(tablePos)) {
    return -1
  }

  let tableIndex = -1
  let resolvedIndex = -1

  view.state.doc.descendants((node, pos) => {
    if (node.type?.name !== 'table') {
      return true
    }

    tableIndex += 1
    if (pos === tablePos) {
      resolvedIndex = tableIndex
      return false
    }

    return true
  })

  return resolvedIndex
}

const resetActiveTableLayout = () => {
  const view = getWysiwygView()
  const tableInfo = getFreshActiveTableInfo()
  if (!view || !tableInfo) {
    return
  }

  const tableIndex = getTableIndexFromTablePos(view, tableInfo.tablePos)
  if (tableIndex < 0) {
    return
  }

  const resolvedTableElement = getEditorLayoutTableElements()[tableIndex] || getEditorTableElements()[tableIndex]
  const rowCount = tableInfo.rowCount || getTableRowCount(resolvedTableElement)
  const columnCount = tableInfo.columnCount || getTableColumnCount(resolvedTableElement)
  const currentLayout = tableLayoutMetadata[tableIndex] || null
  const defaultLayout = {
    ...createDefaultTableLayout(resolvedTableElement, rowCount, columnCount),
    align: currentLayout?.align || activeTableAlignment.value || 'left',
  }
  const nextLayouts = [...tableLayoutMetadata]
  nextLayouts[tableIndex] = defaultLayout
  tableLayoutMetadata = trimTableLayoutMetadata(nextLayouts)
  updateEditorTableLayoutStyles()
  updatePreviewFromEditor()
  hideTableResizeHandle()
  ElMessage.success('已恢复默认宽高')
}

const updateTableResizeDragState = (dragState, clientX, clientY) => {
  if (!dragState?.tableElement) {
    return
  }

  const {
    tableElement,
    tableIndex,
    kind,
    startX,
    startY,
    startWidth,
    startHeight,
    maxWidth,
    minWidth,
    minColumnWidth,
    minHeight,
    columnIndex,
    rowIndex,
    startColumns,
    startRows,
  } = dragState
  const resolvedTableIndex =
    Number.isInteger(tableIndex) && tableIndex >= 0
      ? tableIndex
      : getEditorLayoutTableElements().indexOf(tableElement)
  const delta = clientX - startX
  const deltaY = clientY - startY
  let nextWidth = startWidth
  let nextColumns = [...startColumns]
  let nextHeight = startRows.length ? startHeight : null
  let nextRows = [...startRows]

  if (kind === 'table') {
    nextWidth = Math.min(Math.max(startWidth + delta, minWidth), maxWidth)
    const scale = nextWidth / startWidth
    nextColumns = normalizeResizeColumns(startColumns.map((width) => width * scale), nextWidth, minColumnWidth)
  } else if (kind === 'table-height') {
    nextHeight = Math.max(startHeight + deltaY, minHeight)
    const scale = nextHeight / startHeight
    nextRows = normalizeResizeRows(startRows.map((height) => height * scale), nextHeight)
  } else if (kind === 'row') {
    const currentRowHeight = startRows[rowIndex]
    if (!Number.isFinite(currentRowHeight)) {
      return
    }

    const safeDeltaY = Math.max(deltaY, MIN_TABLE_ROW_HEIGHT - currentRowHeight)
    nextRows[rowIndex] = Math.round(currentRowHeight + safeDeltaY)
    nextHeight = nextRows.reduce((sum, height) => sum + height, 0)
    nextRows = normalizeResizeRows(nextRows, nextHeight)
  } else {
    const leftWidth = startColumns[columnIndex]
    const rightWidth = startColumns[columnIndex + 1]
    const safeDelta = Math.min(
      Math.max(delta, minColumnWidth - leftWidth),
      rightWidth - minColumnWidth
    )

    nextColumns[columnIndex] = Math.round(leftWidth + safeDelta)
    nextColumns[columnIndex + 1] = Math.round(rightWidth - safeDelta)
    nextWidth = startWidth
  }

  const nextLayout = {
    width: nextWidth,
    columns: nextColumns,
  }
  if (nextRows.length && nextHeight) {
    nextLayout.height = nextHeight
    nextLayout.rows = nextRows
  }

  const normalizedLayout = normalizeTableLayout(
    nextLayout,
    getTableColumnCount(tableElement),
    nextWidth,
    getTableRowCount(tableElement),
    nextHeight || tableElement.getBoundingClientRect().height
  )

  if (!normalizedLayout) {
    return
  }

  const appliedLayout = setEditorTableLayoutMetadata(tableElement, resolvedTableIndex, normalizedLayout)
  if (!appliedLayout) {
    return
  }

  const currentTableElement = getEditorLayoutTableElements()[resolvedTableIndex] || tableElement
  tableResizeHandleTableElement = currentTableElement
  const tableRect = currentTableElement.getBoundingClientRect()
  const columnBoundaryLeft = getTableColumnBoundaryPositions(currentTableElement)[columnIndex]
  const rowBoundaryTop = getTableRowBoundaryPositions(currentTableElement)[rowIndex]
  const handleLeft =
    kind === 'table-height' || kind === 'row'
      ? tableRect.left
      : kind === 'table'
      ? tableRect.right
      : Number.isFinite(columnBoundaryLeft)
      ? columnBoundaryLeft
      : tableResizeHandle.left

  tableResizeHandle.left = handleLeft
  tableResizeHandle.top =
    kind === 'table-height'
      ? tableRect.bottom
      : kind === 'row' && Number.isFinite(rowBoundaryTop)
      ? rowBoundaryTop
      : tableRect.top
  tableResizeHandle.width = kind === 'table-height' || kind === 'row' ? tableRect.width : 14
  tableResizeHandle.height = kind === 'table-height' || kind === 'row' ? 14 : tableRect.height

  const hintText =
    kind === 'table'
      ? `${Math.round(appliedLayout.width)}px`
      : kind === 'table-height'
      ? `${Math.round(appliedLayout.height || nextHeight || tableRect.height)}px`
      : kind === 'row'
      ? `${Math.round(appliedLayout.rows?.[rowIndex] || nextRows[rowIndex] || tableRect.height)}px`
      : `${Math.round(appliedLayout.columns?.[columnIndex] || nextColumns[columnIndex])}px / ${Math.round(
          appliedLayout.columns?.[columnIndex + 1] || nextColumns[columnIndex + 1]
        )}px`

  showTableResizeSizeHint(
    hintText,
    {
      left: tableResizeHandle.left,
      top: tableResizeHandle.top,
      width: tableResizeHandle.width,
      height: tableResizeHandle.height,
    },
    kind
  )
}

const stopTableResizeDrag = () => {
  const dragState = tableResizeDragState

  if (!tableResizeHandleDragging.value && !dragState) {
    return
  }

  tableResizeHandleDragging.value = false
  hideTableResizeSizeHint()
  if (dragState?.moveListener) {
    window.removeEventListener('mousemove', dragState.moveListener, true)
  }
  if (dragState?.endListener) {
    window.removeEventListener('mouseup', dragState.endListener, true)
  }
  tableResizeDragState = null
  updateEditorTableLayoutStyles()
  currentMarkdown.value = getCurrentMarkdownWithTableLayouts()
}

const startTableResizeDrag = (event, resizeInfo = null) => {
  event?.preventDefault?.()
  event?.stopPropagation?.()

  const tableElement = resizeInfo?.tableElement || tableResizeHandleTableElement
  const resizeKind = resizeInfo?.kind || tableResizeHandle.kind
  const resizeColumnIndex = Number.isInteger(resizeInfo?.columnIndex)
    ? resizeInfo.columnIndex
    : tableResizeHandle.columnIndex
  const resizeRowIndex = Number.isInteger(resizeInfo?.rowIndex)
    ? resizeInfo.rowIndex
    : tableResizeHandle.rowIndex
  const columnCount = getTableColumnCount(tableElement)
  const rowCount = getTableRowCount(tableElement)
  if (!tableElement || columnCount < 1) {
    hideTableResizeHandle()
    return
  }

  if (
    resizeKind === 'column' &&
    (resizeColumnIndex < 0 || resizeColumnIndex >= columnCount - 1)
  ) {
    hideTableResizeHandle()
    return
  }

  if (resizeKind === 'row' && (resizeRowIndex < 0 || resizeRowIndex >= rowCount)) {
    hideTableResizeHandle()
    return
  }

  const editorContentsWidth = Math.round(getEditorContentsWidthForTable(tableElement))
  const maxWidth = Math.max(1, editorContentsWidth || Math.round(getAvailableTableWidth(tableElement)) || 1)
  const minColumnWidth = Math.max(
    0,
    Math.min(MIN_TABLE_COLUMN_WIDTH, Math.floor(maxWidth / columnCount))
  )
  const minWidth = Math.min(columnCount * minColumnWidth, maxWidth)
  const tableWidth = Math.min(Math.round(tableElement.getBoundingClientRect().width), maxWidth)
  const tableHeight = Math.round(tableElement.getBoundingClientRect().height)
  const columns = getTableColumnWidths(tableElement, { minColumnWidth })
  const tableIndex = getEditorLayoutTableElements().indexOf(tableElement)
  const existingLayout = tableIndex >= 0 ? tableLayoutMetadata[tableIndex] : null
  const shouldTrackRows =
    resizeKind === 'table-height' ||
    resizeKind === 'row' ||
    Boolean(existingLayout?.height || existingLayout?.rows?.length)
  const rows = shouldTrackRows ? getTableRowHeights(tableElement) : []
  const minHeight = rowCount * MIN_TABLE_ROW_HEIGHT
  const startWidth = Math.max(1, Math.min(Math.max(tableWidth, minWidth), maxWidth))

  const dragState = {
    tableElement,
    tableIndex,
    kind: resizeKind,
    startX: event.clientX,
    startY: event.clientY,
    startWidth,
    startHeight: Math.max(tableHeight, minHeight),
    minWidth,
    minColumnWidth,
    minHeight,
    maxWidth,
    columnIndex: resizeColumnIndex,
    rowIndex: resizeRowIndex,
    startColumns: normalizeResizeColumns(columns, startWidth, minColumnWidth),
    startRows: rows.length ? normalizeResizeRows(rows, Math.max(tableHeight, minHeight)) : [],
  }
  const moveListener = (moveEvent) => {
    if (!Number.isFinite(moveEvent.clientX) || !Number.isFinite(moveEvent.clientY)) {
      return
    }

    moveEvent.preventDefault()
    moveEvent.stopPropagation()
    updateTableResizeDragState(dragState, moveEvent.clientX, moveEvent.clientY)
  }
  const endListener = (endEvent) => {
    endEvent.preventDefault()
    endEvent.stopPropagation()
    if (Number.isFinite(endEvent.clientX) && Number.isFinite(endEvent.clientY)) {
      updateTableResizeDragState(dragState, endEvent.clientX, endEvent.clientY)
    }
    stopTableResizeDrag()
  }

  dragState.moveListener = moveListener
  dragState.endListener = endListener
  tableResizeDragState = dragState
  tableResizeHandleDragging.value = true
  window.addEventListener('mousemove', moveListener, true)
  window.addEventListener('mouseup', endListener, true)
  updateTableResizeDragState(dragState, event.clientX, event.clientY)
  hideToolbar()
  hideTableActionPanel()
  hideTableHoverControl()
  clearNativeTableCellVisualSelection()
}

const handleTableResizeHandleDown = (event) => {
  const target = event.target instanceof Element ? event.target : null
  if (isTableResizeIgnoredElement(target)) {
    return
  }

  const resizeInfo = target?.closest?.('.table-resize-handle')
    ? {
        kind: tableResizeHandle.kind,
        tableElement: tableResizeHandleTableElement,
        columnIndex: tableResizeHandle.columnIndex,
        rowIndex: tableResizeHandle.rowIndex,
      }
    : getTableResizeHitInfo(event, true)

  if (!resizeInfo) {
    return
  }

  event.preventDefault()
  event.stopPropagation()
  startTableResizeDrag(event, resizeInfo)
}

const resetNativeTableCellSelectionDrag = () => {
  nativeTableCellSelectionAnchor = null
  nativeTableCellSelectionAnchorPosition = null
  nativeTableCellSelectionDragging = false
  nativeTableCellSelectionMoved = false
}

const getDomTableCellFromResolvedPos = (view, $pos) => {
  if (!view || !$pos) {
    return null
  }

  for (let depth = $pos.depth; depth > 0; depth -= 1) {
    const node = $pos.node(depth)
    if (!tableCellTypeNames.includes(node.type?.name)) {
      continue
    }

    const cellPos = $pos.before(depth)
    const domNode = view.nodeDOM(cellPos)
    const domElement = domNode instanceof Element ? domNode : domNode?.parentElement
    const cellElement = domElement?.matches?.('td, th') ? domElement : domElement?.closest?.('td, th')

    if (cellElement && editorRoot.value?.contains(cellElement)) {
      return cellElement
    }
  }

  try {
    const domAtPos = view.domAtPos($pos.pos)
    const domElement =
      domAtPos.node instanceof Element ? domAtPos.node : domAtPos.node?.parentElement
    const cellElement = domElement?.closest?.('td, th')

    if (cellElement && editorRoot.value?.contains(cellElement)) {
      return cellElement
    }
  } catch {
    // Toast UI can occasionally expose a position that has no direct DOM mapping yet.
  }

  return null
}

const collectProseMirrorSelectedTableCells = () => {
  const view = getWysiwygView()
  const selection = view?.state?.selection

  if (!view || !selection?.isCellSelection || (selection.ranges?.length || 0) < 2) {
    return []
  }

  const selectedCells = new Set()

  selection.ranges.forEach((range) => {
    const cellElement = getDomTableCellFromResolvedPos(view, range.$from)
    if (cellElement) {
      selectedCells.add(cellElement)
    }
  })

  return Array.from(selectedCells)
}

const collectNativeSelectedTableCells = () => {
  const selection = window.getSelection?.()
  const editorContentsElements = Array.from(editorRoot.value?.querySelectorAll('.toastui-editor-contents') || [])

  if (
    !selection ||
    selection.rangeCount < 1 ||
    selection.isCollapsed ||
    !editorContentsElements.length ||
    (!isNodeInsideEditor(selection.anchorNode) && !isNodeInsideEditor(selection.focusNode))
  ) {
    return []
  }

  const range = selection.getRangeAt(0)
  const selectionRects = Array.from(range.getClientRects()).filter((rect) => rect.width > 0 || rect.height > 0)
  const cells = editorContentsElements.flatMap((editorContents) =>
    Array.from(editorContents.querySelectorAll('th, td'))
  )
  const pointHitCells = new Set()

  selectionRects.forEach((selectionRect) => {
    const probeX = Math.min(
      Math.max(selectionRect.left + Math.max(selectionRect.width / 2, 1), 0),
      Math.max(window.innerWidth - 1, 0)
    )
    const probeY = Math.min(
      Math.max(selectionRect.top + Math.max(selectionRect.height / 2, 1), 0),
      Math.max(window.innerHeight - 1, 0)
    )
    const cellElement = getTableCellFromPoint(probeX, probeY)
    if (cellElement) {
      pointHitCells.add(cellElement)
    }
  })

  const hitCells = cells.filter((cellElement) => {
    if (pointHitCells.has(cellElement)) {
      return true
    }

    try {
      if (range.intersectsNode(cellElement)) {
        return true
      }
    } catch {
      return false
    }

    const cellRect = cellElement.getBoundingClientRect()
    return selectionRects.some((selectionRect) => doRectsIntersect(selectionRect, cellRect))
  })

  return expandTableCellsToRect(hitCells)
}

const syncNativeTableCellVisualSelection = () => {
  const selectedCells = expandTableCellsToRect([
    ...collectProseMirrorSelectedTableCells(),
    ...collectNativeSelectedTableCells(),
  ])

  if (selectedCells.length >= 2) {
    if (selectedCells.every(isNativeTableCellVisuallySelected)) {
      nativeSelectedTableCellElements = new Set(selectedCells)
      renderNativeTableCellSelectionStyle(selectedCells)
      return true
    }

    return markNativeTableCellVisualSelection(selectedCells)
  }

  const liveSelectedCells = Array.from(nativeSelectedTableCellElements).filter(
    (cellElement) => cellElement.isConnected && editorRoot.value?.contains(cellElement)
  )

  if (liveSelectedCells.length > 1) {
    nativeSelectedTableCellElements = new Set(liveSelectedCells)
    renderNativeTableCellSelectionStyle(liveSelectedCells)
    return true
  }

  if (nativeTableCellSelectionRect) {
    return reapplyStoredNativeTableCellVisualSelection()
  }

  return false
}

const syncTableMultiCellSelectionState = () => {
  const hasNativeTableCells = syncNativeTableCellVisualSelection()
  tableMultiCellSelectionActive.value = hasNativeTableCells || isMultiCellSelectionActive()
}

const cancelToastContextMenuSync = () => {
  if (toastContextMenuFrame) {
    window.cancelAnimationFrame(toastContextMenuFrame)
    toastContextMenuFrame = null
  }
}

const placeToastTableContextMenu = (clientX, clientY) => {
  const menu = editorRoot.value?.querySelector('.toastui-editor-context-menu')
  if (!menu || window.getComputedStyle(menu).display === 'none') {
    return
  }

  const margin = 12
  const gap = 10
  const menuRect = menu.getBoundingClientRect()
  const menuWidth = menuRect.width || 220
  const menuHeight = menuRect.height || 360
  const left = Math.min(Math.max(clientX + gap, margin), Math.max(margin, window.innerWidth - menuWidth - margin))
  const belowTop = clientY + gap
  const aboveTop = clientY - menuHeight - gap
  const top =
    belowTop + menuHeight <= window.innerHeight - margin
      ? belowTop
      : Math.max(margin, Math.min(aboveTop, window.innerHeight - menuHeight - margin))

  menu.style.position = 'fixed'
  menu.style.left = `${left}px`
  menu.style.top = `${top}px`
  menu.style.maxHeight = `${Math.max(180, window.innerHeight - margin * 2)}px`
  menu.style.overflowY = 'auto'
}

const scheduleToastTableContextMenuPlacement = (event) => {
  const target = event.target instanceof Element ? event.target : null
  const cellElement = target?.closest?.('td, th')
  if (!cellElement || !editorRoot.value?.contains(cellElement)) {
    return
  }

  const view = getWysiwygView()
  const tableInfo = resolveTableInfoFromCell(cellElement)
  const focusPos =
    view && tableInfo
      ? findTableCellTextPos(view.state.doc, tableInfo.tablePos, tableInfo.rowIndex, tableInfo.columnIndex)
      : null

  const keepExistingCellSelection = isMultiCellSelectionActive() && cellElement.classList.contains('toastui-editor-cell-selected')

  if (!keepExistingCellSelection && view && tableInfo && focusPos !== null) {
    activeTableInfo.value = tableInfo
    view.dispatch(view.state.tr.setSelection(TextSelection.create(view.state.doc, focusPos)))
    view.focus()
  }

  const { clientX, clientY } = event
  cancelToastContextMenuSync()
  toastContextMenuFrame = window.requestAnimationFrame(() => {
    toastContextMenuFrame = window.requestAnimationFrame(() => {
      toastContextMenuFrame = null
      placeToastTableContextMenu(clientX, clientY)
    })
  })
}

const hideHoverBlockHint = () => {
  hoverBlockHintVisible.value = false
  hoverBlockHint.label = ''
  hoverBlockHint.top = -9999
  hoverBlockHint.left = -9999
}

const getElementsBoundingRect = (elements) => {
  const rects = elements
    .filter((element) => element?.isConnected && editorRoot.value?.contains(element))
    .map((element) => element.getBoundingClientRect())
    .filter((rect) => rect.width > 0 || rect.height > 0)

  if (!rects.length) {
    return null
  }

  const left = Math.min(...rects.map((rect) => rect.left))
  const top = Math.min(...rects.map((rect) => rect.top))
  const right = Math.max(...rects.map((rect) => rect.right))
  const bottom = Math.max(...rects.map((rect) => rect.bottom))

  return {
    left,
    top,
    right,
    bottom,
    width: right - left,
    height: bottom - top,
  }
}

const getTableHoverControlAnchorRect = (cellElement) => {
  const selectedCells = [
    ...Array.from(nativeSelectedTableCellElements || []),
    ...getTableCellsFromSelectionRect(nativeTableCellSelectionRect),
  ]
  const selectedRect = getElementsBoundingRect(selectedCells)

  if (selectedRect) {
    return selectedRect
  }

  return cellElement?.getBoundingClientRect?.() || null
}

const showTableHoverControl = (cellElement) => {
  if (hasActiveEditorTextSelection()) {
    hideTableHoverControl()
    return
  }

  const tableElement = cellElement?.closest?.('table')
  if (!tableElement || !editorRoot.value?.contains(tableElement)) {
    hideTableHoverControl()
    return
  }

  const rect = tableElement.getBoundingClientRect()
  if (!isRectInViewport(rect)) {
    hideTableHoverControl()
    return
  }

  const controlSize = 34
  const controlGap = 8
  const anchorRect = getTableHoverControlAnchorRect(cellElement)
  if (!anchorRect) {
    hideTableHoverControl()
    return
  }

  const cellPosition = getDomTableCellPosition(cellElement)
  const view = getWysiwygView()

  tableHoverControlCellElement = cellElement
  tableHoverControlTableInfo =
    resolveTableInfoFromCell(cellElement) ||
    resolveTableInfoFromNativeSelectionRect() ||
    (view
      ? resolveTableInfoFromDomTable(
          view,
          tableElement,
          cellPosition?.rowIndex ?? nativeTableCellSelectionRect?.minRow ?? 0,
          cellPosition?.columnIndex ?? nativeTableCellSelectionRect?.minColumn ?? 0,
          tableElement.rows.length,
          tableElement.rows[0]?.cells?.length || 0
        )
      : null)
  const desiredTop = anchorRect.top - controlSize - controlGap
  const fallbackTop = anchorRect.bottom + controlGap
  const nextTop =
    desiredTop >= 8
      ? desiredTop
      : Math.min(fallbackTop, Math.max(8, window.innerHeight - controlSize - 8))

  tableHoverControlPosition.top = Math.max(8, Math.min(nextTop, Math.max(8, window.innerHeight - controlSize - 8)))
  tableHoverControlPosition.left = Math.min(
    Math.max(anchorRect.left + anchorRect.width / 2 - controlSize / 2, 8),
    Math.max(8, window.innerWidth - controlSize - 8)
  )
  tableHoverControlVisible.value = true
}

const getConnectedTableCellElement = (...cellElements) =>
  cellElements.find((cellElement) => cellElement?.isConnected && editorRoot.value?.contains(cellElement)) || null

const getFallbackTableHoverControlCell = () => {
  const selectedCellElement = getConnectedTableCellElement(...getTableCellsFromSelectionRect(nativeTableCellSelectionRect))
  if (selectedCellElement) {
    return selectedCellElement
  }

  const x = tableHoverControlPosition.left + 17
  const y = tableHoverControlPosition.top + 17
  const elements = document.elementsFromPoint?.(x, y) || []
  for (const element of elements) {
    const cellElement = element.closest?.('td, th')
    if (cellElement && editorRoot.value?.contains(cellElement)) {
      return cellElement
    }
  }

  return null
}

const openTableActionPanelFromHoverControl = () => {
  if (hasActiveEditorTextSelection()) {
    hideTableHoverControl()
    hideTableActionPanel()
    return
  }

  const cellElement =
    getConnectedTableCellElement(tableHoverControlCellElement, nativeSelectedTableCellElements.values().next().value) ||
    getFallbackTableHoverControlCell()
  const tableInfo =
    tableHoverControlTableInfo || resolveTableInfoFromNativeSelectionRect() || resolveTableInfoFromCell(cellElement)

  if (!cellElement?.isConnected || !editorRoot.value?.contains(cellElement) || !tableInfo) {
    hideTableHoverControl()
    return
  }

  resetNativeTableCellSelectionDrag()
  if (!nativeTableCellSelectionRect && nativeSelectedTableCellElements.size < 2) {
    clearNativeTableCellVisualSelection()
  }
  showTableActionPanel(cellElement, tableInfo)
  suppressNextTableEditorClick = true
  window.setTimeout(() => {
    suppressNextTableEditorClick = false
  }, 250)
  hideTableHoverControl()
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
  if (tableResizeHandleVisible.value || tableResizeHandleDragging.value) {
    hideHoverBlockHint()
    return
  }

  if (tableHoverControlVisible.value) {
    hideHoverBlockHint()
    return
  }

  const pointerNode = getNodeFromPoint(event.clientX, event.clientY)
  const pointerElement =
    pointerNode instanceof Node
      ? pointerNode.nodeType === Node.ELEMENT_NODE
        ? pointerNode
        : pointerNode.parentElement
      : null

  if (pointerElement?.closest?.('.table-hover-control')) {
    hideHoverBlockHint()
    return
  }

  if (
    toolbarVisible.value ||
    event.buttons > 0 ||
    nativeTableCellSelectionDragging ||
    tableMultiCellSelectionActive.value ||
    nativeTableCellSelectionRect
  ) {
    hideHoverBlockHint()
    hideTableHoverControl()
    return
  }

  if (!(pointerNode instanceof Node)) {
    hideHoverBlockHint()
    return
  }

  if (!pointerElement) {
    hideHoverBlockHint()
    hideTableHoverControl()
    return
  }

  const editorContents = pointerElement.closest?.('.toastui-editor-contents')
  if (!editorContents || !editorRoot.value?.contains(editorContents)) {
    hideHoverBlockHint()
    hideTableHoverControl()
    return
  }

  const tableCellElement = pointerElement.closest?.('td, th')
  if (tableCellElement && editorRoot.value?.contains(tableCellElement)) {
    hideHoverBlockHint()
    return
  }

  hideTableHoverControl()

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
  toolbarSelectionInTable.value = false
  toolbarState.strong.active = false
  toolbarState.strong.full = false
  toolbarState.italic.active = false
  toolbarState.italic.full = false
  toolbarState.strike.active = false
  toolbarState.strike.full = false
  toolbarState.code.active = false
  toolbarState.code.full = false
  toolbarState.cellAlignLeft.active = false
  toolbarState.cellAlignLeft.full = false
  toolbarState.cellAlignCenter.active = false
  toolbarState.cellAlignCenter.full = false
  toolbarState.cellAlignRight.active = false
  toolbarState.cellAlignRight.full = false
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

const hasActiveEditorTextSelection = () => {
  const view = getWysiwygView()
  const selection = view?.state?.selection
  if (!selection || selection.empty) {
    return false
  }

  if (
    selection.isCellSelection ||
    tableMultiCellSelectionActive.value ||
    nativeTableCellSelectionRect ||
    nativeSelectedTableCellElements.size > 1
  ) {
    return false
  }

  return getSelectionTextSegments(view).length > 0
}

const setToolbarToggleState = (target, active, full) => {
  target.active = active
  target.full = full
}

const tableCellTypeNames = ['tableHeadCell', 'tableBodyCell']

const addTableCellEntryFromResolvedPos = (entries, $pos) => {
  if (!$pos) {
    return
  }

  for (let depth = $pos.depth; depth > 0; depth -= 1) {
    const node = $pos.node(depth)
    if (tableCellTypeNames.includes(node.type?.name)) {
      entries.set($pos.before(depth), { pos: $pos.before(depth), node })
      return
    }
  }
}

const collectSelectedTableCellEntries = (view) => {
  const selection = view?.state?.selection
  if (!view || !selection) {
    return []
  }

  const entries = new Map()

  if (selection.isCellSelection && selection.ranges?.length) {
    selection.ranges.forEach((range) => {
      addTableCellEntryFromResolvedPos(entries, range.$from)
    })
  } else {
    addTableCellEntryFromResolvedPos(entries, selection.$from)
    addTableCellEntryFromResolvedPos(entries, selection.$to)

    view.state.doc.nodesBetween(selection.from, selection.to, (node, pos) => {
      if (tableCellTypeNames.includes(node.type?.name)) {
        entries.set(pos, { pos, node })
        return false
      }

      return true
    })
  }

  return Array.from(entries.values())
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
  const isInsideTableCell = (segment) =>
    tableCellTypeNames.includes(segment.parentType) ||
    segment.ancestors.some((node) => tableCellTypeNames.includes(node.type?.name))

  toolbarSelectionInTable.value = segments.every(isInsideTableCell)

  if (toolbarSelectionInTable.value) {
    const selectedCells = collectSelectedTableCellEntries(view)
    const isLeftAlignedCell = ({ node }) => !node.attrs?.align || node.attrs.align === 'left'
    const hasCenterAlignedCell = selectedCells.some(({ node }) => node.attrs?.align === 'center')
    const allCellsCenterAligned =
      selectedCells.length > 0 && selectedCells.every(({ node }) => node.attrs?.align === 'center')
    const hasRightAlignedCell = selectedCells.some(({ node }) => node.attrs?.align === 'right')
    const allCellsRightAligned =
      selectedCells.length > 0 && selectedCells.every(({ node }) => node.attrs?.align === 'right')
    const hasLeftAlignedCell = selectedCells.some(isLeftAlignedCell)
    const allCellsLeftAligned = selectedCells.length > 0 && selectedCells.every(isLeftAlignedCell)

    setToolbarToggleState(toolbarState.cellAlignLeft, hasLeftAlignedCell, allCellsLeftAligned)
    setToolbarToggleState(toolbarState.cellAlignCenter, hasCenterAlignedCell, allCellsCenterAligned)
    setToolbarToggleState(toolbarState.cellAlignRight, hasRightAlignedCell, allCellsRightAligned)
  }

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

const buildTableInfo = (tableNode, tablePos, rowIndex, columnIndex, rowCount, columnCount) => ({
  tableNode,
  tablePos,
  rowIndex,
  columnIndex,
  rowCount,
  columnCount,
})

const resolveTableInfoFromPos = (doc, pos, rowIndex, columnIndex, rowCount, columnCount) => {
  if (!Number.isInteger(pos) || pos < 0 || pos > doc.content.size) {
    return null
  }

  const $pos = doc.resolve(pos)
  for (let depth = $pos.depth; depth >= 0; depth -= 1) {
    const node = $pos.node(depth)
    if (node?.type?.name === 'table') {
      return buildTableInfo(
        node,
        depth === 0 ? 0 : $pos.before(depth),
        rowIndex,
        columnIndex,
        rowCount,
        columnCount
      )
    }
  }

  return null
}

const resolveTableInfoFromDomTable = (view, tableElement, rowIndex, columnIndex, rowCount, columnCount) => {
  let tableInfo = null

  view.state.doc.descendants((node, pos) => {
    if (tableInfo || node.type.name !== 'table') {
      return !tableInfo
    }

    const tableDom = view.nodeDOM(pos)
    if (
      tableDom &&
      (tableDom === tableElement ||
        tableDom.contains?.(tableElement) ||
        tableElement.contains?.(tableDom))
    ) {
      tableInfo = buildTableInfo(node, pos, rowIndex, columnIndex, rowCount, columnCount)
      return false
    }

    return true
  })

  return tableInfo
}

const resolveTableInfoFromVisibleTableOrder = (view, tableElement, rowIndex, columnIndex, rowCount, columnCount) => {
  if (!view || !tableElement) {
    return null
  }

  const visibleTableIndex = getVisibleEditorTableElements().indexOf(tableElement)
  if (visibleTableIndex < 0) {
    return null
  }

  let currentTableIndex = -1
  let tableInfo = null

  view.state.doc.descendants((node, pos) => {
    if (tableInfo || node.type.name !== 'table') {
      return !tableInfo
    }

    currentTableIndex += 1
    if (currentTableIndex === visibleTableIndex) {
      tableInfo = buildTableInfo(node, pos, rowIndex, columnIndex, rowCount, columnCount)
      return false
    }

    return true
  })

  return tableInfo
}

const resolveTableInfoFromNativeSelectionRect = () => {
  const view = getWysiwygView()
  const selectionRect = nativeTableCellSelectionRect
  if (!view || !selectionRect) {
    return null
  }

  const candidateTable =
    getEditorTableElements()[selectionRect.tableIndex] ||
    getVisibleEditorTableElements()[selectionRect.tableIndex] ||
    getVisibleEditorTableElements()[0]

  if (candidateTable) {
    const tableInfo =
      resolveTableInfoFromVisibleTableOrder(
        view,
        candidateTable,
        selectionRect.minRow,
        selectionRect.minColumn,
        candidateTable.rows.length,
        candidateTable.rows[0]?.cells?.length || 0
      ) ||
      resolveTableInfoFromDomTable(
        view,
        candidateTable,
        selectionRect.minRow,
        selectionRect.minColumn,
        candidateTable.rows.length,
        candidateTable.rows[0]?.cells?.length || 0
      )

    if (tableInfo) {
      return tableInfo
    }
  }

  const tableEntries = []
  view.state.doc.descendants((node, pos) => {
    if (node.type.name === 'table') {
      tableEntries.push({ node, pos })
    }
  })

  const tableEntry = tableEntries[Math.min(selectionRect.tableIndex, tableEntries.length - 1)] || tableEntries[0]
  if (!tableEntry) {
    return null
  }

  const rowCount = tableEntry.node.child(0).childCount + tableEntry.node.child(1).childCount
  const columnCount = tableEntry.node.child(0).firstChild?.childCount || 0
  return buildTableInfo(
    tableEntry.node,
    tableEntry.pos,
    selectionRect.minRow,
    selectionRect.minColumn,
    rowCount,
    columnCount
  )
}

const rememberEditorSelectionRange = () => {
  const view = getWysiwygView()
  const selection = view?.state?.selection
  if (!view || !selection) {
    return
  }

  lastEditorSelectionRange = [selection.from, selection.to]
}

const updateFixedToolbarSnapshot = () => {
  const snapshot = getFixedToolbarSnapshot(getWysiwygView())
  Object.assign(fixedToolbarState, snapshot.state)
  fixedToolbarSelectedText.value = snapshot.selectedText
}

const rememberFixedToolbarSelection = () => {
  rememberEditorSelectionRange()
  updateFixedToolbarSnapshot()
}

const restoreInsertionSelection = () => {
  if (!editorInstance || !lastEditorSelectionRange) {
    return
  }

  const view = getWysiwygView()
  const docSize = view?.state?.doc?.content?.size
  if (!view || !Number.isFinite(docSize)) {
    return
  }

  const [start, end] = lastEditorSelectionRange
  const safeStart = Math.max(0, Math.min(start, docSize))
  const safeEnd = Math.max(0, Math.min(end, docSize))

  editorInstance.focus()
  editorInstance.setSelection(safeStart, safeEnd)
}

const syncAfterFixedToolbarCommand = () => {
  updatePreviewFromEditor()
  nextTick(() => {
    rememberEditorSelectionRange()
    updateFixedToolbarSnapshot()
  })
}

const runFixedToolbarCommand = (command, payload) => {
  if (!editorInstance) {
    return
  }

  restoreInsertionSelection()
  editorInstance.exec(command, payload)
  syncAfterFixedToolbarCommand()
}

const applyFixedToolbarHeading = (level) => {
  runFixedToolbarCommand('heading', { level })
}

const insertFixedToolbarLink = (payload) => {
  runFixedToolbarCommand('addLink', payload)
}

const resolveTableInfoFromCell = (cellElement) => {
  const view = getWysiwygView()
  const rowElement = cellElement?.closest?.('tr')
  const tableElement = cellElement?.closest?.('table')

  if (!view || !rowElement || !tableElement) {
    return null
  }

  const rowIndex = Array.from(tableElement.rows).indexOf(rowElement)
  const columnIndex = Array.from(rowElement.cells).indexOf(cellElement)
  const columnCount = tableElement.rows[0]?.cells?.length || 0

  if (rowIndex < 0 || columnIndex < 0 || columnCount < 1) {
    return null
  }

  const doc = view.state.doc
  const rowCount = tableElement.rows.length
  const domTableInfo = resolveTableInfoFromDomTable(
    view,
    tableElement,
    rowIndex,
    columnIndex,
    rowCount,
    columnCount
  )

  if (domTableInfo) {
    return domTableInfo
  }

  const orderedTableInfo = resolveTableInfoFromVisibleTableOrder(
    view,
    tableElement,
    rowIndex,
    columnIndex,
    rowCount,
    columnCount
  )

  if (orderedTableInfo) {
    return orderedTableInfo
  }

  const baseCandidates = [
    view.state.selection?.from,
    view.state.selection?.to,
    lastEditorSelectionRange?.[0],
    lastEditorSelectionRange?.[1],
  ]

  try {
    baseCandidates.push(view.posAtDOM(cellElement, 0))
    baseCandidates.push(view.posAtDOM(cellElement, cellElement.childNodes.length))
  } catch {
    // Fallback candidates above are enough when Toast UI cannot map the cell itself.
  }

  const contentElement = cellElement.querySelector?.('p, div, span, br')
  if (contentElement) {
    try {
      baseCandidates.push(view.posAtDOM(contentElement, 0))
    } catch {
      // Ignore unmapped child nodes.
    }
  }

  const candidates = new Set()
  baseCandidates.forEach((pos) => {
    if (!Number.isInteger(pos)) {
      return
    }

    for (let offset = -2; offset <= 3; offset += 1) {
      const safePos = pos + offset
      if (safePos >= 0 && safePos <= doc.content.size) {
        candidates.add(safePos)
      }
    }
  })

  for (const pos of candidates) {
    const tableInfo = resolveTableInfoFromPos(doc, pos, rowIndex, columnIndex, rowCount, columnCount)
    if (tableInfo) {
      return tableInfo
    }
  }

  return null
}

const showTableActionPanel = (cellElement, tableInfoOverride = null) => {
  if (hasActiveEditorTextSelection()) {
    hideTableActionPanel()
    hideTableHoverControl()
    hideTableResizeHandle()
    return
  }

  const tableInfo = tableInfoOverride || resolveTableInfoFromCell(cellElement)
  if (!tableInfo) {
    hideTableActionPanel()
    return
  }

  const rect = cellElement.getBoundingClientRect()
  const panelWidth = 304
  const panelHeight = 324
  const gap = 10
  const desiredLeft = rect.right + gap
  const fallbackLeft = rect.left - panelWidth - gap

  activeTableInfo.value = tableInfo
  tableActionPanelPosition.top = Math.min(
    Math.max(rect.top, 12),
    Math.max(12, window.innerHeight - panelHeight - 12)
  )
  tableActionPanelPosition.left =
    desiredLeft + panelWidth <= window.innerWidth - 12
      ? desiredLeft
      : Math.max(12, fallbackLeft)
  tableActionPanelVisible.value = true
}

const bindEditorSelectionListeners = () => {
  cleanupEditorSelectionListeners?.()

  const rootElement = editorRoot.value
  if (!rootElement) {
    cleanupEditorSelectionListeners = null
    return
  }

  const punctuationInputPattern = /^[，。！？；：,.!?;:]$/u
  let punctuationSelectionFrame = null
  let editorCompositionActive = false

  const getWysiwygDomSelectionRange = (view) => {
    const domSelection = window.getSelection()
    if (
      !domSelection?.anchorNode ||
      !domSelection.focusNode ||
      !view.dom.contains(domSelection.anchorNode) ||
      !view.dom.contains(domSelection.focusNode)
    ) {
      return null
    }

    try {
      const anchor = view.posAtDOM(domSelection.anchorNode, domSelection.anchorOffset)
      const focus = view.posAtDOM(domSelection.focusNode, domSelection.focusOffset)
      return {
        from: Math.min(anchor, focus),
        to: Math.max(anchor, focus),
        collapsed: domSelection.isCollapsed,
      }
    } catch {
      return null
    }
  }

  const schedulePunctuationSelectionCollapse = (event) => {
    const punctuation = event.data || ''
    const view = getWysiwygView()
    const target = event.target
    if (
      !punctuationInputPattern.test(punctuation) ||
      !view ||
      target !== view.dom
    ) {
      return
    }

    const inputRange = getWysiwygDomSelectionRange(view)
    if (!inputRange) {
      return
    }

    const expectedFrom = inputRange.to - punctuation.length
    const expectedTo = inputRange.to
    if (punctuationSelectionFrame !== null) {
      window.cancelAnimationFrame(punctuationSelectionFrame)
    }

    punctuationSelectionFrame = window.requestAnimationFrame(() => {
      punctuationSelectionFrame = null
      const currentView = getWysiwygView()
      const currentRange = currentView ? getWysiwygDomSelectionRange(currentView) : null
      if (
        !currentView ||
        currentRange?.collapsed !== false ||
        currentRange.from !== expectedFrom ||
        currentRange.to !== expectedTo ||
        currentView.state.doc.textBetween(expectedFrom, expectedTo, '') !== punctuation
      ) {
        return
      }

      window.getSelection()?.collapseToEnd()
      currentView.dispatch(
        currentView.state.tr.setSelection(TextSelection.create(currentView.state.doc, expectedTo))
      )
    })
  }

  const handleEditorCompositionStart = (event) => {
    const view = getWysiwygView()
    if (view && event.target instanceof Node && view.dom.contains(event.target)) {
      editorCompositionActive = true
    }
  }

  const handleEditorCompositionEnd = (event) => {
    editorCompositionActive = false
    schedulePunctuationSelectionCollapse(event)
  }

  const handleEditorInput = (event) => {
    if (
      ['insertText', 'insertCompositionText'].includes(event.inputType) &&
      !editorCompositionActive &&
      !event.isComposing
    ) {
      schedulePunctuationSelectionCollapse(event)
    }
  }

  const handleSelectionCommit = () => {
    nextTick(() => {
      rememberEditorSelectionRange()
      syncTableMultiCellSelectionState()
      scheduleToolbarSync()

      if (hasActiveEditorTextSelection()) {
        hideTableActionPanel()
        hideTableHoverControl()
        hideTableResizeHandle()
      }

      window.requestAnimationFrame(() => {
        syncTableMultiCellSelectionState()
      })
    })
  }

  const updateNativeTableCellDragSelection = (event) => {
    if (!nativeTableCellSelectionDragging || !nativeTableCellSelectionAnchor) {
      return false
    }

    const cellElement = getTableCellFromEvent(event)
    if (!cellElement) {
      return nativeSelectedTableCellElements.size > 1
    }

    if (cellElement === nativeTableCellSelectionAnchor && !nativeTableCellSelectionMoved) {
      return false
    }

    nativeTableCellSelectionMoved = true
    hideTableActionPanel()
    return applyTableCellRectVisualSelection(
      nativeTableCellSelectionAnchorPosition || nativeTableCellSelectionAnchor,
      cellElement
    )
  }

  const handlePointerDown = (event) => {
    if (event.button !== 0) {
      return
    }

    const cellElement = getTableCellFromEvent(event)
    const imageElement = getImageElementFromEvent(event)

    hideToolbar()
    hideHoverBlockHint()
    if (!imageElement) {
      hideImageToolbar()
    }

    if (cellElement) {
      const cellPosition = getDomTableCellPosition(cellElement)
      if (!cellPosition || cellPosition.tableIndex < 0) {
        resetNativeTableCellSelectionDrag()
        clearNativeTableCellVisualSelection()
        return
      }

      nativeTableCellSelectionAnchor = cellElement
      nativeTableCellSelectionAnchorPosition = {
        tableIndex: cellPosition.tableIndex,
        rowIndex: cellPosition.rowIndex,
        columnIndex: cellPosition.columnIndex,
      }
      nativeTableCellSelectionDragging = true
      nativeTableCellSelectionMoved = false
      clearNativeTableCellVisualSelection()
      return
    }

    resetNativeTableCellSelectionDrag()
    clearNativeTableCellVisualSelection()
  }

  const handleTableSelectionMove = (event) => {
    updateNativeTableCellDragSelection(event)
  }

  const handleTableSelectionEnd = (event) => {
    if (!nativeTableCellSelectionDragging) {
      return
    }

    const hasVisualSelection =
      updateNativeTableCellDragSelection(event) || nativeSelectedTableCellElements.size > 1
    const focusCellElement = getTableCellFromEvent(event) || nativeTableCellSelectionAnchor

    resetNativeTableCellSelectionDrag()

    if (hasVisualSelection) {
      tableMultiCellSelectionActive.value = true
      hideHoverBlockHint()
      hideTableActionPanel()
      showTableHoverControl(focusCellElement, event.clientX, event.clientY)
      scheduleToolbarSync()
    }
  }

  const handleEditorClick = (event) => {
    if (suppressNextTableEditorClick) {
      suppressNextTableEditorClick = false
      event.stopImmediatePropagation()
      return
    }

    const imageElement = getImageElementFromEvent(event)
    if (imageElement) {
      event.preventDefault()
      event.stopImmediatePropagation()
      resetNativeTableCellSelectionDrag()
      clearNativeTableCellVisualSelection()
      showImageToolbar(imageElement)
      return
    }

    if (hasActiveEditorTextSelection()) {
      resetNativeTableCellSelectionDrag()
      hideTableActionPanel()
      hideTableHoverControl()
      hideTableResizeHandle()
      hideImageToolbar()
      return
    }

    const cellElement = getTableCellFromEvent(event)

    if (cellElement) {
      resetNativeTableCellSelectionDrag()

      if (isMultiCellSelectionActive() || nativeSelectedTableCellElements.size > 1) {
        hideTableActionPanel()
        return
      }

      clearNativeTableCellVisualSelection()
      hideTableActionPanel()
      showTableHoverControl(cellElement, event.clientX, event.clientY)
      return
    }

    resetNativeTableCellSelectionDrag()
    clearNativeTableCellVisualSelection()
    hideTableHoverControl()
    hideTableActionPanel()
    hideImageToolbar()
  }

  const handleEditorKeydown = (event) => {
    if (!imageToolbarVisible.value || !['Backspace', 'Delete'].includes(event.key)) {
      return
    }

    event.preventDefault()
    event.stopImmediatePropagation()
    deleteActiveImage()
  }

  const handleTableActionContextMenu = (event) => {
    if (hasActiveEditorTextSelection()) {
      hideTableActionPanel()
      hideTableHoverControl()
      hideTableResizeHandle()
      return
    }

    const cellElement = getTableCellFromEvent(event)

    if (!cellElement || isMultiCellSelectionActive() || nativeSelectedTableCellElements.size > 1) {
      hideTableActionPanel()
      return
    }

    event.preventDefault()
    event.stopImmediatePropagation()
    resetNativeTableCellSelectionDrag()
    clearNativeTableCellVisualSelection()
    showTableActionPanel(cellElement)
  }

  const handleToastContextMenuClick = (event) => {
    const target = event.target instanceof Element ? event.target : null
    if (!target?.closest?.('.toastui-editor-context-menu .menu-item')) {
      return
    }

    window.requestAnimationFrame(() => {
      updatePreviewFromEditor()
      updateToolbarState()
      scheduleToolbarSync()
    })
  }

  rootElement.addEventListener('mouseup', handleSelectionCommit)
  rootElement.addEventListener('keyup', handleSelectionCommit)
  rootElement.addEventListener('touchend', handleSelectionCommit)
  rootElement.addEventListener('compositionstart', handleEditorCompositionStart)
  rootElement.addEventListener('compositionend', handleEditorCompositionEnd)
  rootElement.addEventListener('input', handleEditorInput)
  rootElement.addEventListener('mousedown', handlePointerDown, true)
  rootElement.addEventListener('keydown', handleEditorKeydown, true)
  rootElement.addEventListener('click', handleEditorClick, true)
  rootElement.addEventListener('contextmenu', handleTableActionContextMenu, true)
  rootElement.addEventListener('contextmenu', scheduleToastTableContextMenuPlacement, true)
  document.addEventListener('mousemove', handleTableSelectionMove, true)
  document.addEventListener('mouseup', handleTableSelectionEnd, true)
  rootElement.addEventListener('click', handleToastContextMenuClick, true)

  cleanupEditorSelectionListeners = () => {
    rootElement.removeEventListener('mouseup', handleSelectionCommit)
    rootElement.removeEventListener('keyup', handleSelectionCommit)
    rootElement.removeEventListener('touchend', handleSelectionCommit)
    rootElement.removeEventListener('compositionstart', handleEditorCompositionStart)
    rootElement.removeEventListener('compositionend', handleEditorCompositionEnd)
    rootElement.removeEventListener('input', handleEditorInput)
    rootElement.removeEventListener('mousedown', handlePointerDown, true)
    rootElement.removeEventListener('keydown', handleEditorKeydown, true)
    rootElement.removeEventListener('click', handleEditorClick, true)
    rootElement.removeEventListener('contextmenu', handleTableActionContextMenu, true)
    rootElement.removeEventListener('contextmenu', scheduleToastTableContextMenuPlacement, true)
    document.removeEventListener('mousemove', handleTableSelectionMove, true)
    document.removeEventListener('mouseup', handleTableSelectionEnd, true)
    rootElement.removeEventListener('click', handleToastContextMenuClick, true)
    if (punctuationSelectionFrame !== null) {
      window.cancelAnimationFrame(punctuationSelectionFrame)
      punctuationSelectionFrame = null
    }
  }
}

const bindEditorHoverListeners = () => {
  cleanupEditorHoverListeners?.()

  if (!editorRoot.value) {
    cleanupEditorHoverListeners = null
    return
  }

  const handleMouseMove = (event) => {
    updateTableResizeHandle(event)
    updateHoverBlockHint(event)
  }

  document.addEventListener('mousemove', handleMouseMove, true)
  document.addEventListener('mousedown', handleTableResizeHandleDown, true)

  cleanupEditorHoverListeners = () => {
    document.removeEventListener('mousemove', handleMouseMove, true)
    document.removeEventListener('mousedown', handleTableResizeHandleDown, true)
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

  applyStoredTableLayoutsToEditor()
  currentMarkdown.value = getCurrentMarkdownWithTableLayouts()
  previewHtml.value = editorInstance.getHTML()
  floatingPreviewMode.value = 'body'
  floatingPreviewBodyHtml.value = ''
  hideFloatingPreview()
  hideImageToolbar()

  window.requestAnimationFrame(() => {
    decorateCodeBlocks()
    applyStoredTableLayoutsToEditor()
  })
}

const syncToolbarPosition = () => {
  if (isFixedToolbarMode.value) {
    hideToolbar()
    return
  }

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

  const wasSelectionInTable = toolbarSelectionInTable.value
  updateToolbarState()

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

  if (wasSelectionInTable !== toolbarSelectionInTable.value) {
    nextTick(() => {
      scheduleToolbarSync()
    })
  }
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

const applySelectedTableCellAlign = (align = null) => {
  const view = getWysiwygView()
  const selectedCells = collectSelectedTableCellEntries(view)

  if (!view || !selectedCells.length) {
    return
  }

  const tr = view.state.tr
  const nextAlign = align === 'left' ? null : align

  selectedCells.forEach(({ pos, node }) => {
    tr.setNodeMarkup(pos, null, {
      ...node.attrs,
      align: nextAlign,
    })
  })

  if (tr.docChanged) {
    view.dispatch(tr.scrollIntoView())
  }

  view.focus()
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
  } else if (command === 'tableCellAlignLeft') {
    applySelectedTableCellAlign('left')
  } else if (command === 'tableCellAlignCenter') {
    applySelectedTableCellAlign('center')
  } else if (command === 'tableCellAlignRight') {
    applySelectedTableCellAlign('right')
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

const createEmptyTableRow = (schema, cellType, columnCount) => {
  const { paragraph, tableRow } = schema.nodes
  const cells = Array.from({ length: columnCount }, () => cellType.create(null, paragraph.create()))
  return tableRow.create(null, cells)
}

const showTableSizeLimitMessage = () => {
  ElMessage.warning(`表格最多支持 ${MAX_TABLE_ROW_COUNT} 行 * ${MAX_TABLE_COLUMN_COUNT} 列`)
}

const normalizeTableInsertSize = (rowCount = 3, columnCount = 3) => ({
  rowCount: Math.min(Math.max(Number(rowCount) || 1, 1), MAX_TABLE_ROW_COUNT),
  columnCount: Math.min(Math.max(Number(columnCount) || 1, 1), MAX_TABLE_COLUMN_COUNT),
})

const createTableNode = (schema, rowCount = 3, columnCount = 3) => {
  const { table, tableHead, tableBody, tableHeadCell, tableBodyCell } = schema.nodes

  if (!table || !tableHead || !tableBody || !tableHeadCell || !tableBodyCell) {
    return null
  }

  const tableSize = normalizeTableInsertSize(rowCount, columnCount)
  const headRow = createEmptyTableRow(schema, tableHeadCell, tableSize.columnCount)
  const bodyRows = Array.from({ length: Math.max(tableSize.rowCount - 1, 1) }, () =>
    createEmptyTableRow(schema, tableBodyCell, tableSize.columnCount)
  )

  return table.create(null, [tableHead.create(null, headRow), tableBody.create(null, bodyRows)])
}

const findFirstTableCellTextPos = (doc, from, to) => {
  let textPos = null

  doc.nodesBetween(from, Math.min(to, doc.content.size), (node, pos, parent) => {
    if (textPos !== null) {
      return false
    }

    if (
      node.type.name === 'paragraph' &&
      (parent?.type?.name === 'tableHeadCell' || parent?.type?.name === 'tableBodyCell')
    ) {
      textPos = pos + 1
      return false
    }

    return true
  })

  return textPos
}

const applySelectedTable = (rows, columns) => {
  sideTablePickerVisible.value = false
  applyTable(rows, columns)
}

const toggleSideTablePicker = () => {
  if (!editorReady.value) {
    return
  }

  hideTableActionPanel()
  rememberEditorSelectionRange()
  sideTablePickerVisible.value = !sideTablePickerVisible.value
}

const applyTable = (rowCount = 3, columnCount = 3) => {
  if (!editorInstance) {
    return
  }

  const tableSize = normalizeTableInsertSize(rowCount, columnCount)
  if (tableSize.rowCount !== rowCount || tableSize.columnCount !== columnCount) {
    showTableSizeLimitMessage()
  }

  restoreInsertionSelection()

  const view = getWysiwygView()
  const selection = view?.state?.selection
  if (!view || !selection) {
    return
  }

  const tableNode = createTableNode(view.state.schema, tableSize.rowCount, tableSize.columnCount)
  if (!tableNode) {
    return
  }

  let tr = view.state.tr

  if (!selection.empty) {
    const insertPos = Math.min(selection.to, view.state.doc.content.size)
    tr = tr.setSelection(Selection.near(view.state.doc.resolve(insertPos), 1))
  }

  const insertPos = tr.selection.from
  tr.replaceSelectionWith(tableNode, false)

  const firstCellTextPos = findFirstTableCellTextPos(tr.doc, insertPos, insertPos + tableNode.nodeSize)
  if (firstCellTextPos !== null) {
    tr.setSelection(TextSelection.create(tr.doc, firstCellTextPos))
  }

  tr.scrollIntoView()
  view.dispatch(tr)
  view.focus()

  const tableIndex = getTableIndexFromTablePos(view, insertPos)
  const tableElement = tableIndex >= 0 ? getEditorLayoutTableElements()[tableIndex] : null
  const initialLayout = createDefaultTableLayout(tableElement, tableSize.rowCount, tableSize.columnCount)
  if (tableIndex >= 0) {
    const nextLayouts = [...tableLayoutMetadata]
    while (nextLayouts.length <= tableIndex) {
      nextLayouts.push(null)
    }
    nextLayouts[tableIndex] = initialLayout
    tableLayoutMetadata = trimTableLayoutMetadata(nextLayouts)
    updateEditorTableLayoutStyles()
  }

  updatePreviewFromEditor()
  updateToolbarState()
  updateFixedToolbarSnapshot()

  nextTick(() => {
    scheduleToolbarSync()
  })
}

const getTableRowsBySection = (tableNode) => {
  const tableHead = tableNode.child(0)
  const tableBody = tableNode.child(1)
  const headRows = []
  const bodyRows = []

  tableHead?.forEach?.((row) => {
    headRows.push(row)
  })

  tableBody?.forEach?.((row) => {
    bodyRows.push(row)
  })

  return { tableHead, tableBody, headRows, bodyRows }
}

const createEmptyTableCell = (schema, cellType, attrs = null) => {
  const paragraph = schema.nodes.paragraph
  return cellType.create(attrs, paragraph.create())
}

const getTableCellSpan = (cellNode, attrName) => {
  const value = Number(cellNode?.attrs?.[attrName])
  return Number.isFinite(value) && value > 1 ? value : 1
}

const isExtendedTableCell = (cellNode) => Boolean(cellNode?.attrs?.extended)

const getTableRowsByGlobalIndex = (tableInfo) => {
  if (!tableInfo?.tableNode) {
    return null
  }

  const { tableHead, tableBody, headRows, bodyRows } = getTableRowsBySection(tableInfo.tableNode)
  return {
    tableHead,
    tableBody,
    headRows,
    bodyRows,
    rows: [...headRows, ...bodyRows],
  }
}

const getTableCellNodeAt = (rows, rowIndex, columnIndex) => rows[rowIndex]?.child?.(columnIndex) || null

const getMergeTableCellSelectionInfo = (refreshTableInfo = true) => {
  const tableInfo = (refreshTableInfo ? getFreshActiveTableInfo() : activeTableInfo.value) || resolveTableInfoFromNativeSelectionRect()
  const selectionRect = nativeTableCellSelectionRect

  if (!tableInfo || !selectionRect || selectionRect.minRow === selectionRect.maxRow && selectionRect.minColumn === selectionRect.maxColumn) {
    return null
  }

  const rowInfo = getTableRowsByGlobalIndex(tableInfo)
  if (!rowInfo) {
    return null
  }

  const { rows, headRows } = rowInfo
  if (selectionRect.minRow < headRows.length) {
    return null
  }

  for (let rowIndex = selectionRect.minRow; rowIndex <= selectionRect.maxRow; rowIndex += 1) {
    for (let columnIndex = selectionRect.minColumn; columnIndex <= selectionRect.maxColumn; columnIndex += 1) {
      const cellNode = getTableCellNodeAt(rows, rowIndex, columnIndex)
      if (
        !cellNode ||
        cellNode.type?.name !== 'tableBodyCell' ||
        isExtendedTableCell(cellNode) ||
        getTableCellSpan(cellNode, 'rowspan') > 1 ||
        getTableCellSpan(cellNode, 'colspan') > 1
      ) {
        return null
      }
    }
  }

  return {
    ...rowInfo,
    tableInfo,
    selectionRect,
    rowSpan: selectionRect.maxRow - selectionRect.minRow + 1,
    colSpan: selectionRect.maxColumn - selectionRect.minColumn + 1,
  }
}

const getSplitTableCellInfo = (refreshTableInfo = true) => {
  const tableInfo = refreshTableInfo ? getFreshActiveTableInfo() : activeTableInfo.value
  if (!tableInfo || tableInfo.rowIndex < 1) {
    return null
  }

  const rowInfo = getTableRowsByGlobalIndex(tableInfo)
  if (!rowInfo) {
    return null
  }

  const cellNode = getTableCellNodeAt(rowInfo.rows, tableInfo.rowIndex, tableInfo.columnIndex)
  const rowSpan = getTableCellSpan(cellNode, 'rowspan')
  const colSpan = getTableCellSpan(cellNode, 'colspan')

  if (!cellNode || isExtendedTableCell(cellNode) || (rowSpan < 2 && colSpan < 2)) {
    return null
  }

  return {
    ...rowInfo,
    tableInfo,
    cellNode,
    rowSpan,
    colSpan,
  }
}

const rebuildTableNode = (schema, sourceTableNode, tableHead, tableBody, headRows, bodyRows) => {
  const { table, tableHead: tableHeadType, tableBody: tableBodyType } = schema.nodes
  return table.create(sourceTableNode.attrs || null, [
    tableHeadType.create(tableHead?.attrs || null, headRows),
    tableBodyType.create(tableBody?.attrs || null, bodyRows),
  ])
}

const getFreshActiveTableInfo = () => {
  const view = getWysiwygView()
  const tableInfo = activeTableInfo.value

  if (!view || !tableInfo) {
    return null
  }

  const tableNode = view.state.doc.nodeAt(tableInfo.tablePos)
  if (tableNode?.type?.name !== 'table') {
    return null
  }

  const rowCount = tableNode.child(0).childCount + tableNode.child(1).childCount
  const columnCount = tableNode.child(0).firstChild?.childCount || 0
  const nextTableInfo = {
    ...tableInfo,
    tableNode,
    rowIndex: Math.max(0, Math.min(tableInfo.rowIndex, rowCount - 1)),
    columnIndex: Math.max(0, Math.min(tableInfo.columnIndex, columnCount - 1)),
    rowCount,
    columnCount,
  }

  activeTableInfo.value = nextTableInfo
  return nextTableInfo
}

const replaceActiveTable = (nextTableNode, nextRowIndex, nextColumnIndex, nextLayout = null) => {
  const view = getWysiwygView()
  const tableInfo = getFreshActiveTableInfo()
  if (!view || !tableInfo) {
    return
  }

  const tableIndex = getTableIndexFromTablePos(view, tableInfo.tablePos)
  const rowCount = nextTableNode.child(0).childCount + nextTableNode.child(1).childCount
  const columnCount = nextTableNode.child(0).firstChild?.childCount || 0
  const safeRowIndex = Math.max(0, Math.min(nextRowIndex, rowCount - 1))
  const safeColumnIndex = Math.max(0, Math.min(nextColumnIndex, columnCount - 1))
  const tr = view.state.tr.replaceWith(
    tableInfo.tablePos,
    tableInfo.tablePos + tableInfo.tableNode.nodeSize,
    nextTableNode
  )
  const focusPos = findTableCellTextPos(tr.doc, tableInfo.tablePos, safeRowIndex, safeColumnIndex)

  if (focusPos !== null) {
    tr.setSelection(TextSelection.create(tr.doc, focusPos))
  }

  view.dispatch(tr.scrollIntoView())
  view.focus()

  if (nextLayout && tableIndex >= 0) {
    const nextLayouts = [...tableLayoutMetadata]
    while (nextLayouts.length <= tableIndex) {
      nextLayouts.push(null)
    }
    nextLayouts[tableIndex] = nextLayout
    tableLayoutMetadata = trimTableLayoutMetadata(nextLayouts)
  }

  activeTableInfo.value = {
    ...tableInfo,
    tableNode: nextTableNode,
    rowIndex: safeRowIndex,
    columnIndex: safeColumnIndex,
    rowCount,
    columnCount,
  }

  updatePreviewFromEditor()
  updateToolbarState()
  updateEditorTableLayoutStyles()

  nextTick(() => {
    scheduleToolbarSync()
  })
}

const findTableCellTextPos = (doc, tablePos, rowIndex, columnIndex) => {
  let currentRowIndex = -1
  let currentColumnIndex = -1
  let textPos = null
  const tableNode = doc.nodeAt(tablePos)

  if (!tableNode) {
    return null
  }

  doc.nodesBetween(tablePos, tablePos + tableNode.nodeSize, (node, pos) => {
    if (textPos !== null) {
      return false
    }

    if (node.type.name === 'tableRow') {
      currentRowIndex += 1
      currentColumnIndex = -1
      return true
    }

    if (node.type.name === 'tableHeadCell' || node.type.name === 'tableBodyCell') {
      currentColumnIndex += 1
      if (currentRowIndex === rowIndex && currentColumnIndex === columnIndex) {
        node.descendants((child, offset) => {
          if (child.type.name === 'paragraph') {
            textPos = pos + 1 + offset + 1
            return false
          }
          return true
        })
        return false
      }
    }

    return true
  })

  return textPos
}

const addTableColumn = (direction = 'right') => {
  const view = getWysiwygView()
  const tableInfo = getFreshActiveTableInfo()
  if (!view || !tableInfo) {
    return
  }

  if (tableInfo.columnCount >= MAX_TABLE_COLUMN_COUNT) {
    showTableSizeLimitMessage()
    return
  }

  const schema = view.state.schema
  const { tableRow, tableHeadCell, tableBodyCell } = schema.nodes
  const { tableHead, tableBody, headRows, bodyRows } = getTableRowsBySection(tableInfo.tableNode)
  const insertIndex = direction === 'left' ? tableInfo.columnIndex : tableInfo.columnIndex + 1
  const insertCell = (row, cellType) => {
    const cells = []
    row.forEach((cell) => {
      cells.push(cell)
    })
    cells.splice(insertIndex, 0, createEmptyTableCell(schema, cellType))
    return tableRow.create(row.attrs || null, cells)
  }
  const nextHeadRows = headRows.map((row) => insertCell(row, tableHeadCell))
  const nextBodyRows = bodyRows.map((row) => insertCell(row, tableBodyCell))
  const currentLayout = getTableLayoutForMutation(tableInfo)
  const nextColumns = [...currentLayout.layout.columns]
  nextColumns.splice(insertIndex, 0, getDefaultTableColumnWidth(currentLayout.tableElement))
  const nextLayout = {
    ...currentLayout.layout,
    width: sumLayoutSizes(nextColumns),
    columns: nextColumns,
  }

  replaceActiveTable(
    rebuildTableNode(schema, tableInfo.tableNode, tableHead, tableBody, nextHeadRows, nextBodyRows),
    tableInfo.rowIndex,
    insertIndex,
    nextLayout
  )
}

const deleteTableColumn = () => {
  const view = getWysiwygView()
  const tableInfo = getFreshActiveTableInfo()
  if (!view || !tableInfo || tableInfo.columnCount <= 1) {
    return
  }

  const schema = view.state.schema
  const tableRow = schema.nodes.tableRow
  const { tableHead, tableBody, headRows, bodyRows } = getTableRowsBySection(tableInfo.tableNode)
  const removeIndex = tableInfo.columnIndex
  const removeCell = (row) => {
    const cells = []
    row.forEach((cell, offset, index) => {
      if (index !== removeIndex) {
        cells.push(cell)
      }
    })
    return tableRow.create(row.attrs || null, cells)
  }
  const nextHeadRows = headRows.map(removeCell)
  const nextBodyRows = bodyRows.map(removeCell)
  const currentLayout = getTableLayoutForMutation(tableInfo)
  const nextColumns = currentLayout.layout.columns.filter((_, index) => index !== removeIndex)
  const nextLayout = {
    ...currentLayout.layout,
    width: sumLayoutSizes(nextColumns),
    columns: nextColumns,
  }

  replaceActiveTable(
    rebuildTableNode(schema, tableInfo.tableNode, tableHead, tableBody, nextHeadRows, nextBodyRows),
    tableInfo.rowIndex,
    Math.max(0, tableInfo.columnIndex - 1),
    nextLayout
  )
}

const addTableRow = (direction = 'below') => {
  const view = getWysiwygView()
  const tableInfo = getFreshActiveTableInfo()
  if (!view || !tableInfo) {
    return
  }

  if (tableInfo.rowCount >= MAX_TABLE_ROW_COUNT) {
    showTableSizeLimitMessage()
    return
  }

  const schema = view.state.schema
  const { tableHead, tableBody, headRows, bodyRows } = getTableRowsBySection(tableInfo.tableNode)
  const headRowCount = headRows.length
  const bodyRowIndex = tableInfo.rowIndex - headRowCount
  const insertBodyIndex =
    direction === 'above'
      ? Math.max(0, bodyRowIndex)
      : Math.min(Math.max(0, bodyRowIndex + 1), bodyRows.length)
  const nextRowIndex =
    direction === 'above'
      ? Math.max(headRowCount, tableInfo.rowIndex)
      : Math.max(headRowCount, tableInfo.rowIndex + 1)
  const nextBodyRows = [...bodyRows]

  nextBodyRows.splice(
    Math.min(insertBodyIndex, nextBodyRows.length),
    0,
    createEmptyTableRow(schema, schema.nodes.tableBodyCell, tableInfo.columnCount)
  )
  const currentLayout = getTableLayoutForMutation(tableInfo)
  const nextRows = [...(currentLayout.layout.rows || [])]
  nextRows.splice(nextRowIndex, 0, getDefaultTableRowHeight(currentLayout.tableElement))
  const nextLayout = {
    ...currentLayout.layout,
    height: sumLayoutSizes(nextRows),
    rows: nextRows,
  }

  replaceActiveTable(
    rebuildTableNode(schema, tableInfo.tableNode, tableHead, tableBody, headRows, nextBodyRows),
    nextRowIndex,
    tableInfo.columnIndex,
    nextLayout
  )
}

const deleteTableRow = () => {
  const view = getWysiwygView()
  const tableInfo = getFreshActiveTableInfo()
  if (!view || !tableInfo || !canDeleteSelectedTableRow.value) {
    return
  }

  const schema = view.state.schema
  const { tableHead, tableBody, headRows, bodyRows } = getTableRowsBySection(tableInfo.tableNode)
  const nextBodyRows = [...bodyRows]

  nextBodyRows.splice(tableInfo.rowIndex - 1, 1)
  const currentLayout = getTableLayoutForMutation(tableInfo)
  const nextRows = currentLayout.layout.rows.filter((_, index) => index !== tableInfo.rowIndex)
  const nextLayout = {
    ...currentLayout.layout,
    height: sumLayoutSizes(nextRows),
    rows: nextRows,
  }

  replaceActiveTable(
    rebuildTableNode(schema, tableInfo.tableNode, tableHead, tableBody, headRows, nextBodyRows),
    Math.max(1, tableInfo.rowIndex - 1),
    tableInfo.columnIndex,
    nextLayout
  )
}

const deleteActiveTable = () => {
  const view = getWysiwygView()
  const tableInfo = getFreshActiveTableInfo()
  if (!view || !tableInfo) {
    return
  }

  const paragraph = view.state.schema.nodes.paragraph.create()
  const tr = view.state.tr.replaceWith(
    tableInfo.tablePos,
    tableInfo.tablePos + tableInfo.tableNode.nodeSize,
    paragraph
  )

  tr.setSelection(TextSelection.create(tr.doc, tableInfo.tablePos + 1))
  view.dispatch(tr.scrollIntoView())
  view.focus()

  activeTableInfo.value = null
  clearNativeTableCellVisualSelection()
  hideTableSelectionOverlay()
  hideTableResizeHandle()
  hideTableHoverControl()
  hideTableActionPanel()
  updatePreviewFromEditor()
  updateToolbarState()
  ElMessage.success('已删除表格')

  nextTick(() => {
    scheduleToolbarSync()
  })
}

const mergeSelectedTableCells = () => {
  suppressNextTableEditorClick = false
  const view = getWysiwygView()
  const mergeInfo = getMergeTableCellSelectionInfo()
  if (!view || !mergeInfo) {
    ElMessage.warning('请先选择正文区域内连续的多个普通单元格。')
    return
  }

  const { tableInfo, tableHead, tableBody, headRows, bodyRows, selectionRect, rowSpan, colSpan } = mergeInfo
  const schema = view.state.schema
  const nextBodyRows = bodyRows.map((row, bodyRowIndex) => {
    const globalRowIndex = headRows.length + bodyRowIndex
    const cells = []

    row.forEach((cell, offset, columnIndex) => {
      if (
        globalRowIndex < selectionRect.minRow ||
        globalRowIndex > selectionRect.maxRow ||
        columnIndex < selectionRect.minColumn ||
        columnIndex > selectionRect.maxColumn
      ) {
        cells.push(cell)
        return
      }

      if (globalRowIndex === selectionRect.minRow && columnIndex === selectionRect.minColumn) {
        const contentNodes = []
        for (let rowIndex = selectionRect.minRow; rowIndex <= selectionRect.maxRow; rowIndex += 1) {
          const sourceBodyRow = bodyRows[rowIndex - headRows.length]
          for (let colIndex = selectionRect.minColumn; colIndex <= selectionRect.maxColumn; colIndex += 1) {
            const sourceCell = sourceBodyRow?.child?.(colIndex)
            if (!sourceCell) {
              continue
            }

            if (contentNodes.length === 0 || sourceCell.textContent.trim()) {
              sourceCell.forEach((child) => {
                contentNodes.push(child)
              })
            }
          }
        }

        cells.push(
          cell.type.create(
            {
              ...cell.attrs,
              colspan: colSpan > 1 ? colSpan : null,
              rowspan: rowSpan > 1 ? rowSpan : null,
              extended: null,
            },
            contentNodes.length ? contentNodes : [schema.nodes.paragraph.create()]
          )
        )
        return
      }

      cells.push(
        cell.type.create({
          ...cell.attrs,
          colspan: null,
          rowspan: null,
          extended: true,
        })
      )
    })

    return row.type.create(row.attrs || null, cells)
  })

  replaceActiveTable(
    rebuildTableNode(schema, tableInfo.tableNode, tableHead, tableBody, headRows, nextBodyRows),
    selectionRect.minRow,
    selectionRect.minColumn
  )
  clearNativeTableCellVisualSelection()
  hideTableActionPanel()
}

const splitSelectedTableCell = () => {
  suppressNextTableEditorClick = false
  const view = getWysiwygView()
  const splitInfo = getSplitTableCellInfo()
  if (!view || !splitInfo) {
    ElMessage.warning('请选择一个已合并的正文单元格。')
    return
  }

  const { tableInfo, tableHead, tableBody, headRows, bodyRows, cellNode, rowSpan, colSpan } = splitInfo
  const schema = view.state.schema
  const startBodyRowIndex = tableInfo.rowIndex - headRows.length
  const nextBodyRows = bodyRows.map((row, bodyRowIndex) => {
    const cells = []

    row.forEach((cell, offset, columnIndex) => {
      const insideSplitArea =
        bodyRowIndex >= startBodyRowIndex &&
        bodyRowIndex < startBodyRowIndex + rowSpan &&
        columnIndex >= tableInfo.columnIndex &&
        columnIndex < tableInfo.columnIndex + colSpan

      if (!insideSplitArea) {
        cells.push(cell)
        return
      }

      if (bodyRowIndex === startBodyRowIndex && columnIndex === tableInfo.columnIndex) {
        cells.push(
          cellNode.type.create(
            {
              ...cellNode.attrs,
              colspan: null,
              rowspan: null,
              extended: null,
            },
            cellNode.content
          )
        )
        return
      }

      cells.push(createEmptyTableCell(schema, cell.type, { ...cell.attrs, extended: null, colspan: null, rowspan: null }))
    })

    return row.type.create(row.attrs || null, cells)
  })

  replaceActiveTable(
    rebuildTableNode(schema, tableInfo.tableNode, tableHead, tableBody, headRows, nextBodyRows),
    tableInfo.rowIndex,
    tableInfo.columnIndex
  )
  hideTableActionPanel()
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
    language: 'zh-CN',
    usageStatistics: false,
    toolbarItems: [],
    autofocus: false,
    hooks: {
      addImageBlobHook: uploadEditorImage,
    },
    events: {
      change: () => {
        updatePreviewFromEditor()
        updateFixedToolbarSnapshot()
      },
      caretChange: () => {
        nextTick(() => {
          rememberEditorSelectionRange()
          updateFixedToolbarSnapshot()
          syncTableMultiCellSelectionState()
          scheduleToolbarSync()
        })
      },
      focus: () => {
        nextTick(() => {
          rememberEditorSelectionRange()
          updateFixedToolbarSnapshot()
          syncTableMultiCellSelectionState()
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
    rememberEditorSelectionRange()
    updateFixedToolbarSnapshot()
    bindEditorSelectionListeners()
    bindEditorHoverListeners()
  })
}

const setFormFromNote = (note) => {
  const parsedMarkdown = extractTableLayoutMetadata(note.markdown_content || '')

  form.title = note.title || ''
  form.tag_names = note.tags?.map((tag) => tag.name) || []
  tableLayoutMetadata = parsedMarkdown.layouts
  currentMarkdown.value = parsedMarkdown.markdown
  previewHtml.value = note.rendered_html || ''

  // 初始化 lastSavedContent，避免第一次自动保存触发
  lastSavedContent = note.markdown_content || ''

  if (editorInstance) {
    setEditorMarkdownFromStoredContent(note.markdown_content || '')
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

    const markdownContent = getCurrentMarkdownWithTableLayouts()
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

const formatDateTime = formatEditorDateTime

const getImageUploadErrorDetail = (error) => {
  const data = error.response?.data
  if (!data) {
    return '图片上传失败，请检查网络后重试。'
  }

  return (
    data.image?.[0] ||
    data.note_id?.[0] ||
    data.non_field_errors?.[0] ||
    data.detail ||
    '图片上传失败，请稍后重试。'
  )
}

const validateEditorImageFile = (file) => {
  if (!file?.type?.startsWith('image/')) {
    return '请选择 PNG、JPEG、GIF 或 WebP 图片文件。'
  }

  if (file.size > 8 * 1024 * 1024) {
    return `图片大小不能超过 8 MB，当前文件：${(file.size / 1024 / 1024).toFixed(2)} MB。`
  }

  return ''
}

const uploadEditorImageFile = async (file) => {
  const validationMessage = validateEditorImageFile(file)
  if (validationMessage) {
    ElMessage.warning(validationMessage)
    return null
  }

  const altText = file.name?.replace(/\.[^.]+$/, '') || 'image'
  const formData = new FormData()
  formData.append('note_id', route.params.id)
  formData.append('image', file)
  formData.append('alt_text', altText)

  try {
    const { data } = await api.post('/notes/images/', formData)
    return {
      ...data,
      alt_text: data.alt_text || altText,
    }
  } catch (error) {
    ElMessage.error(getImageUploadErrorDetail(error))
    return null
  }
}

const uploadEditorImage = async (blob, callback) => {
  const data = await uploadEditorImageFile(blob)
  if (data) {
    callback(data.image_url, data.alt_text)
    ElMessage.success('图片已上传并插入正文')
    updatePreviewFromEditor()
  }

  return false
}

const triggerEditorImageUpload = () => {
  if (!editorReady.value) {
    return
  }

  hideTableActionPanel()
  hideImageToolbar()
  sideTablePickerVisible.value = false
  rememberEditorSelectionRange()
  imageInsertInput.value?.click()
}

const handleImageInsertChange = async (event) => {
  const file = event.target.files?.[0]
  event.target.value = ''

  if (!file || !editorInstance) {
    return
  }

  const data = await uploadEditorImageFile(file)
  if (!data) {
    return
  }

  restoreInsertionSelection()
  editorInstance.exec('addImage', {
    imageUrl: data.image_url,
    altText: data.alt_text,
  })
  currentMarkdown.value = getCurrentMarkdownWithTableLayouts()
  updatePreviewFromEditor()
  rememberEditorSelectionRange()
  ElMessage.success('图片已上传并插入正文')
}

const normalizeImageReferenceValue = (value = '') => {
  try {
    return decodeURI(value).replace(/\\/g, '/')
  } catch {
    return value.replace(/\\/g, '/')
  }
}

const buildImageReferenceCandidates = (src = '') => {
  const normalizedSrc = normalizeImageReferenceValue(src)
  const candidates = new Set([src, normalizedSrc])

  try {
    const url = new URL(src, window.location.origin)
    candidates.add(url.href)
    candidates.add(url.pathname)
    candidates.add(`${url.pathname}${url.search}`)
    candidates.add(url.pathname.replace(/^\//, ''))
  } catch {
    // 非 URL 字符串只使用原始候选。
  }

  return Array.from(candidates).filter(Boolean)
}

const findMarkdownImageMatch = (markdown, imageSrc) => {
  const candidates = buildImageReferenceCandidates(imageSrc)
  const imagePattern = /!\[([^\]]*)\]\(([^)\s]+)(?:\s+["'][^"']*["'])?\)/g
  let match = imagePattern.exec(markdown)

  while (match) {
    const referenceUrl = normalizeImageReferenceValue(match[2])
    if (candidates.some((candidate) => referenceUrl === normalizeImageReferenceValue(candidate))) {
      return {
        start: match.index,
        end: match.index + match[0].length,
        alt: match[1],
        url: match[2],
      }
    }

    match = imagePattern.exec(markdown)
  }

  const fallbackCandidate = candidates.find((candidate) => markdown.includes(candidate))
  if (fallbackCandidate) {
    const start = markdown.indexOf(fallbackCandidate)
    return {
      start,
      end: start + fallbackCandidate.length,
      alt: '',
      url: fallbackCandidate,
    }
  }

  return null
}

const updateEditorMarkdown = (markdown) => {
  setEditorMarkdownFromStoredContent(markdown)
  currentMarkdown.value = getCurrentMarkdownWithTableLayouts()
  updatePreviewFromEditor()
}

const replaceActiveImageMarkdown = (replacementMarkdown) => {
  if (!activeEditorImage.value?.src || !editorInstance) {
    return false
  }

  const markdown = getCurrentMarkdownWithTableLayouts()
  const match = findMarkdownImageMatch(markdown, activeEditorImage.value.src)
  if (!match) {
    ElMessage.warning('没有在正文中找到这张图片的引用。')
    return false
  }

  const nextMarkdown = `${markdown.slice(0, match.start)}${replacementMarkdown}${markdown.slice(match.end)}`
  updateEditorMarkdown(nextMarkdown)
  hideImageToolbar()
  return true
}

const findImageRecordBySrc = async (src) => {
  let page = 1

  while (page <= 20) {
    const { data } = await api.get('/notes/images/', {
      params: {
        note_id: route.params.id,
        page,
        page_size: 60,
      },
    })
    const candidates = buildImageReferenceCandidates(src).map(normalizeImageReferenceValue)
    const imageRecord = (data.results || []).find((image) =>
      candidates.includes(normalizeImageReferenceValue(image.image_url || ''))
    )

    if (imageRecord || !data.next) {
      return imageRecord || null
    }

    page += 1
  }

  return null
}

const hideImageToolbar = () => {
  imageToolbarVisible.value = false
  activeEditorImage.value = null
  imageToolbarPosition.top = -9999
  imageToolbarPosition.left = -9999
}

const showImageToolbar = (imageElement) => {
  const rect = imageElement.getBoundingClientRect()
  activeEditorImage.value = {
    src: imageElement.getAttribute('src') || '',
    alt: imageElement.getAttribute('alt') || '',
  }
  imageToolbarPosition.top = Math.max(12, rect.top - 48)
  imageToolbarPosition.left = Math.min(
    Math.max(12, rect.left),
    Math.max(12, window.innerWidth - 236)
  )
  imageToolbarVisible.value = true
  hideToolbar()
  hideTableActionPanel()
  hideTableHoverControl()
}

const getImageElementFromEvent = (event) => {
  const target = event.target instanceof Element ? event.target : null
  const imageElement = target?.closest?.('.toastui-editor-contents img')
  return imageElement instanceof HTMLImageElement ? imageElement : null
}

const viewActiveImage = () => {
  if (!activeEditorImage.value?.src) {
    return
  }

  window.open(activeEditorImage.value.src, '_blank', 'noopener,noreferrer')
}

const triggerImageReplacement = () => {
  if (!activeEditorImage.value?.src) {
    return
  }

  imageReplaceInput.value?.click()
}

const handleImageReplacementChange = async (event) => {
  const file = event.target.files?.[0]
  event.target.value = ''

  if (!file || !activeEditorImage.value?.src) {
    return
  }

  const data = await uploadEditorImageFile(file)
  if (!data) {
    return
  }

  const safeAltText = (data.alt_text || activeEditorImage.value.alt || 'image').replaceAll(']', '\\]')
  if (replaceActiveImageMarkdown(`![${safeAltText}](${data.image_url})`)) {
    ElMessage.success('图片已替换，旧图片可在孤儿图片中清理。')
  }
}

const deleteActiveImage = async () => {
  if (!activeEditorImage.value?.src) {
    return
  }

  let shouldDeleteFile = false
  try {
    await ElMessageBox.confirm(
      '要同时删除这张图片的文件吗？',
      '删除图片',
      {
        confirmButtonText: '删除引用和文件',
        cancelButtonText: '只删除引用',
        distinguishCancelAndClose: true,
        type: 'warning',
      }
    )
    shouldDeleteFile = true
  } catch (action) {
    if (action === 'cancel') {
      shouldDeleteFile = false
    } else {
      return
    }
  }

  const imageSrc = activeEditorImage.value.src
  const deletedReference = replaceActiveImageMarkdown('')
  if (!deletedReference) {
    return
  }

  if (!shouldDeleteFile) {
    ElMessage.success('已删除正文中的图片引用。')
    return
  }

  try {
    const imageRecord = await findImageRecordBySrc(imageSrc)
    if (!imageRecord) {
      ElMessage.warning('已删除引用，但未找到对应图片文件记录。')
      return
    }

    await api.delete(`/notes/images/${imageRecord.id}/`)
    ElMessage.success('已删除图片引用和文件。')
  } catch (error) {
    const detail = error.response?.data?.detail || '已删除引用，但图片文件删除失败。'
    ElMessage.warning(detail)
  }
}

// 定时自动保存，间隔由偏好设置控制。
const autoSave = async () => {
  if (!editorInstance || !editorSettings.value.autoSaveEnabled) return

  const currentContent = getCurrentMarkdownWithTableLayouts()

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
  stopAutoSave()

  if (!editorSettings.value.autoSaveEnabled) {
    return
  }

  autoSaveTimer = setInterval(() => {
    autoSave()
  }, editorSettings.value.autoSaveIntervalMs)
}

// 停止自动保存
const stopAutoSave = () => {
  if (autoSaveTimer) {
    clearInterval(autoSaveTimer)
    autoSaveTimer = null
  }
}

const handleEditorSettingsChange = (event) => {
  editorSettings.value = event.detail || getEditorSettings()
  if (isFixedToolbarMode.value) {
    hideToolbar()
    sideTablePickerVisible.value = false
    nextTick(updateFixedToolbarSnapshot)
  }
  startAutoSave()
}

// 手动保存（Ctrl+S）
const handleManualSave = async () => {
  if (!editorInstance) return

  const currentContent = getCurrentMarkdownWithTableLayouts()

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
    lastSavedContent = data.markdown_content

    ElMessage.success('已恢复到选定版本')
    await fetchVersions()
  } catch (error) {
    ElMessage.error('恢复版本失败')
  }
}

const handleDocumentSelection = () => {
  nextTick(() => {
    rememberEditorSelectionRange()
    updateFixedToolbarSnapshot()
    syncTableMultiCellSelectionState()
    scheduleToolbarSync()

    window.requestAnimationFrame(() => {
      syncTableMultiCellSelectionState()
    })
  })
}

watch(
  () => form.title,
  () => {
    floatingPreviewMode.value = 'title'
    floatingPreviewBodyHtml.value = buildTitlePreviewHtml(form.title)
    showFloatingPreview()
  }
)

watch(
  () => form.tag_names.join('|'),
  () => {
    floatingPreviewMode.value = 'tags'
    floatingPreviewBodyHtml.value = buildTagPreviewHtml(form.tag_names)
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
  window.addEventListener(EDITOR_SETTINGS_CHANGE_EVENT, handleEditorSettingsChange)

  document.addEventListener('selectionchange', handleDocumentSelection)
  window.addEventListener('resize', hideToolbar)
  window.addEventListener('resize', hideTableActionPanel)
  window.addEventListener('resize', hideTableHoverControl)
  window.addEventListener('resize', hideTableResizeHandle)
  window.addEventListener('resize', hideImageToolbar)
  window.addEventListener('resize', refreshTableSelectionOverlay)
  window.addEventListener('scroll', scheduleToolbarSync, true)
  window.addEventListener('scroll', hideTableActionPanel, true)
  window.addEventListener('scroll', hideTableHoverControl, true)
  window.addEventListener('scroll', hideTableResizeHandle, true)
  window.addEventListener('scroll', hideImageToolbar, true)
  window.addEventListener('scroll', refreshTableSelectionOverlay, true)
  document.addEventListener('scroll', scheduleToolbarSync, true)
  document.addEventListener('scroll', hideTableHoverControl, true)
  document.addEventListener('scroll', hideTableResizeHandle, true)
  document.addEventListener('scroll', hideImageToolbar, true)
  document.addEventListener('scroll', refreshTableSelectionOverlay, true)
})

onBeforeUnmount(() => {
  // 清理定时器
  stopAutoSave()

  // 移除键盘快捷键监听
  document.removeEventListener('keydown', handleKeyboardShortcut)
  window.removeEventListener(EDITOR_SETTINGS_CHANGE_EVENT, handleEditorSettingsChange)

  document.removeEventListener('selectionchange', handleDocumentSelection)
  window.removeEventListener('resize', hideToolbar)
  window.removeEventListener('resize', hideTableActionPanel)
  window.removeEventListener('resize', hideTableHoverControl)
  window.removeEventListener('resize', hideTableResizeHandle)
  window.removeEventListener('resize', hideImageToolbar)
  window.removeEventListener('resize', refreshTableSelectionOverlay)
  window.removeEventListener('scroll', scheduleToolbarSync, true)
  window.removeEventListener('scroll', hideTableActionPanel, true)
  window.removeEventListener('scroll', hideTableHoverControl, true)
  window.removeEventListener('scroll', hideTableResizeHandle, true)
  window.removeEventListener('scroll', hideImageToolbar, true)
  window.removeEventListener('scroll', refreshTableSelectionOverlay, true)
  document.removeEventListener('scroll', scheduleToolbarSync, true)
  document.removeEventListener('scroll', hideTableHoverControl, true)
  document.removeEventListener('scroll', hideTableResizeHandle, true)
  document.removeEventListener('scroll', hideImageToolbar, true)
  document.removeEventListener('scroll', refreshTableSelectionOverlay, true)
  cancelToolbarSync()
  cleanupEditorSelectionListeners?.()
  cleanupEditorSelectionListeners = null
  cleanupEditorHoverListeners?.()
  cleanupEditorHoverListeners = null
  cancelToastContextMenuSync()
  hideHoverBlockHint()
  hideTableHoverControl()
  hideTableActionPanel()
  stopTableResizeDrag()
  hideTableResizeHandle()
  hideTableSelectionOverlay()
  tableLayoutStyleElement?.remove()
  tableLayoutStyleElement = null
  clearNativeTableCellVisualSelection()
  nativeTableCellSelectionStyleElement?.remove()
  nativeTableCellSelectionStyleElement = null
  hideFloatingPreview()
  finishInlineCodeLanguageEdit(false)
  editorInstance?.destroy()
  editorInstance = null
})
</script>

<template>
  <main class="edit-page page-shell">
    <WorkspaceShell>
      <section class="edit-stage" v-loading="loading" :style="editorFontSizeStyle">
        <NoteEditHeader
          :saving="saving"
          :auto-save-enabled="editorSettings.autoSaveEnabled"
          :auto-save-status-text="autoSaveStatusText"
          @back="goToDetail"
          @save="saveNote"
        />

        <section class="editor-layout fade-rise-enter-delay">
          <article class="editor-main">
            <NoteEditorPanel
              v-model:title="form.title"
              v-model:tag-input-value="tagInputValue"
              :tags="form.tag_names"
              :tag-input-visible="tagInputVisible"
              :word-count="wordCount"
              @remove-tag="handleTagRemove"
              @show-tag-input="showTagInput"
              @confirm-tag-input="handleTagInputConfirm"
              @cancel-tag-input="cancelTagInput"
            >
              <template #editor>
                <FixedEditorToolbar
                  v-if="isFixedToolbarMode"
                  :editor-ready="editorReady"
                  :toolbar-state="fixedToolbarState"
                  :selected-text="fixedToolbarSelectedText"
                  :heading-options="headingOptions"
                  :max-table-rows="MAX_TABLE_ROW_COUNT"
                  :max-table-columns="MAX_TABLE_COLUMN_COUNT"
                  @remember-selection="rememberFixedToolbarSelection"
                  @command="runFixedToolbarCommand"
                  @apply-heading="applyFixedToolbarHeading"
                  @insert-link="insertFixedToolbarLink"
                  @insert-image="triggerEditorImageUpload"
                  @insert-table="applyTable"
                />
                <div
                  ref="editorRoot"
                  class="wysiwyg-editor"
                  :class="{ 'is-editor-empty': !currentMarkdown.trim() }"
                  :data-placeholder="editorPlaceholder"
                ></div>
                <input
                  ref="imageInsertInput"
                  class="image-replace-input"
                  type="file"
                  accept="image/png,image/jpeg,image/gif,image/webp"
                  @change="handleImageInsertChange"
                />
                <input
                  ref="imageReplaceInput"
                  class="image-replace-input"
                  type="file"
                  accept="image/png,image/jpeg,image/gif,image/webp"
                  @change="handleImageReplacementChange"
                />
              </template>
            </NoteEditorPanel>
          </article>

          <div
            v-if="imageToolbarVisible"
            class="editor-image-toolbar"
            :style="{ top: `${imageToolbarPosition.top}px`, left: `${imageToolbarPosition.left}px` }"
            @mousedown.prevent
          >
            <button type="button" @click="viewActiveImage">查看</button>
            <button type="button" @click="triggerImageReplacement">替换</button>
            <button type="button" class="danger" @click="deleteActiveImage">删除</button>
          </div>

          <FloatingFormatToolbar
            v-if="!isFixedToolbarMode"
            ref="floatingToolbar"
            :visible="toolbarVisible"
            :position="toolbarPosition"
            :toolbar-state="toolbarState"
            :selection-in-table="toolbarSelectionInTable"
            :heading-options="headingOptions"
            @command="runEditorCommand"
            @apply-heading="applyHeading"
            @apply-block-quote="applyBlockQuote"
            @apply-code-block="applyCodeBlock"
            @apply-code-block-auto-format="applyCodeBlockAutoFormat"
            @apply-horizontal-rule="applyHorizontalRule"
          />

          <EditorTableOverlays
            :hover-block-hint-visible="hoverBlockHintVisible"
            :hover-block-hint="hoverBlockHint"
            :table-hover-control-visible="tableHoverControlVisible"
            :table-hover-control-position="tableHoverControlPosition"
            :table-selection-overlay="tableSelectionOverlay"
            :table-resize-handle-visible="tableResizeHandleVisible"
            :table-resize-handle="tableResizeHandle"
            :table-resize-handle-dragging="tableResizeHandleDragging"
            :table-resize-size-hint="tableResizeSizeHint"
            @open-action-panel="openTableActionPanelFromHoverControl"
            @start-resize="startTableResizeDrag"
          />
        </section>

        <VersionHistoryDrawer
          :visible="versionDrawerVisible"
          :versions="versions"
          :format-date-time="formatDateTime"
          @close="closeVersionDrawer"
          @preview="previewVersion"
          @toggle="toggleVersionDrawer"
        />

        <SideTableToolbar
          v-if="!isFixedToolbarMode"
          v-model:visible="sideTablePickerVisible"
          :editor-ready="editorReady"
          @remember-selection="rememberEditorSelectionRange"
          @insert-image="triggerEditorImageUpload"
          @toggle="toggleSideTablePicker"
          @select="applySelectedTable"
        />

        <TableActionPanel
          :visible="tableActionPanelVisible"
          :position="tableActionPanelPosition"
          :active-table-info="activeTableInfo"
          :active-table-alignment="activeTableAlignment"
          :can-add-selected-table-row="canAddSelectedTableRow"
          :can-add-selected-table-column="canAddSelectedTableColumn"
          :can-merge-selected-table-cells="canMergeSelectedTableCells"
          :can-split-selected-table-cell="canSplitSelectedTableCell"
          :can-delete-selected-table-row="canDeleteSelectedTableRow"
          :can-delete-selected-table-column="canDeleteSelectedTableColumn"
          @add-row="addTableRow"
          @add-column="addTableColumn"
          @merge-cells="mergeSelectedTableCells"
          @split-cell="splitSelectedTableCell"
          @delete-row="deleteTableRow"
          @delete-column="deleteTableColumn"
          @delete-table="deleteActiveTable"
          @reset-layout="resetActiveTableLayout"
          @align-table="applyActiveTableAlignment"
        />

        <FloatingPreview
          :visible="floatingPreviewVisible"
          :title="resolveFloatingPreviewTitle(floatingPreviewMode)"
          :ready="editorReady"
          :body-html="floatingPreviewBodyHtml"
        />
      </section>
    </WorkspaceShell>

    <VersionPreviewDialog
      v-model:visible="versionPreview.visible"
      :version="versionPreview.version"
      :format-date-time="formatDateTime"
      @close="closeVersionPreview"
      @restore="restoreVersion"
    />
  </main>
</template>

<style scoped>
.edit-page {
  padding: 20px;
  overflow-x: hidden;
}

.edit-stage {
  min-height: calc(100vh - 20px);
  min-height: calc(100svh - 20px);
  margin-top: 20px;
}

.editor-layout {
  display: grid;
  grid-template-columns: 1fr;
  gap: 26px;
  align-items: start;
  margin-top: 34px;
}

.editor-main {
  display: grid;
  gap: 22px;
  min-width: 0;
  max-width: 100%;
  padding: 0;
}

.wysiwyg-editor :deep(.toastui-editor-context-menu) {
  position: fixed !important;
  z-index: 230;
  max-height: calc(100svh - 24px);
  overflow-y: auto;
  overscroll-behavior: contain;
}

.wysiwyg-editor {
  position: relative;
  min-width: 0;
  max-width: 100%;
  min-height: 560px;
}

.wysiwyg-editor.is-editor-empty::before {
  position: absolute;
  z-index: 1;
  top: 22px;
  left: 24px;
  color: #94a3b8;
  line-height: 1.95;
  pointer-events: none;
  content: attr(data-placeholder);
}

.image-replace-input {
  display: none;
}

.editor-image-toolbar {
  position: fixed;
  z-index: 240;
  display: inline-flex;
  gap: 6px;
  align-items: center;
  padding: 6px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 8px;
  background: var(--surface);
  box-shadow: var(--shadow-soft);
}

.editor-image-toolbar button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 54px;
  min-height: 32px;
  padding: 0 10px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  font-size: 0.82rem;
  font-weight: 700;
  cursor: pointer;
  transition:
    border-color 0.18s ease,
    background-color 0.18s ease,
    color 0.18s ease;
}

.editor-image-toolbar button:hover {
  border-color: var(--accent-border);
  background: var(--accent-soft);
  color: var(--accent);
}

.editor-image-toolbar button.danger:hover {
  border-color: color-mix(in srgb, var(--danger) 34%, transparent);
  background: var(--danger-soft);
  color: var(--danger);
}

.wysiwyg-editor :deep(.toastui-editor-defaultUI) {
  height: auto !important;
  max-width: 100%;
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
  min-width: 0;
  max-width: 100%;
  overflow-x: hidden;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.9);
}

.wysiwyg-editor :deep(.toastui-editor-main-container) {
  height: auto !important;
  min-width: 0;
  max-width: 100%;
  overflow-x: hidden !important;
  font-family: 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.wysiwyg-editor :deep(.toastui-editor-ww-container) {
  height: auto !important;
  min-width: 0;
  max-width: 100%;
  overflow-x: hidden !important;
  background: transparent;
}

.wysiwyg-editor :deep(.toastui-editor-contents) {
  min-height: 520px;
  max-width: 100%;
  overflow-x: hidden;
  padding: 22px 24px;
  color: var(--brand-navy);
  font-size: var(--editor-font-size, 1rem);
  line-height: 1.95;
  overflow-wrap: anywhere;
  word-break: break-word;
  font-family: inherit;
}

.wysiwyg-editor :deep(.toastui-editor-contents pre),
.wysiwyg-editor :deep(.toastui-editor-contents code),
.wysiwyg-editor :deep(.toastui-editor-contents .toastui-editor-ww-code-block),
.wysiwyg-editor :deep(.toastui-editor-contents .toastui-editor-ww-code-block code) {
  font-family: 'Cascadia Code', 'Consolas', monospace;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.wysiwyg-editor :deep(.toastui-editor-contents pre),
.wysiwyg-editor :deep(.toastui-editor-contents .toastui-editor-ww-code-block) {
  max-width: 100%;
  overflow-x: hidden;
  white-space: pre-wrap;
}

.wysiwyg-editor :deep(.toastui-editor-contents :not(pre) > code) {
  white-space: normal;
  overflow-wrap: anywhere;
  word-break: break-word;
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

.wysiwyg-editor :deep(.toastui-editor-contents table) {
  width: 100%;
  inline-size: 100%;
  max-width: 100%;
  max-inline-size: 100%;
  min-width: 0;
  min-inline-size: 0;
  margin: 18px 0;
  border: 1px solid rgba(100, 116, 139, 0.42);
  border-collapse: collapse;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.8);
  box-shadow: inset 0 0 0 1px rgba(100, 116, 139, 0.18);
  table-layout: fixed;
  overflow: hidden;
  box-sizing: border-box;
}

.wysiwyg-editor :deep(.toastui-editor-contents thead th) {
  background: rgba(15, 23, 42, 0.07);
}

.wysiwyg-editor :deep(.toastui-editor-contents th),
.wysiwyg-editor :deep(.toastui-editor-contents td) {
  min-width: 0;
  max-width: 0;
  padding: 12px 14px;
  border-right: 1px solid rgba(100, 116, 139, 0.36);
  border-bottom: 1px solid rgba(100, 116, 139, 0.36);
  overflow-wrap: anywhere;
  word-break: break-word;
  vertical-align: top;
}

.wysiwyg-editor :deep(.toastui-editor-contents th[extended]),
.wysiwyg-editor :deep(.toastui-editor-contents td[extended]) {
  display: none;
}

.wysiwyg-editor :deep(.toastui-editor-contents th:not([align])),
.wysiwyg-editor :deep(.toastui-editor-contents td:not([align])) {
  text-align: left;
}

.wysiwyg-editor :deep(.toastui-editor-contents table *::selection) {
  background: rgba(147, 197, 253, 0.34);
  color: inherit;
}

.wysiwyg-editor :deep(.toastui-editor-contents th.toastui-editor-cell-selected),
.wysiwyg-editor :deep(.toastui-editor-contents td.toastui-editor-cell-selected),
.wysiwyg-editor :deep(.toastui-editor-contents th.moonbird-native-cell-selected),
.wysiwyg-editor :deep(.toastui-editor-contents td.moonbird-native-cell-selected) {
  border-color: rgba(37, 99, 235, 0.42) !important;
  background: rgba(191, 219, 254, 0.2) !important;
  background-color: rgba(191, 219, 254, 0.2) !important;
  box-shadow:
    inset 0 0 0 9999px rgba(191, 219, 254, 0.18),
    inset 0 0 0 1px rgba(37, 99, 235, 0.34);
  color: #111827;
}

.wysiwyg-editor :deep(.toastui-editor-contents th.toastui-editor-cell-selected *),
.wysiwyg-editor :deep(.toastui-editor-contents td.toastui-editor-cell-selected *),
.wysiwyg-editor :deep(.toastui-editor-contents th.moonbird-native-cell-selected *),
.wysiwyg-editor :deep(.toastui-editor-contents td.moonbird-native-cell-selected *) {
  background: transparent !important;
  color: inherit !important;
}

.wysiwyg-editor :deep(.toastui-editor-contents th:last-child),
.wysiwyg-editor :deep(.toastui-editor-contents td:last-child) {
  border-right: none;
}

.wysiwyg-editor :deep(.toastui-editor-contents tr:last-child td) {
  border-bottom: none;
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

@media (max-width: 1380px) {
  .editor-layout {
    grid-template-columns: 1fr;
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
  .editor-main {
    padding: 0;
  }

  .wysiwyg-editor :deep(.inline-code-language-chip),
  .wysiwyg-editor :deep(.inline-code-language-input) {
    right: 12px;
    min-width: 68px;
  }
}

@media (max-width: 520px) {
  .editor-main {
    padding: 0;
  }

  .editor-head {
    align-items: flex-start;
    flex-direction: column;
  }

  .wysiwyg-editor :deep(.toastui-editor-contents) {
    min-height: 420px;
    padding: 18px 16px;
  }

}
</style>
