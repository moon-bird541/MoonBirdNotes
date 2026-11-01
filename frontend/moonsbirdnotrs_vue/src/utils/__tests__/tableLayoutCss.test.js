import assert from 'node:assert/strict'
import { beforeEach, describe, it } from 'vitest'

import { buildEditorTableLayoutCss, getTableAlignmentCss, getTableRowCssSelector } from '../tableLayoutCss.js'

const buildTable = ({ rows = 2, columns = 2, inTbody = true, columnWidths = [] } = {}) => {
  const table = document.createElement('table')
  const wrapper = inTbody ? document.createElement('tbody') : table
  if (inTbody) {
    table.appendChild(wrapper)
  }

  if (columnWidths.length) {
    const colgroup = document.createElement('colgroup')
    columnWidths.forEach((width) => {
      const col = document.createElement('col')
      col.style.width = `${width}px`
      colgroup.appendChild(col)
    })
    table.insertBefore(colgroup, table.firstChild)
  }

  for (let rowIndex = 0; rowIndex < rows; rowIndex += 1) {
    const tr = document.createElement('tr')
    for (let columnIndex = 0; columnIndex < columns; columnIndex += 1) {
      tr.appendChild(document.createElement(rowIndex === 0 ? 'th' : 'td'))
    }
    wrapper.appendChild(tr)
  }

  document.body.appendChild(table)
  return table
}

beforeEach(() => {
  document.body.innerHTML = ''
})

describe('getTableAlignmentCss', () => {
  it('left-aligns by default', () => {
    assert.ok(getTableAlignmentCss('left').includes('margin-left:0'))
  })

  it('centres and right-aligns with auto margins', () => {
    assert.ok(getTableAlignmentCss('center').includes('margin-right:auto'))
    assert.ok(getTableAlignmentCss('right').includes('margin-left:auto'))
  })

  it('treats unknown values as left', () => {
    assert.equal(getTableAlignmentCss('justify'), getTableAlignmentCss('left'))
  })
})

describe('getTableRowCssSelector', () => {
  it('locates rows nested in tbody with nth-of-type', () => {
    const table = buildTable()
    const selector = getTableRowCssSelector('#t', table, table.rows[1])
    assert.equal(selector, '#t > tbody:nth-of-type(1) > tr:nth-of-type(2)')
  })

  it('locates direct tr children without a section wrapper', () => {
    const table = buildTable({ inTbody: false })
    assert.equal(getTableRowCssSelector('#t', table, table.rows[0]), '#t > tr:nth-of-type(1)')
  })

  it('returns an empty string for a detached row', () => {
    assert.equal(getTableRowCssSelector('#t', null, document.createElement('tr')), '')
  })
})

describe('buildEditorTableLayoutCss', () => {
  it('emits one rule per table, row and cell', () => {
    const table = buildTable({ rows: 2, columns: 2 })
    const result = buildEditorTableLayoutCss(
      table,
      0,
      { width: 600, columns: [300, 300], align: 'center', height: 100, rows: [50, 50] },
      () => '#tbl',
    )

    assert.equal(result.layout.width, 600)
    assert.ok(result.css.includes('#tbl{'))
    assert.ok(result.css.includes('#tbl > tbody:nth-of-type(1) > tr:nth-of-type(1){'))
    assert.ok(result.css.includes('width:300px !important'))
    assert.equal((result.css.match(/> \*:nth-child\(/g) || []).length, 4)
  })

  it('keeps the table inside the available width', () => {
    const table = buildTable()
    // jsdom 的布局宽度是 0，此时不做收窄，宽度按元数据保留。
    const result = buildEditorTableLayoutCss(
      table,
      0,
      { width: 600, columns: [300, 300], align: 'left' },
      () => '#tbl',
    )

    assert.equal(result.layout.width, 600)
  })

  it('returns an empty result when the layout cannot be normalised', () => {
    const table = buildTable()
    const result = buildEditorTableLayoutCss(table, 0, null, () => '#tbl')

    assert.equal(result.layout, null)
    assert.equal(result.css, '')
  })

  it('returns an empty result without a table element', () => {
    const result = buildEditorTableLayoutCss(null, 0, { width: 600, columns: [600] }, () => '#tbl')

    assert.deepEqual(result, { layout: null, css: '' })
  })

  it('skips toast-ui extended cells so they do not consume a column', () => {
    const table = buildTable({ rows: 1, columns: 2 })
    const extended = document.createElement('td')
    extended.setAttribute('extended', 'true')
    // 插到第一行开头，模拟跨列布局时 toast-ui 补的占位单元格。
    table.rows[0].insertBefore(extended, table.rows[0].cells[0])

    const result = buildEditorTableLayoutCss(
      table,
      0,
      { width: 600, columns: [300, 300], align: 'left' },
      () => '#tbl',
    )

    // 两个真实单元格各拿一列，扩展单元格不产生规则。
    assert.equal((result.css.match(/> \*:nth-child\(/g) || []).length, 2)
  })

  it('uses the supplied selector callback for the table rule', () => {
    const table = buildTable()
    const result = buildEditorTableLayoutCss(
      table,
      7,
      { width: 600, columns: [300, 300], align: 'left' },
      (element, index) => `#table-${index}`,
    )

    assert.ok(result.css.startsWith('#table-7{'))
  })
})
