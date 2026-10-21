import { expect, test } from '@playwright/test'

const currentUser = {
  id: 1,
  username: 'theme-tester',
}

const note = {
  id: 1,
  title: '午夜主题验收笔记',
  excerpt: '用于验证暗色阅读与编辑表面。',
  word_count: 64,
  tags: [{ id: 1, name: '主题' }],
  is_pinned: false,
  importance: 3,
  markdown_content: '# 午夜正文\n\n> 安静阅读\n\n| 表头 | 内容 |\n| --- | --- |\n| 深色 | 清晰 |\n\n```js\nconst theme = "dark"\n```',
  rendered_html: '<h1>午夜正文</h1><blockquote>安静阅读</blockquote><table><thead><tr><th>表头</th><th>内容</th></tr></thead><tbody><tr><td>深色</td><td>清晰</td></tr></tbody></table><pre><code>const theme = "dark"</code></pre>',
  created_at: '2026-08-20T08:00:00Z',
  updated_at: '2026-08-20T09:00:00Z',
}

const summary = {
  stats: {
    note_count: 1,
    word_count: 64,
    tag_count: 1,
  },
  tag_distribution: [{ id: 1, name: '主题', count: 1, percentage: 100 }],
  recent_notes: [note],
  upload_activity: [{ date: '2026-08-20', count: 1 }],
}

const fulfillJson = (route, status, body) =>
  route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })

const mockThemeApi = async (page) => {
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname

    if (path === '/api/session/') {
      return fulfillJson(route, 200, { user: currentUser })
    }
    if (path === '/api/notes/summary/') {
      return fulfillJson(route, 200, summary)
    }
    if (path === '/api/notes/tags/') {
      return fulfillJson(route, 200, note.tags)
    }
    if (path === '/api/notes/') {
      return fulfillJson(route, 200, { count: 1, next: null, previous: null, results: [note] })
    }
    if (path === '/api/notes/1/') {
      return fulfillJson(route, 200, note)
    }
    if (path === '/api/notes/1/versions/') {
      return fulfillJson(route, 200, [])
    }

    return fulfillJson(route, 404, { detail: `Unhandled dark-theme API: ${request.method()} ${path}` })
  })
}

const parseRgb = (value) => {
  const channels = value.match(/[\d.]+/g)?.slice(0, 3).map(Number)
  if (!channels || channels.length !== 3) {
    throw new Error(`Unable to parse CSS color: ${value}`)
  }
  return channels
}

const relativeLuminance = (channels) => {
  const linear = channels.map((channel) => {
    const normalized = channel / 255
    return normalized <= 0.04045 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
}

const contrastRatio = (foreground, background) => {
  const foregroundLuminance = relativeLuminance(parseRgb(foreground))
  const backgroundLuminance = relativeLuminance(parseRgb(background))
  const lighter = Math.max(foregroundLuminance, backgroundLuminance)
  const darker = Math.min(foregroundLuminance, backgroundLuminance)
  return (lighter + 0.05) / (darker + 0.05)
}

const expectDarkSurface = async (locator) => {
  const backgroundColor = await locator.evaluate((element) => getComputedStyle(element).backgroundColor)
  expect(Math.max(...parseRgb(backgroundColor))).toBeLessThan(100)
}

const pageErrors = new WeakMap()

test.beforeEach(async ({ page }) => {
  const errors = []
  pageErrors.set(page, errors)
  page.on('pageerror', (error) => errors.push(error.message))
  await mockThemeApi(page)
})

test.afterEach(async ({ page }) => {
  expect(pageErrors.get(page)).toEqual([])
})

test('dark theme switches immediately, persists, and themes the core note flow', async ({ page }) => {
  await page.goto('/')

  await page.getByRole('button', { name: '设置' }).click()
  await page.getByRole('button', { name: '黑夜', exact: true }).click()

  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await expect.poll(() => page.evaluate(() => localStorage.getItem('moonbird_theme'))).toBe('dark')

  const homePanel = page.locator('.overview-board')
  await expect(homePanel).toBeVisible()
  await expectDarkSurface(homePanel)

  const homeColors = await homePanel.evaluate((element) => ({
    background: getComputedStyle(element).backgroundColor,
    foreground: getComputedStyle(element.querySelector('h2')).color,
  }))
  expect(contrastRatio(homeColors.foreground, homeColors.background)).toBeGreaterThanOrEqual(4.5)

  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')

  await page.goto('/notes')
  await expect(page.getByRole('heading', { name: '笔记摊开' })).toBeVisible()
  await expectDarkSurface(page.locator('.notes-board'))

  await page.goto('/notes/1')
  await expect(page.getByRole('heading', { name: '午夜主题验收笔记' })).toBeVisible()
  await expectDarkSurface(page.locator('.reader-main'))

  await page.goto('/notes/1/edit')
  await expect(page.getByPlaceholder('无标题')).toHaveValue('午夜主题验收笔记')
  await expectDarkSurface(page.locator('.toastui-editor-main'))
})

test('dark home remains within a mobile viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.addInitScript(() => localStorage.setItem('moonbird_theme', 'dark'))
  await page.goto('/')

  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await expectDarkSurface(page.locator('.overview-board'))
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth))
    .toBeLessThanOrEqual(0)
})
