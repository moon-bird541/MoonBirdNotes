<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Icon } from '@iconify/vue'

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

const HEATMAP_WEEK_COUNT = 11
const recentIconNames = ['ph:tag', 'ph:article', 'ph:book-open', 'ph:code', 'ph:pencil-line']
const recentToneNames = ['green', 'paper', 'gold', 'blue', 'violet']

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

const goToTags = () => {
  router.push('/tags')
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

const formatRecentDateTime = (value) => formatDateTime(value).replace(/\s+/, '\n')

const resolveRecentIcon = (index) => recentIconNames[index % recentIconNames.length]

const resolveRecentTone = (index) => recentToneNames[index % recentToneNames.length]

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
            <h1>
              今日的书桌
              <Icon class="title-sun" icon="ph:sun" />
            </h1>
            <p class="home-subtitle">
              欢迎回来，<span>{{ currentUser?.username || 'moodbird' }}</span>。先看 5 篇新东西。
            </p>
          </div>

          <div class="home-actions">
            <el-button class="cta-button" type="primary" size="large" @click="createNewNote" :loading="creating">
              <Icon icon="ph:plus" />
              创建笔记
            </el-button>
            <el-button class="cta-button-secondary" size="large" @click="goToNotes">
              查看全部
              <Icon icon="ph:arrow-right" />
            </el-button>
          </div>
        </header>

        <section class="overview-board fade-rise-enter-delay" aria-label="笔记统计">
          <div class="panel-title">
            <span class="panel-title-icon"><Icon icon="ph:book-bookmark" /></span>
            <h2>桌面数字</h2>
          </div>

          <div class="metric-rail">
            <article class="metric-item">
              <span class="metric-icon"><Icon icon="ph:notebook" /></span>
              <span>
                <small>笔记总数</small>
                <strong>{{ formatNumber(stats.note_count) }}</strong>
              </span>
            </article>
            <article class="metric-item">
              <span class="metric-icon"><Icon icon="ph:text-aa" /></span>
              <span>
                <small>累计字数</small>
                <strong>{{ formatNumber(stats.word_count) }}</strong>
              </span>
            </article>
            <article class="metric-item">
              <span class="metric-icon"><Icon icon="ph:tag" /></span>
              <span>
                <small>活跃标签</small>
                <strong>{{ formatNumber(stats.tag_count) }}</strong>
              </span>
            </article>
          </div>
        </section>

        <section class="activity-board fade-rise-enter-delay-2" aria-label="笔记上传热力图">
          <div class="activity-head">
            <div class="panel-title">
              <span class="panel-title-icon"><Icon icon="ph:flame" /></span>
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
                <span class="summary-icon is-green"><Icon icon="ph:calendar-check" /></span>
                <span>活跃天数</span>
                <strong>{{ activeActivityDays }}</strong>
              </div>
              <div class="activity-summary-item">
                <span class="summary-icon is-gold"><Icon icon="ph:star" /></span>
                <span>最高单日</span>
                <strong>{{ maxActivityCount }}</strong>
              </div>
              <div class="activity-summary-item">
                <span class="summary-icon is-blue"><Icon icon="ph:cloud-arrow-up" /></span>
                <span>日均上传</span>
                <strong>{{ averageActivityCount }}</strong>
              </div>
            </div>
          </div>
        </section>

        <section class="workspace-board fade-rise-enter-delay-2">
          <div class="recent-panel">
            <div class="panel-head">
              <div class="panel-title">
                <span class="panel-title-icon"><Icon icon="ph:book-open-text" /></span>
                <h2>最近 5 篇</h2>
              </div>
              <button class="text-action" type="button" @click="goToNotes">
                全部笔记
                <Icon icon="ph:arrow-right" />
              </button>
            </div>

            <div v-if="recentNotes.length" class="recent-list">
              <button
                v-for="(note, index) in recentNotes"
                :key="note.id"
                class="recent-item"
                type="button"
                @click="goToDetail(note)"
              >
                <span class="recent-date">{{ formatRecentDateTime(note.updated_at || note.created_at) }}</span>
                <span class="recent-note-icon" :class="`is-${resolveRecentTone(index)}`">
                  <Icon :icon="resolveRecentIcon(index)" />
                </span>
                <span class="recent-copy">
                  <strong>{{ note.title }}</strong>
                  <small>{{ note.excerpt }}</small>
                </span>
                <span class="recent-meta">
                  <span>{{ formatWordCount(note.word_count) }}</span>
                  <Icon icon="ph:bell-simple" />
                  <Icon icon="ph:dots-three" />
                </span>
              </button>
            </div>

            <div v-else class="empty-state">
              <strong>{{ hasNotes ? '最近没有可展示的笔记' : '还没有笔记' }}</strong>
              <p>{{ hasNotes ? '可以进入列表查看全部内容。' : '创建第一篇笔记后，这里会显示最近内容。' }}</p>
            </div>
          </div>

          <aside class="tag-panel">
            <div class="panel-head">
              <div class="panel-title">
                <span class="panel-title-icon"><Icon icon="ph:tag" /></span>
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

            <button class="tag-footer-action" type="button" @click="goToTags">
              查看全部标签
              <Icon icon="ph:arrow-right" />
            </button>
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
  background: transparent;
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
  width: min(100%, 1280px);
  margin: 0 auto 0 clamp(0px, 2.8vw, 34px);
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
  color: var(--text-muted);
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
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 38px;
  padding-inline: 14px;
  border-radius: var(--radius-md);
  font-weight: 700;
}

.cta-button {
  border: none;
  background: var(--brand-blue);
  box-shadow: none;
}

.cta-button-secondary {
  border: 1px solid var(--border-soft);
  background: var(--surface);
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
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-md);
  background:
    linear-gradient(160deg, rgba(250, 244, 233, 0.92), rgba(232, 219, 199, 0.7)),
    var(--surface);
  box-shadow: var(--shadow-subtle);
}

.overview-board::after {
  position: absolute;
  top: 20px;
  right: 20px;
  width: 9px;
  height: 9px;
  border-radius: 999px;
  background: var(--brand-gold);
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
  margin-top: 14px;
  padding: 18px 20px;
  overflow: hidden;
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-md);
  background:
    linear-gradient(135deg, rgba(248, 240, 226, 0.9), rgba(237, 225, 206, 0.72)),
    var(--surface);
  box-shadow: var(--shadow-subtle);
}

.activity-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 11px;
  border-bottom: 1px solid var(--border-soft);
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
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-md);
  background: var(--panel-background-soft);
}

.activity-summary-item {
  display: grid;
  align-content: center;
  gap: 8px;
  min-width: 0;
  padding: 16px 18px;
}

.activity-summary-item + .activity-summary-item {
  border-left: 1px solid var(--border-soft);
}

.activity-summary-item span {
  color: var(--text-muted);
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
  border-top: 1px solid var(--border-soft);
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
  border-top: 1px solid var(--border-soft);
}

.metric-icon {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border: 1px solid var(--accent-border);
  border-radius: var(--radius-md);
  background: var(--accent-soft);
  color: var(--brand-blue);
}

.metric-icon svg {
  width: 1.08rem;
  height: 1.08rem;
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
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-md);
  background:
    linear-gradient(180deg, rgba(250, 244, 233, 0.9), rgba(238, 226, 207, 0.68)),
    var(--surface);
  box-shadow: var(--shadow-subtle);
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
  border-bottom: 1px solid var(--border-soft);
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
  color: var(--brand-blue);
  font-weight: 700;
  cursor: pointer;
  transition:
    opacity 0.2s var(--motion-calm),
    transform 0.2s var(--motion-snappy);
}

.text-action:hover {
  opacity: 0.72;
  transform: translateX(2px);
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
  border-bottom: 1px solid var(--border-soft);
  border-radius: 0;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition:
    background 0.2s var(--motion-calm),
    padding 0.2s var(--motion-snappy);
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
  background: var(--surface-muted);
}

.tag-track span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--moss);
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
    border-left: 1px solid var(--border-soft);
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
    border-top: 1px solid var(--border-soft);
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
    border-top: 1px solid var(--border-soft);
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

/* Screenshot-matched desk dashboard */
.home-page {
  padding: 0;
  background: var(--app-background);
}

.home-stage {
  grid-template-areas:
    'top top'
    'overview activity'
    'tags recent';
  grid-template-columns: 368px minmax(0, 1fr);
  gap: 20px 30px;
  /* 同一网格行的左右面板必须等高，避免四个主区域边线错位。 */
  align-items: stretch;
  width: auto;
  max-width: none;
  margin: 0;
  padding: 52px 48px 48px 58px;
}

.home-topbar {
  align-items: flex-start;
  padding: 0 0 14px;
}

.home-topbar h1 {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: clamp(2rem, 2.4vw, 2.45rem);
  font-weight: 850;
  line-height: 1.08;
}

.title-sun {
  width: 30px;
  height: 30px;
  color: var(--brand-gold);
}

.home-subtitle {
  margin-top: 12px;
  color: var(--text-muted);
  font-size: 1rem;
}

.home-subtitle span {
  color: var(--brand-blue);
  font-weight: 750;
}

.home-actions {
  gap: 18px;
  padding-top: 8px;
}

.home-actions :deep(.el-button) {
  height: 48px;
  min-height: 48px;
  padding-inline: 24px;
  border-radius: 10px;
  font-size: 0.96rem;
}

.cta-button {
  background: linear-gradient(180deg, #b96949, #9f432a);
  box-shadow: 0 12px 20px rgba(150, 70, 38, 0.16);
}

.cta-button-secondary {
  border-color: var(--border-soft);
  background: var(--control-background);
}

.overview-board,
.activity-board,
.recent-panel,
.tag-panel {
  height: 100%;
  border: 1px solid var(--border-soft);
  border-radius: 12px;
  background: var(--panel-background);
  box-shadow: var(--shadow-subtle), var(--inset-highlight);
}

.overview-board,
.tag-panel {
  padding: 24px;
}

.activity-board,
.recent-panel {
  padding: 24px 26px;
}

.activity-board {
  margin-top: 0;
}

.overview-board::after {
  display: none;
}

.panel-title {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.panel-title h2,
.activity-head h2,
.panel-head h2 {
  margin: 0;
  color: var(--text-primary);
  font-size: 1.16rem;
  font-weight: 850;
  line-height: 1.2;
}

.panel-title-icon {
  display: inline-grid;
  place-items: center;
  width: 22px;
  height: 22px;
  color: var(--brand-blue);
}

.panel-title-icon svg {
  width: 1.08rem;
  height: 1.08rem;
}

.metric-rail,
.panel-head,
.activity-head {
  border-color: var(--divider);
}

.metric-rail {
  margin-top: 14px;
}

.metric-item {
  min-height: 82px;
  gap: 22px;
  padding: 16px 0;
}

.metric-icon {
  width: 48px;
  height: 48px;
  border-color: var(--accent-border);
  border-radius: 10px;
  background: var(--accent-soft);
  color: var(--brand-blue);
}

.metric-icon svg {
  width: 1.24rem;
  height: 1.24rem;
}

.metric-item small {
  margin-bottom: 8px;
  color: var(--text-muted);
  font-size: 0.88rem;
}

.metric-item strong {
  color: var(--text-primary);
  font-size: 1.58rem;
  font-weight: 850;
}

.activity-head {
  padding-bottom: 16px;
}

.activity-head > span {
  color: var(--text-muted);
  font-size: 0.92rem;
}

.activity-body {
  grid-template-columns: minmax(230px, 286px) minmax(0, 1fr);
  gap: 52px;
  align-items: center;
  padding-top: 20px;
}

.activity-heatmap {
  grid-auto-columns: 16px;
  gap: 5px;
}

.activity-week {
  grid-template-rows: repeat(7, 16px);
  gap: 5px;
}

.activity-day,
.activity-legend i {
  width: 16px;
  height: 16px;
  border: 1px solid var(--border-soft);
  border-radius: 4px;
  background: var(--control-background);
  box-shadow: none;
}

.activity-day.is-level-1,
.activity-legend i.is-level-1 {
  background: color-mix(in srgb, var(--moss) 28%, var(--panel-background));
}

.activity-day.is-level-2,
.activity-legend i.is-level-2 {
  background: color-mix(in srgb, var(--moss) 46%, var(--panel-background));
}

.activity-day.is-level-3,
.activity-legend i.is-level-3 {
  background: color-mix(in srgb, var(--moss) 70%, var(--panel-background));
}

.activity-day.is-level-4,
.activity-legend i.is-level-4 {
  background: var(--moss);
}

.activity-legend {
  margin-top: 14px;
  color: var(--text-muted);
  font-size: 0.78rem;
}

.activity-summary {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  border: none;
  border-radius: 0;
  background: transparent;
}

.activity-summary-item {
  justify-items: center;
  gap: 10px;
  min-height: 170px;
  padding: 18px 20px;
  text-align: center;
}

.activity-summary-item + .activity-summary-item {
  border-left: 1px solid var(--divider);
}

.summary-icon {
  display: inline-grid;
  place-items: center;
  width: 48px;
  height: 48px;
  margin-bottom: 8px;
  border-radius: 999px;
}

.summary-icon svg {
  width: 1.35rem;
  height: 1.35rem;
}

.summary-icon.is-green {
  background: rgba(91, 119, 78, 0.12);
  color: var(--moss);
}

.summary-icon.is-gold {
  background: rgba(218, 160, 64, 0.13);
  color: var(--brand-gold);
}

.summary-icon.is-blue {
  background: rgba(74, 136, 188, 0.12);
  color: var(--moss);
}

.activity-summary-item > span:not(.summary-icon) {
  color: var(--text-muted);
  font-size: 0.9rem;
  font-weight: 700;
}

.activity-summary-item strong {
  color: var(--text-primary);
  font-size: clamp(2.05rem, 3vw, 2.55rem);
  font-weight: 850;
}

.tag-list {
  align-content: center;
  gap: 28px;
  min-height: 0;
  padding: 16px 0;
}

.tag-panel {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
}

.tag-label {
  font-size: 0.94rem;
}

.tag-label strong {
  color: var(--text-muted);
  font-weight: 600;
}

.tag-track {
  height: 5px;
  background: var(--surface-muted);
}

.tag-track span {
  background: var(--moss);
}

.tag-footer-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  min-height: 44px;
  margin-top: 10px;
  border: 1px solid var(--border-soft);
  border-radius: 8px;
  background: var(--control-background);
  color: var(--brand-blue);
  font: inherit;
  font-weight: 750;
  cursor: pointer;
}

.recent-panel {
  min-height: 421px;
}

.recent-list {
  padding-top: 0;
}

.recent-item {
  grid-template-columns: 50px 42px minmax(0, 1fr) 150px;
  gap: 14px;
  min-height: 62px;
  padding: 11px 0;
}

.recent-date {
  color: var(--text-muted);
  font-size: 0.82rem;
  line-height: 1.28;
  white-space: pre-line;
}

.recent-note-icon {
  display: inline-grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border: 1px solid var(--border-soft);
  border-radius: 8px;
}

.recent-note-icon svg {
  width: 1.15rem;
  height: 1.15rem;
}

.recent-note-icon.is-green {
  background: var(--moss-soft);
  color: var(--moss);
}

.recent-note-icon.is-paper {
  background: var(--accent-soft);
  color: var(--brand-blue);
}

.recent-note-icon.is-gold {
  background: color-mix(in srgb, var(--brand-gold) 16%, var(--panel-background));
  color: var(--brand-gold);
}

.recent-note-icon.is-blue {
  background: var(--panel-background-soft);
  color: var(--moss);
}

.recent-note-icon.is-violet {
  background: var(--panel-background-soft);
  color: var(--accent);
}

.recent-copy strong {
  color: var(--text-primary);
  font-size: 0.95rem;
  font-weight: 850;
}

.recent-copy small {
  color: var(--text-muted);
  font-size: 0.82rem;
}

.recent-meta {
  display: grid;
  grid-template-columns: 1fr 22px 22px;
  gap: 13px;
  align-items: center;
  justify-self: stretch;
  color: var(--text-muted);
}

.recent-meta svg {
  width: 1rem;
  height: 1rem;
  color: var(--brand-blue);
}

.recent-meta svg:last-child {
  color: var(--text-muted);
}

@media (max-width: 1280px) {
  .home-stage {
    grid-template-columns: minmax(280px, 340px) minmax(0, 1fr);
    padding-inline: 32px;
  }

  .activity-body {
    grid-template-columns: 1fr;
    gap: 24px;
  }
}

@media (max-width: 980px) {
  .home-stage {
    grid-template-areas:
      'top'
      'overview'
      'activity'
      'tags'
      'recent';
    grid-template-columns: 1fr;
    padding: 24px 16px;
  }

  .activity-summary-item {
    min-height: 128px;
  }

  .overview-board,
  .activity-board,
  .recent-panel,
  .tag-panel {
    height: auto;
  }

  .tag-list {
    gap: 15px;
    padding-block: 20px;
  }
}

@media (max-width: 640px) {
  .recent-item {
    grid-template-columns: 46px minmax(0, 1fr);
  }

  .recent-date,
  .recent-meta {
    grid-column: 1 / -1;
  }

  .recent-meta {
    grid-template-columns: auto 22px 22px;
    justify-content: start;
  }
}
</style>
