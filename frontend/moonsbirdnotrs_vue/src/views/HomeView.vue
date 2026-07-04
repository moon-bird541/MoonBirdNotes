<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowRight, CollectionTag, Document, Plus, Reading } from '@element-plus/icons-vue'

import WorkspaceShell from '../components/WorkspaceShell.vue'
import api from '../services/api'

const router = useRouter()
const creating = ref(false)
const summaryLoading = ref(false)
const summary = ref({
  stats: {
    note_count: 0,
    word_count: 0,
    tag_count: 0,
  },
  tag_distribution: [],
  recent_notes: [],
  upload_activity: [],
})

const HEATMAP_WEEK_COUNT = 5

const currentUser = computed(() => {
  const raw = localStorage.getItem('current_user')
  return raw ? JSON.parse(raw) : null
})

const stats = computed(() => summary.value.stats || {})
const recentNotes = computed(() => summary.value.recent_notes || [])
const tagDistribution = computed(() => summary.value.tag_distribution || [])
const hasNotes = computed(() => Number(stats.value.note_count || 0) > 0)
const uploadActivity = computed(() => summary.value.upload_activity || [])
const activityCountByDate = computed(() =>
  uploadActivity.value.reduce((map, item) => {
    map.set(item.date, Number(item.count || 0))
    return map
  }, new Map())
)
const maxActivityCount = computed(() =>
  Math.max(0, ...uploadActivity.value.map((item) => Number(item.count || 0)))
)
const totalActivityCount = computed(() =>
  uploadActivity.value.reduce((sum, item) => sum + Number(item.count || 0), 0)
)
const activeActivityDays = computed(
  () => uploadActivity.value.filter((item) => Number(item.count || 0) > 0).length
)
const averageActivityCount = computed(() => (totalActivityCount.value / 31).toFixed(1))

const fetchSummary = async () => {
  summaryLoading.value = true

  try {
    const { data } = await api.get('/notes/summary/', {
      params: {
        recent_limit: 5,
      },
    })

    summary.value = data
  } catch (error) {
    const detail = error.response?.data?.detail || '加载首页统计失败，请稍后重试。'
    ElMessage.error(detail)
  } finally {
    summaryLoading.value = false
  }
}

const goToNotes = () => {
  router.push('/notes')
}

const goToDetail = (note) => {
  router.push({ name: 'note-detail', params: { id: note.id } })
}

const createNewNote = async () => {
  creating.value = true

  try {
    const { data } = await api.post('/notes/create/', {
      title: '未命名笔记',
      markdown_content: '',
      tag_names: ['未分类'],
    })

    ElMessage.success('笔记创建成功，正在跳转...')
    router.push({ name: 'note-edit', params: { id: data.id } })
  } catch (error) {
    const detail =
      error.response?.data?.title?.[0] ||
      error.response?.data?.tag_names?.[0] ||
      error.response?.data?.detail ||
      '创建笔记失败，请稍后重试。'
    ElMessage.error(detail)
  } finally {
    creating.value = false
  }
}

const formatNumber = (value) => new Intl.NumberFormat('zh-CN').format(Number(value || 0))

const formatWordCount = (value) => `${formatNumber(value)} 字`

const formatDateTime = (value) => {
  if (!value) {
    return '-'
  }

  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

const startOfDay = (date) => new Date(date.getFullYear(), date.getMonth(), date.getDate())

const addDays = (date, days) => {
  const nextDate = new Date(date)
  nextDate.setDate(nextDate.getDate() + days)
  return nextDate
}

const toDateKey = (date) => {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const formatActivityDate = (date) =>
  new Intl.DateTimeFormat('zh-CN', {
    month: 'long',
    day: 'numeric',
  }).format(date)

const resolveActivityLevel = (count) => {
  if (!count) {
    return 0
  }

  const maxCount = maxActivityCount.value || 1
  return Math.min(4, Math.max(1, Math.ceil((count / maxCount) * 4)))
}

const heatmapWeeks = computed(() => {
  const today = startOfDay(new Date())
  const endDate = addDays(today, 6 - today.getDay())
  const startDate = addDays(endDate, -(HEATMAP_WEEK_COUNT * 7 - 1))

  return Array.from({ length: HEATMAP_WEEK_COUNT }, (_, weekIndex) =>
    Array.from({ length: 7 }, (_, dayIndex) => {
      const date = addDays(startDate, weekIndex * 7 + dayIndex)
      const dateKey = toDateKey(date)
      const count = activityCountByDate.value.get(dateKey) || 0
      const isFuture = date > today

      return {
        date: dateKey,
        count,
        isFuture,
        level: isFuture ? 0 : resolveActivityLevel(count),
        label: `${formatActivityDate(date)}：${count} 篇笔记`,
      }
    })
  )
})

const resolveTagWidth = (tag) => {
  if (!tag?.percentage) {
    return '0%'
  }

  return `${Math.max(tag.percentage, 6)}%`
}

onMounted(() => {
  fetchSummary()
})
</script>

<template>
  <main class="home-page page-shell">
    <WorkspaceShell>
      <section v-loading="summaryLoading" class="home-stage">
        <header class="home-topbar fade-rise-enter">
          <div>
            <p class="home-brand">MoonBirdNotes</p>
            <h1>个人知识库工作台</h1>
            <p class="home-subtitle">
              欢迎回来，{{ currentUser?.username || '管理员' }}。这里汇总当前笔记规模、标签结构和最近更新。
            </p>
          </div>

          <div class="home-actions">
            <el-button class="cta-button" type="primary" size="large" :icon="Plus" @click="createNewNote" :loading="creating">
              创建笔记
            </el-button>
            <el-button class="cta-button-secondary" size="large" :icon="ArrowRight" @click="goToNotes">
              查看全部
            </el-button>
          </div>
        </header>

        <section class="overview-board fade-rise-enter-delay" aria-label="笔记统计">
          <div class="overview-copy">
            <p class="home-kicker">Overview</p>
            <h2>知识库概览</h2>
          </div>

          <div class="metric-rail">
            <article class="metric-item">
              <span class="metric-icon"><el-icon><Document /></el-icon></span>
              <span>
                <small>笔记总数</small>
                <strong>{{ formatNumber(stats.note_count) }}</strong>
              </span>
            </article>
            <article class="metric-item">
              <span class="metric-icon"><el-icon><Reading /></el-icon></span>
              <span>
                <small>累计字数</small>
                <strong>{{ formatNumber(stats.word_count) }}</strong>
              </span>
            </article>
            <article class="metric-item">
              <span class="metric-icon"><el-icon><CollectionTag /></el-icon></span>
              <span>
                <small>活跃标签</small>
                <strong>{{ formatNumber(stats.tag_count) }}</strong>
              </span>
            </article>
          </div>
        </section>

        <section class="activity-board fade-rise-enter-delay-2" aria-label="笔记上传热力图">
          <div class="activity-head">
            <div>
              <p class="home-kicker">Activity</p>
              <h2>上传热力图</h2>
            </div>
            <span>{{ totalActivityCount }} 篇 / 近一个月</span>
          </div>

          <div class="activity-body">
            <div class="activity-heatmap-panel">
              <div class="activity-heatmap-wrap">
                <div class="activity-heatmap" role="img" aria-label="近一个月每天上传笔记数量">
                  <div v-for="(week, weekIndex) in heatmapWeeks" :key="weekIndex" class="activity-week">
                    <span
                      v-for="day in week"
                      :key="day.date"
                      class="activity-day"
                      :class="[`is-level-${day.level}`, { 'is-future': day.isFuture }]"
                      :title="day.label"
                    ></span>
                  </div>
                </div>
              </div>

              <div class="activity-legend" aria-hidden="true">
                <span>少</span>
                <i class="is-level-0"></i>
                <i class="is-level-1"></i>
                <i class="is-level-2"></i>
                <i class="is-level-3"></i>
                <i class="is-level-4"></i>
                <span>多</span>
              </div>
            </div>

            <div class="activity-summary" aria-label="近一个月上传摘要">
              <div class="activity-summary-item">
                <span>活跃天数</span>
                <strong>{{ activeActivityDays }}</strong>
              </div>
              <div class="activity-summary-item">
                <span>最高单日</span>
                <strong>{{ maxActivityCount }}</strong>
              </div>
              <div class="activity-summary-item">
                <span>日均上传</span>
                <strong>{{ averageActivityCount }}</strong>
              </div>
            </div>
          </div>
        </section>

        <section class="workspace-board fade-rise-enter-delay-2">
          <div class="recent-panel">
            <div class="panel-head">
              <div>
                <p class="home-kicker">Recent Notes</p>
                <h2>最近 5 篇</h2>
              </div>
              <button class="text-action" type="button" @click="goToNotes">
                全部笔记
                <el-icon><ArrowRight /></el-icon>
              </button>
            </div>

            <div v-if="recentNotes.length" class="recent-list">
              <button
                v-for="note in recentNotes"
                :key="note.id"
                class="recent-item"
                type="button"
                @click="goToDetail(note)"
              >
                <span class="recent-date">{{ formatDateTime(note.updated_at || note.created_at) }}</span>
                <span class="recent-copy">
                  <strong>{{ note.title }}</strong>
                  <small>{{ note.excerpt }}</small>
                </span>
                <span class="recent-meta">{{ formatWordCount(note.word_count) }}</span>
              </button>
            </div>

            <div v-else class="empty-state">
              <strong>{{ hasNotes ? '最近没有可展示的笔记' : '还没有笔记' }}</strong>
              <p>{{ hasNotes ? '可以进入列表查看全部内容。' : '创建第一篇笔记后，这里会显示最近内容。' }}</p>
            </div>
          </div>

          <aside class="tag-panel">
            <div class="panel-head">
              <div>
                <p class="home-kicker">Tags</p>
                <h2>标签分布</h2>
              </div>
            </div>

            <div v-if="tagDistribution.length" class="tag-list">
              <div v-for="tag in tagDistribution" :key="tag.id || tag.name" class="tag-row">
                <div class="tag-label">
                  <span>{{ tag.name }}</span>
                  <strong>{{ tag.count }} 篇</strong>
                </div>
                <div class="tag-track" aria-hidden="true">
                  <span :style="{ width: resolveTagWidth(tag) }"></span>
                </div>
              </div>
            </div>

            <div v-else class="empty-state compact">
              <strong>暂无标签数据</strong>
              <p>添加标签后会显示分布情况。</p>
            </div>
          </aside>
        </section>
      </section>
    </WorkspaceShell>
  </main>
</template>

<style scoped>
.home-page {
  min-height: 100vh;
  min-height: 100svh;
  padding: 0 18px 28px;
  background: #f8fafc;
}

.home-stage {
  display: grid;
  grid-template-areas:
    'top top'
    'overview activity'
    'tags recent';
  grid-template-columns: minmax(260px, 310px) minmax(0, 1fr);
  gap: 16px 18px;
  align-items: start;
  width: min(100%, 1260px);
  margin: 0 auto;
  padding-top: 24px;
}

.home-topbar {
  grid-area: top;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 2px 0 10px;
}

.home-topbar > div:first-child {
  max-width: 720px;
}

.home-brand,
.home-kicker {
  margin: 0 0 7px;
  color: #64748b;
  font-size: 0.76rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.home-topbar h1 {
  margin: 0;
  color: var(--brand-navy);
  font-size: 1.78rem;
  line-height: 1.18;
  letter-spacing: 0;
}

.home-subtitle {
  max-width: 620px;
  margin: 7px 0 0;
  color: var(--ink-soft);
  font-size: 0.94rem;
  line-height: 1.68;
}

.home-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.cta-button,
.cta-button-secondary {
  min-height: 38px;
  padding-inline: 14px;
  border-radius: 10px;
  font-weight: 700;
}

.cta-button {
  border: none;
  background: #1d4ed8;
  box-shadow: none;
}

.cta-button-secondary {
  border: 1px solid #dbe3ef;
  background: #ffffff;
  color: var(--brand-navy);
}

.overview-board {
  grid-area: overview;
  position: relative;
  display: grid;
  gap: 18px;
  min-width: 0;
  min-height: 0;
  margin-top: 0;
  padding: 20px;
  overflow: hidden;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: #ffffff;
  box-shadow: none;
}

.overview-board::after {
  position: absolute;
  top: 20px;
  right: 20px;
  width: 9px;
  height: 9px;
  border-radius: 999px;
  background: #2563eb;
  content: '';
  pointer-events: none;
}

.overview-copy h2 {
  margin: 0;
  color: var(--brand-navy);
  font-size: 1.08rem;
  line-height: 1.2;
  letter-spacing: 0;
}

.activity-board {
  grid-area: activity;
  min-width: 0;
  margin-top: 0;
  padding: 18px 20px;
  overflow: hidden;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: #ffffff;
  box-shadow: none;
}

.activity-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 11px;
  border-bottom: 1px solid #e2e8f0;
}

.activity-head h2 {
  margin: 0;
  color: var(--brand-navy);
  font-size: 1.08rem;
  line-height: 1.2;
  letter-spacing: 0;
}

.activity-head > span {
  color: var(--ink-soft);
  font-size: 0.86rem;
  font-weight: 700;
  white-space: nowrap;
}

.activity-body {
  display: grid;
  grid-template-columns: max-content minmax(260px, 1fr);
  gap: 28px;
  align-items: stretch;
  padding-top: 16px;
}

.activity-heatmap-panel {
  display: grid;
  align-content: space-between;
  gap: 14px;
  min-width: 0;
}

.activity-heatmap-wrap {
  overflow-x: visible;
  padding: 0;
}

.activity-heatmap {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: 14px;
  gap: 5px;
  width: max-content;
  min-width: 0;
}

.activity-week {
  display: grid;
  grid-template-rows: repeat(7, 14px);
  gap: 5px;
}

.activity-day,
.activity-legend i {
  display: block;
  width: 14px;
  height: 14px;
  border-radius: 3px;
  background: #eef2f7;
  box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.1);
}

.activity-day {
  transition:
    transform 0.16s ease,
    box-shadow 0.16s ease;
}

.activity-day:hover {
  transform: scale(1.22);
  box-shadow:
    inset 0 0 0 1px rgba(15, 23, 42, 0.14),
    0 8px 18px rgba(15, 23, 42, 0.12);
}

.activity-day.is-future {
  opacity: 0.32;
}

.activity-day.is-level-1,
.activity-legend i.is-level-1 {
  background: #c6e8cc;
}

.activity-day.is-level-2,
.activity-legend i.is-level-2 {
  background: #8fd39d;
}

.activity-day.is-level-3,
.activity-legend i.is-level-3 {
  background: #4fbf66;
}

.activity-day.is-level-4,
.activity-legend i.is-level-4 {
  background: #257c35;
}

.activity-legend {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 7px;
  padding-top: 0;
  color: var(--ink-soft);
  font-size: 0.8rem;
  font-weight: 700;
}

.activity-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  align-self: stretch;
  min-width: 0;
  overflow: hidden;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #f8fafc;
}

.activity-summary-item {
  display: grid;
  align-content: center;
  gap: 8px;
  min-width: 0;
  padding: 16px 18px;
}

.activity-summary-item + .activity-summary-item {
  border-left: 1px solid #e2e8f0;
}

.activity-summary-item span {
  color: #64748b;
  font-size: 0.82rem;
  font-weight: 700;
}

.activity-summary-item strong {
  overflow: hidden;
  color: var(--brand-navy);
  font-size: clamp(1.45rem, 2.2vw, 2rem);
  line-height: 1;
  letter-spacing: 0;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.metric-rail {
  display: grid;
  grid-template-columns: 1fr;
  min-width: 0;
  border-top: 1px solid #e2e8f0;
}

.metric-item {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 14px;
  min-width: 0;
  min-height: 70px;
  padding: 13px 0;
}

.metric-item + .metric-item {
  border-top: 1px solid #edf2f7;
}

.metric-icon {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border: 1px solid #dbeafe;
  border-radius: 10px;
  background: #eff6ff;
  color: #1d4ed8;
}

.metric-item span:last-child {
  min-width: 0;
}

.metric-item small,
.recent-date,
.recent-meta,
.recent-copy small,
.tag-label strong {
  color: var(--ink-soft);
}

.metric-item small {
  display: block;
  margin-bottom: 8px;
  font-size: 0.86rem;
}

.metric-item strong {
  display: block;
  overflow: hidden;
  color: var(--brand-navy);
  font-size: 1.48rem;
  line-height: 1;
  letter-spacing: 0;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workspace-board {
  display: contents;
}

.recent-panel,
.tag-panel {
  min-width: 0;
  padding: 20px;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: #ffffff;
  box-shadow: none;
}

.recent-panel {
  grid-area: recent;
}

.tag-panel {
  grid-area: tags;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #e2e8f0;
}

.panel-head h2 {
  margin: 0;
  color: var(--brand-navy);
  font-size: 1.08rem;
  line-height: 1.2;
  letter-spacing: 0;
}

.text-action {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0;
  border: none;
  background: transparent;
  color: #1d4ed8;
  font-weight: 700;
  cursor: pointer;
  transition: opacity 0.2s ease;
}

.text-action:hover {
  opacity: 0.72;
}

.recent-list {
  display: flex;
  flex-direction: column;
}

.recent-item {
  display: grid;
  grid-template-columns: 88px minmax(0, 1fr) auto;
  gap: 16px;
  align-items: center;
  width: 100%;
  margin-inline: 0;
  padding: 15px 0;
  border: none;
  border-bottom: 1px solid #edf2f7;
  border-radius: 0;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition:
    background 0.2s ease,
    padding 0.2s ease;
}

.recent-item:hover {
  background: transparent;
}

.recent-item:hover .recent-copy strong,
.recent-item:hover .recent-date {
  color: var(--brand-blue);
}

.recent-copy {
  min-width: 0;
}

.recent-copy strong,
.recent-copy small {
  display: block;
}

.recent-copy strong {
  overflow: hidden;
  color: var(--brand-navy);
  font-size: 0.98rem;
  text-overflow: ellipsis;
  white-space: nowrap;
  transition: color 0.2s ease;
}

.recent-copy small {
  overflow: hidden;
  margin-top: 6px;
  line-height: 1.6;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recent-meta {
  justify-self: end;
  font-size: 0.9rem;
  white-space: nowrap;
}

.tag-list {
  display: grid;
  gap: 14px;
  padding-top: 16px;
}

.tag-row {
  display: grid;
  gap: 10px;
}

.tag-label {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: var(--brand-navy);
}

.tag-label span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tag-label strong {
  flex: 0 0 auto;
  font-size: 0.9rem;
}

.tag-track {
  height: 6px;
  overflow: hidden;
  border-radius: 999px;
  background: #edf2f7;
}

.tag-track span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: #2563eb;
  box-shadow: none;
}

.empty-state {
  padding: 32px 0;
  color: var(--ink-soft);
}

.empty-state.compact {
  padding-top: 20px;
}

.empty-state strong {
  display: block;
  color: var(--brand-navy);
}

.empty-state p {
  margin: 8px 0 0;
  line-height: 1.7;
}

@media (max-width: 1100px) {
  .home-stage {
    grid-template-areas:
      'top'
      'overview'
      'activity'
      'recent'
      'tags';
    grid-template-columns: 1fr;
  }

  .metric-rail {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .metric-item {
    display: flex;
    justify-content: flex-start;
    padding: 14px 18px;
  }

  .metric-item + .metric-item {
    border-top: none;
    border-left: 1px solid #edf2f7;
  }

  .activity-body {
    grid-template-columns: 1fr;
  }

  .activity-heatmap-wrap {
    overflow-x: auto;
  }
}

@media (max-width: 980px) {
  .home-page {
    padding: 0 14px 24px;
  }

  .home-stage {
    min-height: auto;
    margin-top: 0;
  }

  .home-topbar {
    display: grid;
    padding-bottom: 10px;
  }

  .home-actions {
    justify-content: flex-start;
  }

  .metric-rail {
    grid-template-columns: 1fr;
  }

  .metric-item {
    padding: 14px 0;
  }

  .metric-item + .metric-item {
    border-top: 1px solid #edf2f7;
    border-left: none;
  }
}

@media (max-width: 640px) {
  .home-topbar h1 {
    font-size: 1.72rem;
    letter-spacing: 0;
  }

  .home-actions,
  .home-actions :deep(.el-button) {
    width: 100%;
  }

  .overview-board,
  .activity-board,
  .recent-panel,
  .tag-panel {
    padding: 16px;
    border-radius: 12px;
  }

  .activity-head {
    align-items: flex-start;
    flex-direction: column;
  }

  .activity-summary {
    grid-template-columns: 1fr;
  }

  .activity-summary-item + .activity-summary-item {
    border-top: 1px solid #e2e8f0;
    border-left: none;
  }

  .metric-item {
    min-height: 86px;
    padding: 16px;
  }

  .recent-item {
    grid-template-columns: 1fr;
    gap: 8px;
  }

  .recent-meta {
    justify-self: start;
  }
}
</style>
