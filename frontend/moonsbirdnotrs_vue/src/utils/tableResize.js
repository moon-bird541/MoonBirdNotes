/*
 * 表格拖拽缩放的纯计算
 * ---------------------------------------------------------------------------
 * 从 NoteEditView 里抽出来的原因：这是整块表格交互中唯一不需要 DOM 的部分，
 * 也是唯一能写成断言的部分。拖拽列宽 / 行高 / 整表宽高的边界条件（最小值、
 * 最大可用宽度、总和守恒）出过错很难靠肉眼发现，所以单独放在这里并配单测。
 *
 * 约定：
 *   - 所有尺寸都是 CSS 像素，返回前统一取整；
 *   - 单列宽度不小于 minColumnWidth，单行高度不小于 MIN_TABLE_ROW_HEIGHT；
 *   - 返回的 columns / rows 总和必须精确等于 width / height，不做静默漂移。
 */

export const MIN_TABLE_COLUMN_WIDTH = 64
export const MIN_TABLE_ROW_HEIGHT = 40

const toPositiveNumber = (value) => {
  const numberValue = Number(value)
  return Number.isFinite(numberValue) && numberValue > 0 ? numberValue : null
}

/**
 * 把列宽按「最小宽度 + 剩余弹性宽度」重新分配，保证总和精确等于 totalWidth。
 * @param {number[]} columns
 * @param {number} totalWidth
 * @param {number} [minColumnWidth]
 * @returns {number[]}
 */
export const normalizeResizeColumns = (
  columns = [],
  totalWidth = 0,
  minColumnWidth = MIN_TABLE_COLUMN_WIDTH,
) => {
  const safeMinColumnWidth = Math.max(0, Math.round(minColumnWidth))
  const columnCount = columns.length

  if (!columnCount) {
    return []
  }

  const safeTotalWidth = Math.max(Math.round(totalWidth), safeMinColumnWidth * columnCount)
  const currentColumns = columns.map((width) => Math.max(Math.round(width), safeMinColumnWidth))
  const flexibleWidths = currentColumns.map((width) => Math.max(width - safeMinColumnWidth, 0))
  const flexibleTotal = flexibleWidths.reduce((sum, width) => sum + width, 0)
  const extraWidth = safeTotalWidth - safeMinColumnWidth * columnCount

  const safeColumns = currentColumns.map(
    (width, index) =>
      safeMinColumnWidth +
      Math.round(
        flexibleTotal ? (flexibleWidths[index] / flexibleTotal) * extraWidth : extraWidth / columnCount,
      ),
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

/**
 * 行高不做等比例缩放：只把差值补到末行，避免拖动一行时整表跳动。
 * @param {number[]} rows
 * @param {number} totalHeight
 * @returns {number[]}
 */
export const normalizeResizeRows = (rows = [], totalHeight = 0) => {
  const safeRows = rows.map((height) => Math.max(Math.round(height), MIN_TABLE_ROW_HEIGHT))

  if (!safeRows.length) {
    return []
  }

  const currentTotal = safeRows.reduce((sum, height) => sum + height, 0)

  if (!currentTotal || Math.abs(currentTotal - totalHeight) < 1) {
    return safeRows
  }

  const diff = Math.round(totalHeight - currentTotal)
  safeRows[safeRows.length - 1] = Math.max(MIN_TABLE_ROW_HEIGHT, safeRows[safeRows.length - 1] + diff)
  return safeRows
}

/**
 * 根据一次拖拽位移算出新的表格布局。
 *
 * kind:
 *   - `table`        整表宽度（鼠标拖右边缘）
 *   - `table-height` 整表高度（鼠标拖下边缘）
 *   - `row`          单行高度
 *   - 其他（默认）   单列边界，左右两列此消彼长
 *
 * @returns {{ width: number, columns: number[], height?: number, rows?: number[] } | null}
 */
export const computeTableResizeLayout = (params = {}) => {
  const {
    kind,
    delta = 0,
    deltaY = 0,
    startWidth = 0,
    startHeight = 0,
    startColumns = [],
    startRows = [],
    maxWidth,
    minWidth = MIN_TABLE_COLUMN_WIDTH,
    minColumnWidth = MIN_TABLE_COLUMN_WIDTH,
    minHeight = MIN_TABLE_ROW_HEIGHT,
    columnIndex = -1,
    rowIndex = -1,
  } = params

  const safeStartWidth = toPositiveNumber(startWidth)
  const safeStartRows = Array.isArray(startRows) ? startRows : []
  const safeStartColumns = Array.isArray(startColumns) ? startColumns : []

  let nextWidth = safeStartWidth || 0
  let nextColumns = [...safeStartColumns]
  let nextHeight = safeStartRows.length && startHeight ? startHeight : null
  let nextRows = [...safeStartRows]

  if (kind === 'table') {
    if (!safeStartWidth) {
      return null
    }
    const upperBound = toPositiveNumber(maxWidth) ?? Number.POSITIVE_INFINITY
    nextWidth = Math.min(Math.max(safeStartWidth + delta, minWidth), upperBound)
    const scale = nextWidth / safeStartWidth
    nextColumns = normalizeResizeColumns(
      safeStartColumns.map((width) => width * scale),
      nextWidth,
      minColumnWidth,
    )
  } else if (kind === 'table-height') {
    if (!startHeight) {
      return null
    }
    nextHeight = Math.max(startHeight + deltaY, minHeight)
    const scale = nextHeight / startHeight
    nextRows = normalizeResizeRows(
      safeStartRows.map((height) => height * scale),
      nextHeight,
    )
  } else if (kind === 'row') {
    const currentRowHeight = safeStartRows[rowIndex]
    if (!Number.isFinite(currentRowHeight)) {
      return null
    }

    const safeDeltaY = Math.max(deltaY, MIN_TABLE_ROW_HEIGHT - currentRowHeight)
    nextRows[rowIndex] = Math.round(currentRowHeight + safeDeltaY)
    nextHeight = nextRows.reduce((sum, height) => sum + height, 0)
    nextRows = normalizeResizeRows(nextRows, nextHeight)
  } else {
    const leftWidth = safeStartColumns[columnIndex]
    const rightWidth = safeStartColumns[columnIndex + 1]

    if (!Number.isFinite(leftWidth) || !Number.isFinite(rightWidth)) {
      return null
    }

    const safeDelta = Math.min(
      Math.max(delta, minColumnWidth - leftWidth),
      rightWidth - minColumnWidth,
    )

    nextColumns[columnIndex] = Math.round(leftWidth + safeDelta)
    nextColumns[columnIndex + 1] = Math.round(rightWidth - safeDelta)
  }

  const layout = {
    width: nextWidth,
    columns: nextColumns,
  }

  if (nextRows.length && nextHeight) {
    layout.height = nextHeight
    layout.rows = nextRows
  }

  return layout
}
