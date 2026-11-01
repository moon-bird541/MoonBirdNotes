import assert from 'node:assert/strict'
import { describe, it } from 'vitest'

import {
  computeTableResizeLayout,
  MIN_TABLE_COLUMN_WIDTH,
  MIN_TABLE_ROW_HEIGHT,
  normalizeResizeColumns,
  normalizeResizeRows,
} from '../tableResize.js'

describe('normalizeResizeColumns', () => {
  it('returns an empty array when there are no columns', () => {
    assert.deepEqual(normalizeResizeColumns([], 600), [])
  })

  it('keeps the total exactly equal to the requested width', () => {
    const columns = normalizeResizeColumns([100, 250, 700], 800)
    assert.equal(columns.reduce((sum, width) => sum + width, 0), 800)
  })

  it('never returns a column below the minimum width', () => {
    const columns = normalizeResizeColumns([1, 1, 1], 120, MIN_TABLE_COLUMN_WIDTH)
    assert.ok(columns.every((width) => width >= MIN_TABLE_COLUMN_WIDTH))
  })

  it('raises the total when the requested width cannot fit the minimums', () => {
    const columns = normalizeResizeColumns([10, 10], 40, MIN_TABLE_COLUMN_WIDTH)
    assert.equal(
      columns.reduce((sum, width) => sum + width, 0),
      MIN_TABLE_COLUMN_WIDTH * 2,
    )
  })

  it('distributes the slack proportionally to the flexible part', () => {
    const columns = normalizeResizeColumns([200, 200], 600, MIN_TABLE_COLUMN_WIDTH)
    assert.deepEqual(columns, [300, 300])
  })
})

describe('normalizeResizeRows', () => {
  it('returns an empty array when there are no rows', () => {
    assert.deepEqual(normalizeResizeRows([], 100), [])
  })

  it('leaves rows untouched when the total already matches', () => {
    assert.deepEqual(normalizeResizeRows([40, 60], 100), [40, 60])
  })

  it('absorbs the difference in the last row', () => {
    assert.deepEqual(normalizeResizeRows([40, 60], 150), [40, 110])
  })

  it('never shrinks the last row below the minimum height', () => {
    const rows = normalizeResizeRows([40, 40], 20)
    assert.ok(rows.every((height) => height >= MIN_TABLE_ROW_HEIGHT))
  })
})

describe('computeTableResizeLayout - table width', () => {
  it('grows the table with the pointer', () => {
    const layout = computeTableResizeLayout({
      kind: 'table',
      delta: 100,
      startWidth: 600,
      startColumns: [300, 300],
      minWidth: 320,
      maxWidth: 1200,
    })

    assert.equal(layout.width, 700)
    assert.equal(layout.columns.reduce((sum, width) => sum + width, 0), 700)
  })

  it('clamps to the maximum available width', () => {
    const layout = computeTableResizeLayout({
      kind: 'table',
      delta: 9999,
      startWidth: 600,
      startColumns: [300, 300],
      maxWidth: 900,
    })

    assert.equal(layout.width, 900)
  })

  it('clamps to the minimum width', () => {
    const layout = computeTableResizeLayout({
      kind: 'table',
      delta: -9999,
      startWidth: 600,
      startColumns: [300, 300],
      minWidth: 320,
      maxWidth: 1200,
    })

    assert.equal(layout.width, 320)
  })

  it('returns null when the start width is unknown', () => {
    assert.equal(
      computeTableResizeLayout({ kind: 'table', delta: 10, startWidth: 0, startColumns: [100] }),
      null,
    )
  })
})

describe('computeTableResizeLayout - table height', () => {
  it('scales rows and keeps the total equal to the new height', () => {
    const layout = computeTableResizeLayout({
      kind: 'table-height',
      deltaY: 50,
      startHeight: 100,
      startRows: [50, 50],
      minHeight: 40,
    })

    assert.equal(layout.height, 150)
    assert.equal(layout.rows.reduce((sum, height) => sum + height, 0), 150)
  })

  it('refuses to shrink below the minimum height', () => {
    const layout = computeTableResizeLayout({
      kind: 'table-height',
      deltaY: -9999,
      startHeight: 100,
      startRows: [50, 50],
      minHeight: 80,
    })

    assert.equal(layout.height, 80)
  })
})

describe('computeTableResizeLayout - single row', () => {
  it('changes only the dragged row and keeps the total consistent', () => {
    const layout = computeTableResizeLayout({
      kind: 'row',
      deltaY: 30,
      startHeight: 100,
      startRows: [50, 50],
      rowIndex: 0,
    })

    assert.equal(layout.rows[0], 80)
    assert.equal(layout.rows.reduce((sum, height) => sum + height, 0), layout.height)
  })

  it('stops at the minimum row height', () => {
    const layout = computeTableResizeLayout({
      kind: 'row',
      deltaY: -9999,
      startHeight: 100,
      startRows: [50, 50],
      rowIndex: 0,
    })

    assert.equal(layout.rows[0], MIN_TABLE_ROW_HEIGHT)
  })

  it('returns null for an out-of-range row index', () => {
    assert.equal(
      computeTableResizeLayout({
        kind: 'row',
        deltaY: 10,
        startHeight: 100,
        startRows: [50, 50],
        rowIndex: 9,
      }),
      null,
    )
  })
})

describe('computeTableResizeLayout - column boundary', () => {
  it('moves width from one column to its neighbour without changing the table width', () => {
    const layout = computeTableResizeLayout({
      kind: 'column',
      delta: 40,
      startWidth: 600,
      startColumns: [300, 300],
      columnIndex: 0,
    })

    assert.equal(layout.width, 600)
    assert.deepEqual(layout.columns, [340, 260])
  })

  it('stops when the neighbour reaches its minimum width', () => {
    const layout = computeTableResizeLayout({
      kind: 'column',
      delta: 9999,
      startWidth: 600,
      startColumns: [300, 300],
      columnIndex: 0,
      minColumnWidth: MIN_TABLE_COLUMN_WIDTH,
    })

    assert.equal(layout.columns[1], MIN_TABLE_COLUMN_WIDTH)
    assert.equal(layout.columns[0] + layout.columns[1], 600)
  })

  it('stops when the dragged column reaches its minimum width', () => {
    const layout = computeTableResizeLayout({
      kind: 'column',
      delta: -9999,
      startWidth: 600,
      startColumns: [300, 300],
      columnIndex: 0,
      minColumnWidth: MIN_TABLE_COLUMN_WIDTH,
    })

    assert.equal(layout.columns[0], MIN_TABLE_COLUMN_WIDTH)
    assert.equal(layout.columns[0] + layout.columns[1], 600)
  })

  it('returns null when the boundary is the last column', () => {
    assert.equal(
      computeTableResizeLayout({
        kind: 'column',
        delta: 10,
        startWidth: 600,
        startColumns: [300, 300],
        columnIndex: 1,
      }),
      null,
    )
  })
})
