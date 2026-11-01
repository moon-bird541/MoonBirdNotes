import assert from 'node:assert/strict'
import { describe, it } from 'vitest'

import {
  buildTableCellSelectionRect,
  collectCellsInSelectionRect,
  doRectsIntersect,
  filterCellsIntersectingRect,
  resolveTableCellPosition,
} from '../tableSelection.js'

const makeRows = (rowCount, columnCount) =>
  Array.from({ length: rowCount }, (_, rowIndex) => ({
    cells: Array.from({ length: columnCount }, (_, columnIndex) => ({ id: `${rowIndex}-${columnIndex}` })),
  }))

describe('doRectsIntersect', () => {
  it('is true when the rectangles overlap', () => {
    assert.equal(
      doRectsIntersect({ left: 0, right: 10, top: 0, bottom: 10 }, { left: 5, right: 15, top: 5, bottom: 15 }),
      true,
    )
  })

  it('is false when they only touch edges', () => {
    assert.equal(
      doRectsIntersect({ left: 0, right: 10, top: 0, bottom: 10 }, { left: 10, right: 20, top: 0, bottom: 10 }),
      false,
    )
  })

  it('is false when they are far apart', () => {
    assert.equal(
      doRectsIntersect({ left: 0, right: 10, top: 0, bottom: 10 }, { left: 100, right: 110, top: 0, bottom: 10 }),
      false,
    )
  })

  it('is false for missing rectangles', () => {
    assert.equal(doRectsIntersect(null, { left: 0, right: 1, top: 0, bottom: 1 }), false)
  })
})

describe('buildTableCellSelectionRect', () => {
  it('normalises a reversed drag into min/max bounds', () => {
    const rect = buildTableCellSelectionRect(
      { tableIndex: 0, rowIndex: 3, columnIndex: 4 },
      { tableIndex: 0, rowIndex: 1, columnIndex: 2 },
    )

    assert.deepEqual(rect, { tableIndex: 0, minRow: 1, maxRow: 3, minColumn: 2, maxColumn: 4 })
  })

  it('returns null when the two positions are in different tables', () => {
    assert.equal(
      buildTableCellSelectionRect(
        { tableIndex: 0, rowIndex: 0, columnIndex: 0 },
        { tableIndex: 1, rowIndex: 0, columnIndex: 0 },
      ),
      null,
    )
  })

  it('returns null when either position is invalid', () => {
    assert.equal(buildTableCellSelectionRect(null, { tableIndex: 0 }), null)
    assert.equal(
      buildTableCellSelectionRect({ tableIndex: -1, rowIndex: 0, columnIndex: 0 }, { tableIndex: 0, rowIndex: 0, columnIndex: 0 }),
      null,
    )
  })

  it('handles a single-cell selection', () => {
    const rect = buildTableCellSelectionRect(
      { tableIndex: 2, rowIndex: 1, columnIndex: 1 },
      { tableIndex: 2, rowIndex: 1, columnIndex: 1 },
    )

    assert.deepEqual(rect, { tableIndex: 2, minRow: 1, maxRow: 1, minColumn: 1, maxColumn: 1 })
  })
})

describe('collectCellsInSelectionRect', () => {
  it('returns the cells inside the rectangle in row-major order', () => {
    const cells = collectCellsInSelectionRect(makeRows(3, 3), {
      minRow: 0,
      maxRow: 1,
      minColumn: 1,
      maxColumn: 2,
    })

    assert.deepEqual(
      cells.map((cell) => cell.id),
      ['0-1', '0-2', '1-1', '1-2'],
    )
  })

  it('skips rows and columns that do not exist', () => {
    const cells = collectCellsInSelectionRect(makeRows(2, 2), {
      minRow: 1,
      maxRow: 5,
      minColumn: 1,
      maxColumn: 5,
    })

    assert.deepEqual(
      cells.map((cell) => cell.id),
      ['1-1'],
    )
  })

  it('returns an empty array without a rectangle', () => {
    assert.deepEqual(collectCellsInSelectionRect(makeRows(2, 2), null), [])
  })
})

describe('resolveTableCellPosition', () => {
  const buildTable = () => {
    const table = document.createElement('table')
    const tbody = document.createElement('tbody')
    for (let rowIndex = 0; rowIndex < 2; rowIndex += 1) {
      const tr = document.createElement('tr')
      for (let columnIndex = 0; columnIndex < 2; columnIndex += 1) {
        const td = document.createElement('td')
        td.dataset.position = `${rowIndex}-${columnIndex}`
        tr.appendChild(td)
      }
      tbody.appendChild(tr)
    }
    table.appendChild(tbody)
    document.body.appendChild(table)
    return table
  }

  it('reports the row and column of a cell', () => {
    const table = buildTable()
    const cell = table.rows[1].cells[0]
    const position = resolveTableCellPosition(cell, 0)

    assert.equal(position.rowIndex, 1)
    assert.equal(position.columnIndex, 0)
    assert.equal(position.tableIndex, 0)
    assert.equal(position.tableElement, table)
    table.remove()
  })

  it('returns null for an element that is not inside a table', () => {
    const div = document.createElement('div')
    document.body.appendChild(div)
    assert.equal(resolveTableCellPosition(div, 0), null)
    div.remove()
  })
})

describe('filterCellsIntersectingRect', () => {
  const buildTable = () => {
    const table = document.createElement('table')
    const tbody = document.createElement('tbody')
    for (let rowIndex = 0; rowIndex < 2; rowIndex += 1) {
      const tr = document.createElement('tr')
      for (let columnIndex = 0; columnIndex < 2; columnIndex += 1) {
        tr.appendChild(document.createElement('td'))
      }
      tbody.appendChild(tr)
    }
    table.appendChild(tbody)
    document.body.appendChild(table)
    return table
  }

  it('keeps only the cells inside the rectangle', () => {
    const table = buildTable()
    const cells = Array.from(table.querySelectorAll('td'))
    const filtered = filterCellsIntersectingRect(cells, {
      minRow: 1,
      maxRow: 1,
      minColumn: 0,
      maxColumn: 1,
    })

    assert.equal(filtered.length, 2)
    assert.equal(filtered[0], table.rows[1].cells[0])
    table.remove()
  })

  it('returns an empty array for non-array input', () => {
    assert.deepEqual(filterCellsIntersectingRect(null, { minRow: 0, maxRow: 0, minColumn: 0, maxColumn: 0 }), [])
  })
})
