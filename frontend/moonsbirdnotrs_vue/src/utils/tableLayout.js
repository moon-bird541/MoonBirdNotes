export const MIN_TABLE_COLUMN_WIDTH = 64
export const MIN_TABLE_ROW_HEIGHT = 40
export const MAX_TABLE_ROW_COUNT = 9
export const MAX_TABLE_COLUMN_COUNT = 9

const TABLE_ALIGNMENTS = new Set(['left', 'center', 'right'])

const TABLE_LAYOUT_META_PATTERN = /<!--\s*moonbird-table-layouts:([\s\S]*?)-->\s*/g

const toPositiveNumber = (value) => {
  const numberValue = Number(value)
  return Number.isFinite(numberValue) && numberValue > 0 ? numberValue : null
}

const roundSize = (value) => Math.round(value)

const clampMinWidth = (value) => Math.max(0, toPositiveNumber(value) || 0)

const normalizeTableAlign = (align) => (TABLE_ALIGNMENTS.has(align) ? align : 'left')

const getElementInnerWidth = (element) => {
  if (!element) {
    return 0
  }

  const rawWidth = element.clientWidth || element.getBoundingClientRect?.().width || 0
  if (!rawWidth || typeof window === 'undefined') {
    return rawWidth
  }

  const styles = window.getComputedStyle?.(element)
  const paddingLeft = toPositiveNumber(styles?.paddingLeft?.replace('px', '')) || 0
  const paddingRight = toPositiveNumber(styles?.paddingRight?.replace('px', '')) || 0
  return Math.max(0, rawWidth - paddingLeft - paddingRight)
}

const getCellSpan = (cellElement) => {
  const span = Number(cellElement?.getAttribute?.('colspan'))
  return Number.isFinite(span) && span > 1 ? span : 1
}

const isExtendedCell = (cellElement) => cellElement?.hasAttribute?.('extended')

export const getTableColumnCount = (tableElement) => {
  const rows = Array.from(tableElement?.rows || [])
  if (!rows.length) {
    return 0
  }

  return rows.reduce((maxCount, rowElement) => {
    const rowCount = Array.from(rowElement.cells).reduce(
      (count, cellElement) => count + (isExtendedCell(cellElement) ? 0 : getCellSpan(cellElement)),
      0
    )
    return Math.max(maxCount, rowCount)
  }, 0)
}

export const getTableRowCount = (tableElement) => tableElement?.rows?.length || 0

const normalizeLayoutList = (layouts) => {
  const normalized = Array.isArray(layouts) ? [...layouts] : []
  while (normalized.length && !normalized[normalized.length - 1]) {
    normalized.pop()
  }
  return normalized
}

export const normalizeTableLayout = (
  layout,
  columnCount,
  fallbackWidth = 0,
  rowCount = 0,
  fallbackHeight = 0
) => {
  if (!layout || columnCount < 1) {
    return null
  }

  const width = toPositiveNumber(layout.width) || toPositiveNumber(fallbackWidth)
  const fallbackColumnWidth = width ? width / columnCount : MIN_TABLE_COLUMN_WIDTH
  const columns = Array.from({ length: columnCount }, (_, index) => {
    const columnWidth = toPositiveNumber(layout.columns?.[index])
    return roundSize(Math.max(columnWidth || fallbackColumnWidth, MIN_TABLE_COLUMN_WIDTH))
  })
  const totalWidth = roundSize(Math.max(width || columns.reduce((sum, value) => sum + value, 0), columnCount * MIN_TABLE_COLUMN_WIDTH))

  const normalizedLayout = {
    width: totalWidth,
    columns,
    align: normalizeTableAlign(layout.align),
  }

  const hasRowLayout =
    rowCount > 0 &&
    (Array.isArray(layout.rows) || toPositiveNumber(layout.height))

  if (hasRowLayout) {
    const height = toPositiveNumber(layout.height) || toPositiveNumber(fallbackHeight)
    const fallbackRowHeight = height ? height / rowCount : MIN_TABLE_ROW_HEIGHT
    const rows = Array.from({ length: rowCount }, (_, index) => {
      const rowHeight = toPositiveNumber(layout.rows?.[index])
      return roundSize(Math.max(rowHeight || fallbackRowHeight, MIN_TABLE_ROW_HEIGHT))
    })
    const totalHeight = roundSize(
      Math.max(height || rows.reduce((sum, value) => sum + value, 0), rowCount * MIN_TABLE_ROW_HEIGHT)
    )

    normalizedLayout.height = totalHeight
    normalizedLayout.rows = rows
  }

  return normalizedLayout
}

export const getAvailableTableWidth = (tableElement) => {
  const containerElement =
    tableElement?.closest?.('.toastui-editor-contents, .markdown-body') ||
    tableElement?.parentElement

  return roundSize(getElementInnerWidth(containerElement) || getElementInnerWidth(tableElement))
}

export const fitTableLayoutToMaxWidth = (layout, maxWidth) => {
  const availableWidth = roundSize(toPositiveNumber(maxWidth) || 0)
  if (!layout || !availableWidth || layout.width <= availableWidth) {
    return layout
  }

  const scale = availableWidth / layout.width
  const columns = Array.isArray(layout.columns)
    ? layout.columns.map((width) => Math.max(0, roundSize((toPositiveNumber(width) || 0) * scale)))
    : []
  const columnTotal = columns.reduce((sum, width) => sum + width, 0)
  if (columns.length && columnTotal !== availableWidth) {
    let diff = availableWidth - columnTotal
    for (let index = columns.length - 1; index >= 0 && diff !== 0; index -= 1) {
      if (diff > 0) {
        columns[index] += diff
        diff = 0
      } else {
        const reducibleWidth = Math.min(columns[index], Math.abs(diff))
        columns[index] -= reducibleWidth
        diff += reducibleWidth
      }
    }
  }

  return {
    ...layout,
    width: availableWidth,
    columns,
  }
}

export const extractTableLayoutMetadata = (markdown = '') => {
  let layouts = []
  const cleanedMarkdown = String(markdown).replace(TABLE_LAYOUT_META_PATTERN, (_, rawJson) => {
    try {
      const parsed = JSON.parse(rawJson.trim())
      layouts = normalizeLayoutList(
        Array.isArray(parsed?.tables)
          ? parsed.tables.map((layout) =>
              layout
                ? {
                    width: layout.width,
                    columns: layout.columns,
                    align: layout.align,
                    height: layout.height,
                    rows: layout.rows,
                  }
                : null
            )
          : []
      )
    } catch {
      layouts = []
    }
    return ''
  })

  return {
    markdown: cleanedMarkdown.trimEnd(),
    layouts,
  }
}

export const serializeMarkdownWithTableLayouts = (markdown = '', layouts = []) => {
  const cleanedMarkdown = extractTableLayoutMetadata(markdown).markdown
  const normalizedLayouts = normalizeLayoutList(layouts)

  if (!normalizedLayouts.length) {
    return cleanedMarkdown
  }

  return `${cleanedMarkdown}\n\n<!-- moonbird-table-layouts:${JSON.stringify({ tables: normalizedLayouts })} -->`
}

export const getTableColumnWidths = (tableElement, options = {}) => {
  const columnCount = getTableColumnCount(tableElement)
  if (columnCount < 1) {
    return []
  }

  const minColumnWidth = clampMinWidth(options.minColumnWidth ?? MIN_TABLE_COLUMN_WIDTH)
  const tableWidth = tableElement.getBoundingClientRect().width || columnCount * MIN_TABLE_COLUMN_WIDTH
  const fallbackColumnWidth = tableWidth / columnCount
  const widths = Array.from({ length: columnCount }, () => fallbackColumnWidth)

  const colWidths = Array.from(getDirectColgroup(tableElement)?.children || [])
    .slice(0, columnCount)
    .map((colElement) => toPositiveNumber(String(colElement.style.width || colElement.getAttribute('width') || '').replace('px', '')))

  if (colWidths.length === columnCount && colWidths.every(Boolean)) {
    return colWidths.map((width) => roundSize(Math.max(width, minColumnWidth)))
  }

  Array.from(tableElement.rows).forEach((rowElement) => {
    let columnIndex = 0

    Array.from(rowElement.cells).forEach((cellElement) => {
      if (isExtendedCell(cellElement)) {
        return
      }

      const span = getCellSpan(cellElement)
      const styleWidth = toPositiveNumber(String(cellElement.style.width || '').replace('px', ''))
      const measuredWidth = cellElement.getBoundingClientRect().width
      const cellWidth = styleWidth || measuredWidth || fallbackColumnWidth * span
      const widthPerColumn = cellWidth / span

      for (let index = 0; index < span && columnIndex + index < columnCount; index += 1) {
        widths[columnIndex + index] = widthPerColumn
      }
      columnIndex += span
    })
  })

  return widths.map((width) => roundSize(Math.max(width, minColumnWidth)))
}

export const getTableRowHeights = (tableElement) =>
  Array.from(tableElement?.rows || []).map((rowElement) => {
    const styleHeight = toPositiveNumber(String(rowElement.style.height || '').replace('px', ''))
    const measuredHeight = rowElement.getBoundingClientRect().height
    return roundSize(Math.max(styleHeight || measuredHeight || MIN_TABLE_ROW_HEIGHT, MIN_TABLE_ROW_HEIGHT))
  })

const tableHasCustomLayout = (tableElement) => {
  if (
    tableElement?.dataset?.moonbirdLayoutCustomized === 'true' ||
    tableElement?.style?.width ||
    tableElement?.style?.height
  ) {
    return true
  }

  return Array.from(tableElement?.rows || []).some(
    (rowElement) =>
      Boolean(rowElement.style.height) ||
      Array.from(rowElement.cells).some(
        (cellElement) => Boolean(cellElement.style.width) || Boolean(cellElement.style.height)
      )
  )
}

const getDirectColgroup = (tableElement) =>
  Array.from(tableElement?.children || []).find((element) => element.tagName === 'COLGROUP') || null

export const setTableInlineLimit = (tableElement, width) => {
  if (!tableElement) {
    return
  }

  const safeWidth = Math.max(0, roundSize(width))
  tableElement.style.width = `min(${safeWidth}px, 100%)`
  tableElement.style.maxWidth = '100%'
  tableElement.style.minWidth = '0'
  tableElement.style.inlineSize = `min(${safeWidth}px, 100%)`
  tableElement.style.maxInlineSize = '100%'
  tableElement.style.minInlineSize = '0'
  tableElement.style.tableLayout = 'fixed'
  tableElement.style.boxSizing = 'border-box'
  tableElement.style.overflow = 'hidden'
}

export const applyTableAlignment = (tableElement, align = 'left') => {
  if (!tableElement) {
    return
  }

  const normalizedAlign = normalizeTableAlign(align)
  if (normalizedAlign === 'center') {
    tableElement.style.marginLeft = 'auto'
    tableElement.style.marginRight = 'auto'
  } else if (normalizedAlign === 'right') {
    tableElement.style.marginLeft = 'auto'
    tableElement.style.marginRight = '0'
  } else {
    tableElement.style.marginLeft = '0'
    tableElement.style.marginRight = 'auto'
  }
}

export const syncTableColgroup = (tableElement, columns = [], options = {}) => {
  if (!tableElement || !columns.length) {
    return
  }

  const minColumnWidth = clampMinWidth(options.minColumnWidth ?? MIN_TABLE_COLUMN_WIDTH)
  let colgroupElement = getDirectColgroup(tableElement)
  if (!colgroupElement) {
    colgroupElement = document.createElement('colgroup')
    tableElement.insertBefore(colgroupElement, tableElement.firstChild)
  }

  while (colgroupElement.children.length < columns.length) {
    colgroupElement.appendChild(document.createElement('col'))
  }

  while (colgroupElement.children.length > columns.length) {
    colgroupElement.lastElementChild?.remove()
  }

  Array.from(colgroupElement.children).forEach((colElement, index) => {
    const width = roundSize(Math.max(columns[index], minColumnWidth))
    colElement.style.width = `${width}px`
    colElement.style.minWidth = minColumnWidth ? `${minColumnWidth}px` : '0'
  })
}

export const collectTableLayoutsFromTables = (tableElements) =>
  normalizeLayoutList(
    Array.from(tableElements || []).map((tableElement) => {
      if (!tableHasCustomLayout(tableElement)) {
        return null
      }

      return normalizeTableLayout(
        {
          width: tableElement.getBoundingClientRect().width,
          columns: getTableColumnWidths(tableElement),
          height: tableElement.getBoundingClientRect().height,
          rows: getTableRowHeights(tableElement),
        },
        getTableColumnCount(tableElement),
        tableElement.getBoundingClientRect().width,
        getTableRowCount(tableElement),
        tableElement.getBoundingClientRect().height
      )
    })
  )

export const applyTableLayoutToDom = (tableElement, layout, markCustomized = true) => {
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

  if (markCustomized) {
    tableElement.dataset.moonbirdLayoutCustomized = 'true'
  }

  Array.from(tableElement.rows).forEach((rowElement, rowIndex) => {
    let columnIndex = 0
    const rowHeight = fittedLayout.rows?.[rowIndex]

    if (rowHeight) {
      rowElement.style.height = `${rowHeight}px`
      rowElement.style.boxSizing = 'border-box'
    }

    Array.from(rowElement.cells).forEach((cellElement) => {
      if (isExtendedCell(cellElement)) {
        return
      }

      const span = getCellSpan(cellElement)
      const cellWidth = fittedLayout.columns
        .slice(columnIndex, columnIndex + span)
        .reduce((sum, width) => sum + width, 0)

      cellElement.style.width = `${roundSize(cellWidth)}px`
      cellElement.style.maxWidth = '0'
      cellElement.style.minWidth = '0'
      cellElement.style.overflowWrap = 'anywhere'
      cellElement.style.wordBreak = 'break-word'
      if (rowHeight) {
        cellElement.style.height = `${rowHeight}px`
      }
      cellElement.style.boxSizing = 'border-box'
      columnIndex += span
    })
  })

  return fittedLayout
}

export const applyTableLayoutsToTables = (tableElements, layouts) => {
  Array.from(tableElements || []).forEach((tableElement, index) => {
    if (layouts?.[index]) {
      applyTableLayoutToDom(tableElement, layouts[index], true)
    }
  })
}
