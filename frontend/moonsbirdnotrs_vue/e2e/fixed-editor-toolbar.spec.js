import { expect, test } from '@playwright/test'

const currentUser = {
  id: 1,
  username: 'toolbar-tester',
}

const note = {
  id: 1,
  title: 'Toolbar note',
  tags: [{ id: 1, name: 'test' }],
  markdown_content: 'alpha beta',
  rendered_html: '<p>alpha beta</p>',
  created_at: '2026-08-17T00:00:00Z',
  updated_at: '2026-08-17T00:00:00Z',
}

const diary = {
  id: 9,
  note_id: 19,
  diary_date: '2026-08-17',
  title: 'Toolbar diary',
  mood: '平静',
  weather: '晴',
  summary: 'Toolbar regression coverage',
  markdown_content: 'diary body',
  rendered_html: '<p>diary body</p>',
  created_at: '2026-08-17T00:00:00Z',
  updated_at: '2026-08-17T00:00:00Z',
}

const fulfillJson = (route, status, body) =>
  route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })

const mockEditorApi = async (page) => {
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname

    if (path === '/api/session/') {
      return fulfillJson(route, 200, { user: currentUser })
    }
    if (path === '/api/notes/1/') {
      return fulfillJson(route, 200, note)
    }
    if (path === '/api/notes/tags/') {
      return fulfillJson(route, 200, [{ id: 1, name: 'test' }])
    }
    if (path === '/api/notes/1/versions/') {
      return fulfillJson(route, 200, [])
    }
    if (path === '/api/notes/diaries/by-date/2026-08-17/') {
      return fulfillJson(route, 200, diary)
    }

    return fulfillJson(route, 404, { detail: `Unhandled toolbar API: ${request.method()} ${path}` })
  })
}

const fixedToolbar = (page) => page.getByRole('navigation', { name: '固定正文工具栏' })
const wysiwygEditor = (page) => page.locator('.toastui-editor-ww-container .ProseMirror')

const selectEditorText = (editor, start, end) =>
  editor.evaluate(
    (root, rangeOffsets) => {
      const textBlock = root.querySelector('p, h1, h2, h3, blockquote, li')
      const walker = document.createTreeWalker(textBlock, NodeFilter.SHOW_TEXT)
      const textNodes = []
      let textNode = walker.nextNode()
      while (textNode) {
        textNodes.push(textNode)
        textNode = walker.nextNode()
      }

      const resolveOffset = (targetOffset) => {
        let consumed = 0
        for (const node of textNodes) {
          const nextConsumed = consumed + node.textContent.length
          if (targetOffset <= nextConsumed) {
            return { node, offset: targetOffset - consumed }
          }
          consumed = nextConsumed
        }
        throw new Error(`Editor text offset ${targetOffset} is out of range`)
      }

      const start = resolveOffset(rangeOffsets.start)
      const end = resolveOffset(rangeOffsets.end)
      const range = document.createRange()
      range.setStart(start.node, start.offset)
      range.setEnd(end.node, end.offset)
      const selection = document.getSelection()
      selection.removeAllRanges()
      selection.addRange(range)
      document.dispatchEvent(new Event('selectionchange'))
    },
    { start, end }
  )

const useFixedToolbarOnStartup = (page) =>
  page.addInitScript(() => {
    localStorage.setItem(
      'moonbird_editor_settings',
      JSON.stringify({
        toolbarMode: 'fixed',
      })
    )
  })

const pageErrors = new WeakMap()

test.beforeEach(async ({ page }) => {
  const errors = []
  pageErrors.set(page, errors)
  page.on('pageerror', (error) => errors.push(error.message))
  await mockEditorApi(page)
})

test.afterEach(async ({ page }) => {
  expect(pageErrors.get(page)).toEqual([])
})

test('settings switches both editors between current and fixed toolbar modes', async ({ page }) => {
  await page.addInitScript(() => {
    if (sessionStorage.getItem('toolbar-old-settings-seeded')) {
      return
    }
    localStorage.setItem(
      'moonbird_editor_settings',
      JSON.stringify({ fontSizePx: 18, toolbarMode: 'legacy-floating' })
    )
    sessionStorage.setItem('toolbar-old-settings-seeded', 'true')
  })
  await page.goto('/notes/1/edit')

  await expect(fixedToolbar(page)).toHaveCount(0)
  await expect(page.locator('.editor-side-toolbar')).toBeVisible()

  await page.getByRole('button', { name: '设置' }).click()
  await page.getByRole('button', { name: '固定工具栏', exact: true }).click()

  await expect(fixedToolbar(page)).toBeVisible()
  await expect(page.locator('.editor-side-toolbar')).toHaveCount(0)
  await expect.poll(() => page.evaluate(() => {
    const settings = JSON.parse(localStorage.getItem('moonbird_editor_settings'))
    return { fontSizePx: settings.fontSizePx, toolbarMode: settings.toolbarMode }
  })).toEqual({ fontSizePx: 18, toolbarMode: 'fixed' })

  await page.goto('/diary/2026-08-17/edit')
  await expect(fixedToolbar(page)).toBeVisible()
  await expect(page.locator('.floating-toolbar')).toHaveCount(0)

  const diaryEditor = wysiwygEditor(page)
  await diaryEditor.click()
  await selectEditorText(diaryEditor, 0, 5)
  await fixedToolbar(page).getByRole('button', { name: '标题 H2' }).click()
  await expect(diaryEditor.locator('h2')).toContainText('diary body')

  await page.getByRole('button', { name: '设置' }).click()
  await page.getByRole('button', { name: '当前模式', exact: true }).click()
  await expect(fixedToolbar(page)).toHaveCount(0)

  await diaryEditor.click()
  await selectEditorText(diaryEditor, 0, 5)
  await expect(page.locator('.floating-toolbar')).toBeVisible()
})

test('fixed note toolbar keeps selection for formatting, links, and tables', async ({ page }) => {
  await useFixedToolbarOnStartup(page)
  await page.goto('/notes/1/edit')

  const toolbar = fixedToolbar(page)
  const editor = wysiwygEditor(page)
  await expect(toolbar).toBeVisible()
  await editor.click()

  await selectEditorText(editor, 0, 5)
  const boldButton = toolbar.getByRole('button', { name: '加粗' })
  await boldButton.click()
  await expect(editor.locator('strong')).toContainText('alpha')
  await expect(boldButton).toHaveAttribute('aria-pressed', 'true')

  await editor.click()
  await page.keyboard.press('Control+End')
  await toolbar.getByRole('button', { name: '斜体' }).click()
  await page.keyboard.insertText(' tail')
  await expect(editor.locator('em')).toContainText('tail')

  await selectEditorText(editor, 6, 10)
  await toolbar.getByRole('button', { name: '插入链接' }).click()
  const linkUrlInput = page.getByPlaceholder('https://example.com')
  await linkUrlInput.fill('javascript:alert(1)')
  await page.getByRole('button', { name: '插入', exact: true }).click()
  await expect(page.getByText('链接仅支持 http、https、mailto、tel 或相对地址')).toBeVisible()
  await expect(editor.locator('a')).toHaveCount(0)
  await linkUrlInput.fill('https://example.com/docs')
  await page.getByRole('button', { name: '插入', exact: true }).click()
  await expect(editor.locator('a[href="https://example.com/docs"]')).toContainText('beta')

  await editor.click()
  await page.keyboard.press('Control+End')
  await toolbar.getByRole('button', { name: '插入表格' }).click()
  await page.getByRole('button', { name: '插入 2 行 3 列表格' }).click()
  await expect(editor.locator('table')).toBeVisible()
  await expect(editor.locator('table tr')).toHaveCount(2)

  const fileChooserPromise = page.waitForEvent('filechooser')
  await toolbar.getByRole('button', { name: '上传图片' }).click()
  await fileChooserPromise
})

test('fixed toolbar scrolls internally on a narrow viewport without widening the page', async ({ page }) => {
  await page.setViewportSize({ width: 480, height: 760 })
  await useFixedToolbarOnStartup(page)
  await page.goto('/diary/2026-08-17/edit')

  const toolbar = fixedToolbar(page)
  await expect(toolbar).toBeVisible()
  await expect(toolbar).toHaveCSS('position', 'sticky')

  const dimensions = await toolbar.evaluate((element) => {
    const track = element.querySelector('.fixed-editor-toolbar-track')
    return {
      toolbarTop: Math.round(element.getBoundingClientRect().top),
      pageWidth: document.documentElement.scrollWidth,
      viewportWidth: window.innerWidth,
      trackClientWidth: track.clientWidth,
      trackScrollWidth: track.scrollWidth,
    }
  })

  expect(dimensions.pageWidth).toBeLessThanOrEqual(dimensions.viewportWidth)
  expect(dimensions.trackScrollWidth).toBeGreaterThan(dimensions.trackClientWidth)

  await toolbar.evaluate((element) => element.scrollIntoView({ block: 'start' }))
  await expect
    .poll(() => toolbar.evaluate((element) => Math.round(element.getBoundingClientRect().top)))
    .toBeGreaterThanOrEqual(7)
  const stickyTop = await toolbar.evaluate((element) => Math.round(element.getBoundingClientRect().top))
  expect(stickyTop).toBeLessThan(dimensions.toolbarTop)
  expect(stickyTop).toBeLessThanOrEqual(50)
})
