<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'

import WorkspaceShell from '../components/WorkspaceShell.vue'
import KnowledgeRunTracePanel from '../components/KnowledgeRunTracePanel.vue'
import {
  fetchKnowledgeRuns,
  fetchKnowledgeRunTrace,
} from '../services/knowledgeChat'

const router = useRouter()
const route = useRoute()
const runs = ref([])
const runsLoading = ref(false)
const runIdInput = ref('')
const activeRunId = ref('')
const trace = ref(null)
const traceLoading = ref(false)
const traceError = ref('')

const formatTime = (value) => new Intl.DateTimeFormat('zh-CN', {
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
}).format(new Date(value))

const loadRuns = async () => {
  runsLoading.value = true
  try {
    const response = await fetchKnowledgeRuns()
    runs.value = response.data.results || []
    if (!activeRunId.value && runs.value.length) {
      const requestedRun = typeof route.query.run === 'string' ? route.query.run : ''
      selectRun(requestedRun || runs.value[0].run_id)
    }
  } finally {
    runsLoading.value = false
  }
}

const loadTrace = async () => {
  if (!activeRunId.value) return
  traceLoading.value = true
  traceError.value = ''
  trace.value = null
  try {
    const response = await fetchKnowledgeRunTrace(activeRunId.value)
    trace.value = response.data
  } catch (error) {
    traceError.value = error.response?.status === 404
      ? '该轨迹不存在、不属于当前账号，或由持久化功能启用前的旧版本产生。'
      : '无法读取运行轨迹，请稍后重试。'
  } finally {
    traceLoading.value = false
  }
}

const selectRun = (runId) => {
  activeRunId.value = runId
  runIdInput.value = runId
  loadTrace()
}

const queryRun = () => {
  const runId = runIdInput.value.trim()
  if (!/^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(runId)) {
    trace.value = null
    traceError.value = '请输入有效的 run_id。'
    return
  }
  selectRun(runId)
}

const openSource = (source) => {
  if (source.type === 'diary' && source.diary_date) {
    router.push({ name: 'diary', params: { date: source.diary_date } })
    return
  }

  router.push({ name: 'note-detail', params: { id: source.note_id } })
}

onMounted(loadRuns)
</script>

<template>
  <WorkspaceShell>
    <main class="trace-page">
      <header class="page-header">
        <div>
          <p>RAG DIAGNOSTICS</p>
          <h1>链路诊断</h1>
          <span>按 run_id 检查检索、工具、模型与会话持久化的完整执行顺序。</span>
        </div>
        <form @submit.prevent="queryRun">
          <Icon icon="ph:magnifying-glass" />
          <input v-model="runIdInput" aria-label="运行 ID" placeholder="输入 run_id" />
          <button type="submit">查询</button>
        </form>
      </header>

      <div class="trace-workspace">
        <aside class="run-index">
          <div class="index-heading">
            <div>
              <span>最近运行</span>
              <strong>{{ runs.length }}</strong>
            </div>
            <button type="button" aria-label="刷新运行列表" :disabled="runsLoading" @click="loadRuns">
              <Icon icon="ph:arrow-clockwise" />
            </button>
          </div>

          <p v-if="runsLoading && !runs.length" class="index-state">正在读取运行记录…</p>
          <p v-else-if="!runs.length" class="index-state">暂无运行记录，请先在知识对话中发起问题。</p>
          <button
            v-for="item in runs"
            :key="item.run_id"
            type="button"
            class="run-item"
            :class="{ 'is-active': item.run_id === activeRunId }"
            @click="selectRun(item.run_id)"
          >
            <span class="run-status" :class="`is-${item.status}`"></span>
            <div>
              <code>{{ item.run_id.slice(0, 8) }}</code>
              <small>{{ formatTime(item.created_at) }}</small>
            </div>
            <span>{{ item.status === 'completed' ? '完成' : '失败' }}</span>
          </button>
        </aside>

        <section class="trace-detail">
          <div v-if="!activeRunId && !traceError" class="empty-detail">
            <Icon icon="ph:git-branch" />
            <h2>选择一条运行记录</h2>
            <p>左侧显示当前账号最近的 RAG 运行，也可以在顶部直接输入 run_id。</p>
          </div>
          <KnowledgeRunTracePanel
            v-else
            open
            embedded
            :loading="traceLoading"
            :error="traceError"
            :trace="trace"
            @retry="loadTrace"
            @open-source="openSource"
          />
        </section>
      </div>
    </main>
  </WorkspaceShell>
</template>

<style scoped>
.trace-page { display: grid; grid-template-rows: auto minmax(0, 1fr); height: 100vh; height: 100svh; overflow: hidden; background: var(--panel-background); color: var(--text-primary); }
.page-header { display: flex; align-items: end; justify-content: space-between; gap: 30px; padding: 30px clamp(26px, 4vw, 62px) 22px; border-bottom: 1px solid var(--border-soft); animation: header-in .4s ease-out both; }
.page-header p { margin: 0 0 7px; color: var(--moss); font-size: .68rem; font-weight: 800; letter-spacing: .18em; }
.page-header h1 { margin: 0; font: 700 clamp(2rem, 3vw, 2.8rem)/1.1 Georgia, 'Noto Serif SC', serif; }
.page-header span { display: block; margin-top: 9px; color: var(--text-muted); font-size: .84rem; }
.page-header form { display: flex; align-items: center; width: min(440px, 45vw); padding: 7px 8px 7px 14px; border: 1px solid var(--border-soft); border-radius: 13px; background: var(--control-background); }
.page-header form > svg { color: var(--moss); }
.page-header input { flex: 1; min-width: 0; padding: 7px 10px; border: 0; outline: 0; background: transparent; color: inherit; font-family: 'Cascadia Code', Consolas, monospace; font-size: .76rem; }
.page-header form button { padding: 8px 14px; border: 0; border-radius: 9px; background: var(--accent); color: var(--text-on-accent); cursor: pointer; }
.trace-workspace { display: grid; grid-template-columns: 250px minmax(0, 1fr); min-height: 0; }
.run-index { overflow-y: auto; padding: 22px 18px; border-right: 1px solid rgba(45, 57, 73, .12); }
.index-heading { display: flex; align-items: center; justify-content: space-between; padding: 0 5px 14px; }
.index-heading div { display: flex; align-items: baseline; gap: 8px; }
.index-heading span { color: var(--text-muted); font-size: .75rem; font-weight: 750; }
.index-heading strong { color: var(--brand-gold); font: 1rem Georgia, serif; }
.index-heading button { display: grid; place-items: center; width: 30px; height: 30px; border: 0; border-radius: 50%; background: transparent; color: var(--moss); cursor: pointer; }
.run-item { display: grid; grid-template-columns: 8px minmax(0, 1fr) auto; align-items: center; gap: 10px; width: 100%; padding: 13px 8px; border: 0; border-bottom: 1px solid rgba(45, 57, 73, .09); background: transparent; color: inherit; text-align: left; cursor: pointer; transition: padding .18s ease, background .18s ease; }
.run-item:hover, .run-item.is-active { padding-left: 13px; background: rgba(101, 119, 99, .07); }
.run-status { width: 6px; height: 6px; border-radius: 50%; background: var(--danger); }
.run-status.is-completed { background: var(--moss); }
.run-item div { display: grid; gap: 4px; }
.run-item code { font-size: .78rem; font-weight: 700; }
.run-item small, .run-item > span:last-child { color: var(--text-muted); font-size: .67rem; }
.index-state { padding: 20px 5px; color: var(--text-muted); font-size: .78rem; line-height: 1.6; }
.trace-detail { min-width: 0; overflow-y: auto; background: var(--panel-background-soft); }
.empty-detail { display: grid; place-items: center; align-content: center; min-height: 65vh; padding: 40px; text-align: center; }
.empty-detail > svg { color: var(--moss); font-size: 2.4rem; }
.empty-detail h2 { margin: 18px 0 7px; font: 700 1.4rem Georgia, 'Noto Serif SC', serif; }
.empty-detail p { max-width: 380px; margin: 0; color: var(--text-muted); line-height: 1.7; }
@keyframes header-in { from { opacity: 0; transform: translateY(-8px); } to { opacity: 1; transform: translateY(0); } }
@media (max-width: 820px) { .trace-page { height: auto; min-height: 100svh; overflow: visible; } .page-header { align-items: stretch; flex-direction: column; } .page-header form { width: 100%; } .trace-workspace { grid-template-columns: 1fr; } .run-index { display: flex; gap: 8px; overflow-x: auto; border-right: 0; border-bottom: 1px solid rgba(45, 57, 73, .12); } .index-heading { flex: 0 0 120px; } .run-item { flex: 0 0 170px; border-bottom: 0; } }
@media (max-width: 480px) { .page-header { padding: 22px 18px 18px; } .page-header h1 { font-size: 1.85rem; } .page-header form { padding-left: 10px; } .page-header form button { padding-inline: 11px; } .run-index { padding: 14px 12px; } .trace-detail { overflow-x: hidden; } }
@media (prefers-reduced-motion: reduce) { .page-header { animation: none; } }
</style>
