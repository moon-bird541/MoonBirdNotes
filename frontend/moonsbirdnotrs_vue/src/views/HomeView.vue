<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Icon } from '@iconify/vue'

import WorkspaceShell from '../components/WorkspaceShell.vue'
import api from '../services/api'
import { formatTaskRange, resolveUrgencyTone } from '../utils/tasks'

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

// 首页任务面板：只取待办段（<= 24 小时）的未完成任务
const taskLoading = ref(false)
const todoTasks = ref([])
const taskStats = ref({
  todo_count: 0,
  project_count: 0,
  overdue_count: 0,
  completed_today: 0,
})

const HEATMAP_WEEK_COUNT = 11
const recentIconNames = ['ph:article', 'ph:book-open', 'ph:code', 'ph:pencil-line', 'ph:sparkle']
const recentToneNames = ['paper', 'moss', 'gold', 'blue', 'stone']

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

// 替换掉原本冰冷挫败的“日均0.0”，以书桌心境状态呈现
const writingMood = computed(() => {
  if (totalActivityCount.value >= 10) return '文思泉涌'
  if (totalActivityCount.value >= 3) return '笔耕不辍'
  if (totalActivityCount.value > 0) return '渐入佳境'
  return '静待提笔'
})

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

const goToTasks = () => {
  router.push({ name: 'tasks' })
}

const fetchTasks = async () => {
  taskLoading.value = true

  try {
    const { data } = await api.get('/tasks/summary/')
    todoTasks.value = data.todo_tasks || []
    taskStats.value = data.stats || taskStats.value
  } catch {
    todoTasks.value = []
  } finally {
    taskLoading.value = false
  }
}

const completeTaskFromHome = async (task) => {
  try {
    await api.post(`/tasks/${task.id}/complete/`, {})
    ElMessage.success('任务已完成。')
    fetchTasks()
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '操作失败，请稍后重试。')
  }
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
      title: '未命名手稿',
      markdown_content: '',
      tag_names: ['未分类'],
    })

    ElMessage.success('手稿创建成功，正在进入书写...')
    router.push({ name: 'note-edit', params: { id: data.id } })
  } catch (error) {
    const detail =
      error.response?.data?.title?.[0] ||
      error.response?.data?.tag_names?.[0] ||
      error.response?.data?.detail ||
      '创建手稿失败，请稍后重试。'
    ElMessage.error(detail)
  } finally {
    creating.value = false
  }
}

const formatNumber = (value) => new Intl.NumberFormat('zh-CN').format(Number(value || 0))

const formatWordCount = (value) => `${formatNumber(value)} 字`

const formatDateTime = (value) => {
  if (!value) return '-'

  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

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
  if (!count) return 0
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
        label: `${formatActivityDate(date)}：${count} 篇手稿`,
      }
    })
  )
})

onMounted(() => {
  fetchSummary()
  fetchTasks()
})
</script>

<template>
  <main class="home-page page-shell">
    <WorkspaceShell>
      <section v-loading="summaryLoading" class="home-stage">
        <!-- 顶部 Header：旧书桌迎宾栏 + 宏观知识沉淀印章 -->
        <header class="home-topbar fade-rise-enter">
          <div class="topbar-welcome">
            <div class="welcome-heading-row">
              <h1>
                今日的书桌
                <Icon class="title-sun" icon="ph:sun-horizon" />
              </h1>
            </div>

            <p class="home-subtitle">
              欢迎回来，<span>{{ currentUser?.username || 'moodbird' }}</span>。安静写字，常读常新。
            </p>

            <!-- 沉淀印章条：把全局宏观数据置于顶层，解除待办卡片的臃肿 -->
            <div class="desk-stats-strip">
              <span class="desk-stat-item">
                <Icon icon="ph:notebook" />
                <span>手稿 <strong>{{ formatNumber(stats.note_count) }}</strong> 篇</span>
              </span>
              <span class="desk-stat-sep">/</span>
              <span class="desk-stat-item">
                <Icon icon="ph:text-t" />
                <span>墨迹 <strong>{{ formatNumber(stats.word_count) }}</strong> 字</span>
              </span>
              <span class="desk-stat-sep">/</span>
              <span class="desk-stat-item">
                <Icon icon="ph:bookmarks" />
                <span>领域 <strong>{{ formatNumber(stats.tag_count) }}</strong> 个</span>
              </span>
              <span v-if="taskStats.overdue_count > 0" class="desk-stat-item is-overdue-alert">
                <Icon icon="ph:warning-circle" />
                <span>逾期 <strong>{{ formatNumber(taskStats.overdue_count) }}</strong> 项待办</span>
              </span>
            </div>
          </div>

          <div class="home-actions">
            <el-button class="cta-button" type="primary" size="large" @click="createNewNote" :loading="creating">
              <Icon icon="ph:plus" />
              提笔新记
            </el-button>
            <el-button class="cta-button-secondary" size="large" @click="goToNotes">
              全部笔记
              <Icon icon="ph:arrow-right" />
            </el-button>
          </div>
        </header>

        <!-- 主内容区：左侧辅助栏 (待办 + 标签云) + 右侧主内容 (热力足迹 + 最近手迹) -->
        <div class="desk-grid">
          <!-- 左侧辅助列 (350px) -->
          <div class="desk-side-column fade-rise-enter-delay">
            <!-- 1. 今日待办 (纯粹的行动清单，支持快捷勾选) -->
            <section v-loading="taskLoading" class="overview-board desk-card" aria-label="今日待办">
              <div class="panel-head">
                <div class="panel-title">
                  <span class="panel-title-icon"><Icon icon="ph:check-square-offset" /></span>
                  <h2>今日待办</h2>
                </div>
                <button class="text-action" type="button" @click="goToTasks">
                  全部任务
                  <Icon icon="ph:arrow-right" />
                </button>
              </div>

              <div class="todo-status-subhead">
                <span>{{ taskStats.todo_count }} 条待办 · {{ taskStats.project_count }} 个关联项目</span>
              </div>

              <div v-if="todoTasks.length" class="todo-list">
                <article
                  v-for="task in todoTasks"
                  :key="task.id"
                  class="todo-item"
                  :class="[`is-${resolveUrgencyTone(task.urgency)}`, { 'is-overdue': task.is_overdue }]"
                >
                  <button
                    type="button"
                    class="todo-check"
                    title="标记完成"
                    aria-label="标记完成"
                    @click="completeTaskFromHome(task)"
                  >
                    <Icon icon="ph:circle" />
                  </button>

                  <div class="todo-copy">
                    <strong>{{ task.title }}</strong>
                    <small>{{ formatTaskRange(task) }}</small>
                  </div>

                  <span v-if="task.is_overdue" class="todo-overdue">逾期</span>
                </article>
              </div>

              <div v-else class="empty-state compact">
                <Icon class="empty-icon" icon="ph:coffee" />
                <strong>今日暂无待办</strong>
                <p>24 小时内无到期事项，可安心阅读与创作。</p>
              </div>
            </section>

            <!-- 2. 知识领域 (标签胶囊云，告别灰暗长条进度条) -->
            <section class="tag-board desk-card" aria-label="知识领域">
              <div class="panel-head">
                <div class="panel-title">
                  <span class="panel-title-icon"><Icon icon="ph:bookmarks" /></span>
                  <h2>知识领域</h2>
                </div>
                <button class="text-action" type="button" @click="goToTags">
                  全部标签
                  <Icon icon="ph:arrow-right" />
                </button>
              </div>

              <div v-if="tagDistribution.length" class="tag-cloud">
                <button
                  v-for="tag in tagDistribution"
                  :key="tag.id || tag.name"
                  class="tag-pill"
                  type="button"
                  @click="goToTags"
                  :title="`查看「${tag.name}」相关笔记 (${tag.count} 篇)`"
                >
                  <span class="tag-pill-hash">#</span>
                  <span class="tag-pill-name">{{ tag.name }}</span>
                  <span class="tag-pill-count">{{ tag.count }}</span>
                </button>
              </div>

              <div v-else class="empty-state compact">
                <Icon class="empty-icon" icon="ph:tag" />
                <strong>暂无标签</strong>
                <p>在编辑手稿时贴上标签，知识更有条理。</p>
              </div>
            </section>
          </div>

          <!-- 右侧主阅读与足迹栏 (1fr) -->
          <div class="desk-main-column fade-rise-enter-delay-2">
            <!-- 3. 笔耕足迹（热力图，去除冰冷挫败的日均0.0） -->
            <section class="activity-board desk-card" aria-label="笔耕足迹">
              <div class="panel-head">
                <div class="panel-title">
                  <span class="panel-title-icon"><Icon icon="ph:flame" /></span>
                  <h2>笔耕足迹</h2>
                </div>
                <span class="activity-submeta">近一个月沉淀 {{ totalActivityCount }} 篇手稿</span>
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

                <!-- 更有温度的 3 个统计卡片 -->
                <div class="activity-summary" aria-label="近一个月写作状态">
                  <div class="activity-summary-item">
                    <span class="summary-icon is-green"><Icon icon="ph:calendar-check" /></span>
                    <span class="summary-label">活跃天数</span>
                    <strong>{{ activeActivityDays }} <small>天</small></strong>
                  </div>
                  <div class="activity-summary-item">
                    <span class="summary-icon is-gold"><Icon icon="ph:star" /></span>
                    <span class="summary-label">单日最高</span>
                    <strong>{{ maxActivityCount }} <small>篇</small></strong>
                  </div>
                  <div class="activity-summary-item">
                    <span class="summary-icon is-blue"><Icon icon="ph:feather" /></span>
                    <span class="summary-label">书桌状态</span>
                    <strong class="status-text">{{ writingMood }}</strong>
                  </div>
                </div>
              </div>
            </section>

            <!-- 4. 最近手迹（5 篇手账卡片） -->
            <section class="recent-panel desk-card" aria-label="最近手迹">
              <div class="panel-head">
                <div class="panel-title">
                  <span class="panel-title-icon"><Icon icon="ph:book-open-text" /></span>
                  <h2>最近手迹</h2>
                </div>
                <button class="text-action" type="button" @click="goToNotes">
                  全部手稿
                  <Icon icon="ph:arrow-right" />
                </button>
              </div>

              <div v-if="recentNotes.length" class="recent-note-list">
                <article
                  v-for="(note, index) in recentNotes"
                  :key="note.id"
                  class="recent-note-item"
                  @click="goToDetail(note)"
                >
                  <!-- 左侧图标与时间 -->
                  <div class="item-visual-col">
                    <span class="item-type-icon" :class="`is-${resolveRecentTone(index)}`">
                      <Icon :icon="resolveRecentIcon(index)" />
                    </span>
                    <span class="item-date">{{ formatDateTime(note.updated_at || note.created_at) }}</span>
                  </div>

                  <!-- 主体内容：标题、真实标签、优雅2行摘要 -->
                  <div class="item-content-col">
                    <div class="item-title-row">
                      <h3 class="item-title">
                        <span v-if="note.is_pinned" class="pinned-tag" title="置顶手稿">
                          <Icon icon="ph:push-pin-fill" />
                        </span>
                        {{ note.title || '未命名手稿' }}
                      </h3>

                      <div v-if="note.tags && note.tags.length" class="item-tags">
                        <span v-for="tag in note.tags.slice(0, 2)" :key="tag.id || tag.name" class="item-tag-pill">
                          #{{ tag.name }}
                        </span>
                      </div>
                    </div>

                    <p class="item-excerpt">{{ note.excerpt }}</p>
                  </div>

                  <!-- 右侧元信息与交互反馈 -->
                  <div class="item-meta-col">
                    <span class="item-word-count">{{ formatWordCount(note.word_count) }}</span>
                    <span class="item-enter-btn" title="查看手稿">
                      <Icon icon="ph:arrow-up-right" />
                    </span>
                  </div>
                </article>
              </div>

              <div v-else class="empty-state">
                <Icon class="empty-icon" icon="ph:notebook" />
                <strong>{{ hasNotes ? '最近没有可展示的手稿' : '书桌还空着' }}</strong>
                <p>{{ hasNotes ? '可以进入笔记列表查看全部内容。' : '提笔创建第一篇笔记后，这里会沉淀最近手稿。' }}</p>
              </div>
            </section>
          </div>
        </div>
      </section>
    </WorkspaceShell>
  </main>
</template>

<style scoped>
.home-page {
  min-height: 100vh;
  min-height: 100svh;
  padding: 0;
  background: var(--app-background);
}

.home-stage {
  width: min(100%, 1400px);
  margin: 0 auto;
  padding: 44px 48px 48px 54px;
}

/* ================== 顶部 Header 与 墨迹印章条 ================== */
.home-topbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  padding-bottom: 28px;
}

.topbar-welcome {
  flex: 1;
  min-width: 0;
}

.welcome-heading-row {
  display: flex;
  align-items: center;
  gap: 16px;
}

.home-topbar h1 {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0;
  color: var(--text-primary);
  font-size: clamp(2rem, 2.4vw, 2.45rem);
  font-weight: 850;
  line-height: 1.1;
  letter-spacing: -0.01em;
}

.title-sun {
  width: 32px;
  height: 32px;
  color: var(--brand-gold);
  flex-shrink: 0;
}

.home-subtitle {
  margin: 10px 0 0;
  color: var(--ink-soft);
  font-size: 0.98rem;
  line-height: 1.5;
}

.home-subtitle span {
  color: var(--brand-blue);
  font-weight: 750;
}

/* 墨迹沉淀印章条 */
.desk-stats-strip {
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 14px;
  padding: 6px 14px;
  border: 1px solid var(--border-soft);
  border-radius: 999px;
  background: var(--control-background);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.4);
}

.desk-stat-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text-muted);
  font-size: 0.85rem;
}

.desk-stat-item svg {
  width: 1rem;
  height: 1rem;
  color: var(--moss);
}

.desk-stat-item strong {
  color: var(--text-primary);
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}

.desk-stat-sep {
  color: var(--border-soft);
  font-size: 0.8rem;
}

.desk-stat-item.is-overdue-alert {
  color: var(--danger);
}

.desk-stat-item.is-overdue-alert svg {
  color: var(--danger);
}

.desk-stat-item.is-overdue-alert strong {
  color: var(--danger);
}

.home-actions {
  display: flex;
  align-items: center;
  gap: 14px;
  padding-top: 4px;
  flex-shrink: 0;
}

.home-actions :deep(.el-button) {
  height: 46px;
  min-height: 46px;
  padding-inline: 20px;
  border-radius: 10px;
  font-size: 0.94rem;
  font-weight: 750;
  transition: transform 0.18s var(--motion-snappy), box-shadow 0.18s var(--motion-calm);
}

.cta-button {
  border: none;
  background: linear-gradient(180deg, #b96949, #9f432a);
  color: #fff8ec !important;
  box-shadow: 0 10px 20px rgba(150, 70, 38, 0.18);
}

.cta-button:hover {
  transform: translateY(-1px);
  box-shadow: 0 14px 26px rgba(150, 70, 38, 0.24);
}

.cta-button-secondary {
  border: 1px solid var(--border-soft);
  background: var(--control-background);
  color: var(--text-primary) !important;
}

.cta-button-secondary:hover {
  transform: translateY(-1px);
  border-color: var(--accent-border);
  background: var(--surface);
}

/* ================== 主网格布局 ================== */
.desk-grid {
  display: grid;
  grid-template-columns: 350px minmax(0, 1fr);
  gap: 26px;
  align-items: start;
}

.desk-side-column,
.desk-main-column {
  display: flex;
  flex-direction: column;
  gap: 24px;
  min-width: 0;
}

/* 通用书桌卡片容器 */
.desk-card {
  position: relative;
  padding: 22px 24px;
  border: 1px solid var(--border-soft);
  border-radius: 14px;
  background: var(--panel-background);
  box-shadow: var(--shadow-subtle), var(--inset-highlight);
  transition: border-color 0.2s var(--motion-calm);
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--divider);
}

.panel-title {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.panel-title h2 {
  margin: 0;
  color: var(--text-primary);
  font-size: 1.15rem;
  font-weight: 850;
  line-height: 1.2;
}

.panel-title-icon {
  display: inline-grid;
  place-items: center;
  width: 24px;
  height: 24px;
  color: var(--brand-blue);
}

.panel-title-icon svg {
  width: 1.15rem;
  height: 1.15rem;
}

.text-action {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0;
  border: none;
  background: transparent;
  color: var(--brand-blue);
  font-size: 0.88rem;
  font-weight: 750;
  cursor: pointer;
  transition: opacity 0.2s var(--motion-calm), transform 0.2s var(--motion-snappy);
}

.text-action:hover {
  opacity: 0.75;
  transform: translateX(2px);
}

/* ================== 1. 今日待办 ================== */
.todo-status-subhead {
  margin-top: 10px;
  margin-bottom: 12px;
  color: var(--text-muted);
  font-size: 0.82rem;
  font-weight: 650;
}

.todo-list {
  display: grid;
  gap: 8px;
  min-width: 0;
}

.todo-item {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  padding: 11px 14px;
  border: 1px solid var(--border-soft);
  border-left: 3px solid var(--border-soft);
  border-radius: var(--radius-sm);
  background: var(--panel-background-soft);
  transition: transform 0.16s var(--motion-snappy), background 0.16s ease;
}

.todo-item:hover {
  transform: translateX(2px);
  background: var(--control-hover-background);
}

.todo-item.is-low {
  border-left-color: var(--moss);
}

.todo-item.is-medium {
  border-left-color: var(--brand-gold);
}

.todo-item.is-high {
  border-left-color: var(--brand-blue);
}

.todo-item.is-urgent {
  border-left-color: var(--danger);
}

.todo-item.is-overdue {
  background: var(--danger-soft);
}

.todo-check {
  display: inline-grid;
  place-items: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--text-muted);
  font-size: 1.15rem;
  cursor: pointer;
  transition: color 0.18s var(--motion-calm), transform 0.18s var(--motion-snappy);
}

.todo-check:hover {
  color: var(--moss);
  transform: scale(1.15);
}

.todo-copy {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.todo-copy strong {
  overflow: hidden;
  color: var(--text-primary);
  font-size: 0.92rem;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.todo-copy small {
  color: var(--text-muted);
  font-size: 0.78rem;
  font-variant-numeric: tabular-nums;
}

.todo-overdue {
  padding: 2px 7px;
  border-radius: 999px;
  background: var(--danger-soft);
  color: var(--danger);
  font-size: 0.72rem;
  font-weight: 750;
}

/* ================== 2. 知识领域标签胶囊云 ================== */
.tag-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 9px;
  padding-top: 16px;
}

.tag-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 7px 12px;
  border: 1px solid var(--border-soft);
  border-radius: 8px;
  background: var(--control-background);
  color: var(--text-secondary);
  font: inherit;
  font-size: 0.88rem;
  cursor: pointer;
  transition: transform 0.16s var(--motion-snappy), border-color 0.16s ease, background 0.16s ease;
}

.tag-pill:hover {
  transform: translateY(-1px);
  border-color: var(--accent-border);
  background: var(--control-hover-background);
  color: var(--brand-blue);
}

.tag-pill-hash {
  color: var(--brand-gold);
  font-weight: 700;
}

.tag-pill-name {
  font-weight: 650;
}

.tag-pill-count {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 999px;
  background: var(--surface-muted);
  color: var(--text-muted);
  font-size: 0.76rem;
  font-weight: 700;
}

/* ================== 3. 笔耕足迹（热力图） ================== */
.activity-submeta {
  color: var(--text-muted);
  font-size: 0.88rem;
  font-weight: 650;
}

.activity-body {
  display: grid;
  grid-template-columns: minmax(230px, 286px) minmax(0, 1fr);
  gap: 40px;
  align-items: center;
  padding-top: 20px;
}

.activity-heatmap-panel {
  display: grid;
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
  grid-auto-columns: 16px;
  gap: 5px;
  width: max-content;
}

.activity-week {
  display: grid;
  grid-template-rows: repeat(7, 16px);
  gap: 5px;
}

.activity-day,
.activity-legend i {
  display: block;
  width: 16px;
  height: 16px;
  border: 1px solid var(--border-soft);
  border-radius: 4px;
  background: var(--control-background);
  box-shadow: none;
  transition: transform 0.16s ease, box-shadow 0.16s ease;
}

.activity-day:hover {
  transform: scale(1.22);
  box-shadow: 0 4px 10px rgba(42, 33, 23, 0.12);
}

.activity-day.is-future {
  opacity: 0.3;
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
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--text-muted);
  font-size: 0.78rem;
  font-weight: 700;
}

.activity-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  align-items: center;
  border-left: 1px solid var(--divider);
  padding-left: 36px;
}

.activity-summary-item {
  display: grid;
  justify-items: center;
  gap: 6px;
  padding: 12px 14px;
  text-align: center;
}

.activity-summary-item + .activity-summary-item {
  border-left: 1px solid var(--divider);
}

.summary-icon {
  display: inline-grid;
  place-items: center;
  width: 44px;
  height: 44px;
  margin-bottom: 4px;
  border-radius: 999px;
}

.summary-icon svg {
  width: 1.3rem;
  height: 1.3rem;
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
  color: var(--brand-blue);
}

.summary-label {
  color: var(--text-muted);
  font-size: 0.86rem;
  font-weight: 700;
}

.activity-summary-item strong {
  color: var(--text-primary);
  font-size: clamp(1.8rem, 2.5vw, 2.2rem);
  font-weight: 850;
  line-height: 1.1;
}

.activity-summary-item strong small {
  font-size: 0.85rem;
  font-weight: 650;
  color: var(--text-muted);
}

.activity-summary-item strong.status-text {
  font-size: clamp(1.2rem, 1.8vw, 1.45rem);
  color: var(--brand-blue);
  margin-top: 4px;
}

/* ================== 4. 最近手迹 ================== */
.recent-note-list {
  display: flex;
  flex-direction: column;
}

.recent-note-item {
  display: grid;
  grid-template-columns: 110px minmax(0, 1fr) auto;
  gap: 20px;
  align-items: center;
  padding: 15px 8px;
  border-bottom: 1px solid var(--divider);
  cursor: pointer;
  transition: background 0.18s var(--motion-calm), padding 0.18s var(--motion-snappy);
}

.recent-note-item:last-child {
  border-bottom: none;
}

.recent-note-item:hover {
  background: var(--control-hover-background);
  border-radius: 10px;
}

.recent-note-item:hover .item-title {
  color: var(--brand-blue);
}

.recent-note-item:hover .item-enter-btn {
  opacity: 1;
  transform: translate(2px, -2px);
  color: var(--brand-blue);
}

/* 左侧图标与时间 */
.item-visual-col {
  display: flex;
  align-items: center;
  gap: 12px;
}

.item-type-icon {
  display: inline-grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border: 1px solid var(--border-soft);
  border-radius: 8px;
  flex-shrink: 0;
}

.item-type-icon svg {
  width: 1.1rem;
  height: 1.1rem;
}

.item-type-icon.is-paper {
  background: var(--accent-soft);
  color: var(--brand-blue);
}

.item-type-icon.is-moss {
  background: var(--moss-soft);
  color: var(--moss);
}

.item-type-icon.is-gold {
  background: color-mix(in srgb, var(--brand-gold) 16%, var(--panel-background));
  color: var(--brand-gold);
}

.item-type-icon.is-blue {
  background: rgba(74, 136, 188, 0.12);
  color: var(--brand-blue);
}

.item-type-icon.is-stone {
  background: var(--control-background);
  color: var(--text-muted);
}

.item-date {
  color: var(--text-muted);
  font-size: 0.78rem;
  line-height: 1.35;
  white-space: pre-line;
  font-variant-numeric: tabular-nums;
}

/* 主体信息列 */
.item-content-col {
  display: grid;
  gap: 5px;
  min-width: 0;
}

.item-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.item-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  color: var(--text-primary);
  font-size: 1rem;
  font-weight: 850;
  line-height: 1.3;
  transition: color 0.18s ease;
}

.pinned-tag {
  display: inline-flex;
  align-items: center;
  color: var(--brand-gold);
  font-size: 0.95rem;
}

.item-tags {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.item-tag-pill {
  padding: 1px 7px;
  border-radius: 999px;
  background: var(--surface-muted);
  color: var(--text-muted);
  font-size: 0.74rem;
  font-weight: 650;
}

.item-excerpt {
  margin: 0;
  color: var(--ink-soft);
  font-size: 0.86rem;
  line-height: 1.55;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 右侧元信息列 */
.item-meta-col {
  display: flex;
  align-items: center;
  gap: 14px;
  color: var(--text-muted);
  font-size: 0.86rem;
  white-space: nowrap;
}

.item-word-count {
  font-variant-numeric: tabular-nums;
  font-size: 0.82rem;
}

.item-enter-btn {
  display: inline-grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  opacity: 0.45;
  transition: opacity 0.18s ease, transform 0.18s var(--motion-snappy), color 0.18s ease;
}

.item-enter-btn svg {
  width: 1.15rem;
  height: 1.15rem;
}

/* ================== 通用空状态 ================== */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px 16px;
  text-align: center;
  color: var(--text-muted);
}

.empty-state.compact {
  padding: 24px 12px;
}

.empty-icon {
  width: 32px;
  height: 32px;
  margin-bottom: 10px;
  color: var(--border-soft);
}

.empty-state strong {
  color: var(--text-primary);
  font-size: 0.96rem;
}

.empty-state p {
  margin: 6px 0 0;
  font-size: 0.84rem;
  line-height: 1.6;
}

/* ================== 响应式适配 ================== */
@media (max-width: 1240px) {
  .desk-grid {
    grid-template-columns: 310px minmax(0, 1fr);
    gap: 20px;
  }

  .activity-body {
    grid-template-columns: 1fr;
    gap: 22px;
  }

  .activity-summary {
    border-left: none;
    border-top: 1px solid var(--divider);
    padding-left: 0;
    padding-top: 20px;
  }
}

@media (max-width: 980px) {
  .home-stage {
    padding: 28px 20px 36px;
  }

  .home-topbar {
    flex-direction: column;
    align-items: stretch;
    gap: 16px;
  }

  .home-actions {
    justify-content: flex-start;
  }

  .desk-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .recent-note-item {
    grid-template-columns: 1fr;
    gap: 10px;
  }

  .item-meta-col {
    justify-content: space-between;
  }

  .item-visual-col {
    justify-content: space-between;
  }
}
</style>
