import { expect, test } from '@playwright/test'

const currentUser = { id: 1, username: 'local' }

const diary = {
  id: 9,
  note_id: 19,
  diary_date: '2026-08-17',
  title: '日记验收',
  mood: '平静',
  weather: '晴',
  summary: '日记摘要',
  markdown_content: '> [!TIP] 日记提示\n> 正文\n\n```js title="a.js" showLineNumbers\nconst a = 1\n```',
  rendered_html: '',
  created_at: '2026-08-17T00:00:00Z',
  updated_at: '2026-08-17T00:00:00Z',
}

const json = (route, body, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

test('diary editor previews callouts and inserts them from the toolbar', async ({ page }) => {
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))

  await page.addInitScript(() => {
    localStorage.setItem(
      'moonbird_editor_settings',
      JSON.stringify({ autoSaveEnabled: false })
    )
  })

  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/session/') return json(route, { user: currentUser })
    if (path === '/api/notes/diaries/by-date/2026-08-17/') return json(route, diary)
    if (path.startsWith('/api/notes/diaries/')) return json(route, diary)
    return json(route, { detail: `unhandled ${path}` }, 404)
  })

  await page.goto('/diary/2026-08-17/edit', { waitUntil: 'domcontentloaded' })

  const editorRoot = page.locator('.diary-editor-root .toastui-editor-ww-container')
  await expect(editorRoot.locator('.ProseMirror')).toBeVisible()

  // 已有内容在富文本里也按最终外观显示
  const callout = editorRoot.locator('blockquote.moonbird-callout-tip')
  await expect(callout).toHaveCount(1)
  await expect(callout.locator('.mb-callout-preview-title')).toHaveText('✦ 日记提示')

  const codeHead = editorRoot.locator('.mb-code-preview-head')
  await expect(codeHead.locator('.mb-code-preview-title')).toHaveText('a.js')

  // 工具栏插入提示框也要写成真正的引用块
  const toolbar = page.getByRole('navigation', { name: '固定正文工具栏' })
  await expect(toolbar).toBeVisible()

  // 光标已在日记的提示框里，此时按钮语义是「修改或取消」，用稳定的 data-action 定位
  await toolbar.locator('[data-action="callout"]').click()
  await page.locator('.fixed-callout-option', { hasText: '注意' }).click()

  await expect(editorRoot.locator('blockquote.moonbird-callout')).toHaveCount(1)
  await expect(editorRoot.locator('blockquote.moonbird-callout-note')).toHaveCount(1)
  await expect(editorRoot).toContainText('正文')

  expect(errors).toEqual([])
})
