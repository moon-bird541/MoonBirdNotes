import { expect, test } from '@playwright/test'

const currentUser = {
  id: 1,
  username: 'acceptance-admin',
}

const summary = {
  stats: {
    note_count: 12,
    word_count: 3456,
    tag_count: 4,
  },
  tag_distribution: [
    { id: 1, name: '验收', count: 3, percentage: 25 },
  ],
  recent_notes: [
    {
      id: 42,
      title: '验收笔记',
      excerpt: '用于验证首页数据渲染。',
      word_count: 128,
      created_at: '2026-07-16T08:00:00Z',
      updated_at: '2026-07-16T09:00:00Z',
    },
  ],
  upload_activity: [{ date: '2026-07-16', count: 2 }],
}

const notes = {
  count: 1,
  next: null,
  previous: null,
  results: [
    {
      id: 42,
      title: '验收笔记',
      excerpt: '用于验证笔记列表渲染。',
      word_count: 128,
      tags: [{ id: 1, name: '验收' }],
      is_pinned: false,
      importance: 3,
      created_at: '2026-07-16T08:00:00Z',
      updated_at: '2026-07-16T09:00:00Z',
    },
  ],
}

const fulfillJson = (route, status, body) =>
  route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })

const mockApi = async (page, { authenticated = false } = {}) => {
  let sessionAuthenticated = authenticated

  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname

    if (path === '/api/session/') {
      return fulfillJson(
        route,
        sessionAuthenticated ? 200 : 401,
        sessionAuthenticated ? { user: currentUser } : { detail: 'Unauthenticated' }
      )
    }

    if (path === '/api/token/refresh/') {
      return fulfillJson(route, 401, { detail: 'Unauthenticated' })
    }

    if (path === '/api/login/' && request.method() === 'POST') {
      sessionAuthenticated = true
      return fulfillJson(route, 200, { user: currentUser })
    }

    if (path === '/api/logout/' && request.method() === 'POST') {
      sessionAuthenticated = false
      return fulfillJson(route, 200, { detail: 'Logged out' })
    }

    if (path === '/api/notes/summary/') {
      return fulfillJson(route, 200, summary)
    }

    if (path === '/api/notes/tags/') {
      return fulfillJson(route, 200, [{ id: 1, name: '验收' }])
    }

    if (path === '/api/notes/') {
      return fulfillJson(route, 200, notes)
    }

    return fulfillJson(route, 404, { detail: `Unhandled acceptance API: ${path}` })
  })
}

const pageErrors = new WeakMap()

test.beforeEach(async ({ page }) => {
  const errors = []
  pageErrors.set(page, errors)
  page.on('pageerror', (error) => errors.push(error.message))
})

test.afterEach(async ({ page }) => {
  expect(pageErrors.get(page)).toEqual([])
})

test('未登录访问工作台时跳转到登录页', async ({ page }) => {
  await mockApi(page)

  await page.goto('/')

  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByRole('heading', { name: '知识记录，有序归档。' })).toBeVisible()
  await expect(page.getByLabel('登录表单')).toBeVisible()

  await page.getByRole('button', { name: '登录并进入' }).click()
  await expect(page.getByText('请填写用户名与密码。')).toBeVisible()
})

test('管理员可以登录并看到首页摘要', async ({ page }) => {
  await mockApi(page)
  await page.goto('/login')

  await page.getByPlaceholder('用户名').fill('acceptance-admin')
  await page.getByPlaceholder('密码').fill('acceptance-password')

  const loginRequest = page.waitForRequest(
    (request) => new URL(request.url()).pathname === '/api/login/' && request.method() === 'POST'
  )
  await page.getByRole('button', { name: '登录并进入' }).click()

  expect((await loginRequest).postDataJSON()).toEqual({
    username: 'acceptance-admin',
    password: 'acceptance-password',
  })
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('heading', { name: '今日的书桌' })).toBeVisible()
  await expect(page.getByText('欢迎回来，')).toContainText('acceptance-admin')
  await expect(page.getByText('验收笔记')).toBeVisible()
})

test('已登录用户可以进入笔记列表并退出登录', async ({ page }) => {
  await mockApi(page, { authenticated: true })
  await page.goto('/')

  await page.getByRole('button', { name: '笔记列表' }).click()

  await expect(page).toHaveURL(/\/notes$/)
  await expect(page.getByRole('heading', { name: '笔记摊开' })).toBeVisible()
  await expect(page.getByText('验收笔记')).toBeVisible()

  await page.getByRole('button', { name: '退出登录' }).click()
  await expect(page).toHaveURL(/\/login$/)
})
