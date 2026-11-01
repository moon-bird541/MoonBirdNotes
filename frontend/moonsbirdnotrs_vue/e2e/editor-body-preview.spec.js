import { expect, test } from '@playwright/test'

const currentUser = { id: 1, username: 'local' }

const markdown = [
  '> [!TIP] 编辑器标题',
  '> 编辑器预览正文',
  '',
  '```js title="preview.js" {1} showLineNumbers',
  'const a = 1',
  'const b = 2',
  '```',
  '',
  '::: code-group labels=[one.js, two.py]',
  '',
  '```js',
  'console.log(1)',
  '```',
  '',
  '```py',
  'print(2)',
  '```',
  '',
  ':::',
].join('\n')

const makeNote = () => ({
  id: 1,
  title: '预览验收',
  source_filename: 'preview.md',
  file_url: null,
  markdown_content: markdown,
  rendered_html: '',
  word_count: 32,
  tags: [{ id: 1, name: '预览' }],
  is_pinned: false,
  pinned_at: null,
  importance: '0',
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
    if (path === '/api/notes/1/edit/') return json(route, makeNote())
    if (path === '/api/notes/1/versions/') return json(route, [])
    if (path === '/api/notes/tags/') return json(route, [{ id: 1, name: '预览' }])
    return json(route, { detail: `unhandled ${path}` }, 404)
  })
}

test('editor body preview renders extensions and sanitizes html', async ({ page }) => {
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))

  await mock(page)
  await page.goto('/notes/1/edit', { waitUntil: 'domcontentloaded' })

  await page.getByRole('button', { name: '正文预览' }).click()

  const dialog = page.locator('.el-dialog').filter({ hasText: '正文预览' })
  await expect(dialog).toBeVisible()

  // 提示框
  const callout = dialog.locator('.moonbird-callout-tip')
  await expect(callout).toBeVisible()
  await expect(callout.locator('.moonbird-callout-title')).toContainText('编辑器标题')
  await expect(callout).toContainText('编辑器预览正文')

  // 代码块标题与行号
  const codeBlock = dialog.locator('.moonbird-code').first()
  await expect(codeBlock.locator('.moonbird-code-title')).toHaveText('preview.js')
  await expect(codeBlock.locator('.moonbird-code-lineno')).toHaveCount(2)

  // 代码组
  const group = dialog.locator('.moonbird-code-group')
  await expect(group).toBeVisible()
  const tabs = group.locator('.moonbird-code-tab')
  await expect(tabs).toHaveCount(2)
  await expect(tabs.first()).toHaveText('one.js')

  // 净化：预览内容不允许出现脚本或内联事件
  const html = await dialog.locator('.body-preview').innerHTML()
  expect(html).not.toContain('<script')
  expect(html).not.toMatch(/ on\w+=/i)

  expect(errors).toEqual([])
})
