<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'

import WorkspaceShell from '../components/WorkspaceShell.vue'
import { fetchKnowledgeTokenUsage } from '../services/knowledgeChat'

const router = useRouter()
const loading = ref(false)
const error = ref('')
const filterError = ref('')
const runs = ref([])
const dateFrom = ref('')
const dateTo = ref('')
const page = ref(1)
const pageSize = ref(20)
const pagination = ref({
  page: 1,
  page_size: 20,
  total_count: 0,
  total_pages: 0,
  has_previous: false,
  has_next: false,
})
const summary = ref({
  run_count: 0,
  token_reported_run_count: 0,
  llm_request_count: 0,
  prompt_tokens: 0,
  completion_tokens: 0,
  total_tokens: 0,
})

const inputRatio = computed(() => {
  if (!summary.value.total_tokens) return 0
  return Math.round((summary.value.prompt_tokens / summary.value.total_tokens) * 100)
})
const outputRatio = computed(() => summary.value.total_tokens ? 100 - inputRatio.value : 0)
const hasDateFilter = computed(() => Boolean(dateFrom.value || dateTo.value))

const coverageText = computed(() => {
  const total = summary.value.run_count
  if (!total) return '暂无记录'
  return `${summary.value.token_reported_run_count} / ${total} 条完整记录`
})

const pageRangeText = computed(() => {
  if (!pagination.value.total_count) return '0 条记录'
  const first = (pagination.value.page - 1) * pagination.value.page_size + 1
  const last = Math.min(
    pagination.value.page * pagination.value.page_size,
    pagination.value.total_count,
  )
  return `第 ${first}–${last} 条，共 ${pagination.value.total_count} 条`
})

const formatNumber = (value) => Number(value || 0).toLocaleString('zh-CN')
const formatDuration = (value) => {
  if (value == null) return '--'
  return value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${value.toFixed(0)} ms`
}
const formatTime = (value) => new Intl.DateTimeFormat('zh-CN', {
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
}).format(new Date(value))

const loadUsage = async () => {
  loading.value = true
  error.value = ''
  try {
    const params = {
      page: page.value,
      page_size: pageSize.value,
    }
    if (dateFrom.value) params.date_from = dateFrom.value
    if (dateTo.value) params.date_to = dateTo.value
    const response = await fetchKnowledgeTokenUsage(params)
    runs.value = response.data.results || []
    summary.value = { ...summary.value, ...(response.data.summary || {}) }
    pagination.value = { ...pagination.value, ...(response.data.pagination || {}) }
  } catch {
    error.value = '暂时无法读取 Token 记录。'
  } finally {
    loading.value = false
  }
}

const applyFilters = () => {
  filterError.value = ''
  if (dateFrom.value && dateTo.value && dateFrom.value > dateTo.value) {
    filterError.value = '结束日期不能早于开始日期。'
    return
  }
  page.value = 1
  loadUsage()
}

const clearFilters = () => {
  dateFrom.value = ''
  dateTo.value = ''
  filterError.value = ''
  page.value = 1
  loadUsage()
}

const changePageSize = () => {
  page.value = 1
  loadUsage()
}

const goToPage = (targetPage) => {
  if (
    loading.value
    || targetPage < 1
    || targetPage > pagination.value.total_pages
  ) return
  page.value = targetPage
  loadUsage()
}

const openTrace = (item) => {
  if (!item.trace_available) return
  router.push({ name: 'rag-traces', query: { run: item.run_id } })
}

onMounted(loadUsage)
</script>

<template>
  <WorkspaceShell>
    <main class="usage-page">
      <header class="page-header">
        <div>
          <p>TOKEN LEDGER</p>
          <h1>Token 用量</h1>
          <span>Knowledge Agent 模型用量账本。</span>
        </div>
        <button type="button" :disabled="loading" aria-label="刷新 Token 用量" @click="loadUsage()">
          <Icon icon="ph:arrow-clockwise" :class="{ 'is-spinning': loading }" />
          <span>刷新</span>
        </button>
      </header>

      <form class="usage-filters" aria-label="Token 用量日期筛选" @submit.prevent="applyFilters">
        <div class="date-fields">
          <label>
            <span>开始日期</span>
            <input v-model="dateFrom" type="date" :max="dateTo || undefined">
          </label>
          <span class="date-separator" aria-hidden="true">至</span>
          <label>
            <span>结束日期</span>
            <input v-model="dateTo" type="date" :min="dateFrom || undefined">
          </label>
        </div>
        <div class="filter-actions">
          <button type="submit" :disabled="loading">
            <Icon icon="ph:funnel" />
            <span>筛选</span>
          </button>
          <button
            type="button"
            class="is-secondary"
            :disabled="loading || (!dateFrom && !dateTo)"
            @click="clearFilters"
          >
            <Icon icon="ph:x" />
            <span>清除</span>
          </button>
        </div>
        <p v-if="filterError" class="filter-error" role="alert">{{ filterError }}</p>
      </form>

      <section class="usage-overview" aria-label="Token 用量汇总">
        <div class="total-usage">
          <span>累计消耗</span>
          <strong>{{ formatNumber(summary.total_tokens) }}</strong>
          <small>tokens · {{ coverageText }}</small>
        </div>
        <dl>
          <div>
            <dt>输入 Token</dt>
            <dd>{{ formatNumber(summary.prompt_tokens) }}</dd>
          </div>
          <div>
            <dt>输出 Token</dt>
            <dd>{{ formatNumber(summary.completion_tokens) }}</dd>
          </div>
          <div>
            <dt>模型请求</dt>
            <dd>{{ formatNumber(summary.llm_request_count) }}</dd>
          </div>
        </dl>
      </section>

      <section class="token-balance" aria-label="输入输出占比">
        <div class="balance-heading">
          <div>
            <span>输入</span>
            <strong>{{ inputRatio }}%</strong>
          </div>
          <div>
            <span>输出</span>
            <strong>{{ outputRatio }}%</strong>
          </div>
        </div>
        <div class="balance-track">
          <span :style="{ width: `${inputRatio}%` }"></span>
        </div>
      </section>

      <section class="usage-history">
        <div class="section-heading">
          <div>
            <h2>运行明细</h2>
            <p>只记录脱敏后的 Token、状态和耗时。</p>
          </div>
          <span>{{ formatNumber(summary.run_count) }} 次运行</span>
        </div>

        <div v-if="error" class="page-state is-error">
          <Icon icon="ph:warning-circle" />
          <p>{{ error }}</p>
          <button type="button" @click="loadUsage">重新读取</button>
        </div>
        <div v-else-if="loading && !runs.length" class="page-state">
          <span class="spinner"></span>
          <p>正在整理 Token 记录…</p>
        </div>
        <div v-else-if="!runs.length" class="page-state">
          <Icon icon="ph:chart-line-up" />
          <p v-if="hasDateFilter">当前日期范围内没有 Token 记录。</p>
          <p v-else>暂无 Token 记录，请先在知识对话中发起问题。</p>
        </div>
        <div v-else class="usage-table-wrap">
          <table class="usage-table">
            <thead>
              <tr>
                <th>时间</th>
                <th>运行</th>
                <th>状态</th>
                <th>请求</th>
                <th>输入</th>
                <th>输出</th>
                <th>总 Token</th>
                <th>耗时</th>
                <th><span class="sr-only">查看轨迹</span></th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="item in runs"
                :key="item.run_id"
                :class="{ 'has-trace': item.trace_available }"
                :tabindex="item.trace_available ? 0 : undefined"
                @click="openTrace(item)"
                @keydown.enter="openTrace(item)"
              >
                <td>{{ formatTime(item.created_at) }}</td>
                <td><code>{{ item.run_id.slice(0, 8) }}</code></td>
                <td>
                  <span class="status-label" :class="`is-${item.status}`">
                    {{ item.status === 'completed' ? '完成' : '失败' }}
                  </span>
                </td>
                <td>{{ item.llm_usage.request_count }}</td>
                <td>{{ item.llm_usage.prompt_tokens == null ? '--' : formatNumber(item.llm_usage.prompt_tokens) }}</td>
                <td>{{ item.llm_usage.completion_tokens == null ? '--' : formatNumber(item.llm_usage.completion_tokens) }}</td>
                <td class="total-cell">
                  {{ item.llm_usage.total_tokens == null ? '--' : formatNumber(item.llm_usage.total_tokens) }}
                  <small v-if="item.llm_usage.usage_status === 'partial'">部分记录</small>
                </td>
                <td>{{ formatDuration(item.duration_ms) }}</td>
                <td><Icon v-if="item.trace_available" icon="ph:arrow-up-right" /></td>
              </tr>
            </tbody>
          </table>
        </div>

        <footer v-if="pagination.total_count" class="usage-pagination">
          <span>{{ pageRangeText }}</span>
          <div>
            <label>
              <span class="sr-only">每页记录数</span>
              <select v-model.number="pageSize" :disabled="loading" @change="changePageSize">
                <option :value="10">10 条 / 页</option>
                <option :value="20">20 条 / 页</option>
                <option :value="50">50 条 / 页</option>
                <option :value="100">100 条 / 页</option>
              </select>
            </label>
            <button
              type="button"
              title="上一页"
              aria-label="上一页"
              :disabled="loading || !pagination.has_previous"
              @click="goToPage(page - 1)"
            >
              <Icon icon="ph:caret-left" />
            </button>
            <strong>第 {{ pagination.page }} / {{ pagination.total_pages }} 页</strong>
            <button
              type="button"
              title="下一页"
              aria-label="下一页"
              :disabled="loading || !pagination.has_next"
              @click="goToPage(page + 1)"
            >
              <Icon icon="ph:caret-right" />
            </button>
          </div>
        </footer>
      </section>
    </main>
  </WorkspaceShell>
</template>

<style scoped>
.usage-page {
  min-height: 100vh;
  min-height: 100svh;
  padding: 34px clamp(28px, 5vw, 76px) 56px;
  overflow-x: hidden;
  background: var(--page-bg, #f7f2e8);
  color: var(--brand-navy, #25354b);
}

.page-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 28px;
  animation: page-in 0.4s ease-out both;
}

.page-header p {
  margin: 0 0 8px;
  color: var(--moss, #657763);
  font-size: 0.7rem;
  font-weight: 800;
  letter-spacing: 0;
}

.page-header h1 {
  margin: 0;
  font: 700 2.8rem/1.1 Georgia, 'Noto Serif SC', serif;
  letter-spacing: 0;
}

.page-header span {
  display: block;
  margin-top: 9px;
  color: var(--text-muted, #766f65);
  font-size: 0.85rem;
}

.page-header button,
.page-state button {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border: 1px solid rgba(45, 57, 73, 0.16);
  border-radius: 8px;
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
}

.page-header button:disabled { opacity: 0.5; }
.page-header svg.is-spinning { animation: spin 0.7s linear infinite; }

.usage-filters {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 18px;
  margin-top: 36px;
  padding: 18px 0;
  border-block: 1px solid rgba(45, 57, 73, 0.13);
  animation: content-in 0.48s 0.03s ease-out both;
}

.date-fields,
.filter-actions,
.usage-pagination > div {
  display: flex;
  align-items: center;
  gap: 10px;
}

.date-fields label { display: grid; gap: 7px; }
.date-fields label > span {
  color: var(--text-muted, #766f65);
  font-size: 0.68rem;
  font-weight: 750;
}

.date-fields input,
.usage-pagination select {
  min-height: 38px;
  border: 1px solid rgba(45, 57, 73, 0.18);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.32);
  color: inherit;
  font: inherit;
}

.date-fields input { min-width: 148px; padding: 0 10px; }
.date-separator { margin-top: 20px; color: var(--text-muted, #766f65); font-size: 0.72rem; }
.filter-actions { margin-left: auto; }
.filter-actions button,
.usage-pagination button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  min-height: 38px;
  padding: 0 14px;
  border: 1px solid var(--moss, #657763);
  border-radius: 6px;
  background: var(--moss, #657763);
  color: #fff;
  font: inherit;
  font-size: 0.76rem;
  font-weight: 700;
  cursor: pointer;
}
.filter-actions button.is-secondary {
  border-color: rgba(45, 57, 73, 0.18);
  background: transparent;
  color: inherit;
}
.filter-actions button:disabled,
.usage-pagination button:disabled { cursor: default; opacity: 0.45; }
.filter-error { flex-basis: 100%; margin: 0; color: #a24d3f; font-size: 0.75rem; }

.usage-overview {
  display: grid;
  grid-template-columns: minmax(290px, 1.15fr) minmax(430px, 1fr);
  align-items: end;
  gap: clamp(36px, 7vw, 110px);
  margin-top: 30px;
  padding: 40px 0 38px;
  border-block: 1px solid rgba(45, 57, 73, 0.13);
  animation: content-in 0.48s 0.06s ease-out both;
}

.total-usage { display: grid; }
.total-usage > span,
.usage-overview dt,
.balance-heading span {
  color: var(--text-muted, #766f65);
  font-size: 0.72rem;
  font-weight: 750;
}

.total-usage strong {
  margin: 8px 0 3px;
  min-width: 0;
  font: 700 6rem/0.95 Georgia, 'Times New Roman', serif;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0;
  overflow-wrap: anywhere;
}

.total-usage small { color: var(--moss, #657763); font-size: 0.76rem; }

.usage-overview dl {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  margin: 0;
}

.usage-overview dl > div {
  min-width: 0;
  padding-left: 22px;
  border-left: 1px solid rgba(45, 57, 73, 0.13);
}

.usage-overview dd {
  margin: 9px 0 0;
  font: 700 1.8rem/1.2 Georgia, serif;
  font-variant-numeric: tabular-nums;
}

.token-balance { padding: 24px 0 38px; animation: content-in 0.48s 0.1s ease-out both; }
.balance-heading { display: flex; justify-content: space-between; }
.balance-heading div { display: flex; align-items: baseline; gap: 7px; }
.balance-heading div:last-child { flex-direction: row-reverse; }
.balance-heading strong { color: var(--moss, #657763); font-size: 0.78rem; }
.balance-track { height: 5px; margin-top: 11px; overflow: hidden; background: rgba(165, 124, 50, 0.28); }
.balance-track span { display: block; height: 100%; background: var(--moss, #657763); transition: width 0.45s ease; }

.usage-history { margin-top: 16px; animation: content-in 0.48s 0.14s ease-out both; }
.section-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; padding-bottom: 18px; }
.section-heading h2 { margin: 0; font: 700 1.35rem/1.2 Georgia, 'Noto Serif SC', serif; }
.section-heading p { margin: 6px 0 0; color: var(--text-muted, #766f65); font-size: 0.78rem; }
.section-heading > span { color: var(--moss, #657763); font-size: 0.75rem; font-weight: 750; }

.usage-table-wrap { overflow-x: auto; border-top: 1px solid rgba(45, 57, 73, 0.14); }
.usage-table { width: 100%; min-width: 860px; border-collapse: collapse; font-size: 0.78rem; }
.usage-table th { padding: 12px 14px; color: var(--text-muted, #766f65); font-size: 0.67rem; font-weight: 750; text-align: right; }
.usage-table th:first-child,
.usage-table th:nth-child(2),
.usage-table th:nth-child(3) { text-align: left; }
.usage-table td { padding: 15px 14px; border-top: 1px solid rgba(45, 57, 73, 0.09); text-align: right; font-variant-numeric: tabular-nums; }
.usage-table td:first-child,
.usage-table td:nth-child(2),
.usage-table td:nth-child(3) { text-align: left; }
.usage-table tbody tr { transition: background 0.18s ease; }
.usage-table tbody tr.has-trace { cursor: pointer; }
.usage-table tbody tr.has-trace:hover { background: rgba(101, 119, 99, 0.065); }
.usage-table tbody tr:focus-visible { outline: 2px solid var(--moss, #657763); outline-offset: -2px; }
.usage-table code { color: var(--moss, #657763); font-size: 0.75rem; font-weight: 700; }
.usage-table td:last-child { width: 24px; padding-right: 4px; color: var(--moss, #657763); font-size: 1rem; }
.total-cell { font-weight: 750; }
.total-cell small { display: block; margin-top: 3px; color: #a57c32; font-size: 0.62rem; font-weight: 600; }
.status-label { display: inline-flex; align-items: center; gap: 6px; color: #a24d3f; }
.status-label::before { width: 6px; height: 6px; border-radius: 50%; background: currentColor; content: ''; }
.status-label.is-completed { color: var(--moss, #657763); }

.usage-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  min-height: 64px;
  border-top: 1px solid rgba(45, 57, 73, 0.13);
  color: var(--text-muted, #766f65);
  font-size: 0.72rem;
}
.usage-pagination select { padding: 0 30px 0 10px; }
.usage-pagination button { width: 34px; min-height: 34px; padding: 0; background: transparent; color: inherit; }
.usage-pagination strong { min-width: 82px; color: inherit; text-align: center; }

.page-state { display: grid; place-items: center; min-height: 260px; border-top: 1px solid rgba(45, 57, 73, 0.13); color: var(--text-muted, #766f65); text-align: center; }
.page-state > svg { font-size: 2rem; }
.page-state p { margin: 12px 0; }
.page-state.is-error { color: #a24d3f; }
.spinner { width: 24px; height: 24px; border: 2px solid rgba(101, 119, 99, 0.2); border-top-color: var(--moss, #657763); border-radius: 50%; animation: spin 0.7s linear infinite; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0, 0, 0, 0); }

@keyframes page-in { from { opacity: 0; transform: translateY(-8px); } to { opacity: 1; transform: translateY(0); } }
@keyframes content-in { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
@keyframes spin { to { transform: rotate(360deg); } }

@media (max-width: 920px) {
  .usage-overview { grid-template-columns: 1fr; align-items: start; }
  .total-usage strong { font-size: 4.5rem; }
}

@media (max-width: 640px) {
  .usage-page { padding: 24px 18px 40px; }
  .page-header { align-items: flex-start; }
  .page-header h1 { font-size: 2.1rem; }
  .page-header button { width: 42px; height: 42px; justify-content: center; padding: 0; }
  .page-header button span { display: none; }
  .usage-filters { align-items: stretch; flex-direction: column; margin-top: 28px; }
  .date-fields { align-items: flex-end; }
  .date-fields label { flex: 1; min-width: 0; }
  .date-fields input { width: 100%; min-width: 0; }
  .filter-actions { width: 100%; margin-left: 0; }
  .filter-actions button { flex: 1; }
  .usage-overview { gap: 32px; margin-top: 24px; padding-block: 30px; }
  .total-usage strong { font-size: 3.2rem; }
  .usage-overview dl { grid-template-columns: 1fr; gap: 15px; }
  .usage-overview dl > div { display: flex; align-items: baseline; justify-content: space-between; padding: 0 0 12px; border-left: 0; border-bottom: 1px solid rgba(45, 57, 73, 0.1); }
  .usage-overview dd { margin: 0; }
  .usage-pagination { align-items: flex-start; flex-direction: column; padding: 16px 0; }
  .usage-pagination > div { width: 100%; justify-content: space-between; }
}

@media (prefers-reduced-motion: reduce) {
  .page-header,
  .usage-overview,
  .usage-filters,
  .token-balance,
  .usage-history { animation: none; }
  .balance-track span { transition: none; }
}
</style>
