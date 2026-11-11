import assert from 'node:assert/strict'
import { describe, it } from 'vitest'

import { normalizePastedCodeHtml } from '../pastedCode.js'

const parse = (html) => new DOMParser().parseFromString(html, 'text/html')

describe('normalizePastedCodeHtml', () => {
  it('returns null when there is nothing to repair', () => {
    assert.equal(normalizePastedCodeHtml(''), null)
    assert.equal(normalizePastedCodeHtml('<p>纯文本</p>'), null)
    assert.equal(normalizePastedCodeHtml('<pre>a\nb\nc</pre>'), null)
  })

  it('merges a run of single-line <pre> blocks into one code block', () => {
    const lines = ['{', '  "a": 1,', '  "b": 2', '}']
    const html = lines.map((line) => `<pre>${line}</pre>`).join('')
    const normalized = normalizePastedCodeHtml(html)
    const pres = parse(normalized).querySelectorAll('pre')

    assert.equal(pres.length, 1)
    assert.equal(pres[0].textContent, lines.join('\n'))
  })

  it('keeps two adjacent single-line blocks untouched', () => {
    assert.equal(normalizePastedCodeHtml('<pre>a</pre><pre>b</pre>'), null)
  })

  it('does not merge blocks that already contain multiple lines', () => {
    const html = '<pre>a\nb</pre><pre>c\nd</pre><pre>e\nf</pre>'
    assert.equal(normalizePastedCodeHtml(html), null)
  })

  it('keeps the <code> element and its language class of the first block', () => {
    const html = ['<pre><code class="language-json">a</code></pre>', '<pre><code class="language-json">b</code></pre>', '<pre><code class="language-json">c</code></pre>'].join('')
    const normalized = normalizePastedCodeHtml(html)
    const code = parse(normalized).querySelector('pre > code')

    assert.equal(code.className, 'language-json')
    assert.equal(code.textContent, 'a\nb\nc')
  })

  it('flattens <pre><div>line</div>…</pre> into newline separated text', () => {
    const html = '<pre><div>line1</div><div>line2</div><div>line3</div></pre>'
    const normalized = normalizePastedCodeHtml(html)
    const pre = parse(normalized).querySelector('pre')

    assert.equal(pre.children.length, 0)
    assert.equal(pre.textContent, 'line1\nline2\nline3')
  })

  it('ignores whitespace text nodes between the merged blocks', () => {
    const html = '<pre>a</pre>\n<pre>b</pre>\n  <pre>c</pre>'
    const normalized = normalizePastedCodeHtml(html)
    const pres = parse(normalized).querySelectorAll('pre')

    assert.equal(pres.length, 1)
    assert.equal(pres[0].textContent, 'a\nb\nc')
  })
})
