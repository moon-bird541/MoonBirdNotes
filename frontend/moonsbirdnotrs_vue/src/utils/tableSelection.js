/*
 * 表格多选区域的纯计算
 * ---------------------------------------------------------------------------
 * 从 NoteEditView 里抽出来的原因和 tableResize.js 一样：矩形相交、选区归一化、
 * 按行列号取单元格这三件事都不依赖编辑器实例，但一旦算错会表现为「高亮的格子
 * 和拖过的格子不一致」这种很难复现的 bug，所以单独放这里并配单测。
 *
 * 行列号约定：0 起始，左闭右闭区间（minRow/maxRow、minColumn/maxColumn 都是含端点的）。
 */

/**
 * 判断两个 DOMRect 形状的对象是否相交。
 * 只要接触边不重叠就算不相交（用严格不等号）。
 */
export const doRectsIntersect = (rectA, rectB) => {
  if (!rectA || !rectB) {
    return false
  }

  return (
    rectA.left < rectB.right &&
    rectA.right > rectB.left &&
    rectA.top < rectB.bottom &&
    rectA.bottom > rectB.top
  )
}

/**
 * 由拖拽起点与终点的单元格位置算出一个选区矩形。
 * 两张表之间、或任一位置无效时返回 null（不做跨表选区）。
 */
export const buildTableCellSelectionRect = (anchorPosition, focusPosition) => {
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

/**
 * 从表格行的二维结构里按选区矩形取单元格。
 * 传入的是 `HTMLTableElement.rows`（每项带 cells），越界或缺失的行列会被跳过。
 *
 * @param {ArrayLike<{ cells?: ArrayLike<unknown> }>} rows
 * @param {{ minRow: number, maxRow: number, minColumn: number, maxColumn: number } | null} selectionRect
 * @returns {unknown[]}
 */
export const collectCellsInSelectionRect = (rows, selectionRect) => {
  if (!selectionRect || !rows) {
    return []
  }

  const selectedCells = []

  for (let rowIndex = selectionRect.minRow; rowIndex <= selectionRect.maxRow; rowIndex += 1) {
    const rowElement = rows[rowIndex]
    for (let columnIndex = selectionRect.minColumn; columnIndex <= selectionRect.maxColumn; columnIndex += 1) {
      const cellElement = rowElement?.cells?.[columnIndex]
      if (cellElement) {
        selectedCells.push(cellElement)
      }
    }
  }

  return selectedCells
}

/**
 * 把单元格的 DOM 位置换算成 { tableIndex, rowIndex, columnIndex }。
 * 行列号直接从 tbody 的实际顺序取，不信任 colspan：跨列单元格只算它自己那一格。
 */
export const resolveTableCellPosition = (cellElement, tableIndex = -1) => {
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
    tableIndex,
    rowIndex,
    columnIndex,
  }
}

/**
 * 返回一个把单元格扩张到「矩形覆盖范围」的判定函数。
 * 只保留矩形命中的单元格，保持输入顺序。
 */
export const filterCellsIntersectingRect = (cellElements, selectionRect) => {
  if (!Array.isArray(cellElements) || !selectionRect) {
    return []
  }

  return cellElements.filter((cellElement) => {
    const position = resolveTableCellPosition(cellElement)
    if (!position) {
      return false
    }

    return (
      position.rowIndex >= selectionRect.minRow &&
      position.rowIndex <= selectionRect.maxRow &&
      position.columnIndex >= selectionRect.minColumn &&
      position.columnIndex <= selectionRect.maxColumn
    )
  })
}
