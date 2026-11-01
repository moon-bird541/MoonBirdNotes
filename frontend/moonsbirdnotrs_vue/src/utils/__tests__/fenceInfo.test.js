import assert from 'node:assert/strict'
import { describe, it } from 'vitest'

import {
  buildCodeBlockHtml,
  buildFenceInfo,
  buildLineMarkMap,
  escapeHtml,
  getFenceLanguage,
  parseCodeGroupLabels,
  parseFenceInfo,
  parseLineRanges,
  replaceFenceLanguage,
  splitInfoTokens,
} from '../fenceInfo.js'

describe('parseFenceInfo', () => {
  it('reads language and title', () => {
    const parsed = parseFenceInfo('js title="app.js"')
    assert.equal(parsed.lang, 'js')
    assert.equal(parsed.title, 'app.js')
  })

  it('reads highlight, ins, del, collapse and line number options', () => {
    const parsed = parseFenceInfo(
      'js {1,3-5} ins={6} del={"说明":7-8} showLineNumbers startLineNumber=5 collapse={1-4} wrap=false frame=code',
    )

    const markRanges = parsed.marks.find((mark) => mark.type === 'mark')
    assert.deepEqual(
      markRanges.ranges.map((range) => [range.start, range.end]),
      [
        [1, 1],
        [3, 5],
      ],
    )

    const insRanges = parsed.marks.find((mark) => mark.type === 'ins')
    assert.deepEqual(
      insRanges.ranges.map((range) => [range.start, range.end]),
      [[6, 6]],
    )

    const delRanges = parsed.marks.find((mark) => mark.type === 'del')
    assert.deepEqual(
      delRanges.ranges.map((range) => [range.start, range.end, range.label]),
      [[7, 8, '说明']],
    )

    assert.equal(parsed.showLineNumbers, true)
    assert.equal(parsed.startLineNumber, 5)
    assert.equal(parsed.wrap, false)
    assert.equal(parsed.frame, 'code')
    assert.deepEqual(
      parsed.collapse.map((range) => [range.start, range.end]),
      [[1, 4]],
    )
  })

  it('treats an empty info string as plain text', () => {
    const parsed = parseFenceInfo('')
    assert.equal(parsed.lang, '')
    assert.equal(parsed.title, '')
    assert.deepEqual(parsed.marks, [])
    assert.deepEqual(parsed.collapse, [])
  })
})

describe('splitInfoTokens', () => {
  it('keeps quoted and braced content together', () => {
    assert.deepEqual(splitInfoTokens('js title="a b.js" {1-2}'), ['js', 'title="a b.js"', '{1-2}'])
  })
})

describe('parseLineRanges', () => {
  it('parses single lines and ranges', () => {
    assert.deepEqual(
      parseLineRanges('1,3-5').map((range) => [range.start, range.end]),
      [
        [1, 1],
        [3, 5],
      ],
    )
  })

  it('drops malformed tokens instead of throwing', () => {
    assert.deepEqual(parseLineRanges('abc,,'), [])
  })

  it('never returns a range whose end precedes its start', () => {
    for (const range of parseLineRanges('7-4')) {
      assert.ok(range.end >= range.start)
    }
  })
})

describe('buildLineMarkMap', () => {
  it('keeps the strongest mark per line (del > ins > mark)', () => {
    const marks = [
      { type: 'mark', kind: 'lines', ranges: [{ start: 2, end: 2, label: '' }] },
      { type: 'ins', kind: 'lines', ranges: [{ start: 2, end: 2, label: '' }] },
      { type: 'del', kind: 'lines', ranges: [{ start: 2, end: 2, label: '' }] },
    ]

    const map = buildLineMarkMap(marks, ['a', 'b', 'c'])
    assert.equal(map.get(2).type, 'del')
  })
})

describe('buildCodeBlockHtml', () => {
  it('escapes code text so a fence cannot inject markup', () => {
    const html = buildCodeBlockHtml('<img src=x onerror=alert(1)>', parseFenceInfo('html'))
    assert.ok(!html.includes('<img src=x'))
    assert.ok(html.includes('&lt;img src=x onerror=alert(1)&gt;'))
  })

  it('escapes a crafted title attribute', () => {
    const html = buildCodeBlockHtml('x', parseFenceInfo('js title="a\\" onmouseover=alert(1) x=\\""'))
    // 引号被转义成 &quot;，属性无法提前闭合，因此没有真正的 onmouseover 属性。
    assert.ok(!/" onmouseover=/.test(html))
    assert.ok(html.includes('&quot;'))
  })

  it('renders line numbers starting from startLineNumber', () => {
    const html = buildCodeBlockHtml('a\nb', parseFenceInfo('js showLineNumbers startLineNumber=5'))
    assert.ok(html.includes('>5<'))
    assert.ok(html.includes('>6<'))
  })

  it('collapses only the requested lines', () => {
    const html = buildCodeBlockHtml('a\nb\nc', parseFenceInfo('js collapse={2-2}'))
    const collapsed = html.match(/is-collapsed/g) || []
    assert.equal(collapsed.length, 1)
  })

  it('auto-marks added and removed lines for diff fences', () => {
    const html = buildCodeBlockHtml('-old\n+new\nkeep', parseFenceInfo('diff'))
    assert.ok(html.includes('is-del'))
    assert.ok(html.includes('is-ins'))
  })
})

describe('buildFenceInfo', () => {
  it('round-trips through parseFenceInfo', () => {
    const info = buildFenceInfo({
      lang: 'js',
      title: 'app.js',
      highlight: [{ start: 1, end: 3 }],
      ins: [{ start: 6, end: 6 }],
      del: [{ start: 7, end: 7 }],
      showLineNumbers: true,
      startLineNumber: 5,
      collapse: [{ start: 1, end: 4 }],
      wrap: false,
      frame: 'code',
    })

    const parsed = parseFenceInfo(info)
    assert.equal(parsed.lang, 'js')
    assert.equal(parsed.title, 'app.js')
    assert.equal(parsed.startLineNumber, 5)
    assert.equal(parsed.showLineNumbers, true)
    assert.equal(parsed.wrap, false)
    assert.equal(parsed.frame, 'code')
    assert.equal(parsed.collapse.length, 1)
  })

  it('omits startLineNumber when it is 1 or missing', () => {
    assert.equal(buildFenceInfo({ lang: 'js', startLineNumber: 1 }), 'js')
  })
})

describe('replaceFenceLanguage', () => {
  it('keeps the remaining parameters', () => {
    assert.equal(
      replaceFenceLanguage('js title="a.js" {1-2}', 'python'),
      'python title="a.js" {1-2}',
    )
  })

  it('adds the language when the info string had none', () => {
    assert.equal(replaceFenceLanguage('title="a.js"', 'python'), 'python title="a.js"')
  })

  it('returns the language for an empty info string', () => {
    assert.equal(replaceFenceLanguage('', 'python'), 'python')
  })
})

describe('helpers', () => {
  it('escapeHtml covers the five HTML-significant characters', () => {
    assert.equal(escapeHtml(`&<>"'`), '&amp;&lt;&gt;&quot;&#39;')
  })

  it('getFenceLanguage falls back to text', () => {
    assert.equal(getFenceLanguage(''), 'text')
    assert.equal(getFenceLanguage('js {1}'), 'js')
  })

  it('parseCodeGroupLabels pads missing labels', () => {
    assert.deepEqual(parseCodeGroupLabels('labels=[a.js]', 2), ['a.js', 'Tab 2'])
  })
})
