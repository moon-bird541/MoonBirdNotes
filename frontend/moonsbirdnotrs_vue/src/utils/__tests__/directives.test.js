import assert from 'node:assert/strict'
import { describe, it } from 'vitest'

import { expandDirectives, matchGroupPlaceholder, renderGroupPlaceholder } from '../directives.js'

describe('expandDirectives', () => {
  it('returns the source untouched when there is no container', () => {
    const source = '# title\n\nbody'
    assert.deepEqual(expandDirectives(source), { markdown: source, groups: [] })
  })

  it('turns a :::tip container into a callout blockquote', () => {
    const result = expandDirectives([':::tip[提示标题]', '正文', ':::'].join('\n'))

    assert.ok(result.markdown.includes('> [!TIP] 提示标题'))
    assert.ok(result.markdown.includes('> 正文'))
    assert.ok(!result.markdown.includes(':::'))
  })

  it('maps aliases to their canonical callout type', () => {
    assert.ok(expandDirectives([':::tldr', 'x', ':::'].join('\n')).markdown.includes('> [!ABSTRACT]'))
    assert.ok(expandDirectives([':::error', 'x', ':::'].join('\n')).markdown.includes('> [!DANGER]'))
  })

  it('leaves an unknown container name as plain text', () => {
    const source = [':::unknown', 'x', ':::'].join('\n')
    assert.equal(expandDirectives(source).markdown, source)
  })

  it('leaves an unclosed container as plain text instead of swallowing the rest', () => {
    const source = [':::tip', 'x'].join('\n')
    assert.equal(expandDirectives(source).markdown, source)
  })

  it('extracts a code-group into a placeholder plus rendered panels', () => {
    const source = [
      '::: code-group labels=[a.js, b.py]',
      '',
      '```js',
      'console.log(1)',
      '```',
      '',
      '```py',
      'print(1)',
      '```',
      '',
      ':::',
    ].join('\n')

    const result = expandDirectives(source)
    assert.equal(matchGroupPlaceholder(result.markdown), 0)
    assert.equal(result.groups.length, 1)
    assert.deepEqual(
      result.groups[0].map((panel) => panel.label),
      ['a.js', 'b.py'],
    )
  })

  it('escapes text inside a code-group so it cannot inject markup', () => {
    const source = ['::: code-group', '```html', '<img src=x onerror=alert(1)>', '```', ':::'].join('\n')
    const [panels] = expandDirectives(source).groups

    assert.ok(!panels[0].html.includes('<img src=x'))
  })
})

describe('renderGroupPlaceholder', () => {
  it('renders a tab list with the first panel active', () => {
    const groups = [
      [
        { label: 'a.js', html: '<p>a</p>' },
        { label: 'b.py', html: '<p>b</p>' },
      ],
    ]

    const html = renderGroupPlaceholder(groups, 0)
    assert.ok(html.includes('class="moonbird-code-tab is-active"'))
    assert.ok(html.includes('aria-selected="true"'))
    assert.equal((html.match(/aria-selected="true"/g) || []).length, 1)
  })

  it('returns an empty string for an out-of-range index', () => {
    assert.equal(renderGroupPlaceholder([], 0), '')
  })
})

describe('matchGroupPlaceholder', () => {
  it('returns null for unrelated HTML', () => {
    assert.equal(matchGroupPlaceholder('<p>x</p>'), null)
  })
})
