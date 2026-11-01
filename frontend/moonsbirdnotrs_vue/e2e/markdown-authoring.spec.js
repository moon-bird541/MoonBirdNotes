import { expect, test } from '@playwright/test'

const currentUser = { id: 1, username: 'local' }

const note = {
  id: 1,
  title: '写作验收',
  source_filename: 'w.md',
  file_url: null,
  markdown_content: '第一段正文。\n\n第二段正文。',
  rendered_html: '<p>第一段正文。</p><p>第二段正文。</p>',
  word_count: 12,
  tags: [{ id: 1, name: 'test' }],
  is_pinned: false,
  pinned_at: null,
  importance: '0',
  created_at: '2026-08-17T00:00:00Z',
  updated_at: '2026-08-17T00:00:00Z',
}

const json = (route, body, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

/** 已经带一个自定义标题提示框 + 一段普通正文的笔记（笔记 2）。 */
const noteWithCallout = {
  ...note,
  id: 2,
  title: '已有提示框',
  markdown_content: '> [!WARNING] 上线前必看\n> 警告类。\n\n跟在后面的正文。',
  rendered_html:
    '<blockquote class="moonbird-callout moonbird-callout-warning"><p>上线前必看</p><p>警告类。</p></blockquote><p>跟在后面的正文。</p>',
}

const mockApi = async (page, state) => {
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    const method = route.request().method()

    if (path === '/api/session/') return json(route, { user: currentUser })
    if (path === '/api/notes/1/' && method === 'GET') return json(route, note)
    if (path === '/api/notes/2/' && method === 'GET') return json(route, noteWithCallout)
    if (path === '/api/notes/1/edit/') {
      state.saved = JSON.parse(route.request().postData() || '{}')
      return json(route, { ...note, markdown_content: state.saved.markdown_content })
    }
    if (path === '/api/notes/2/edit/') {
      state.saved = JSON.parse(route.request().postData() || '{}')
      return json(route, { ...noteWithCallout, markdown_content: state.saved.markdown_content })
    }
    if (path === '/api/notes/1/versions/' || path === '/api/notes/2/versions/') return json(route, [])
    if (path === '/api/notes/tags/') return json(route, [{ id: 1, name: 'test' }])
    return json(route, { detail: `unhandled ${method} ${path}` }, 404)
  })
}

/** 关闭自动保存，避免测试期间的定时保存干扰断言。 */
const disableAutoSave = (page) =>
  page.addInitScript(() => {
    localStorage.setItem('moonbird_editor_settings', JSON.stringify({ autoSaveEnabled: false }))
  })

const editor = (page) => page.locator('.toastui-editor-ww-container .ProseMirror')
const floatingToolbar = (page) => page.getByRole('navigation', { name: '固定正文工具栏' })

/** 选中整篇正文并等悬浮工具条出现。 */
const selectAll = async (page) => {
  await editor(page).click()
  await page.keyboard.press('Control+A')
  await expect(floatingToolbar(page)).toBeVisible()
}

/**
 * 点浮层「❢」→ 选类型。
 * 按钮的 aria-label 会随状态变化（插入 / 修改或取消），因此用稳定的 data-action 定位。
 */
const pickCallout = async (page, label) => {
  await floatingToolbar(page).locator('[data-action="callout"]').click()
  await page.locator('.fixed-callout-option', { hasText: label }).click()
}

test('selection toolbar wraps the selected text into a callout', async ({ page }) => {
  const state = { saved: null }
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))

  await disableAutoSave(page)
  await mockApi(page, state)
  await page.goto('/notes/1/edit', { waitUntil: 'domcontentloaded' })
  await expect(editor(page)).toBeVisible()

  await selectAll(page)
  await pickCallout(page, '警告')

  const callout = page.locator('.toastui-editor-ww-container blockquote.moonbird-callout')
  await expect(callout).toHaveCount(1)
  await expect(callout).toHaveClass(/moonbird-callout-warning/)
  // 选中的正文被包进提示框，而不是被占位文字替换
  await expect(callout).toContainText('第一段正文。')
  await expect(callout).toContainText('第二段正文。')
  await expect(callout).not.toContainText('提示内容')

  expect(errors).toEqual([])
})

test('clicking the same callout type again removes the callout', async ({ page }) => {
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))

  await disableAutoSave(page)
  await mockApi(page, { saved: null })
  await page.goto('/notes/1/edit', { waitUntil: 'domcontentloaded' })
  await expect(editor(page)).toBeVisible()

  await selectAll(page)
  await pickCallout(page, '注意')
  await expect(page.locator('blockquote.moonbird-callout-note')).toHaveCount(1)

  // 再次点击同类型 → 取消
  await selectAll(page)
  await pickCallout(page, '注意')

  await expect(page.locator('.toastui-editor-ww-container blockquote.moonbird-callout')).toHaveCount(0)
  await expect(editor(page)).toContainText('第一段正文。')
  await expect(editor(page)).toContainText('第二段正文。')

  expect(errors).toEqual([])
})

test('switching callout type retypes instead of nesting', async ({ page }) => {
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))

  await disableAutoSave(page)
  await mockApi(page, { saved: null })
  await page.goto('/notes/1/edit', { waitUntil: 'domcontentloaded' })
  await expect(editor(page)).toBeVisible()

  await selectAll(page)
  await pickCallout(page, '警告')
  await expect(page.locator('blockquote.moonbird-callout-warning')).toHaveCount(1)

  // 换成提示 → 只改类型，不嵌套
  await selectAll(page)
  await pickCallout(page, '提示')

  await expect(page.locator('.toastui-editor-ww-container blockquote')).toHaveCount(1)
  await expect(page.locator('blockquote.moonbird-callout-tip')).toHaveCount(1)
  await expect(page.locator('blockquote.moonbird-callout-warning')).toHaveCount(0)
  await expect(editor(page)).toContainText('第一段正文。')

  expect(errors).toEqual([])
})

test('retyping from inside the callout keeps its custom title', async ({ page }) => {
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))

  await disableAutoSave(page)
  await mockApi(page, { saved: null })
  await page.goto('/notes/2/edit', { waitUntil: 'domcontentloaded' })
  await expect(editor(page)).toBeVisible()

  const warning = page.locator('blockquote.moonbird-callout-warning')
  await expect(warning).toHaveCount(1)

  // 光标放进「警告类。」这一行并选中它，再改成「提示」
  await warning.locator('p').last().click()
  await page.keyboard.press('End')
  await page.keyboard.press('Shift+Home')
  await expect(floatingToolbar(page)).toBeVisible()

  await pickCallout(page, '提示')

  // 只有一个引用块：没有嵌套
  await expect(page.locator('.toastui-editor-ww-container blockquote')).toHaveCount(1)
  await expect(page.locator('blockquote.moonbird-callout-tip')).toHaveCount(1)
  await expect(page.locator('blockquote.moonbird-callout-warning')).toHaveCount(0)
  // 标题保留、正文不动
  await expect(page.locator('.mb-callout-preview-title')).toHaveText('✦ 上线前必看')
  await expect(editor(page)).toContainText('警告类。')
  await expect(editor(page)).toContainText('跟在后面的正文。')

  expect(errors).toEqual([])
})

test('retyping a callout does not touch unrelated follow-up paragraphs', async ({ page }) => {
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))

  await disableAutoSave(page)
  await mockApi(page, { saved: null })
  await page.goto('/notes/2/edit', { waitUntil: 'domcontentloaded' })
  await expect(editor(page)).toBeVisible()

  // 全选整篇（$from 落在 h1/p 上，不在提示框里）→ 仍然只改那一个提示框
  await selectAll(page)
  await pickCallout(page, '重要')

  await expect(page.locator('.toastui-editor-ww-container blockquote')).toHaveCount(1)
  await expect(page.locator('blockquote.moonbird-callout-important')).toHaveCount(1)
  await expect(editor(page)).toContainText('跟在后面的正文。')

  expect(errors).toEqual([])
})

test('code block options dialog writes title and line marks into the fence', async ({ page }) => {
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))

  await disableAutoSave(page)
  await mockApi(page, { saved: null })
  await page.goto('/notes/1/edit', { waitUntil: 'domcontentloaded' })
  await expect(editor(page)).toBeVisible()

  // 把整段变成代码块
  await selectAll(page)
  await floatingToolbar(page).locator('[data-action="code-block"]').click()

  await selectAll(page)
  await floatingToolbar(page).locator('[data-action="code-block-options"]').click()

  const dialog = page.locator('.el-dialog').filter({ hasText: '代码块设置' })
  await expect(dialog).toBeVisible()

  await dialog.getByPlaceholder('app.js（留空则不显示）').fill('main.js')
  await dialog.getByPlaceholder('1,3-5').fill('1')
  await dialog.getByRole('button', { name: '应用' }).click()

  const head = page.locator('.toastui-editor-ww-container .mb-code-preview-head')
  await expect(head.locator('.mb-code-preview-title')).toHaveText('main.js')
  // 只填了高亮行，没有勾行号，因此徽标是「行标记」
  await expect(head.locator('.mb-code-preview-badges')).toContainText('行标记')
  // 选区是一整篇两个段落，toast-ui 会按块各生成一个代码块；参数只写在第一个上
  await expect(
    page.locator('.toastui-editor-ww-container .toastui-editor-ww-code-block').first()
  ).toHaveAttribute('data-language', /title="main\.js"/)

  expect(errors).toEqual([])
})

test('fixed toolbar still inserts a callout block', async ({ page }) => {
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))

  await disableAutoSave(page)
  await mockApi(page, { saved: null })
  await page.goto('/notes/1/edit', { waitUntil: 'domcontentloaded' })
  await expect(editor(page)).toBeVisible()

  await editor(page).click()
  await page.keyboard.press('Control+End')

  await floatingToolbar(page).getByRole('button', { name: '插入提示框' }).click()
  await page.locator('.fixed-callout-option').first().click()

  const callout = page.locator('.toastui-editor-ww-container blockquote.moonbird-callout').first()
  await expect(callout).toBeVisible()
  await expect(callout).toHaveClass(/moonbird-callout-note/)
  await expect(callout.locator('.mb-callout-preview-title')).toHaveText('ℹ 注意')

  expect(errors).toEqual([])
})
