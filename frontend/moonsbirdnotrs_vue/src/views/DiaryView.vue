<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowLeftBold,
  ArrowRightBold,
  Calendar,
  EditPen,
  Plus,
  Reading,
  RefreshRight,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import Viewer from '@toast-ui/editor/viewer'

import '@toast-ui/editor/dist/toastui-editor-viewer.css'

import WorkspaceShell from '../components/WorkspaceShell.vue'
import api from '../services/api'
import diaryEmptyIllustration from '../assets/diary-empty-illustration.png'
import { enhanceRichContent } from '../utils/richContent'
import { applyTableLayoutsToTables, extractTableLayoutMetadata } from '../utils/tableLayout'
import '../styles/markdown.css'

const route = useRoute()
const router = useRouter()

const articleViewer = ref(null)
const loadingMonth = ref(false)
const loadingEntry = ref(false)
const monthEntries = ref([])
const selectedEntry = ref(null)
const buttonRipples = ref({
  headerEdit: [],
  readerEdit: [],
  emptyEdit: [],
})

let rippleSeed = 0

let viewerInstance = null
let viewerTableLayouts = []

const padDatePart = (value) => String(value).padStart(2, '0')

const toDateKey = (date) =>
  `${date.getFullYear()}-${padDatePart(date.getMonth() + 1)}-${padDatePart(date.getDate())}`

const todayDateKey = () => toDateKey(new Date())

const parseDateKey = (dateKey) => {
  const parts = String(dateKey || '').split('-').map((part) => Number(part))

  if (parts.length !== 3 || parts.some((part) => Number.isNaN(part))) {
    return null
  }

  const [year, month, day] = parts
  const date = new Date(year, month - 1, day)

  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) {
    return null
  }

  return date
}

const normalizeDateKey = (dateKey) => {
  const parsed = parseDateKey(dateKey)
  return parsed ? toDateKey(parsed) : todayDateKey()
}

const getMonthKey = (dateKey) => {
  const parsed = parseDateKey(dateKey) || new Date()
  return `${parsed.getFullYear()}-${padDatePart(parsed.getMonth() + 1)}`
}

const addDays = (date, days) => {
  const nextDate = new Date(date)
  nextDate.setDate(nextDate.getDate() + days)
  return nextDate
}

const addMonths = (monthKey, offset) => {
  const [year, month] = monthKey.split('-').map((part) => Number(part))
  const date = new Date(year, month - 1 + offset, 1)
  return `${date.getFullYear()}-${padDatePart(date.getMonth() + 1)}`
}

const selectedDate = ref(normalizeDateKey(route.params.date))
const monthCursor = ref(getMonthKey(selectedDate.value))

const entriesByDate = computed(() => {
  const map = new Map()
  monthEntries.value.forEach((entry) => {
    map.set(entry.diary_date, entry)
  })
  return map
})

const monthTitle = computed(() => {
  const [year, month] = monthCursor.value.split('-').map((part) => Number(part))
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: 'long',
  }).format(new Date(year, month - 1, 1))
})

const selectedDateLabel = computed(() => {
  const parsed = parseDateKey(selectedDate.value) || new Date()
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    weekday: 'long',
  }).format(parsed)
})

const selectedDateParts = computed(() => {
  const parsed = parseDateKey(selectedDate.value) || new Date()

  return {
    day: padDatePart(parsed.getDate()),
    month: new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'long' }).format(parsed),
    weekday: new Intl.DateTimeFormat('zh-CN', { weekday: 'long' }).format(parsed),
  }
})

const monthEntryCount = computed(() => monthEntries.value.length)

const monthWordCount = computed(() =>
  monthEntries.value.reduce((total, entry) => total + Number(entry.word_count || 0), 0)
)

const isSelectedToday = computed(() => selectedDate.value === todayDateKey())

const selectedDateStatus = computed(() => {
  if (selectedEntry.value) {
    return `${selectedEntry.value.word_count || 0} 字`
  }

  return isSelectedToday.value ? '今天待写' : '尚未记录'
})

const selectedMetaItems = computed(() => {
  if (!selectedEntry.value) {
    return []
  }

  return [
    selectedEntry.value.mood ? { label: '心情', value: selectedEntry.value.mood } : null,
    selectedEntry.value.weather ? { label: '天气', value: selectedEntry.value.weather } : null,
    selectedEntry.value.summary ? { label: '摘要', value: selectedEntry.value.summary } : null,
    { label: '字数', value: `${selectedEntry.value.word_count || 0} 字` },
  ].filter(Boolean)
})

const calendarDays = computed(() => {
  const [year, month] = monthCursor.value.split('-').map((part) => Number(part))
  const firstDay = new Date(year, month - 1, 1)
  const mondayFirstOffset = (firstDay.getDay() + 6) % 7
  const gridStart = addDays(firstDay, -mondayFirstOffset)

  return Array.from({ length: 42 }, (_, index) => {
    const date = addDays(gridStart, index)
    const dateKey = toDateKey(date)
    const entry = entriesByDate.value.get(dateKey)

    return {
      date,
      dateKey,
      entry,
      dayNumber: date.getDate(),
      isCurrentMonth: date.getMonth() === firstDay.getMonth(),
      isToday: dateKey === todayDateKey(),
      isSelected: dateKey === selectedDate.value,
    }
  })
})

const weekdayLabels = ['一', '二', '三', '四', '五', '六', '日']

const resetViewer = () => {
  viewerInstance?.destroy()
  viewerInstance = null

  if (articleViewer.value) {
    articleViewer.value.innerHTML = ''
  }
}

const removeDuplicatedDiaryTitle = (markdown, title) => {
  const lines = String(markdown || '').split(/\r?\n/)
  const firstContentIndex = lines.findIndex((line) => line.trim())

  if (firstContentIndex === -1) {
    return ''
  }

  const firstContent = lines[firstContentIndex].trim()
  const firstHeading = firstContent.match(/^#\s+(.+)$/)

  if (!firstHeading || firstHeading[1].trim() !== String(title || '').trim()) {
    return markdown
  }

  let nextIndex = firstContentIndex + 1
  while (nextIndex < lines.length && !lines[nextIndex].trim()) {
    nextIndex += 1
  }

  return [...lines.slice(0, firstContentIndex), ...lines.slice(nextIndex)].join('\n').trimStart()
}

const renderViewerContent = async () => {
  await nextTick()

  if (!articleViewer.value) {
    return
  }

  if (!selectedEntry.value) {
    resetViewer()
    return
  }

  const parsedMarkdown = extractTableLayoutMetadata(selectedEntry.value.markdown_content || '')
  const viewerMarkdown = removeDuplicatedDiaryTitle(parsedMarkdown.markdown, selectedEntry.value.title)
  viewerTableLayouts = parsedMarkdown.layouts

  const applyViewerTableLayouts = () => {
    applyTableLayoutsToTables(
      articleViewer.value?.querySelectorAll('.toastui-editor-contents table') || [],
      viewerTableLayouts
    )
  }

  const scheduleViewerTableLayouts = () => {
    window.requestAnimationFrame(() => {
      applyViewerTableLayouts()
      enhanceRichContent(articleViewer.value)
      window.requestAnimationFrame(applyViewerTableLayouts)
    })
  }

  if (!viewerInstance) {
    viewerInstance = new Viewer({
      el: articleViewer.value,
      initialValue: viewerMarkdown,
      usageStatistics: false,
    })
    scheduleViewerTableLayouts()
    return
  }

  viewerInstance.setMarkdown(viewerMarkdown)
  scheduleViewerTableLayouts()
}

const fetchMonthEntries = async () => {
  loadingMonth.value = true

  try {
    const { data } = await api.get('/notes/diaries/', {
      params: {
        month: monthCursor.value,
      },
    })
    monthEntries.value = data
  } catch (error) {
    const detail = error.response?.data?.detail || '日记月份数据加载失败。'
    ElMessage.error(detail)
  } finally {
    loadingMonth.value = false
  }
}

const fetchSelectedEntry = async () => {
  loadingEntry.value = true

  try {
    const { data } = await api.get(`/notes/diaries/by-date/${selectedDate.value}/`)
    selectedEntry.value = data
  } catch (error) {
    if (error.response?.status === 404) {
      selectedEntry.value = null
    } else {
      const detail = error.response?.data?.detail || '日记详情加载失败。'
      ElMessage.error(detail)
    }
  } finally {
    loadingEntry.value = false
    await renderViewerContent()
  }
}

const refreshPage = async () => {
  await fetchMonthEntries()
  await fetchSelectedEntry()
}

const selectDate = (dateKey) => {
  router.push({ name: 'diary', params: { date: dateKey } })
}

const changeMonth = async (offset) => {
  monthCursor.value = addMonths(monthCursor.value, offset)
  await fetchMonthEntries()
}

const goToday = () => {
  selectDate(todayDateKey())
}

const goToEdit = () => {
  router.push({ name: 'diary-edit', params: { date: selectedDate.value } })
}

const addButtonRipple = (event, target) => {
  const button = event.currentTarget
  const rect = button.getBoundingClientRect()
  const size = Math.max(rect.width, rect.height) * 1.75
  const originX = event.clientX || rect.left + rect.width / 2
  const originY = event.clientY || rect.top + rect.height / 2
  const ripple = {
    id: rippleSeed += 1,
    size,
    x: originX - rect.left - size / 2,
    y: originY - rect.top - size / 2,
  }

  buttonRipples.value[target] = [...buttonRipples.value[target], ripple]

  window.setTimeout(() => {
    buttonRipples.value[target] = buttonRipples.value[target].filter((item) => item.id !== ripple.id)
  }, 620)
}

const handleEditClick = (event, target) => {
  addButtonRipple(event, target)
  window.setTimeout(goToEdit, 140)
}

const syncRouteDate = async () => {
  const nextDate = normalizeDateKey(route.params.date)
  const nextMonth = getMonthKey(nextDate)
  const shouldReloadMonth = nextMonth !== monthCursor.value

  selectedDate.value = nextDate
  monthCursor.value = nextMonth

  if (shouldReloadMonth) {
    await fetchMonthEntries()
  }

  await fetchSelectedEntry()
}

const formatEntryPreview = (entry) => {
  if (!entry) {
    return ''
  }

  return entry.summary || entry.mood || `${entry.word_count || 0} 字`
}

onMounted(async () => {
  await fetchMonthEntries()
  await syncRouteDate()
})

onBeforeUnmount(() => {
  resetViewer()
})
</script>

<template>
  <main class="diary-page page-shell">
    <WorkspaceShell>
      <section class="diary-stage">
        <header class="diary-header fade-rise-enter">
          <div class="diary-heading-copy">
            <p class="diary-kicker">Diary</p>
            <div class="diary-title-line">
              <h1>日记</h1>
              <span class="diary-date-chip">
                <el-icon><Calendar /></el-icon>
                {{ selectedDateLabel }}
              </span>
              <span class="diary-status-chip" :class="{ 'is-empty': !selectedEntry }">
                {{ selectedEntry ? '已记录' : selectedDateStatus }}
              </span>
            </div>
          </div>

          <div class="diary-header-actions">
            <el-button @click="goToday">
              <el-icon><Calendar /></el-icon>
              <span>今天</span>
            </el-button>
            <el-button :loading="loadingMonth || loadingEntry" @click="refreshPage">
              <el-icon><RefreshRight /></el-icon>
              <span>刷新</span>
            </el-button>
            <el-button class="glow-action ripple-button" type="primary" @click="handleEditClick($event, 'headerEdit')">
              <el-icon><EditPen /></el-icon>
              <span>{{ selectedEntry ? '继续编写' : '编辑这天' }}</span>
              <span
                v-for="ripple in buttonRipples.headerEdit"
                :key="ripple.id"
                class="action-ripple"
                :style="{
                  width: `${ripple.size}px`,
                  height: `${ripple.size}px`,
                  left: `${ripple.x}px`,
                  top: `${ripple.y}px`,
                }"
              ></span>
            </el-button>
          </div>
        </header>

        <section class="diary-layout fade-rise-enter-delay">
          <aside class="diary-calendar-panel" v-loading="loadingMonth">
            <div class="month-toolbar">
              <button type="button" class="icon-button" aria-label="上个月" @click="changeMonth(-1)">
                <el-icon><ArrowLeftBold /></el-icon>
              </button>
              <strong>{{ monthTitle }}</strong>
              <button type="button" class="icon-button" aria-label="下个月" @click="changeMonth(1)">
                <el-icon><ArrowRightBold /></el-icon>
              </button>
            </div>

            <div class="calendar-overview">
              <span>
                <strong :key="`entry-${monthEntryCount}`" class="flip-number">{{ monthEntryCount }}</strong>
                <em>已写天数</em>
              </span>
              <span>
                <strong :key="`word-${monthWordCount}`" class="flip-number">{{ monthWordCount }}</strong>
                <em>本月字数</em>
              </span>
              <span>
                <strong :key="`status-${selectedDateStatus}`" class="flip-number">{{ selectedDateStatus }}</strong>
                <em>选中日期</em>
              </span>
            </div>

            <div class="weekday-row">
              <span v-for="weekday in weekdayLabels" :key="weekday">{{ weekday }}</span>
            </div>

            <Transition name="calendar-swap" mode="out-in">
              <div :key="monthCursor" class="calendar-grid">
                <button
                  v-for="day in calendarDays"
                  :key="day.dateKey"
                  type="button"
                  class="day-cell"
                  :class="{
                    'is-muted': !day.isCurrentMonth,
                    'is-today': day.isToday,
                    'is-selected': day.isSelected,
                    'has-entry': day.entry,
                  }"
                  @click="selectDate(day.dateKey)"
                >
                  <span>{{ day.dayNumber }}</span>
                  <small>{{ formatEntryPreview(day.entry) }}</small>
                </button>
              </div>
            </Transition>
          </aside>

          <article class="diary-reader" v-loading="loadingEntry">
            <div class="reader-heading">
              <Transition name="date-mark" mode="out-in">
                <div :key="selectedDate" class="selected-date-mark" aria-hidden="true">
                  <span>{{ selectedDateParts.month }}</span>
                  <strong>{{ selectedDateParts.day }}</strong>
                </div>
              </Transition>

              <Transition name="date-copy" mode="out-in">
                <div :key="`${selectedDate}-${selectedEntry ? 'written' : 'empty'}`" class="reader-heading-copy">
                  <p>{{ selectedEntry ? 'Current Entry' : 'Selected Date' }}</p>
                  <h2>{{ selectedDateParts.weekday }}</h2>
                  <span>{{ selectedDateLabel }}</span>
                </div>
              </Transition>

              <el-button class="glow-action ripple-button" type="primary" @click="handleEditClick($event, 'readerEdit')">
                <el-icon><Plus v-if="!selectedEntry" /><EditPen v-else /></el-icon>
                <span>{{ selectedEntry ? '编辑日记' : '开始编写' }}</span>
                <span
                  v-for="ripple in buttonRipples.readerEdit"
                  :key="ripple.id"
                  class="action-ripple"
                  :style="{
                    width: `${ripple.size}px`,
                    height: `${ripple.size}px`,
                    left: `${ripple.x}px`,
                    top: `${ripple.y}px`,
                  }"
                ></span>
              </el-button>
            </div>

            <template v-if="selectedEntry">
              <div class="diary-meta-list" v-if="selectedMetaItems.length">
                <span v-for="item in selectedMetaItems" :key="item.label" class="diary-meta-item">
                  <em>{{ item.label }}</em>
                  <strong>{{ item.value }}</strong>
                </span>
              </div>

              <div class="diary-note-title">
                <el-icon><Reading /></el-icon>
                <span>{{ selectedEntry.title }}</span>
              </div>

              <div ref="articleViewer" class="diary-viewer detail-viewer blog-prose"></div>
            </template>

            <template v-else>
              <div class="empty-diary">
                <img class="empty-diary-illustration" :src="diaryEmptyIllustration" alt="" aria-hidden="true" />
                <div class="empty-diary-mark">
                  <span>{{ selectedDateLabel }}</span>
                </div>
                <p>{{ selectedDateLabel }}</p>
                <h2 :key="selectedDate" class="typewriter-title"><span>这一天还没有日记</span></h2>
                <el-button class="glow-action ripple-button" type="primary" @click="handleEditClick($event, 'emptyEdit')">
                  <el-icon><Plus /></el-icon>
                  <span>编写这天日记</span>
                  <span
                    v-for="ripple in buttonRipples.emptyEdit"
                    :key="ripple.id"
                    class="action-ripple"
                    :style="{
                      width: `${ripple.size}px`,
                      height: `${ripple.size}px`,
                      left: `${ripple.x}px`,
                      top: `${ripple.y}px`,
                    }"
                  ></span>
                </el-button>
              </div>
            </template>
          </article>
        </section>
      </section>
    </WorkspaceShell>
  </main>
</template>

<style scoped>
.diary-page {
  background:
    linear-gradient(180deg, rgba(248, 250, 252, 0.96) 0%, rgba(246, 248, 251, 0.82) 48%, var(--page-bg) 100%),
    linear-gradient(90deg, rgba(148, 163, 184, 0.08) 1px, transparent 1px),
    linear-gradient(180deg, rgba(148, 163, 184, 0.08) 1px, transparent 1px);
  background-size: auto, 88px 88px, 88px 88px;
}

.diary-stage {
  --diary-panel-bg: rgba(255, 255, 255, 0.9);
  --diary-panel-strong: rgba(255, 255, 255, 0.96);
  --diary-panel-muted: rgba(248, 250, 252, 0.72);
  --diary-border: rgba(148, 163, 184, 0.18);
  --diary-shadow: 0 24px 54px rgba(15, 23, 42, 0.08);
  --diary-blue-shadow: 0 18px 32px rgba(34, 81, 209, 0.16);
  width: min(1480px, 100%);
  margin: 0 auto;
  padding: 36px clamp(18px, 3vw, 46px) 52px;
}

:global(:root[data-theme='dark']) .diary-page {
  background: var(--app-background);
}

:global(:root[data-theme='dark']) .diary-stage {
  --diary-panel-bg: var(--panel-background);
  --diary-panel-strong: var(--panel-background-raised);
  --diary-panel-muted: var(--panel-background-soft);
  --diary-border: var(--border-soft);
  --diary-shadow: var(--shadow-soft);
  --diary-blue-shadow: var(--shadow-subtle);
}

.diary-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 22px;
  margin-bottom: 24px;
}

.diary-heading-copy {
  display: grid;
  gap: 10px;
  min-width: 0;
}

.diary-title-line {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  min-width: 0;
}

.diary-kicker,
.reader-heading p {
  margin: 0;
  color: var(--brand-blue);
  font-size: 0.75rem;
  font-weight: 800;
  letter-spacing: 0;
  text-transform: uppercase;
}

.diary-header h1,
.reader-heading h2 {
  margin: 0;
  color: var(--brand-navy);
  letter-spacing: 0;
}

.diary-header h1 {
  font-size: 3.6rem;
  line-height: 0.98;
}

.diary-date-chip,
.diary-status-chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 34px;
  max-width: 100%;
  padding: 0 11px;
  border: 1px solid var(--diary-border);
  border-radius: 8px;
  background: var(--diary-panel-strong);
  color: var(--ink-soft);
  font-size: 0.92rem;
  font-weight: 800;
  line-height: 1;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.04);
}

.diary-date-chip :deep(.el-icon) {
  color: var(--brand-blue);
  font-size: 0.94rem;
}

.diary-status-chip {
  border-color: rgba(16, 185, 129, 0.22);
  background: rgba(16, 185, 129, 0.08);
  color: var(--moss);
}

.diary-status-chip.is-empty {
  border-color: rgba(217, 119, 6, 0.2);
  background: rgba(245, 158, 11, 0.09);
  color: var(--brand-gold);
}

.diary-header-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
}

.diary-header-actions :deep(.el-button),
.reader-heading :deep(.el-button),
.empty-diary :deep(.el-button) {
  min-height: 42px;
  padding-inline: 16px;
  border-radius: 8px;
  font-weight: 800;
}

.diary-header-actions :deep(.el-button:not(.el-button--primary)) {
  border-color: var(--diary-border);
  background: var(--diary-panel-strong);
  color: var(--brand-navy);
}

.diary-header-actions :deep(.el-button:not(.el-button--primary):hover) {
  border-color: var(--accent-border);
  background: var(--accent-soft);
  color: var(--brand-blue);
}

.diary-header-actions :deep(.el-button--primary),
.reader-heading :deep(.el-button--primary),
.empty-diary :deep(.el-button--primary) {
  box-shadow: var(--diary-blue-shadow);
}

.diary-layout {
  display: grid;
  grid-template-columns: minmax(320px, 380px) minmax(0, 1fr);
  gap: 22px;
  align-items: start;
}

.diary-calendar-panel,
.diary-reader {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--diary-border);
  border-radius: 8px !important;
  background: var(--diary-panel-bg) !important;
  box-shadow: var(--diary-shadow) !important;
  backdrop-filter: blur(20px);
}

.diary-calendar-panel::before,
.diary-reader::before {
  position: absolute;
  top: 0;
  right: 0;
  left: 0;
  height: 3px;
  background: linear-gradient(90deg, var(--brand-blue), rgba(16, 185, 129, 0.72), rgba(245, 158, 11, 0.72));
  content: '';
}

.diary-calendar-panel {
  position: sticky;
  top: 22px;
  padding: 22px;
}

.month-toolbar {
  display: grid;
  grid-template-columns: 40px minmax(0, 1fr) 40px;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}

.month-toolbar strong {
  color: var(--brand-navy);
  text-align: center;
  font-size: 1.08rem;
  letter-spacing: 0;
}

.icon-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border: 1px solid var(--diary-border);
  border-radius: 8px;
  background: var(--diary-panel-strong);
  color: var(--brand-navy);
  cursor: pointer;
  transition:
    transform 0.2s ease,
    border-color 0.2s ease,
    background 0.2s ease,
    color 0.2s ease,
    box-shadow 0.2s ease;
}

.diary-header-actions :deep(.el-button:not(.el-button--primary)) {
  box-shadow: var(--shadow-subtle);
}

.icon-button:hover {
  transform: translateY(-1px);
  border-color: var(--accent-border);
  background: var(--accent-soft);
  color: var(--brand-blue);
  box-shadow: 0 10px 20px rgba(34, 81, 209, 0.1);
}

.calendar-overview {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1px;
  margin-bottom: 18px;
  overflow: hidden;
  border: 1px solid var(--diary-border);
  border-radius: 8px;
  background: var(--diary-border);
}

.calendar-overview span {
  display: grid;
  gap: 4px;
  min-width: 0;
  padding: 11px 9px;
  background: var(--diary-panel-muted);
}

.calendar-overview strong {
  overflow: hidden;
  color: var(--brand-navy);
  font-size: 1rem;
  font-weight: 900;
  line-height: 1.1;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.calendar-overview em {
  color: var(--text-muted);
  font-size: 0.72rem;
  font-style: normal;
  font-weight: 700;
  line-height: 1.1;
}

.weekday-row,
.calendar-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
}

.weekday-row {
  gap: 6px;
  margin-bottom: 8px;
}

.weekday-row span {
  color: var(--text-muted);
  text-align: center;
  font-size: 0.74rem;
  font-weight: 800;
}

.calendar-grid {
  gap: 7px;
}

.day-cell {
  position: relative;
  display: grid;
  align-content: start;
  gap: 3px;
  min-width: 0;
  min-height: 62px;
  padding: 8px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: var(--brand-navy);
  text-align: left;
  cursor: pointer;
  transition:
    transform 0.18s ease,
    border-color 0.18s ease,
    background 0.18s ease,
    box-shadow 0.18s ease;
}

.day-cell::after {
  position: absolute;
  right: 9px;
  bottom: 9px;
  width: 5px;
  height: 5px;
  border-radius: 999px;
  background: transparent;
  content: '';
}

.day-cell:hover {
  transform: translateY(-1px);
  border-color: var(--accent-border);
  background: var(--accent-soft);
}

.day-cell span {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 27px;
  height: 27px;
  border-radius: 999px;
  font-weight: 900;
}

.day-cell small {
  display: -webkit-box;
  min-height: 18px;
  overflow: hidden;
  color: var(--text-muted);
  font-size: 0.69rem;
  font-weight: 700;
  line-height: 1.35;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 1;
}

.day-cell.is-muted {
  opacity: 0.42;
}

.day-cell.is-today span {
  background: rgba(245, 158, 11, 0.12);
  color: var(--brand-gold);
}

.day-cell.has-entry {
  border-color: rgba(34, 81, 209, 0.14);
  background: rgba(37, 99, 235, 0.055);
}

.day-cell.has-entry::after {
  background: var(--brand-blue);
}

.day-cell.is-selected {
  transform: translateY(-1px);
  border-color: rgba(34, 81, 209, 0.34);
  background:
    linear-gradient(180deg, rgba(37, 99, 235, 0.12), rgba(37, 99, 235, 0.06)),
    var(--diary-panel-strong);
  box-shadow: 0 12px 24px rgba(34, 81, 209, 0.14);
}

.day-cell.is-selected span {
  background: var(--brand-blue);
  color: var(--text-on-accent);
}

.day-cell.is-selected::after {
  background: #10b981;
}

.diary-reader {
  min-height: 620px;
  padding: 30px;
}

.reader-heading {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 18px;
  margin-bottom: 20px;
  padding-bottom: 22px;
  border-bottom: 1px solid var(--diary-border);
}

.selected-date-mark {
  display: grid;
  place-items: center;
  width: 82px;
  height: 92px;
  border: 1px solid rgba(34, 81, 209, 0.16);
  border-radius: 8px;
  background:
    linear-gradient(180deg, rgba(37, 99, 235, 0.11), rgba(37, 99, 235, 0.04)),
    var(--diary-panel-strong);
  color: var(--brand-blue);
}

.selected-date-mark span {
  align-self: end;
  color: var(--ink-soft);
  font-size: 0.72rem;
  font-weight: 800;
  line-height: 1.2;
}

.selected-date-mark strong {
  align-self: start;
  color: var(--brand-navy);
  font-size: 2.75rem;
  font-weight: 900;
  line-height: 0.98;
}

.reader-heading-copy {
  display: grid;
  gap: 5px;
  min-width: 0;
}

.reader-heading h2 {
  color: var(--brand-navy);
  font-size: 2rem;
  line-height: 1.14;
}

.reader-heading-copy > span {
  overflow: hidden;
  color: var(--ink-soft);
  font-size: 0.96rem;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.diary-meta-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.diary-meta-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  max-width: 100%;
  min-height: 34px;
  padding: 0 11px;
  border: 1px solid var(--diary-border);
  border-radius: 8px;
  background: var(--diary-panel-muted);
}

.diary-meta-item em {
  color: var(--text-muted);
  font-size: 0.76rem;
  font-style: normal;
  font-weight: 800;
}

.diary-meta-item strong {
  min-width: 0;
  overflow: hidden;
  color: var(--brand-navy);
  font-size: 0.88rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.diary-note-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  max-width: 100%;
  min-height: 38px;
  margin: 0 0 20px;
  padding: 0 12px;
  border: 1px solid var(--diary-border);
  border-radius: 8px;
  background: var(--diary-panel-muted);
  color: var(--ink-soft);
  font-weight: 800;
}

.diary-note-title :deep(.el-icon) {
  color: var(--brand-blue);
}

.diary-note-title span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.diary-viewer {
  min-height: 390px;
  padding-top: 4px;
}

.diary-viewer :deep(.toastui-editor-contents) {
  max-width: 900px;
  margin: 0 auto;
  overflow-x: hidden;
  font-size: 1rem;
}

/* 内容排版统一由全局 styles/blog-prose.css 提供（对齐博客），
   这里只保留 toast-ui 结构相关的必要修正。 */
.diary-viewer :deep(.toastui-editor-contents .toastui-editor-ww-code-block pre) {
  margin: 0;
  border: none;
  border-radius: 0;
  background: transparent;
}

.empty-diary {
  display: grid;
  justify-items: center;
  align-content: center;
  gap: 10px;
  min-height: 420px;
  padding: 42px 20px;
  border: 1px dashed rgba(34, 81, 209, 0.28);
  border-radius: 8px !important;
  background:
    linear-gradient(180deg, rgba(37, 99, 235, 0.045), rgba(16, 185, 129, 0.035)),
    var(--diary-panel-muted) !important;
  text-align: center;
  box-shadow: none !important;
}

.empty-diary-mark {
  display: grid;
  place-items: center;
  width: 92px;
  height: 92px;
  margin-bottom: 6px;
  border: 1px solid rgba(34, 81, 209, 0.16);
  border-radius: 8px;
  background: var(--diary-panel-strong);
  color: var(--brand-blue);
}

.empty-diary-mark :deep(.el-icon) {
  font-size: 1.15rem;
}

.empty-diary-mark strong {
  color: var(--brand-navy);
  font-size: 2.4rem;
  font-weight: 900;
  line-height: 1;
}

.empty-diary p {
  margin: 0;
  color: var(--text-muted);
  font-weight: 800;
}

.empty-diary h2 {
  margin: 0 0 10px;
  color: var(--brand-navy);
  font-size: 2rem;
  letter-spacing: 0;
}

@media (max-width: 1180px) {
  .diary-layout {
    grid-template-columns: 1fr;
  }

  .diary-calendar-panel {
    position: static;
  }
}

@media (max-width: 820px) {
  .diary-stage {
    padding: 26px 14px 38px;
  }

  .diary-header {
    align-items: stretch;
    flex-direction: column;
  }

  .diary-header h1 {
    font-size: 2.75rem;
  }

  .diary-header-actions {
    justify-content: stretch;
  }

  .diary-header-actions :deep(.el-button) {
    flex: 1 1 124px;
  }

  .reader-heading {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .reader-heading :deep(.el-button) {
    grid-column: 1 / -1;
    width: 100%;
  }
}

@media (max-width: 560px) {
  .diary-calendar-panel,
  .diary-reader {
    padding: 18px;
  }

  .calendar-overview {
    grid-template-columns: 1fr;
  }

  .calendar-grid {
    gap: 5px;
  }

  .day-cell {
    min-height: 48px;
    padding: 6px;
  }

  .day-cell span {
    width: 24px;
    height: 24px;
  }

  .day-cell small {
    display: none;
  }

  .selected-date-mark {
    width: 70px;
    height: 80px;
  }

  .selected-date-mark strong {
    font-size: 2.25rem;
  }

  .reader-heading h2,
  .empty-diary h2 {
    font-size: 1.55rem;
  }

  .diary-viewer :deep(.toastui-editor-contents h1) {
    font-size: 1.85rem;
  }
}

.diary-page {
  background:
    linear-gradient(180deg, rgba(250, 252, 255, 0.98) 0%, rgba(241, 247, 251, 0.92) 44%, rgba(246, 248, 251, 0.98) 100%),
    linear-gradient(115deg, rgba(34, 81, 209, 0.05) 0%, transparent 36%, rgba(14, 165, 233, 0.08) 100%);
}

.diary-stage {
  --diary-panel-bg: rgba(255, 255, 255, 0.64);
  --diary-panel-strong: rgba(255, 255, 255, 0.82);
  --diary-panel-muted: rgba(248, 251, 255, 0.62);
  --diary-border: rgba(173, 190, 214, 0.26);
  --diary-glow: rgba(56, 189, 248, 0.3);
  --diary-shadow:
    18px 18px 44px rgba(148, 163, 184, 0.18),
    -18px -18px 42px rgba(255, 255, 255, 0.78),
    inset 0 1px 0 rgba(255, 255, 255, 0.72);
  --diary-inner-shadow:
    inset 7px 7px 18px rgba(148, 163, 184, 0.13),
    inset -7px -7px 18px rgba(255, 255, 255, 0.84);
  --diary-blue-shadow:
    0 12px 26px rgba(34, 81, 209, 0.18),
    0 0 22px rgba(14, 165, 233, 0.18);
  padding-top: 28px;
}

:global(:root[data-theme='dark']) .diary-stage {
  --diary-panel-bg: var(--panel-background);
  --diary-panel-strong: var(--panel-background-raised);
  --diary-panel-muted: var(--panel-background-soft);
  --diary-border: var(--border-soft);
  --diary-glow: var(--accent-border);
  --diary-shadow: var(--shadow-soft);
  --diary-inner-shadow: inset 0 0 0 1px var(--border-soft);
}

.diary-header {
  padding: 4px 2px 8px;
  margin-bottom: 22px;
}

.diary-kicker {
  color: var(--brand-blue);
  font-size: 0.72rem;
  font-weight: 900;
  letter-spacing: 0.2em;
}

.diary-header h1 {
  font-size: clamp(2.65rem, 4vw, 3.45rem);
  font-weight: 900;
}

.diary-date-chip,
.diary-status-chip {
  min-height: 32px;
  border-color: rgba(173, 190, 214, 0.24);
  background: var(--control-background);
  box-shadow:
    7px 7px 18px rgba(148, 163, 184, 0.12),
    -7px -7px 16px rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(16px);
}

.diary-status-chip {
  border-color: rgba(20, 184, 166, 0.22);
  background: color-mix(in srgb, var(--moss) 10%, var(--control-background));
  color: var(--moss);
}

.diary-status-chip.is-empty {
  border-color: var(--accent-border);
  background: var(--accent-soft);
  color: var(--brand-blue);
}

.diary-header-actions :deep(.el-button),
.reader-heading :deep(.el-button),
.empty-diary :deep(.el-button),
.icon-button,
.day-cell {
  will-change: transform, box-shadow;
}

.diary-header-actions :deep(.el-button),
.reader-heading :deep(.el-button),
.empty-diary :deep(.el-button) {
  min-height: 38px;
  border-radius: 8px;
  transition:
    transform 0.24s cubic-bezier(0.22, 1, 0.36, 1),
    border-color 0.24s ease,
    background 0.24s ease,
    box-shadow 0.24s ease,
    color 0.24s ease;
}

.diary-header-actions :deep(.el-button:hover),
.reader-heading :deep(.el-button:hover),
.empty-diary :deep(.el-button:hover),
.icon-button:hover {
  transform: scale(1.1);
}

.diary-header-actions :deep(.el-button:not(.el-button--primary)) {
  background: var(--control-background);
  box-shadow:
    7px 7px 18px rgba(148, 163, 184, 0.11),
    -7px -7px 18px rgba(255, 255, 255, 0.74);
}

.diary-header-actions :deep(.el-button:not(.el-button--primary):hover) {
  border-color: var(--accent-border);
  background: var(--accent-soft);
  box-shadow:
    0 14px 28px rgba(143, 63, 35, 0.1),
    0 0 24px rgba(77, 97, 68, 0.12);
}

.glow-action {
  position: relative;
  overflow: hidden;
  isolation: isolate;
  border: 1px solid var(--accent-border) !important;
  background:
    linear-gradient(135deg, var(--brand-blue) 0%, var(--brand-gold) 52%, var(--moss) 100%) !important;
  box-shadow:
    0 14px 30px rgba(143, 63, 35, 0.18),
    0 0 26px rgba(77, 97, 68, 0.14) !important;
}

.glow-action:hover {
  box-shadow:
    0 18px 36px rgba(143, 63, 35, 0.22),
    0 0 36px rgba(77, 97, 68, 0.18) !important;
}

.ripple-button > :not(.action-ripple) {
  position: relative;
  z-index: 1;
}

.action-ripple {
  position: absolute;
  z-index: 0;
  border-radius: 999px;
  pointer-events: none;
  background: radial-gradient(circle, color-mix(in srgb, var(--text-primary) 24%, transparent) 0%, var(--accent-soft) 42%, transparent 72%);
  transform: scale(0);
  animation: actionRipple 0.62s ease-out both;
}

.diary-calendar-panel,
.diary-reader {
  border: 1px solid rgba(255, 255, 255, 0.62);
  border-radius: 8px !important;
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.78), rgba(248, 251, 255, 0.56)) !important;
  box-shadow: var(--diary-shadow) !important;
  backdrop-filter: blur(24px) saturate(126%);
}

.diary-calendar-panel::before,
.diary-reader::before {
  inset: 0;
  height: auto;
  padding: 1px;
  border-radius: inherit;
  background: linear-gradient(135deg, color-mix(in srgb, var(--text-primary) 16%, transparent), var(--accent-soft), transparent);
  opacity: 0.9;
  pointer-events: none;
  -webkit-mask:
    linear-gradient(#000 0 0) content-box,
    linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
}

.month-toolbar {
  margin-bottom: 18px;
}

.month-toolbar strong {
  font-size: 1.12rem;
  font-weight: 900;
}

.icon-button {
  border-color: rgba(173, 190, 214, 0.26);
  background: var(--control-background);
  box-shadow:
    6px 6px 16px rgba(148, 163, 184, 0.12),
    -6px -6px 16px rgba(255, 255, 255, 0.78);
}

.icon-button:hover {
  border-color: rgba(14, 165, 233, 0.32);
  background: var(--control-hover-background);
  box-shadow:
    0 12px 24px rgba(34, 81, 209, 0.13),
    0 0 22px rgba(14, 165, 233, 0.18);
}

.calendar-overview {
  gap: 0;
  border-color: rgba(173, 190, 214, 0.18);
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.82), rgba(240, 249, 255, 0.54));
  box-shadow: var(--diary-inner-shadow);
}

.calendar-overview span {
  position: relative;
  padding: 13px 11px;
  background: transparent;
  perspective: 440px;
}

.calendar-overview span + span {
  border-left: 1px solid rgba(173, 190, 214, 0.2);
}

.calendar-overview strong {
  font-size: 1.08rem;
  letter-spacing: 0;
}

.flip-number {
  display: inline-block;
  transform-origin: 50% 100%;
  animation: statFlip 0.52s cubic-bezier(0.22, 1, 0.36, 1) both;
}

.weekday-row {
  margin-bottom: 10px;
}

.weekday-row span {
  font-size: 0.72rem;
  letter-spacing: 0;
}

.calendar-grid {
  gap: 8px;
}

.day-cell {
  min-height: 64px;
  border-color: rgba(255, 255, 255, 0);
  background: var(--panel-background-soft);
  box-shadow:
    5px 5px 13px rgba(148, 163, 184, 0.08),
    -5px -5px 13px rgba(255, 255, 255, 0.46);
  transform-origin: center;
}

.day-cell:hover {
  z-index: 3;
  transform: translateY(-3px) scale(1.1);
  border-color: rgba(14, 165, 233, 0.28);
  background: var(--control-hover-background);
  box-shadow:
    0 14px 28px rgba(34, 81, 209, 0.13),
    0 0 26px rgba(14, 165, 233, 0.18);
}

.day-cell span {
  position: relative;
  overflow: visible;
  background: color-mix(in srgb, var(--panel-background-soft) 46%, transparent);
  transition:
    background 0.24s ease,
    color 0.24s ease,
    box-shadow 0.24s ease;
}

.day-cell span::before {
  position: absolute;
  inset: -6px;
  border-radius: 999px;
  pointer-events: none;
  content: '';
}

.day-cell.is-today span {
  background: rgba(14, 165, 233, 0.1);
  color: var(--moss);
}

.day-cell.has-entry {
  border-color: rgba(14, 165, 233, 0.14);
  background: color-mix(in srgb, var(--moss) 8%, var(--control-background));
}

.day-cell.has-entry::after {
  right: 10px;
  bottom: 10px;
  width: 6px;
  height: 6px;
  background: #0ea5e9;
  box-shadow: 0 0 12px rgba(14, 165, 233, 0.5);
}

.day-cell.is-selected {
  border-color: rgba(34, 81, 209, 0.22);
  background:
    linear-gradient(145deg, rgba(240, 249, 255, 0.84), rgba(255, 255, 255, 0.62));
  box-shadow:
    0 16px 30px rgba(34, 81, 209, 0.16),
    0 0 28px rgba(14, 165, 233, 0.22);
}

.day-cell.is-selected span {
  background: var(--control-selected-background);
  color: var(--brand-blue);
  box-shadow:
    inset 2px 2px 7px rgba(148, 163, 184, 0.12),
    inset -2px -2px 7px rgba(255, 255, 255, 0.84);
}

.day-cell.is-selected span::before {
  border: 1px solid var(--accent-border);
  box-shadow:
    0 0 0 6px var(--accent-soft),
    0 0 22px rgba(77, 97, 68, 0.22);
  animation: selectedDayPulse 2.2s var(--motion-calm) infinite;
}

.day-cell.is-selected::after {
  background: #14b8a6;
  box-shadow: 0 0 12px rgba(20, 184, 166, 0.48);
}

.calendar-swap-enter-active,
.calendar-swap-leave-active {
  transition:
    opacity 0.3s ease,
    transform 0.32s cubic-bezier(0.22, 1, 0.36, 1),
    filter 0.3s ease;
}

.calendar-swap-enter-from {
  opacity: 0;
  filter: blur(3px);
  transform: translateY(9px) scale(0.985);
}

.calendar-swap-leave-to {
  opacity: 0;
  filter: blur(2px);
  transform: translateY(-8px) scale(0.99);
}

.calendar-swap-enter-active .day-cell {
  animation: dayFloatIn 0.34s cubic-bezier(0.22, 1, 0.36, 1) both;
}

.calendar-swap-enter-active .day-cell:nth-child(7n + 2),
.calendar-swap-enter-active .day-cell:nth-child(7n + 5) {
  animation-delay: 0.025s;
}

.calendar-swap-enter-active .day-cell:nth-child(7n + 3),
.calendar-swap-enter-active .day-cell:nth-child(7n + 6) {
  animation-delay: 0.05s;
}

.calendar-swap-enter-active .day-cell:nth-child(7n + 4),
.calendar-swap-enter-active .day-cell:nth-child(7n) {
  animation-delay: 0.075s;
}

.diary-reader {
  min-height: 620px;
  padding: clamp(26px, 3vw, 34px);
}

.reader-heading {
  align-items: center;
  padding-bottom: 24px;
}

.selected-date-mark {
  position: relative;
  width: 88px;
  height: 98px;
  border-color: rgba(255, 255, 255, 0.58);
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.82), rgba(240, 249, 255, 0.58));
  box-shadow:
    10px 10px 24px rgba(148, 163, 184, 0.14),
    -10px -10px 24px rgba(255, 255, 255, 0.76),
    inset 0 0 0 1px rgba(14, 165, 233, 0.1);
}

.selected-date-mark::after {
  position: absolute;
  inset: -5px;
  border: 1px solid rgba(14, 165, 233, 0.24);
  border-radius: inherit;
  box-shadow: 0 0 24px rgba(14, 165, 233, 0.18);
  pointer-events: none;
  content: '';
}

.selected-date-mark span {
  color: var(--ink-soft);
  font-size: 0.7rem;
  letter-spacing: 0;
}

.selected-date-mark strong {
  background: linear-gradient(135deg, var(--brand-navy), var(--brand-blue));
  color: transparent;
  -webkit-background-clip: text;
  background-clip: text;
}

.reader-heading h2 {
  font-size: clamp(1.8rem, 2.4vw, 2.35rem);
  font-weight: 900;
}

.reader-heading-copy > span {
  color: var(--ink-soft);
}

.date-mark-enter-active,
.date-mark-leave-active,
.date-copy-enter-active,
.date-copy-leave-active {
  transition:
    opacity 0.26s ease,
    transform 0.3s cubic-bezier(0.22, 1, 0.36, 1),
    filter 0.26s ease;
}

.date-mark-enter-from,
.date-copy-enter-from {
  opacity: 0;
  filter: blur(3px);
  transform: translateY(8px);
}

.date-mark-leave-to,
.date-copy-leave-to {
  opacity: 0;
  filter: blur(2px);
  transform: translateY(-6px);
}

.diary-meta-item,
.diary-note-title {
  border-color: rgba(173, 190, 214, 0.2);
  background: var(--panel-background-soft);
  box-shadow:
    5px 5px 14px rgba(148, 163, 184, 0.08),
    -5px -5px 14px rgba(255, 255, 255, 0.55);
}

.diary-viewer :deep(.toastui-editor-contents) {
  max-width: 920px;
}

.empty-diary {
  position: relative;
  min-height: 430px;
  border-color: rgba(14, 165, 233, 0.24);
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.58), rgba(240, 249, 255, 0.46)) !important;
  box-shadow: var(--diary-inner-shadow) !important;
}

.empty-diary::before {
  position: absolute;
  inset: 18px;
  border: 1px solid rgba(255, 255, 255, 0.58);
  border-radius: 8px;
  pointer-events: none;
  content: '';
}

.empty-diary-mark {
  position: relative;
  z-index: 1;
  border-color: rgba(255, 255, 255, 0.58);
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.84), rgba(240, 249, 255, 0.58));
  box-shadow:
    10px 10px 24px rgba(148, 163, 184, 0.13),
    -10px -10px 24px rgba(255, 255, 255, 0.74);
}

.empty-diary p,
.empty-diary h2,
.empty-diary :deep(.el-button) {
  position: relative;
  z-index: 1;
}

.typewriter-title {
  min-height: 1.3em;
}

.typewriter-title span {
  position: relative;
  display: inline-block;
  width: 0;
  max-width: 100%;
  overflow: hidden;
  white-space: nowrap;
  animation: typeDiaryEmpty 1.12s steps(9, end) 0.12s both;
}

.typewriter-title span::after {
  position: absolute;
  top: 12%;
  right: 0;
  width: 2px;
  height: 76%;
  border-radius: 999px;
  background: var(--brand-blue);
  box-shadow: 0 0 10px rgba(14, 165, 233, 0.36);
  content: '';
  animation: typeCaret 0.76s steps(1, end) infinite;
}

@keyframes actionRipple {
  0% {
    opacity: 0.68;
    transform: scale(0);
  }

  100% {
    opacity: 0;
    transform: scale(1);
  }
}

@keyframes statFlip {
  0% {
    opacity: 0;
    filter: blur(3px);
    transform: rotateX(-72deg) translateY(8px);
  }

  62% {
    opacity: 1;
    filter: blur(0);
    transform: rotateX(9deg) translateY(0);
  }

  100% {
    opacity: 1;
    filter: blur(0);
    transform: rotateX(0) translateY(0);
  }
}

@keyframes selectedDayPulse {
  0%,
  100% {
    opacity: 0.78;
    transform: scale(0.96);
  }

  50% {
    opacity: 1;
    transform: scale(1.08);
  }
}

@keyframes dayFloatIn {
  0% {
    opacity: 0;
    transform: translateY(7px) scale(0.97);
  }

  100% {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes typeDiaryEmpty {
  to {
    width: 9em;
  }
}

@keyframes typeCaret {
  0%,
  50% {
    opacity: 1;
  }

  51%,
  100% {
    opacity: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .flip-number,
  .day-cell.is-selected span::before,
  .calendar-swap-enter-active .day-cell,
  .typewriter-title span,
  .typewriter-title span::after,
  .action-ripple {
    animation: none;
  }

  .typewriter-title span {
    width: auto;
  }

  .diary-header-actions :deep(.el-button:hover),
  .reader-heading :deep(.el-button:hover),
  .empty-diary :deep(.el-button:hover),
  .icon-button:hover,
  .day-cell:hover {
    transform: none;
  }
}

@media (max-width: 820px) {
  .diary-header-actions :deep(.el-button:hover),
  .reader-heading :deep(.el-button:hover),
  .empty-diary :deep(.el-button:hover),
  .icon-button:hover {
    transform: scale(1.04);
  }

  .day-cell:hover {
    transform: translateY(-2px) scale(1.04);
  }
}

@media (max-width: 560px) {
  .diary-stage {
    padding-top: 20px;
  }

  .calendar-overview span + span {
    border-top: 1px solid rgba(173, 190, 214, 0.2);
    border-left: none;
  }

  .selected-date-mark {
    width: 72px;
    height: 82px;
  }

  .typewriter-title span {
    animation-name: typeDiaryEmptyMobile;
  }
}

@keyframes typeDiaryEmptyMobile {
  to {
    width: min(9em, 100%);
  }
}

.diary-page {
  background:
    linear-gradient(180deg, #f8fafc 0%, #f4f7fb 58%, #f6f8fb 100%),
    radial-gradient(circle at 78% 8%, rgba(37, 99, 235, 0.045), transparent 30%);
}

.diary-stage {
  --diary-panel-bg: rgba(255, 255, 255, 0.86);
  --diary-panel-strong: rgba(255, 255, 255, 0.92);
  --diary-panel-muted: rgba(248, 250, 252, 0.78);
  --diary-border: rgba(148, 163, 184, 0.18);
  --diary-shadow: 0 22px 56px rgba(15, 23, 42, 0.075);
  --diary-inner-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.78);
  --diary-blue-shadow: 0 12px 24px rgba(34, 81, 209, 0.18);
  width: min(1420px, 100%);
  padding-top: 30px;
}

.diary-header {
  margin-bottom: 20px;
}

.diary-kicker {
  color: var(--brand-blue);
  font-size: 0.72rem;
  letter-spacing: 0.18em;
}

.diary-header h1 {
  font-size: clamp(2.75rem, 4.1vw, 3.55rem);
  line-height: 0.98;
}

.diary-date-chip,
.diary-status-chip {
  min-height: 34px;
  border-color: rgba(148, 163, 184, 0.18);
  background: var(--control-background);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.04);
}

.diary-status-chip.is-empty {
  border-color: rgba(14, 165, 233, 0.22);
  background: var(--control-selected-background);
}

.diary-layout {
  grid-template-columns: minmax(320px, 392px) minmax(0, 1fr);
  gap: 24px;
}

.diary-calendar-panel,
.diary-reader {
  border-color: rgba(203, 213, 225, 0.54);
  background: var(--diary-panel-bg) !important;
  box-shadow: var(--diary-shadow) !important;
  backdrop-filter: blur(18px) saturate(112%);
}

.diary-calendar-panel::before,
.diary-reader::before {
  opacity: 0.32;
  background: var(--quote-background);
}

.diary-calendar-panel {
  padding: 24px 24px 22px;
}

.month-toolbar {
  grid-template-columns: 38px minmax(0, 1fr) 38px;
  margin-bottom: 18px;
}

.month-toolbar strong {
  font-size: 1.1rem;
  font-weight: 850;
}

.icon-button {
  width: 38px;
  height: 38px;
  border-color: rgba(148, 163, 184, 0.18);
  background: var(--control-background);
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.045);
}

.icon-button:hover {
  transform: translateY(-1px) scale(1.02);
  border-color: rgba(37, 99, 235, 0.24);
  background: var(--control-hover-background);
  box-shadow: 0 12px 24px rgba(34, 81, 209, 0.1);
}

.calendar-overview {
  margin-bottom: 22px;
  border-color: rgba(148, 163, 184, 0.14);
  background: var(--panel-background-soft);
  box-shadow: var(--inset-highlight);
}

.calendar-overview span {
  min-height: 58px;
  padding: 12px 14px;
}

.calendar-overview span + span {
  border-left-color: rgba(148, 163, 184, 0.14);
}

.calendar-overview strong {
  color: var(--text-primary);
  font-size: 1.05rem;
  font-weight: 850;
}

.calendar-overview em {
  font-size: 0.72rem;
  font-weight: 700;
}

.weekday-row {
  margin-bottom: 8px;
}

.weekday-row span {
  color: var(--text-muted);
  font-size: 0.72rem;
}

.calendar-grid {
  gap: 8px;
}

.day-cell {
  min-height: 58px;
  padding: 8px 9px;
  border-color: transparent;
  background: var(--panel-background-soft);
  box-shadow: none;
}

.day-cell:hover {
  transform: translateY(-2px) scale(1.025);
  border-color: rgba(37, 99, 235, 0.16);
  background: var(--control-hover-background);
  box-shadow: 0 10px 24px rgba(34, 81, 209, 0.08);
}

.day-cell span {
  width: 26px;
  height: 26px;
  color: var(--text-primary);
  font-weight: 850;
}

.day-cell small {
  color: var(--text-muted);
  font-size: 0.68rem;
}

.day-cell.is-muted {
  opacity: 0.42;
}

.day-cell.is-today span {
  background: rgba(37, 99, 235, 0.08);
  color: var(--brand-blue);
}

.day-cell.has-entry {
  border-color: rgba(37, 99, 235, 0.12);
  background: rgba(239, 246, 255, 0.58);
}

.day-cell.has-entry::after {
  width: 5px;
  height: 5px;
  background: #0ea5e9;
  box-shadow: none;
}

.day-cell.is-selected {
  border-color: rgba(37, 99, 235, 0.26);
  background: rgba(239, 246, 255, 0.9);
  box-shadow: 0 12px 28px rgba(37, 99, 235, 0.12);
}

.day-cell.is-selected span {
  background: var(--control-selected-background);
  color: var(--brand-blue);
  box-shadow: 0 0 0 1px rgba(37, 99, 235, 0.18);
}

.day-cell.is-selected span::before {
  inset: -4px;
  border-color: rgba(37, 99, 235, 0.28);
  box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.045);
}

.diary-reader {
  min-height: 620px;
  padding: 28px 32px 32px;
}

.reader-heading {
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 18px;
  margin-bottom: 22px;
  padding-bottom: 22px;
  border-bottom-color: rgba(148, 163, 184, 0.18);
}

.selected-date-mark {
  width: 76px;
  height: 84px;
  border-color: rgba(148, 163, 184, 0.2);
  background: var(--panel-background-raised);
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.06);
}

.selected-date-mark::after {
  inset: -3px;
  border-color: rgba(37, 99, 235, 0.16);
  box-shadow: none;
}

.selected-date-mark span {
  width: 100%;
  overflow: hidden;
  color: var(--text-muted);
  font-size: 0.68rem;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.selected-date-mark strong {
  font-size: 2.6rem;
  line-height: 1;
}

.reader-heading p {
  font-size: 0.72rem;
  letter-spacing: 0.1em;
}

.reader-heading h2 {
  font-size: clamp(1.65rem, 2.2vw, 2.15rem);
  font-weight: 850;
}

.reader-heading-copy > span {
  font-size: 0.94rem;
}

.diary-header-actions :deep(.el-button),
.reader-heading :deep(.el-button),
.empty-diary :deep(.el-button) {
  border-radius: 8px;
}

.diary-header-actions :deep(.el-button:hover),
.reader-heading :deep(.el-button:hover),
.empty-diary :deep(.el-button:hover) {
  transform: translateY(-1px) scale(1.025);
}

.glow-action {
  background: linear-gradient(135deg, var(--brand-blue) 0%, var(--brand-gold) 100%) !important;
  box-shadow: 0 14px 26px rgba(143, 63, 35, 0.18) !important;
}

.glow-action:hover {
  box-shadow: 0 16px 30px rgba(143, 63, 35, 0.22) !important;
}

.empty-diary {
  min-height: 412px;
  padding: 42px 24px;
  border: 1px dashed rgba(148, 163, 184, 0.34);
  background: var(--panel-background-soft) !important;
  box-shadow: var(--inset-highlight) !important;
}

.empty-diary::before {
  display: none;
}

.empty-diary-mark {
  width: 78px;
  height: 78px;
  margin-bottom: 8px;
  border-color: rgba(148, 163, 184, 0.16);
  background: var(--overlay-background);
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.055);
}

.empty-diary-mark strong {
  font-size: 2.2rem;
}

.empty-diary h2 {
  font-size: clamp(1.55rem, 2.4vw, 2rem);
  font-weight: 850;
}

.typewriter-title span {
  width: auto;
  animation: none;
}

.typewriter-title span::after {
  display: none;
}

@media (max-width: 820px) {
  .diary-header-actions :deep(.el-button:hover),
  .reader-heading :deep(.el-button:hover),
  .empty-diary :deep(.el-button:hover),
  .icon-button:hover,
  .day-cell:hover {
    transform: translateY(-1px) scale(1.015);
  }
}

.day-cell.is-selected {
  border-color: rgba(37, 99, 235, 0.18);
  background: var(--control-selected-background);
  box-shadow:
    inset 0 0 0 1px rgba(255, 255, 255, 0.74),
    0 10px 20px rgba(37, 99, 235, 0.08);
}

.day-cell.is-selected:hover {
  transform: translateY(-1px) scale(1.018);
  box-shadow:
    inset 0 0 0 1px rgba(255, 255, 255, 0.82),
    0 12px 22px rgba(37, 99, 235, 0.1);
}

.day-cell.is-selected span {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background: var(--brand-blue);
  color: var(--text-on-accent);
  box-shadow: 0 8px 16px rgba(34, 81, 209, 0.22);
}

.day-cell.is-selected span::before,
.day-cell.is-selected::after {
  display: none;
}

.day-cell.is-selected small {
  color: var(--text-muted);
}

/* Screenshot restoration: warm diary workspace */
.diary-page {
  min-height: 100vh;
  min-height: 100svh;
  background: var(--app-background);
}

.diary-stage {
  width: auto;
  max-width: none;
  margin: 0;
  padding: 42px 48px 42px 58px;
}

.diary-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 28px;
  margin-bottom: 32px;
  padding: 0;
}

.diary-kicker {
  margin: 0 0 10px;
  color: var(--brand-blue);
  font-size: 0.86rem;
  font-weight: 850;
  letter-spacing: 0.24em;
  text-transform: uppercase;
}

.diary-title-line {
  display: flex;
  align-items: center;
  gap: 18px;
  flex-wrap: wrap;
}

.diary-header h1 {
  margin: 0;
  color: var(--text-primary);
  font-size: clamp(3.6rem, 5.3vw, 5.25rem);
  font-weight: 900;
  line-height: 0.92;
}

.diary-date-chip,
.diary-status-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 44px;
  padding: 0 18px;
  border: 1px solid var(--border-soft);
  border-radius: 9px;
  background: var(--control-background);
  color: var(--text-secondary);
  font-size: 0.95rem;
  font-weight: 750;
  box-shadow: 0 10px 22px rgba(99, 69, 43, 0.045);
  backdrop-filter: none;
}

.diary-date-chip .el-icon,
.diary-status-chip .el-icon {
  color: var(--brand-blue);
}

.diary-status-chip,
.diary-status-chip.is-empty {
  border-color: rgba(171, 91, 58, 0.16);
  background: var(--control-selected-background);
  color: var(--brand-blue);
}

.diary-header-actions {
  display: flex;
  align-items: center;
  gap: 18px;
  padding-top: 36px;
}

.diary-header-actions :deep(.el-button),
.reader-heading :deep(.el-button),
.empty-diary :deep(.el-button) {
  min-height: 56px;
  padding-inline: 24px;
  border: 1px solid var(--border-soft);
  border-radius: 10px;
  background: var(--control-background);
  color: var(--text-primary);
  font-size: 0.98rem;
  font-weight: 780;
  box-shadow: 0 12px 24px rgba(99, 69, 43, 0.06);
  transition:
    transform 0.2s var(--motion-snappy),
    box-shadow 0.2s var(--motion-calm),
    background 0.2s var(--motion-calm);
}

.diary-header-actions :deep(.el-button:hover),
.reader-heading :deep(.el-button:hover),
.empty-diary :deep(.el-button:hover) {
  transform: translateY(-1px);
}

.glow-action {
  border-color: rgba(150, 70, 38, 0.22) !important;
  background: linear-gradient(180deg, #c46c43, #a84528) !important;
  color: var(--text-on-accent) !important;
  box-shadow: 0 16px 28px rgba(150, 70, 38, 0.2) !important;
}

.diary-layout {
  display: grid;
  grid-template-columns: minmax(360px, 456px) minmax(0, 1fr);
  gap: 24px;
  align-items: stretch;
}

.diary-calendar-panel,
.diary-reader {
  border: 1px solid var(--border-soft);
  border-radius: 12px !important;
  background: var(--panel-background) !important;
  box-shadow: var(--shadow-soft), var(--inset-highlight) !important;
  backdrop-filter: none;
}

.diary-calendar-panel::before,
.diary-reader::before {
  display: none;
}

.diary-calendar-panel {
  padding: 30px 28px 28px;
}

.month-toolbar {
  display: grid;
  grid-template-columns: 48px minmax(0, 1fr) 48px;
  align-items: center;
  gap: 18px;
  margin-bottom: 22px;
}

.month-toolbar strong {
  color: var(--text-primary);
  font-size: 1.55rem;
  font-weight: 900;
  text-align: center;
}

.icon-button {
  width: 48px;
  height: 48px;
  border: 1px solid var(--border-soft);
  border-radius: 10px;
  background: var(--control-background);
  color: var(--text-primary);
  box-shadow: none;
}

.calendar-overview {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-bottom: 26px;
  border: 1px solid var(--border-soft);
  border-radius: 9px;
  background: var(--panel-background-soft);
  box-shadow: none;
}

.calendar-overview span {
  display: grid;
  gap: 6px;
  min-height: 82px;
  padding: 16px 20px;
}

.calendar-overview span + span {
  border-left: 1px solid var(--divider);
}

.calendar-overview strong {
  color: var(--text-primary);
  font-size: 1.65rem;
  font-weight: 900;
}

.calendar-overview em {
  color: var(--text-muted);
  font-size: 0.82rem;
  font-style: normal;
  font-weight: 700;
}

.weekday-row {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  margin: 0 0 14px;
}

.weekday-row span {
  color: var(--text-muted);
  font-size: 0.86rem;
  font-weight: 850;
  text-align: center;
}

.calendar-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 12px 10px;
}

.day-cell {
  display: grid;
  place-items: center;
  min-height: 64px;
  padding: 6px;
  border: 1px solid transparent;
  border-radius: 10px;
  background: transparent;
  color: var(--text-primary);
  box-shadow: none;
}

.day-cell span {
  width: auto;
  height: auto;
  min-width: 30px;
  color: var(--text-primary);
  font-size: 1.05rem;
  font-weight: 900;
  line-height: 1;
}

.day-cell small {
  margin-top: 5px;
  color: var(--moss);
  font-size: 0.7rem;
  font-weight: 750;
}

.day-cell.is-muted span,
.day-cell.is-muted small {
  color: var(--text-muted);
}

.day-cell.is-today {
  border-color: rgba(91, 119, 78, 0.14);
  background: rgba(91, 119, 78, 0.08);
}

.day-cell.has-entry {
  background: rgba(91, 119, 78, 0.08);
}

.day-cell.has-entry::after {
  display: none;
}

.day-cell.is-selected,
.day-cell.is-selected:hover {
  border-color: rgba(150, 70, 38, 0.2);
  background: linear-gradient(180deg, #c46c43, #a84528);
  color: var(--text-on-accent);
  box-shadow: 0 14px 24px rgba(150, 70, 38, 0.22);
  transform: none;
}

.day-cell.is-selected span {
  width: auto;
  height: auto;
  min-width: 30px;
  border-radius: 0;
  background: transparent;
  color: var(--text-on-accent);
  box-shadow: none;
}

.day-cell.is-selected small {
  color: var(--text-on-accent);
}

.day-cell.is-selected span::before,
.day-cell.is-selected::after {
  display: none;
}

.diary-reader {
  min-height: 724px;
  padding: 32px;
}

.reader-heading {
  display: grid;
  grid-template-columns: 104px minmax(0, 1fr) auto;
  gap: 24px;
  align-items: center;
  margin-bottom: 26px;
  padding-bottom: 24px;
  border-bottom: none;
}

.selected-date-mark {
  width: 104px;
  height: 116px;
  border: 1px solid var(--border-soft);
  border-radius: 10px;
  background: var(--panel-background-raised);
  box-shadow: var(--shadow-subtle);
}

.selected-date-mark::after {
  display: none;
}

.selected-date-mark span {
  color: var(--text-muted);
  font-size: 0.74rem;
  font-weight: 850;
}

.selected-date-mark strong {
  color: var(--brand-blue);
  font-size: 3.3rem;
  font-weight: 900;
  line-height: 0.95;
  -webkit-text-fill-color: var(--brand-blue);
}

.reader-heading p {
  margin: 0 0 8px;
  color: var(--brand-blue);
  font-size: 0.74rem;
  font-weight: 900;
  letter-spacing: 0.22em;
  text-transform: uppercase;
}

.reader-heading h2 {
  margin: 0;
  color: var(--text-primary);
  font-size: clamp(2rem, 2.7vw, 2.6rem);
  font-weight: 900;
}

.reader-heading-copy > span {
  display: block;
  margin-top: 8px;
  color: var(--text-muted);
  font-size: 1rem;
  font-weight: 700;
}

.reader-heading :deep(.el-button) {
  min-width: 142px;
}

.empty-diary {
  display: grid;
  justify-items: center;
  align-content: center;
  min-height: 516px;
  padding: 44px 28px;
  border: 1px dashed rgba(171, 91, 58, 0.24);
  border-radius: 10px;
  background: var(--panel-background-soft) !important;
  box-shadow: none !important;
}

.empty-diary::before {
  display: none;
}

.empty-diary-illustration {
  display: block;
  width: min(320px, 78%);
  height: auto;
  margin: 0 auto 18px;
  object-fit: contain;
  filter: drop-shadow(0 12px 22px rgba(99, 69, 43, 0.08));
}

.empty-diary-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: auto;
  height: 40px;
  margin: 0 0 18px;
  padding: 0 22px;
  border: 1px solid var(--border-soft);
  border-radius: 10px;
  background: var(--control-background);
  color: var(--text-secondary);
  box-shadow: var(--shadow-subtle);
}

.empty-diary-mark span {
  color: var(--text-secondary);
  font-size: 1rem;
  font-weight: 780;
}

.empty-diary > p {
  display: none;
}

.empty-diary h2 {
  margin: 0 0 26px;
  color: var(--text-primary);
  font-size: clamp(2rem, 3.2vw, 2.8rem);
  font-weight: 900;
}

.typewriter-title span {
  width: auto;
  animation: none;
}

.typewriter-title span::after {
  display: none;
}

.diary-header-actions :deep(.el-button:not(.el-button--primary)) {
  box-shadow: var(--shadow-subtle);
}

@media (max-width: 1320px) {
  .diary-stage {
    padding: 32px 30px;
  }

  .diary-layout {
    grid-template-columns: minmax(340px, 420px) minmax(0, 1fr);
  }
}

@media (max-width: 1080px) {
  .diary-header {
    display: grid;
  }

  .diary-header-actions {
    padding-top: 0;
  }

  .diary-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .diary-stage {
    padding: 24px 16px;
  }

  .diary-header h1 {
    font-size: 3.2rem;
  }

  .diary-header-actions {
    flex-direction: column;
    align-items: stretch;
  }

  .diary-header-actions :deep(.el-button) {
    width: 100%;
  }

  .calendar-overview {
    grid-template-columns: 1fr;
  }

  .calendar-overview span + span {
    border-top: 1px solid rgba(123, 83, 58, 0.12);
    border-left: none;
  }

  .reader-heading {
    grid-template-columns: 1fr;
  }

  .empty-diary {
    min-height: 420px;
  }
}
</style>
