import assert from 'node:assert/strict'
import { describe, it } from 'vitest'

import {
  fitTableLayoutToMaxWidth,
  normalizeTableLayout,
  MIN_TABLE_COLUMN_WIDTH,
  MIN_TABLE_ROW_HEIGHT,
  serializeMarkdownWithTableLayouts,
  extractTableLayoutMetadata,
  MAX_TABLE_COLUMN_COUNT,
  MAX_TABLE_ROW_COUNT,
} from '../tableLayout.js'

describe('table limits', () => {
  it('stay at the 9 x 9 documented in PRODUCT_RULES', () => {
    assert.equal(MAX_TABLE_COLUMN_COUNT, 9)
    assert.equal(MAX_TABLE_ROW_COUNT, 9)
  })
})

describe('extractTableLayoutMetadata', () => {
  it('strips the metadata comment and returns the layouts', () => {
    const markdown = [
      'before',
      '',
      '<!-- moonbird-table-layouts:{"tables":[{"width":600,"columns":[300,300],"align":"center"}]} -->',
      '',
      'after',
    ].join('\n')

    const result = extractTableLayoutMetadata(markdown)
    assert.ok(!result.markdown.includes('moonbird-table-layouts'))
    assert.equal(result.layouts.length, 1)
    assert.equal(result.layouts[0].width, 600)
    assert.deepEqual(result.layouts[0].columns, [300, 300])
    assert.equal(result.layouts[0].align, 'center')
  })

  it('ignores broken JSON instead of throwing', () => {
    const result = extractTableLayoutMetadata('a\n\n<!-- moonbird-table-layouts:{not json} -->')
    assert.deepEqual(result.layouts, [])
    assert.ok(result.markdown.startsWith('a'))
  })

  it('returns the markdown untouched when no metadata is present', () => {
    const result = extractTableLayoutMetadata('# title\n\nbody')
    assert.equal(result.markdown, '# title\n\nbody')
    assert.deepEqual(result.layouts, [])
  })
})

describe('serializeMarkdownWithTableLayouts', () => {
  it('round-trips through extractTableLayoutMetadata', () => {
    const layouts = [{ width: 600, columns: [300, 300], align: 'center' }]
    const serialized = serializeMarkdownWithTableLayouts('body', layouts)
    const parsed = extractTableLayoutMetadata(serialized)

    assert.equal(parsed.markdown, 'body')
    assert.equal(parsed.layouts.length, 1)
    assert.equal(parsed.layouts[0].width, 600)
    assert.deepEqual(parsed.layouts[0].columns, [300, 300])
    assert.equal(parsed.layouts[0].align, 'center')
  })

  it('replaces old metadata instead of appending a second copy', () => {
    const once = serializeMarkdownWithTableLayouts('body', [{ width: 500, columns: [500], align: 'left' }])
    const twice = serializeMarkdownWithTableLayouts(once, [{ width: 700, columns: [700], align: 'left' }])

    assert.equal((twice.match(/moonbird-table-layouts/g) || []).length, 1)
    assert.equal(extractTableLayoutMetadata(twice).layouts[0].width, 700)
  })

  it('drops the metadata entirely when there is no layout', () => {
    const serialized = serializeMarkdownWithTableLayouts(
      'body\n\n<!-- moonbird-table-layouts:{"tables":[{"width":500,"columns":[500]}]} -->',
      [],
    )

    assert.equal(serialized, 'body')
  })
})

describe('normalizeTableLayout', () => {
  it('rejects a layout without columns', () => {
    assert.equal(normalizeTableLayout({ width: 600 }, 0), null)
    assert.equal(normalizeTableLayout(null, 3), null)
  })

  it('clamps every column to the minimum width', () => {
    const layout = normalizeTableLayout({ width: 600, columns: [10, 590] }, 2)
    assert.ok(layout.columns.every((width) => width >= MIN_TABLE_COLUMN_WIDTH))
  })

  it('clamps every row to the minimum height', () => {
    const layout = normalizeTableLayout({ width: 600, columns: [300, 300], height: 100, rows: [1, 99] }, 2, 600, 2, 100)
    assert.ok(layout.rows.every((height) => height >= MIN_TABLE_ROW_HEIGHT))
  })

  it('falls back to left alignment for unknown values', () => {
    assert.equal(normalizeTableLayout({ width: 600, columns: [600], align: 'justify' }, 1).align, 'left')
  })
})

describe('fitTableLayoutToMaxWidth', () => {
  it('returns the layout untouched when it already fits', () => {
    const layout = { width: 400, columns: [200, 200], align: 'left' }
    assert.deepEqual(fitTableLayoutToMaxWidth(layout, 800), layout)
  })

  it('scales columns down and keeps the exact total width', () => {
    const layout = { width: 1000, columns: [500, 500], align: 'left' }
    const fitted = fitTableLayoutToMaxWidth(layout, 600)

    assert.equal(fitted.width, 600)
    assert.equal(fitted.columns.reduce((sum, width) => sum + width, 0), 600)
  })

  it('is a no-op when the available width is unknown', () => {
    const layout = { width: 1000, columns: [500, 500], align: 'left' }
    assert.deepEqual(fitTableLayoutToMaxWidth(layout, 0), layout)
  })
})
