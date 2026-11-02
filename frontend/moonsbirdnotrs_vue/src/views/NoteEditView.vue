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
import BodyPreviewDialog from '../editor/components/BodyPreviewDialog.vue'
import CodeBlockOptionsDialog from '../editor/components/CodeBlockOptionsDialog.vue'
import EditorTableOverlays from '../editor/components/EditorTableOverlays.vue'
import FixedEditorToolbar from '../editor/components/FixedEditorToolbar.vue'
import FloatingPreview from '../editor/components/FloatingPreview.vue'
import NoteEditorPanel from '../editor/components/NoteEditorPanel.vue'
import NoteEditHeader from '../editor/components/NoteEditHeader.vue'
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
import { getFenceLanguage, replaceFenceLanguage } from '../utils/fenceInfo'
import { buildEditorTableLayoutCss } from '../utils/tableLayoutCss'
import {
  buildTableCellSelectionRect,
  collectCellsInSelectionRect,
  doRectsIntersect,
  resolveTableCellPosition,
} from '../utils/tableSelection'
import {
  computeTableResizeLayout,
  normalizeResizeColumns,
  normalizeResizeRows,
} from '../utils/tableResize'
import { createRichBlockPreview } from '../utils/editorDecorations'
import { renderMarkdownPreview } from '../utils/markdownPreview'
import { sanitizePreviewHtml } from '../utils/previewSanitizer'
import { applyWysiwygCallout, getActiveCalloutType } from '../utils/wysiwygBlocks'
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
const activeCalloutType = ref('')
const tableMultiCellSelectionActive = ref(false)
const tableActionPanelVisible = ref(false)
const tableHoverControlVisible = ref(false)
const tableResizeHandleVisible = ref(false)
const tableResizeHandleDragging = ref(false)
const activeTableInfo = ref(null)
const floatingPreviewVisible = ref(false)
const editorSettings = ref(getEditorSettings())
const editorPlaceholder = '在这里直接编辑笔记正文'
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

const previewHtml = ref('')
const bodyPreviewVisible = ref(false)
const bodyPreviewHtml = ref('')
const floatingPreviewBodyHtml = ref('')
const currentMarkdown = ref('')
const codeOptionsVisible = ref(false)
const codeOptionsInfo = ref('')
const codeOptionsCode = ref('')
const codeOptionsTarget = ref(null)
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
let floatingPreviewTimer = null
let cleanupEditorSelectionListeners = null
let toolbarStateFrame = null
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

    // 选择器要现场算（依赖编辑器 DOM 路径），样式规则本身由 util 生成。
    const result = buildEditorTableLayoutCss(tableElement, tableIndex, layout, getEditorTableCssSelector)
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
    return serializeMarkdownWithTableLayouts(currentMarkdown.value || '', tableLayoutMetadata)
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

const getDomTableCellPosition = (cellElement) => {
  // 行列号换算在 utils/tableSelection.js（有单测），这里只补上「第几张表」。
  return resolveTableCellPosition(cellElement, getEditorTableElements().indexOf(cellElement?.closest?.('table')))
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

const getTableCellsFromSelectionRect = (selectionRect) => {
  if (!selectionRect) {
    return []
  }

  const tableElement = getEditorTableElements()[selectionRect.tableIndex]
  if (!tableElement) {
    return []
  }

  return collectCellsInSelectionRect(tableElement.rows, selectionRect)
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
    element?.closest?.('.table-action-panel, .table-hover-control, .fixed-editor-toolbar')
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

  // 位移到布局的换算全部收在 utils/tableResize.js（有单测），这里只负责把结果落到 DOM。
  const nextLayout = computeTableResizeLayout({
    kind,
    delta,
    deltaY,
    startWidth,
    startHeight,
    startColumns,
    startRows,
    maxWidth,
    minWidth,
    minColumnWidth,
    minHeight,
    columnIndex,
    rowIndex,
  })

  if (!nextLayout) {
    return
  }

  const nextWidth = nextLayout.width
  const nextHeight = nextLayout.height
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
      ? `${Math.round(appliedLayout.rows?.[rowIndex] || nextLayout.rows?.[rowIndex] || tableRect.height)}px`
      : `${Math.round(appliedLayout.columns?.[columnIndex] || nextLayout.columns?.[columnIndex])}px / ${Math.round(
          appliedLayout.columns?.[columnIndex + 1] || nextLayout.columns?.[columnIndex + 1]
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

const tableCellTypeNames = ['tableHeadCell', 'tableBodyCell']

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

const cancelToolbarStateSync = () => {
  if (toolbarStateFrame !== null) {
    window.cancelAnimationFrame(toolbarStateFrame)
    toolbarStateFrame = null
  }
}

const scheduleToolbarStateSync = () => {
  if (toolbarStateFrame !== null) {
    return
  }

  toolbarStateFrame = window.requestAnimationFrame(() => {
    toolbarStateFrame = null
    syncToolbarState()
  })
}

const isRectInViewport = (rect) =>
  rect.bottom > 0 &&
  rect.top < window.innerHeight &&
  rect.right > 0 &&
  rect.left < window.innerWidth

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

const getWysiwygView = () => editorInstance?.wwEditor?.view || null

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

/**
 * 插入一段 Markdown 片段。
 *
 * 块级片段（`$$…$$`）**不替换选中正文**：用户常先 Ctrl+A 再点按钮，
 * 按替换处理会清空整篇笔记。只有行内公式 `$…$` 才把选中文字包进去。
 */
const insertMarkdownSnippet = (before, after = '', placeholder = '', options = {}) => {
  const view = getWysiwygView()
  if (!view || !editorInstance) {
    return
  }

  restoreInsertionSelection()

  const { state } = view
  const { from, to } = state.selection
  const selected = state.doc.textBetween(from, to, '\n')
  const wrapsSelection = Boolean(options.wrapSelection) && Boolean(selected.trim())

  // 不包裹时把插入点折叠到选区末尾，原内容原样保留
  const insertFrom = wrapsSelection ? from : to
  const insertTo = to
  const body = wrapsSelection ? selected : placeholder
  const text = `${before}${body}${after}`

  const tr = state.tr.insertText(text, insertFrom, insertTo)

  if (wrapsSelection) {
    const caret = insertFrom + text.length
    tr.setSelection(TextSelection.create(tr.doc, caret, caret))
  } else if (placeholder) {
    // 选中占位文本，方便直接输入覆盖
    const placeholderStart = insertFrom + before.length
    tr.setSelection(TextSelection.create(tr.doc, placeholderStart, placeholderStart + placeholder.length))
  }

  tr.scrollIntoView()
  view.dispatch(tr)

  syncAfterFixedToolbarCommand()
}

/** 提示框按钮：同类型再点一次取消，换类型则就地改类型（不嵌套）。 */
const applyFixedToolbarCallout = (kind = 'note') => {
  const view = getWysiwygView()
  if (!view) {
    ElMessage.warning('编辑器尚未准备好，请稍后重试。')
    return
  }

  restoreInsertionSelection()

  const handled = applyWysiwygCallout(view, { kind })
  if (!handled) {
    ElMessage.warning('编辑器尚未准备好，请稍后重试。')
    return
  }

  syncAfterFixedToolbarCommand()
}

const insertFixedToolbarMath = (displayMode) => {
  if (displayMode) {
    insertMarkdownSnippet('$$\n', '\n$$', 'E = mc^2')
    return
  }
  insertMarkdownSnippet('$', '$', 'x^2', { wrapSelection: true })
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
      scheduleToolbarStateSync()

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
      hideTableActionPanel()
      showTableHoverControl(focusCellElement, event.clientX, event.clientY)
      scheduleToolbarStateSync()
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
      scheduleToolbarStateSync()
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
  }

  document.addEventListener('mousemove', handleMouseMove, true)
  document.addEventListener('mousedown', handleTableResizeHandleDown, true)

  cleanupEditorHoverListeners = () => {
    document.removeEventListener('mousemove', handleMouseMove, true)
    document.removeEventListener('mousedown', handleTableResizeHandleDown, true)
  }
}

const getCodeBlockLanguage = (node) => getFenceLanguage(node?.attrs?.language || '')

/** 修改代码块语言：只替换 info-string 的第一个词，保留其余参数。 */
const promptCodeBlockLanguage = async (pos) => {
  const view = getWysiwygView()
  const node = view?.state.doc.nodeAt(pos)
  if (!view || !node || node.type?.name !== 'codeBlock') {
    return
  }

  let nextLanguage = ''
  try {
    const { value } = await ElMessageBox.prompt('只修改语言，标题、行号与行标记会保留。', '代码块语言', {
      confirmButtonText: '保存',
      cancelButtonText: '取消',
      inputValue: getCodeBlockLanguage(node) === 'text' ? '' : getCodeBlockLanguage(node),
      inputPlaceholder: 'js / py / bash（留空表示 text）',
    })
    nextLanguage = value
  } catch {
    return
  }

  const currentInfo = node.attrs.language || ''
  const nextInfo = replaceFenceLanguage(currentInfo, String(nextLanguage || '').trim())

  if (currentInfo === nextInfo) {
    return
  }

  view.dispatch(
    view.state.tr.setNodeMarkup(pos, null, {
      ...node.attrs,
      language: nextInfo,
    })
  )
  updatePreviewFromEditor()
}

/** 打开代码块参数面板（富文本）：把当前 node 的 info-string 与代码回填进去。 */
const openCodeBlockOptions = (pos) => {
  const view = getWysiwygView()
  const node = view?.state.doc.nodeAt(pos)
  if (!view || !node || node.type?.name !== 'codeBlock') {
    return
  }

  codeOptionsTarget.value = { kind: 'wysiwyg', pos }
  codeOptionsInfo.value = node.attrs.language || ''
  codeOptionsCode.value = node.textContent || ''
  codeOptionsVisible.value = true
}

/** 应用参数面板结果：写回 codeBlock 的 info-string。 */
const applyCodeBlockOptions = (info) => {
  const target = codeOptionsTarget.value
  const view = getWysiwygView()
  const node = view && Number.isInteger(target?.pos) ? view.state.doc.nodeAt(target.pos) : null

  if (!view || !node || node.type?.name !== 'codeBlock') {
    ElMessage.warning('没有找到要修改的代码块。')
    return
  }

  view.dispatch(
    view.state.tr.setNodeMarkup(target.pos, null, {
      ...node.attrs,
      language: info,
    })
  )
  updatePreviewFromEditor()

  codeOptionsTarget.value = null
  codeOptionsInfo.value = ''
  codeOptionsCode.value = ''
}

/** 面板打开时的代码块位置会随编辑位移，重新定位到当前选区所在的代码块。 */
const openCodeBlockOptionsAtSelection = () => {
  const view = getWysiwygView()
  const info = getSelectedCodeBlockInfo(view)

  if (!view || !info) {
    ElMessage.info('把光标放进一个代码块里，再打开代码块设置。')
    return
  }

  openCodeBlockOptions(info.pos)
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
    applyStoredTableLayoutsToEditor()
  })
}

/**
 * 顶部固定工具栏的状态刷新。
 *
 * 悬浮工具条已移除，这里只负责两件事：
 *   - 把当前选区的格式状态同步给固定工具栏（按钮高亮 / aria-pressed）
 *   - 记录「❢」当前所处的提示框类型，用于切换与取消
 */
const syncToolbarState = () => {
  updateFixedToolbarSnapshot()

  const view = getWysiwygView()
  activeCalloutType.value = view ? getActiveCalloutType(view.state).toLowerCase() : ''
}

/** 顶部工具栏「⋯」：对选区所在代码块打开参数面板。 */
const openFixedToolbarCodeBlockOptions = () => {
  restoreInsertionSelection()
  openCodeBlockOptionsAtSelection()
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

/**
 * 找到选区"涉及"的代码块。
 *
 * 先看光标祖先链；找不到时再看选区覆盖范围——用户按 Ctrl+A 全选时
 * `$from` 落在文档开头，并不在代码块里，但意图显然是操作这个代码块。
 */
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

  let found = null
  view.state.doc.nodesBetween(selection.from, selection.to, (node, pos) => {
    if (found) {
      return false
    }
    if (node.type.name === 'codeBlock') {
      found = { node, pos }
      return false
    }
    return true
  })

  return found
}

const applyCodeBlockAutoFormat = () => {
  if (!editorInstance || !fixedToolbarState.codeBlock.full) {
    return
  }

  restoreInsertionSelection()

  const view = getWysiwygView()
  const codeBlockInfo = getSelectedCodeBlockInfo(view)
  if (!view || !codeBlockInfo) {
    return
  }

  const { node, pos } = codeBlockInfo
  const formattedCode = formatCodeBlockContent(node.textContent || '', node.attrs?.language || '')

  if (formattedCode === node.textContent) {
    return
  }

  const contentStart = pos + 1
  const contentEnd = contentStart + node.content.size
  const tr = view.state.tr.insertText(formattedCode, contentStart, contentEnd)
  const selectionEnd = contentStart + formattedCode.length

  tr.setSelection(TextSelection.create(tr.doc, contentStart, selectionEnd)).scrollIntoView()
  view.dispatch(tr)
  updatePreviewFromEditor()

  nextTick(() => {
    scheduleToolbarStateSync()
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
  updateFixedToolbarSnapshot()

  nextTick(() => {
    scheduleToolbarStateSync()
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
  updateEditorTableLayoutStyles()

  nextTick(() => {
    scheduleToolbarStateSync()
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
  ElMessage.success('已删除表格')

  nextTick(() => {
    scheduleToolbarStateSync()
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
    // 富文本面板里的提示框 / 代码块即时预览（decoration，不改变文档内容）
    plugins: [
      createRichBlockPreview({
        onEditLanguage: (pos) => promptCodeBlockLanguage(pos),
        onEditOptions: (pos) => openCodeBlockOptions(pos),
        // 光标停在提示框标记行且正在输入时，保留原文以便修改类型与标题
        isEditorFocused: () => Boolean(getWysiwygView()?.hasFocus?.()),
      }),
    ],
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
          scheduleToolbarStateSync()
        })
      },
      focus: () => {
        nextTick(() => {
          rememberEditorSelectionRange()
          updateFixedToolbarSnapshot()
          syncTableMultiCellSelectionState()
          scheduleToolbarStateSync()
        })
      },
      blur: () => {
        nextTick(() => {
          syncTableMultiCellSelectionState()
        })
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

/**
 * 打开正文预览。WYSIWYG 面板只能表示 block 结构，
 * 代码块参数（title / 行标记 / 行号 / 折叠）与代码组在这里才完整可见。
 */
const openBodyPreview = () => {
  const markdown = currentMarkdown.value || ''
  if (!markdown.trim()) {
    ElMessage.warning('正文还是空的，先写点内容吧。')
    return
  }

  bodyPreviewHtml.value = sanitizePreviewHtml(renderMarkdownPreview(markdown))
  bodyPreviewVisible.value = true
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
  if (!editorSettings.value.autoSaveEnabled) return
  if (!editorInstance) return

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
  nextTick(updateFixedToolbarSnapshot)
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
    scheduleToolbarStateSync()

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
  window.addEventListener('resize', hideTableActionPanel)
  window.addEventListener('resize', hideTableHoverControl)
  window.addEventListener('resize', hideTableResizeHandle)
  window.addEventListener('resize', hideImageToolbar)
  window.addEventListener('resize', refreshTableSelectionOverlay)
  window.addEventListener('scroll', scheduleToolbarStateSync, true)
  window.addEventListener('scroll', hideTableActionPanel, true)
  window.addEventListener('scroll', hideTableHoverControl, true)
  window.addEventListener('scroll', hideTableResizeHandle, true)
  window.addEventListener('scroll', hideImageToolbar, true)
  window.addEventListener('scroll', refreshTableSelectionOverlay, true)
  document.addEventListener('scroll', scheduleToolbarStateSync, true)
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
  window.removeEventListener('resize', hideTableActionPanel)
  window.removeEventListener('resize', hideTableHoverControl)
  window.removeEventListener('resize', hideTableResizeHandle)
  window.removeEventListener('resize', hideImageToolbar)
  window.removeEventListener('resize', refreshTableSelectionOverlay)
  window.removeEventListener('scroll', scheduleToolbarStateSync, true)
  window.removeEventListener('scroll', hideTableActionPanel, true)
  window.removeEventListener('scroll', hideTableHoverControl, true)
  window.removeEventListener('scroll', hideTableResizeHandle, true)
  window.removeEventListener('scroll', hideImageToolbar, true)
  window.removeEventListener('scroll', refreshTableSelectionOverlay, true)
  document.removeEventListener('scroll', scheduleToolbarStateSync, true)
  document.removeEventListener('scroll', hideTableHoverControl, true)
  document.removeEventListener('scroll', hideTableResizeHandle, true)
  document.removeEventListener('scroll', hideImageToolbar, true)
  document.removeEventListener('scroll', refreshTableSelectionOverlay, true)
  cancelToolbarStateSync()
  cleanupEditorSelectionListeners?.()
  cleanupEditorSelectionListeners = null
  cleanupEditorHoverListeners?.()
  cleanupEditorHoverListeners = null
  cancelToastContextMenuSync()
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
          @preview="openBodyPreview"
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
                <!--
                  注意：auto-height 是 Toast UI 在 setHeight('auto') 时动态加到根节点上的类，
                  一旦 Vue 因为 is-editor-empty 之类的动态 class 变化重写 className 就会把它抹掉，
                  导致 .toastui-editor-main 被压成 2px、整块编辑区不可见（空笔记输入第一个字即触发）。
                  因此这里把它写进静态 class，让 Vue 每次 patch 都保留它。
                -->
                <div class="wysiwyg-shell">
                  <FixedEditorToolbar
                    :editor-ready="editorReady"
                    :toolbar-state="fixedToolbarState"
                    :selected-text="fixedToolbarSelectedText"
                    :heading-options="headingOptions"
                    :max-table-rows="MAX_TABLE_ROW_COUNT"
                    :max-table-columns="MAX_TABLE_COLUMN_COUNT"
                    :active-callout="activeCalloutType"
                    @remember-selection="rememberFixedToolbarSelection"
                    @command="runFixedToolbarCommand"
                    @apply-heading="applyFixedToolbarHeading"
                    @insert-link="insertFixedToolbarLink"
                    @insert-image="triggerEditorImageUpload"
                    @insert-table="applyTable"
                    @insert-math="insertFixedToolbarMath"
                    @insert-callout="applyFixedToolbarCallout"
                    @open-code-block-options="openFixedToolbarCodeBlockOptions"
                    @apply-code-block-auto-format="applyCodeBlockAutoFormat"
                  />
                  <div
                    ref="editorRoot"
                    class="wysiwyg-editor blog-prose auto-height"
                    :class="{ 'is-editor-empty': !currentMarkdown.trim() }"
                    :data-placeholder="editorPlaceholder"
                  ></div>
                </div>
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

          <EditorTableOverlays
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

    <BodyPreviewDialog v-model:visible="bodyPreviewVisible" :html="bodyPreviewHtml" :title="form.title" />

    <CodeBlockOptionsDialog
      v-model:visible="codeOptionsVisible"
      :info="codeOptionsInfo"
      :code="codeOptionsCode"
      @apply="applyCodeBlockOptions"
    />
  </main>
</template>

<style scoped>
.edit-page {
  padding: 20px;
  /* 用 clip 而不是 hidden：hidden 会把 overflow-y 变成 auto，让这一层变成滚动容器，
     顶部固定工具栏的 position: sticky 就会失效（跟着内容一起滚走）。 */
  overflow-x: clip;
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
  color: var(--text-muted);
  /* 与 blog-prose 正文行高一致，避免空编辑器时占位文字与输入后错位 */
  line-height: 1.75;
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
  border: 1px solid var(--border-soft);
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
  border: 1px solid var(--border-soft);
  border-radius: 22px;
  background: var(--panel-background);
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

/* 编辑区排版统一由全局 styles/blog-prose.css 提供（与阅读端一致），
   这里只保留编辑器结构、字号设置与交互状态相关的规则。 */
.wysiwyg-editor :deep(.toastui-editor-contents) {
  min-height: 520px;
  max-width: 100%;
  overflow-x: hidden;
  padding: 22px 24px;
  /* 编辑器有自己的字号设置，优先级高于 blog-prose 的阅读字号 */
  font-size: var(--editor-font-size, 1rem);
}

.wysiwyg-editor :deep(.toastui-editor-contents :not(pre) > code) {
  white-space: normal;
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
  color: var(--text-primary);
}

.wysiwyg-editor :deep(.toastui-editor-contents th.toastui-editor-cell-selected *),
.wysiwyg-editor :deep(.toastui-editor-contents td.toastui-editor-cell-selected *),
.wysiwyg-editor :deep(.toastui-editor-contents th.moonbird-native-cell-selected *),
.wysiwyg-editor :deep(.toastui-editor-contents td.moonbird-native-cell-selected *) {
  background: transparent !important;
  color: inherit !important;
}

/* toast-ui 代码块外壳：定位与交互控件保留，外观交由 blog-prose */
.wysiwyg-editor :deep(.toastui-editor-contents .toastui-editor-ww-code-block) {
  position: relative;
}

.wysiwyg-editor :deep(.toastui-editor-contents .toastui-editor-ww-code-block pre) {
  margin: 0;
  border: none;
  border-radius: 0;
  background: transparent !important;
  /* 必须显式取浅色文字：pre 若用 inherit 会继承到外层的深色正文，
     在深色代码底上形成“黑框”而看不见内容 */
  color: var(--code-text) !important;
}

.wysiwyg-editor :deep(.toastui-editor-contents .toastui-editor-ww-code-block:after) {
  display: none;
}

.wysiwyg-editor :deep(.toastui-editor-ww-code-block-language) {
  display: none !important;
}

/* 富文本内的提示框即时预览：隐藏标记行，加配色与标题 */
.wysiwyg-editor :deep(.toastui-editor-contents blockquote.moonbird-callout.is-callout-preview) {
  --callout-accent: var(--brand-blue);
  --callout-bg: var(--accent-soft);
  padding: 1rem 1.15rem;
  border: 1px solid color-mix(in srgb, var(--callout-accent) 28%, transparent);
  border-radius: 0.75rem;
  background: var(--callout-bg);
  font-style: normal;
}

.wysiwyg-editor :deep(.toastui-editor-contents blockquote.moonbird-callout-warning.is-callout-preview) {
  --callout-accent: var(--brand-gold);
  --callout-bg: var(--search-highlight-bg);
}

.wysiwyg-editor :deep(.toastui-editor-contents blockquote.moonbird-callout-tip.is-callout-preview) {
  --callout-accent: var(--moss);
  --callout-bg: var(--moss-soft);
}

.wysiwyg-editor :deep(.toastui-editor-contents blockquote.moonbird-callout-important.is-callout-preview) {
  --callout-accent: var(--brand-gold);
  --callout-bg: var(--search-highlight-bg);
}

.wysiwyg-editor :deep(.toastui-editor-contents blockquote.moonbird-callout-danger.is-callout-preview) {
  --callout-accent: var(--danger);
  --callout-bg: var(--danger-soft);
}

.wysiwyg-editor :deep(.toastui-editor-contents blockquote.moonbird-callout.is-callout-preview::before) {
  display: none;
}

/* toast-ui 给 blockquote 内的 p 设了浅灰，即时预览要取回正文颜色 */
.wysiwyg-editor :deep(.toastui-editor-contents blockquote.moonbird-callout.is-callout-preview :is(p, ul, ol, li, span, strong, em, a)) {
  color: inherit;
}

.wysiwyg-editor :deep(.mb-source-hidden) {
  display: none;
}

.wysiwyg-editor :deep(.mb-callout-preview-title) {
  display: block;
  margin-bottom: 0.5em;
  color: var(--callout-accent);
  font-size: 0.9rem;
  font-weight: 700;
  letter-spacing: 0.01em;
  user-select: none;
}

/* 富文本内的代码块参数信息条 */
.wysiwyg-editor :deep(.mb-code-preview-head) {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.4rem;
  padding: 0.45rem 0.9rem;
  border-radius: 0.5rem 0.5rem 0 0;
  background: rgba(15, 23, 42, 0.06);
  color: var(--ink-soft);
  font-family: "Cascadia Code", "Consolas", monospace;
  font-size: 0.74rem;
  line-height: 1.4;
  user-select: none;
}

.wysiwyg-editor :deep(.mb-code-preview-lang) {
  padding: 0.05rem 0.5rem;
  border: none;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.12);
  color: var(--brand-blue);
  font-family: inherit;
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: lowercase;
  cursor: pointer;
}

.wysiwyg-editor :deep(.mb-code-preview-lang:hover) {
  background: rgba(37, 99, 235, 0.2);
}

.wysiwyg-editor :deep(.mb-code-preview-title) {
  overflow: hidden;
  color: var(--brand-navy);
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wysiwyg-editor :deep(.mb-code-preview-badges) {
  margin-left: auto;
  color: var(--ink-soft);
  font-size: 0.72rem;
  white-space: nowrap;
}

.wysiwyg-editor :deep(.mb-code-preview-options) {
  flex: none;
  width: 22px;
  height: 22px;
  padding: 0;
  border: 1px solid var(--border-soft);
  border-radius: 999px;
  background: var(--control-background);
  color: var(--ink-soft);
  font-size: 0.9rem;
  line-height: 1;
  cursor: pointer;
}

.wysiwyg-editor :deep(.mb-code-preview-options:hover) {
  border-color: var(--accent-border);
  color: var(--brand-blue);
}

/* `::: code-group` / `:::` 容器行：弱化成“语法行”，不与正文争夺视觉权重 */
.wysiwyg-editor :deep(.toastui-editor-contents p.mb-directive-preview) {
  padding: 2px 8px;
  border-left: 2px solid var(--border-soft);
  border-radius: 4px;
  background: var(--surface-soft);
  color: var(--ink-soft);
  font-family: "Cascadia Code", "Consolas", monospace;
  font-size: 0.8rem;
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
