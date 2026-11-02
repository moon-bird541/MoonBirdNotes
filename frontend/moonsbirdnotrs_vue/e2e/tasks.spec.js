import { expect, test } from '@playwright/test'

const currentUser = {
  id: 1,
  username: 'acceptance-admin',
}

const taskSummary = {
  todo_tasks: [],
  stats: { todo_count: 0, project_count: 0, overdue_count: 0, completed_today: 0 },
}

const noteSummary = {
  stats: { note_count: 0, word_count: 0, tag_count: 0 },
  tag_distribution: [],
  recent_notes: [],
  upload_activity: [],
}

const taskList = {
  count: 1,
  next: null,
  previous: null,
  results: [
    {
      id: 7,
      title: '发布小红书',
      start_at: '2026-11-02T06:00:00Z',
      end_at: '2026-11-02T08:00:00Z',
      urgency: 3,
      urgency_display: '高',
      is_completed: false,
      completed_at: null,
      summary: '',
      linked_note: null,
      segment: 'todo',
      has_time: true,
      is_overdue: false,
      created_at: '2026-11-02T05:00:00Z',
      updated_at: '2026-11-02T05:00:00Z',
    },
  ],
}

const fulfillJson = (route, status, body) =>
  route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })

const mockApi = async (page) => {
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname

    if (path === '/api/session/') {
      return fulfillJson(route, 200, { user: currentUser })
    }

    if (path === '/api/notes/summary/') {
      return fulfillJson(route, 200, noteSummary)
    }

    if (path === '/api/tasks/summary/') {
      return fulfillJson(route, 200, taskSummary)
    }

    if (path === '/api/tasks/') {
      return fulfillJson(route, 200, taskList)
    }

    if (path === '/api/notes/tags/' || path === '/api/notes/diaries/') {
      return fulfillJson(route, 200, [])
    }

    if (path === '/api/notes/') {
      return fulfillJson(route, 200, { count: 0, next: null, previous: null, results: [] })
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

test('任务列表按待办分段展示', async ({ page }) => {
  await mockApi(page)
  await page.goto('/tasks')

  await expect(page.getByRole('heading', { name: '任务' })).toBeVisible()
  await expect(page.getByText('发布小红书')).toBeVisible()
  await expect(page.getByRole('heading', { name: '待办' })).toBeVisible()
})

test('编辑任务时日期选择面板可以正常打开', async ({ page }) => {
  await mockApi(page)
  await page.goto('/tasks')

  // 点击卡片主体进入编辑弹窗。
  await page.getByText('发布小红书').click()

  const dialog = page.getByRole('dialog')
  await expect(dialog).toBeVisible()
  await expect(dialog.getByText('编辑任务')).toBeVisible()

  // 开始时间的日期选择器必须能展开，否则任务就无法填写时间。
  const startInput = dialog.locator('.el-date-editor').first()
  await startInput.click()

  // 两个选择器都会在 DOM 里各挂一个 panel，只有打开的那个是可见的。
  const panel = page.locator('.el-picker-panel:visible')
  await expect(panel).toHaveCount(1)
  await expect(panel.locator('.el-date-table')).toBeVisible()

  // type="datetime" 的头部带日期 + 时间两个输入框，缺一不可。
  await expect(panel.locator('.el-date-picker__editor-wrap input')).toHaveCount(2)

  // 选中一天并确认，输入框应回填成 YYYY-MM-DD HH:mm。
  await panel.locator('.el-date-table td.available').nth(15).click()
  await panel.getByRole('button', { name: 'OK' }).click()

  await expect(startInput.locator('input')).toHaveValue(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/)
})
