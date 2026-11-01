import { expect, test } from '@playwright/test'

const currentUser = { id: 1, username: 'local' }

const makeNote = (markdown) => ({
  id: 1,
  title: '未命名笔记',
  source_filename: '',
  file_url: null,
  markdown_content: markdown,
  rendered_html: markdown ? `<p>${markdown}</p>` : '',
  word_count: markdown.length,
  tags: [{ id: 1, name: '未分类' }],
  is_pinned: false,
  pinned_at: null,
  importance: '0',
  created_at: '2026-10-21T00:00:00Z',
  updated_at: '2026-10-21T00:00:00Z',
})

const json = (route, body, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

async function mock(page, markdown) {
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/session/') return json(route, { user: currentUser })
    if (path === '/api/notes/1/') return json(route, makeNote(markdown))
    if (path === '/api/notes/tags/') return json(route, [{ id: 1, name: '未分类' }])
    if (path === '/api/notes/1/versions/') return json(route, [])
    if (path === '/api/notes/1/edit/') return json(route, makeNote(markdown))
    return json(route, { detail: `unhandled ${path}` }, 404)
  })
}

test.use({ viewport: { width: 2048, height: 1018 }, deviceScaleFactor: 1.25 })

const state = () => {
  const root = document.querySelector('.wysiwyg-editor')
  const main = document.querySelector('.toastui-editor-main')
  const ww = document.querySelector('.toastui-editor-ww-container')
  const pm = document.querySelector('.toastui-editor-ww-container .ProseMirror')
  const p = pm ? pm.querySelector('p') : null
  const box = p ? p.getBoundingClientRect() : null
  const wwBox = ww ? ww.getBoundingClientRect() : null
  return {
    rootCls: root ? root.getAttribute('class') : null,
    mainHeight: main ? Math.round(main.getBoundingClientRect().height) : null,
    pmHeight: pm ? Math.round(pm.getBoundingClientRect().height) : null,
    pText: p ? p.textContent : null,
    // 相对编辑区的位置：断言文字落在可见编辑区内部，而不是贴到页面别处
    pOffsetTop: box && wwBox ? Math.round(box.top - wwBox.top) : null,
    wwHeight: wwBox ? Math.round(wwBox.height) : null,
  }
}

test('empty note stays usable after first keystroke', async ({ page }) => {
  await mock(page, '')
  await page.goto('/notes/1/edit', { waitUntil: 'domcontentloaded' })

  // 并行跑全量用例时编辑器初始化可能慢于固定等待，先等根节点真正挂载
  await expect(page.locator('.wysiwyg-editor')).toBeVisible()
  await expect(page.locator('.toastui-editor-ww-container .ProseMirror').first()).toBeVisible()

  const before = await page.evaluate(state)
  expect(before.rootCls).toContain('auto-height')

  const pm = page.locator('.toastui-editor-ww-container .ProseMirror').first()
  await pm.click()
  await page.keyboard.type('第一篇笔记')
  await page.waitForTimeout(800)

  const after = await page.evaluate(state)
  console.log('BEFORE', JSON.stringify(before))
  console.log('AFTER ', JSON.stringify(after))

  // regression: Toast UI 的 auto-height 类必须仍然存在
  expect(after.rootCls).toContain('auto-height')
  // 编辑区不能被压扁成 2px
  expect(after.mainHeight).toBeGreaterThan(400)
  // 输入的文字必须落在编辑区内部并且可见
  expect(after.pText).toContain('第一篇笔记')
  // 段落相对编辑区顶部的偏移应保持稳定（不能跑到编辑区外）
  expect(after.pOffsetTop).toBeGreaterThanOrEqual(0)
  expect(after.pOffsetTop).toBeLessThan(after.wwHeight)

  // 继续输入仍然正常
  await page.keyboard.type('，继续输入')
  await page.waitForTimeout(600)
  const more = await page.evaluate(state)
  expect(more.mainHeight).toBeGreaterThan(400)
  expect(more.pText).toContain('继续输入')

  // 清空后再次输入也不能塌陷
  await page.keyboard.press('Control+A')
  await page.keyboard.press('Delete')
  await page.waitForTimeout(500)
  const emptied = await page.evaluate(state)
  expect(emptied.rootCls).toContain('auto-height')
  expect(emptied.mainHeight).toBeGreaterThan(400)

  await page.keyboard.type('重新写')
  await page.waitForTimeout(600)
  const retyped = await page.evaluate(state)
  console.log('RETYPED', JSON.stringify(retyped))
  expect(retyped.rootCls).toContain('auto-height')
  expect(retyped.mainHeight).toBeGreaterThan(400)
  expect(retyped.pOffsetTop).toBeGreaterThanOrEqual(0)

  // 截图只用于失败排查，落在 test-results 下，避免污染仓库根目录
  await page.screenshot({ path: 'test-results/regression-empty-note.png' })
})
