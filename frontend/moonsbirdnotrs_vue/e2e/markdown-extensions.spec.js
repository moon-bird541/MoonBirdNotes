import { expect, test } from '@playwright/test'

const currentUser = { id: 1, username: 'local' }

const markdown = [
  '# 扩展语法验收',
  '',
  '> [!WARNING] 自定义标题',
  '> 提示框正文',
  '',
  '> [!TLDR]',
  '> 别名应折叠成摘要',
  '',
  ':::tip[容器写法]',
  '容器内容',
  ':::',
  '',
  '```js title="app.js" {1} ins={2} showLineNumbers startLineNumber=5 collapse={1-2}',
  'const a = 1',
  'const b = 2',
  'const c = 3',
  '```',
  '',
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

const makeNote = () => ({
  id: 1,
  title: '扩展语法验收',
  source_filename: 'extended.md',
  file_url: null,
  markdown_content: markdown,
  rendered_html: '',
  word_count: 64,
  tags: [{ id: 1, name: '语法' }],
  is_pinned: false,
  pinned_at: null,
  importance: '3',
  created_at: '2026-10-21T00:00:00Z',
  updated_at: '2026-10-21T00:00:00Z',
})

const json = (route, body, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

const mock = async (page) => {
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/session/') return json(route, { user: currentUser })
    if (path === '/api/notes/1/') return json(route, makeNote())
    if (path === '/api/notes/1/versions/') return json(route, [])
    if (path === '/api/notes/tags/') return json(route, [{ id: 1, name: '语法' }])
    return json(route, { detail: `unhandled ${path}` }, 404)
  })
}

test('reader renders firefly markdown extensions', async ({ page }) => {
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))

  await mock(page)
  await page.goto('/notes/1', { waitUntil: 'domcontentloaded' })

  await expect(page.locator('article').getByRole('heading', { name: '扩展语法验收' })).toBeVisible()

  // 提示框：GitHub 写法 + 自定义标题
  const warning = page.locator('blockquote.moonbird-callout-warning').first()
  await expect(warning).toBeVisible()
  await expect(warning.locator('.moonbird-callout-title')).toContainText('自定义标题')
  await expect(warning).toContainText('提示框正文')

  // 别名折叠：TLDR → abstract
  await expect(page.locator('blockquote.moonbird-callout-abstract')).toHaveCount(1)

  // 容器写法
  const container = page.locator('blockquote.moonbird-callout-tip').first()
  await expect(container).toBeVisible()
  await expect(container.locator('.moonbird-callout-title')).toContainText('容器写法')
  await expect(container).toContainText('容器内容')

  // 代码块：标题栏、行号起点、行标记
  const codeBlock = page.locator('.moonbird-code').first()
  await expect(codeBlock).toBeVisible()
  await expect(codeBlock.locator('.moonbird-code-title')).toHaveText('app.js')
  await expect(codeBlock.locator('.moonbird-code-lineno').first()).toHaveText('5')
  await expect(codeBlock.locator('.moonbird-code-line.is-mark')).toHaveCount(1)
  await expect(codeBlock.locator('.moonbird-code-line.is-ins')).toHaveCount(1)

  // 折叠：初始 2 行隐藏，点击后展开
  const collapseToggle = codeBlock.locator('.moonbird-code-toggle')
  await expect(collapseToggle).toBeVisible()
  await expect(codeBlock.locator('.moonbird-code-line.is-collapsed:visible')).toHaveCount(0)
  await collapseToggle.click()
  await expect(codeBlock.locator('.moonbird-code-line.is-collapsed:visible')).toHaveCount(2)

  // Tab 代码组
  const group = page.locator('.moonbird-code-group')
  await expect(group).toBeVisible()
  const tabs = group.locator('.moonbird-code-tab')
  await expect(tabs).toHaveCount(2)
  await expect(tabs.first()).toHaveText('a.js')
  await expect(group.locator('.moonbird-code-panel').first()).toBeVisible()
  await tabs.nth(1).click()
  await expect(group.locator('.moonbird-code-panel').nth(1)).toBeVisible()
  await expect(group.locator('.moonbird-code-panel').first()).toBeHidden()

  expect(errors).toEqual([])
})
