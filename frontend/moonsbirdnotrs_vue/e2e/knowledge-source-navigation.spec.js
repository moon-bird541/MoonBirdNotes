import { expect, test } from '@playwright/test'

const runId = '11111111-1111-4111-8111-111111111111'
const diarySource = {
  note_id: 36,
  title: 'Diary source',
  heading_path: ['Daily log'],
  source_hash: 'a'.repeat(64),
  type: 'diary',
  diary_date: '2026-07-14',
}

const fulfillJson = (route, status, body) => route.fulfill({
  status,
  contentType: 'application/json',
  body: JSON.stringify(body),
})

const mockKnowledgeApi = async (page) => {
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname

    if (path === '/api/session/') {
      return fulfillJson(route, 200, { user: { id: 1, username: 'admin' } })
    }
    if (path === '/api/agent/knowledge/conversations/') {
      return fulfillJson(route, 200, { results: [] })
    }
    if (path === '/api/agent/knowledge/chat/' && request.method() === 'POST') {
      return fulfillJson(route, 200, {
        answer: 'A diary-backed answer.',
        sources: [diarySource],
        insufficient_context: false,
        run_id: runId,
        conversation_id: '22222222-2222-4222-8222-222222222222',
      })
    }
    if (path === '/api/agent/knowledge/runs/') {
      return fulfillJson(route, 200, {
        results: [{
          run_id: runId,
          status: 'completed',
          created_at: '2026-07-14T08:00:00Z',
        }],
      })
    }
    if (path === '/api/agent/knowledge/token-usage/') {
      return fulfillJson(route, 200, {
        summary: {
          run_count: 1,
          token_reported_run_count: 1,
          llm_request_count: 2,
          prompt_tokens: 1200,
          completion_tokens: 300,
          total_tokens: 1500,
        },
        results: [{
          run_id: runId,
          conversation_id: '22222222-2222-4222-8222-222222222222',
          status: 'completed',
          error_code: '',
          created_at: '2026-07-14T08:00:00Z',
          duration_ms: 1240,
          trace_available: true,
          llm_usage: {
            request_count: 2,
            usage_reported_request_count: 2,
            usage_status: 'available',
            prompt_tokens: 1200,
            completion_tokens: 300,
            total_tokens: 1500,
          },
        }],
      })
    }
    if (path === `/api/agent/knowledge/runs/${runId}/trace/`) {
      return fulfillJson(route, 200, {
        run_id: runId,
        http_status: 200,
        duration_ms: 120,
        events: [{
          stage: 'retrieval.completed',
          offset_ms: 20,
          metadata: {
            semantic_available: true,
            dense_candidate_count: 1,
            keyword_candidate_count: 0,
            candidates: [{ ...diarySource, score: 0.9 }],
          },
        }],
      })
    }
    if (path === '/api/notes/diaries/') {
      return fulfillJson(route, 200, [])
    }
    if (path === `/api/notes/diaries/by-date/${diarySource.diary_date}/`) {
      return fulfillJson(route, 404, { detail: 'Not needed for navigation test.' })
    }

    return fulfillJson(route, 404, { detail: `Unhandled test API: ${path}` })
  })
}

test('knowledge chat opens a diary source by diary date', async ({ page }) => {
  await mockKnowledgeApi(page)
  await page.goto('/knowledge-chat')

  await page.getByLabel('输入知识库问题').fill('What happened that day?')
  await page.getByRole('button', { name: '发送问题' }).click()
  await page.getByRole('button', { name: /Diary source/ }).click()

  await expect(page).toHaveURL(`/diary/${diarySource.diary_date}`)
})

test('RAG trace opens a diary candidate by diary date', async ({ page }) => {
  await mockKnowledgeApi(page)
  await page.goto('/rag-traces')

  await page.getByRole('button', { name: /笔记 36/ }).click()

  await expect(page).toHaveURL(`/diary/${diarySource.diary_date}`)
})

test('token ledger shows totals and opens the selected run trace', async ({ page }) => {
  await mockKnowledgeApi(page)
  await page.goto('/token-usage')

  await expect(page.getByRole('heading', { name: 'Token 用量' })).toBeVisible()
  await expect(page.getByText('1,500')).toHaveCount(2)
  await expect(page.getByText('1,200')).toBeVisible()
  await expect(page.getByText('300')).toBeVisible()

  await page.getByText(runId.slice(0, 8)).click()
  await expect(page).toHaveURL(new RegExp(`/rag-traces\\?run=${runId}$`))
  await expect(page.getByText('RAG 全流程轨迹')).toBeVisible()
})
