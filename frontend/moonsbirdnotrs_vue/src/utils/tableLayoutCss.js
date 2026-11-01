/*
 * 编辑器内表格布局的 CSS 生成
 * ---------------------------------------------------------------------------
 * 这套 CSS 是表格能「按用户拖出来的宽高稳定显示」的唯一依据：toast-ui 的所见即
 * 所得面板会不断重排 DOM，行内样式会被丢掉，所以我们把尺寸写成带 !important 的
 * 样式表规则，用 nth-of-type / nth-child 精确定位到表、行、单元格。
 *
 * 从 NoteEditView 抽出来是因为它几乎全是纯计算：只要给到表格元素和一个
 * getTableSelector 回调，输出就完全确定，可以先用 jsdom 断言再相信它。
 */

import {
  MIN_TABLE_ROW_HEIGHT,
  fitTableLayoutToMaxWidth,
  getAvailableTableWidth,
  getTableColumnCount,
  getTableRowCount,
  normalizeTableLayout,
} from './tableLayout.js'

const getCellSpan = (cellElement, attrName) => {
  const span = Number(cellElement?.getAttribute?.(attrName))
  return Number.isFinite(span) && span > 1 ? span : 1
}

export const getTableAlignmentCss = (align = 'left') => {
  if (align === 'center') {
    return 'margin-left:auto !important;margin-right:auto !important;'
  }
  if (align === 'right') {
    return 'margin-left:auto !important;margin-right:0 !important;'
  }
  return 'margin-left:0 !important;margin-right:auto !important;'
}

/**
 * 生成定位到某个 tr 的选择器。
 * 表格可能直接挂 tr，也可能被 thead / tbody / tfoot 包一层，两种情况都要能定位。
 */
export const getTableRowCssSelector = (tableSelector, tableElement, rowElement) => {
  const rowParent = rowElement?.parentElement

  if (!tableElement || !rowElement || !rowParent) {
    return ''
  }

  if (rowParent === tableElement) {
    const rowIndex = Array.from(tableElement.children)
      .filter((element) => element.tagName === 'TR')
      .indexOf(rowElement)
    return rowIndex >= 0 ? `${tableSelector} > tr:nth-of-type(${rowIndex + 1})` : ''
  }

  const sectionTagName = rowParent.tagName.toLowerCase()
  const sectionIndex = Array.from(tableElement.children)
    .filter((element) => element.tagName === rowParent.tagName)
    .indexOf(rowParent)
  const rowIndex = Array.from(rowParent.children)
    .filter((element) => element.tagName === 'TR')
    .indexOf(rowElement)

  if (sectionIndex < 0 || rowIndex < 0) {
    return ''
  }

  const sectionSelector = `${sectionTagName}:nth-of-type(${sectionIndex + 1})`
  return `${tableSelector} > ${sectionSelector} > tr:nth-of-type(${rowIndex + 1})`
}

/**
 * 为一张表格生成完整的布局 CSS。
 *
 * @param {HTMLTableElement} tableElement
 * @param {number} tableIndex 表格在编辑器里的序号（只用于兜底选择器）
 * @param {object} layout 已存的布局元数据
 * @param {(tableElement: HTMLTableElement, tableIndex: number) => string} getTableSelector
 * @returns {{ layout: object | null, css: string }}
 */
export const buildEditorTableLayoutCss = (tableElement, tableIndex, layout, getTableSelector) => {
  if (!tableElement) {
    return { layout: null, css: '' }
  }

  const columnCount = getTableColumnCount(tableElement)
  const rowCount = getTableRowCount(tableElement)
  const normalizedLayout = normalizeTableLayout(
    layout,
    columnCount,
    tableElement.getBoundingClientRect().width,
    rowCount,
    tableElement.getBoundingClientRect().height,
  )

  if (!normalizedLayout) {
    return { layout: null, css: '' }
  }

  const fittedLayout = fitTableLayoutToMaxWidth(normalizedLayout, getAvailableTableWidth(tableElement))
  const tableSelector = getTableSelector(tableElement, tableIndex)
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
      // 跨行 / 跨列时 toast-ui 会额外插入 extended 单元格，它们不参与列宽分配。
      if (cellElement.hasAttribute('extended')) {
        return
      }

      const cellIndex = Array.from(rowElement.children).indexOf(cellElement)
      const colSpan = getCellSpan(cellElement, 'colspan')
      const cellWidth = fittedLayout.columns
        .slice(columnIndex, columnIndex + colSpan)
        .reduce((sum, width) => sum + width, 0)
      const cellHeightRule = rowHeight ? `height:${rowHeight}px !important;` : ''

      if (cellIndex >= 0 && cellWidth > 0) {
        rules.push(
          `${rowSelector} > *:nth-child(${cellIndex + 1}){width:${Math.round(cellWidth)}px !important;max-width:0 !important;min-width:0 !important;overflow-wrap:anywhere !important;word-break:break-word !important;${cellHeightRule}box-sizing:border-box !important;}`,
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
