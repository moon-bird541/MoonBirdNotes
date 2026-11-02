<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Icon } from '@iconify/vue'

import WorkspaceShell from '../components/WorkspaceShell.vue'
import api from '../services/api'
import {
  TASK_SEGMENTS,
  TASK_SORT_OPTIONS,
  TASK_URGENCY_OPTIONS,
  formatTaskRange,
  fromLocalInputValue,
  groupTasksBySegment,
  resolveUrgencyLabel,
  resolveUrgencyTone,
  toLocalInputValue,
} from '../utils/tasks'

const route = useRoute()

const loading = ref(false)
const tasks = ref([])
const activeTab = ref('active')
const sortKey = ref('urgency')
const searchKeyword = ref('')
const saving = ref(false)
const dialogVisible = ref(false)
const editingId = ref(null)

const completionDialogVisible = ref(false)
const completionTarget = ref(null)
const completionSummary = ref('')

// 关联笔记候选：普通笔记与日记分开取，前端分组展示。
const noteOptions = ref([])
const diaryOptions = ref([])
const noteOptionsLoading = ref(false)
const deletedLinkOption = ref(null)

const form = reactive({
  title: '',
  startInput: '',
  endInput: '',
  urgency: null,
  linkedNoteKey: '',
  summary: '',
  isCompleted: false,
})

const isEditing = computed(() => editingId.value !== null)
const segmentGroups = computed(() => groupTasksBySegment(tasks.value))
const hasTasks = computed(() => tasks.value.length > 0)
const dialogTitle = computed(() => (isEditing.value ? '编辑任务' : '新建任务'))

const normalizeKey = (type, id) => (id ? `${type}:${id}` : '')

const resetForm = () => {
  form.title = ''
  form.startInput = ''
  form.endInput = ''
  form.urgency = null
  form.linkedNoteKey = ''
  form.summary = ''
  form.isCompleted = false
  editingId.value = null
  deletedLinkOption.value = null
}

const fetchTasks = async () => {
  loading.value = true

  try {
    const params = { scope: activeTab.value === 'completed' ? 'completed' : 'active' }

    if (activeTab.value === 'active') {
      params.sort = sortKey.value
    }

    if (searchKeyword.value.trim()) {
      params.search = searchKeyword.value.trim()
    }

    const { data } = await api.get('/tasks/', { params, page_size: 100 })
    tasks.value = data.results || []
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '获取任务失败，请稍后重试。')
  } finally {
    loading.value = false
  }
}

const fetchLinkOptions = async () => {
  noteOptionsLoading.value = true

  try {
    const [notesResponse, diariesResponse] = await Promise.all([
      api.get('/notes/', { params: { page_size: 50 } }),
      api.get('/notes/diaries/'),
    ])

    noteOptions.value = (notesResponse.data.results || []).map((note) => ({
      value: normalizeKey('note', note.id),
      label: note.title,
      type: 'note',
      id: note.id,
    }))

    diaryOptions.value = (diariesResponse.data || []).map((entry) => ({
      value: normalizeKey('diary', entry.note_id),
      label: `${entry.diary_date} ${entry.title || '日记'}`,
      type: 'diary',
      id: entry.note_id,
    }))
  } catch {
    // 关联是可选能力，拉不到候选不影响任务本身的增删改。
    noteOptions.value = []
    diaryOptions.value = []
  } finally {
    noteOptionsLoading.value = false
  }
}

const openCreateDialog = () => {
  resetForm()

  const now = new Date()
  const oneHourLater = new Date(now.getTime() + 60 * 60 * 1000)
  form.startInput = toLocalInputValue(now)
  form.endInput = toLocalInputValue(oneHourLater)

  dialogVisible.value = true
  fetchLinkOptions()
}

const openEditDialog = (task) => {
  resetForm()
  editingId.value = task.id
  form.title = task.title
  form.startInput = toLocalInputValue(task.start_at)
  form.endInput = toLocalInputValue(task.end_at)
  form.urgency = task.urgency
  form.summary = task.summary || ''
  form.isCompleted = task.is_completed
  form.linkedNoteKey = task.linked_note
    ? normalizeKey(task.linked_note.type, task.linked_note.id)
    : ''

  // 关联的笔记被软删除后不会出现在候选列表里。这里单独记一份占位信息，
  // 由 deletedLinkOption 渲染，避免下拉框把 note:123 这种内部 key 暴露给用户。
  deletedLinkOption.value = task.linked_note?.is_deleted
    ? {
      value: form.linkedNoteKey,
      label: `${task.linked_note.title}（已删除）`,
    }
    : null

  dialogVisible.value = true
  fetchLinkOptions()
}

const buildPayload = () => {
  const payload = {
    title: form.title.trim(),
    start_at: fromLocalInputValue(form.startInput),
    end_at: fromLocalInputValue(form.endInput),
    urgency: form.urgency,
    summary: form.summary,
    is_completed: form.isCompleted,
  }

  if (form.linkedNoteKey) {
    payload.linked_note_id = Number(form.linkedNoteKey.split(':')[1])
  } else {
    payload.linked_note_id = null
  }

  return payload
}

const submitForm = async () => {
  if (!form.title.trim()) {
    ElMessage.warning('请填写任务标题。')
    return
  }

  if (!form.startInput || !form.endInput) {
    ElMessage.warning('请填写开始时间和结束时间。')
    return
  }

  if (!form.urgency) {
    ElMessage.warning('请选择紧急程度。')
    return
  }

  const payload = buildPayload()

  if (new Date(payload.end_at) < new Date(payload.start_at)) {
    ElMessage.warning('结束时间不能早于开始时间。')
    return
  }

  saving.value = true

  try {
    if (isEditing.value) {
      await api.patch(`/tasks/${editingId.value}/`, payload)
      ElMessage.success('任务已更新。')
    } else {
      await api.post('/tasks/', payload)
      ElMessage.success('任务已创建。')
    }

    dialogVisible.value = false
    resetForm()
    fetchTasks()
  } catch (error) {
    const data = error.response?.data
    const detail =
      data?.end_at?.[0] || data?.title?.[0] || data?.urgency?.[0] || data?.linked_note_id?.[0] || data?.detail || '保存失败，请稍后重试。'
    ElMessage.error(detail)
  } finally {
    saving.value = false
  }
}

const requestComplete = (task) => {
  if (task.is_completed) {
    toggleCompletion(task, null)
    return
  }

  completionTarget.value = task
  completionSummary.value = ''
  completionDialogVisible.value = true
}

const toggleCompletion = async (task, summary) => {
  try {
    const payload = summary === null || summary === undefined ? {} : { summary }
    const { data } = await api.post(`/tasks/${task.id}/complete/`, payload)

    ElMessage.success(data.is_completed ? '任务已完成。' : '任务已恢复。')
    fetchTasks()
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '操作失败，请稍后重试。')
  }
}

const confirmComplete = async (withSummary) => {
  const task = completionTarget.value
  completionDialogVisible.value = false

  if (!task) {
    return
  }

  await toggleCompletion(task, withSummary ? completionSummary.value : '')
}

const removeTask = async (task) => {
  try {
    await ElMessageBox.confirm(
      `确定删除「${task.title}」？删除后无法恢复。`,
      '删除任务',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        confirmButtonClass: 'danger-confirm-button',
        customClass: 'beautiful-confirm-box',
      }
    )
  } catch {
    return
  }

  try {
    await api.delete(`/tasks/${task.id}/`)
    ElMessage.success('任务已删除。')
    fetchTasks()
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '删除失败，请稍后重试。')
  }
}

const linkedNoteLabel = (task) => {
  const linked = task.linked_note

  if (!linked) {
    return ''
  }

  if (linked.is_deleted) {
    return `${linked.type === 'diary' ? '日记' : '笔记'}已删除`
  }

  return linked.diary_date ? `日记 · ${linked.diary_date}` : `笔记 · ${linked.title}`
}

watch([activeTab, sortKey], () => {
  fetchTasks()
})

let searchTimer = null
const scheduleSearch = () => {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(fetchTasks, 240)
}
watch(searchKeyword, scheduleSearch)

onMounted(async () => {
  await fetchTasks()

  const focusId = Number(route.query.task)
  if (focusId) {
    const target = tasks.value.find((task) => task.id === focusId)
    if (target) {
      openEditDialog(target)
    }
  }
})
</script>

<template>
  <main class="tasks-page page-shell">
    <WorkspaceShell>
      <section class="tasks-stage">
        <header class="tasks-header">
          <div class="header-copy">
            <p class="tasks-brand">Tasks</p>
            <h1>任务</h1>
            <p class="tasks-subtitle">
              24 小时内的事放待办，跨多天的事放项目。时间一到就不再装睡。
            </p>
          </div>

          <div class="header-actions">
            <el-button class="cta-button" type="primary" size="large" @click="openCreateDialog">
              <Icon icon="ph:plus" />
              新建任务
            </el-button>
          </div>
        </header>

        <section class="tasks-board">
          <div class="board-head">
            <div class="board-tabs" role="tablist">
              <button
                type="button"
                class="board-tab"
                :class="{ 'is-active': activeTab === 'active' }"
                @click="activeTab = 'active'"
              >
                未完成
              </button>
              <button
                type="button"
                class="board-tab"
                :class="{ 'is-active': activeTab === 'completed' }"
                @click="activeTab = 'completed'"
              >
                已完成
              </button>
            </div>

            <div class="board-tools">
              <el-input
                v-model="searchKeyword"
                class="task-search"
                clearable
                placeholder="搜任务标题"
              >
                <template #prefix>
                  <Icon icon="ph:magnifying-glass" />
                </template>
              </el-input>

              <el-select
                v-if="activeTab === 'active'"
                v-model="sortKey"
                class="sort-select"
                placeholder="排序"
              >
                <el-option
                  v-for="option in TASK_SORT_OPTIONS"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
            </div>
          </div>

          <div v-loading="loading" class="task-list-shell">
            <template v-if="activeTab === 'active'">
              <section
                v-for="segment in TASK_SEGMENTS"
                :key="segment.value"
                class="segment-block"
              >
                <div class="segment-head">
                  <h2>{{ segment.label }}</h2>
                  <span>{{ segment.hint }} · {{ segmentGroups[segment.value].length }} 条</span>
                </div>

                <div v-if="segmentGroups[segment.value].length" class="task-list">
                  <article
                    v-for="task in segmentGroups[segment.value]"
                    :key="task.id"
                    class="task-card"
                    :class="[`is-${resolveUrgencyTone(task.urgency)}`, { 'is-overdue': task.is_overdue, 'has-no-time': !task.has_time }]"
                  >
                    <button
                      type="button"
                      class="task-check"
                      :aria-label="'标记完成'"
                      @click="requestComplete(task)"
                    >
                      <Icon icon="ph:circle" />
                    </button>

                    <div class="task-main" @click="openEditDialog(task)">
                      <h3>{{ task.title }}</h3>
                      <p class="task-meta">
                        <span class="task-range">{{ formatTaskRange(task) }}</span>
                        <span class="urgency-pill">{{ resolveUrgencyLabel(task) }}</span>
                        <span v-if="task.is_overdue" class="overdue-pill">已逾期</span>
                        <span v-if="!task.has_time" class="undated-pill">时间未定</span>
                      </p>
                      <p v-if="task.linked_note" class="task-link" :class="{ 'is-deleted': task.linked_note.is_deleted }">
                        <Icon icon="ph:link-simple" />
                        {{ linkedNoteLabel(task) }}
                      </p>
                    </div>

                    <div class="task-actions">
                      <button type="button" aria-label="编辑任务" @click="openEditDialog(task)">
                        <Icon icon="ph:pencil-line" />
                      </button>
                      <button type="button" aria-label="删除任务" @click="removeTask(task)">
                        <Icon icon="ph:trash" />
                      </button>
                    </div>
                  </article>
                </div>

                <p v-else class="segment-empty">这一段还是空的。</p>
              </section>
            </template>

            <template v-else>
              <div v-if="tasks.length" class="task-list">
                <article
                  v-for="task in tasks"
                  :key="task.id"
                  class="task-card is-done"
                  :class="[`is-${resolveUrgencyTone(task.urgency)}`]"
                >
                  <button
                    type="button"
                    class="task-check is-checked"
                    aria-label="取消完成"
                    @click="requestComplete(task)"
                  >
                    <Icon icon="ph:check-circle" />
                  </button>

                  <div class="task-main" @click="openEditDialog(task)">
                    <h3>{{ task.title }}</h3>
                    <p class="task-meta">
                      <span class="task-range">{{ formatTaskRange(task) }}</span>
                      <span class="urgency-pill">{{ resolveUrgencyLabel(task) }}</span>
                    </p>
                    <p v-if="task.summary" class="task-summary">{{ task.summary }}</p>
                    <p v-else class="task-summary is-empty">没写总结。</p>
                  </div>

                  <div class="task-actions">
                    <button type="button" aria-label="编辑任务" @click="openEditDialog(task)">
                      <Icon icon="ph:pencil-line" />
                    </button>
                    <button type="button" aria-label="删除任务" @click="removeTask(task)">
                      <Icon icon="ph:trash" />
                    </button>
                  </div>
                </article>
              </div>

              <div v-else-if="!hasTasks" class="segment-empty">还没有完成的任务。</div>
            </template>
          </div>
        </section>
      </section>
    </WorkspaceShell>

    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="min(92vw, 560px)"
      class="task-dialog"
      @closed="resetForm"
    >
      <div class="task-form">
        <label class="form-row">
          <span>标题</span>
          <el-input v-model="form.title" maxlength="100" show-word-limit placeholder="这件事叫什么" />
        </label>

        <div class="form-grid">
          <label class="form-row">
            <span>开始时间</span>
            <el-date-picker
              v-model="form.startInput"
              type="datetime"
              placeholder="选择开始时间"
              format="YYYY-MM-DD HH:mm"
              value-format="YYYY-MM-DDTHH:mm"
            />
          </label>

          <label class="form-row">
            <span>结束时间</span>
            <el-date-picker
              v-model="form.endInput"
              type="datetime"
              placeholder="选择结束时间"
              format="YYYY-MM-DD HH:mm"
              value-format="YYYY-MM-DDTHH:mm"
            />
          </label>
        </div>

        <label class="form-row">
          <span>紧急程度</span>
          <el-select v-model="form.urgency" placeholder="必须选一个">
            <el-option
              v-for="option in TASK_URGENCY_OPTIONS"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </label>

        <label class="form-row">
          <span>关联笔记（可选）</span>
          <el-select
            v-model="form.linkedNoteKey"
            filterable
            clearable
            :loading="noteOptionsLoading"
            placeholder="不关联"
          >
            <el-option-group label="日记">
              <el-option
                v-for="option in diaryOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-option-group>
            <el-option-group label="笔记">
              <el-option
                v-for="option in noteOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-option-group>
            <el-option
              v-if="deletedLinkOption"
              :key="deletedLinkOption.value"
              :label="deletedLinkOption.label"
              :value="deletedLinkOption.value"
            />
          </el-select>
        </label>

        <label class="form-row">
          <span>总结</span>
          <el-input
            v-model="form.summary"
            type="textarea"
            :rows="3"
            placeholder="做完再写，记结果和收获"
          />
        </label>
      </div>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitForm">
          {{ isEditing ? '保存' : '创建' }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="completionDialogVisible"
      title="写一句复盘"
      width="min(92vw, 460px)"
      class="task-complete-dialog"
    >
      <p class="complete-hint">可以跳过，之后在「已完成」里补写。</p>
      <el-input
        v-model="completionSummary"
        type="textarea"
        :rows="3"
        placeholder="这件事的结果是什么"
      />

      <template #footer>
        <el-button @click="confirmComplete(false)">跳过</el-button>
        <el-button type="primary" @click="confirmComplete(true)">保存并完成</el-button>
      </template>
    </el-dialog>
  </main>
</template>

<style scoped>
.tasks-page {
  padding: 20px;
}

.tasks-stage {
  margin-top: 20px;
}

.tasks-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
}

.header-copy {
  max-width: 640px;
}

.tasks-brand {
  margin: 0 0 12px;
  color: var(--brand-blue);
  font-size: 0.84rem;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.tasks-header h1 {
  margin: 0;
  color: var(--brand-navy);
  font-size: clamp(2.6rem, 5vw, 4rem);
  line-height: 0.98;
}

.tasks-subtitle {
  margin: 14px 0 0;
  color: var(--text-muted);
  font-size: 0.95rem;
  line-height: 1.7;
}

.cta-button {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  border-radius: var(--radius-md);
}

.tasks-board {
  margin-top: 26px;
  padding: 20px 22px 24px;
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-lg);
  background: var(--panel-background);
  box-shadow: var(--shadow-subtle);
}

.board-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  flex-wrap: wrap;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-soft);
}

.board-tabs {
  display: inline-flex;
  gap: 6px;
  padding: 4px;
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-md);
  background: var(--control-background);
}

.board-tab {
  padding: 8px 18px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  font: inherit;
  font-weight: 700;
  cursor: pointer;
  transition:
    background 0.2s var(--motion-calm),
    color 0.2s var(--motion-calm);
}

.board-tab.is-active {
  background: var(--control-selected-background);
  color: var(--brand-navy);
}

.board-tools {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.task-search {
  width: 220px;
}

.sort-select {
  width: 160px;
}

.task-list-shell {
  min-height: 160px;
  padding-top: 18px;
}

.segment-block + .segment-block {
  margin-top: 26px;
}

.segment-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 12px;
}

.segment-head h2 {
  margin: 0;
  color: var(--brand-navy);
  font-size: 1.15rem;
}

.segment-head span {
  color: var(--text-muted);
  font-size: 0.82rem;
  font-weight: 700;
}

.task-list {
  display: grid;
  gap: 10px;
}

.task-card {
  position: relative;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: start;
  gap: 14px;
  padding: 14px 16px;
  border: 1px solid var(--border-soft);
  border-left: 3px solid var(--border-soft);
  border-radius: var(--radius-md);
  background: var(--panel-background-soft);
  transition:
    transform 0.18s var(--motion-snappy),
    border-color 0.18s var(--motion-calm),
    box-shadow 0.18s var(--motion-calm);
}

.task-card:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-subtle);
}

.task-card.is-low {
  border-left-color: var(--moss);
}

.task-card.is-medium {
  border-left-color: var(--brand-gold);
}

.task-card.is-high {
  border-left-color: var(--brand-blue);
}

.task-card.is-urgent {
  border-left-color: var(--danger);
}

.task-card.is-overdue {
  background: var(--danger-soft);
}

.task-card.is-done {
  opacity: 0.82;
}

.task-check {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  margin-top: 2px;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--text-muted);
  font-size: 1.35rem;
  cursor: pointer;
  transition: color 0.18s var(--motion-calm), transform 0.18s var(--motion-snappy);
}

.task-check:hover {
  color: var(--moss);
  transform: scale(1.08);
}

.task-check.is-checked {
  color: var(--moss);
}

.task-main {
  min-width: 0;
  cursor: pointer;
}

.task-main h3 {
  margin: 0;
  color: var(--text-primary);
  font-size: 1.02rem;
  font-weight: 700;
  line-height: 1.4;
  word-break: break-word;
}

.task-card.is-done .task-main h3 {
  text-decoration: line-through;
  color: var(--text-muted);
}

.task-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin: 8px 0 0;
  color: var(--text-muted);
  font-size: 0.82rem;
}

.task-range {
  font-variant-numeric: tabular-nums;
}

.urgency-pill,
.overdue-pill,
.undated-pill {
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 0.74rem;
  font-weight: 700;
}

.urgency-pill {
  background: var(--surface-muted);
  color: var(--text-secondary);
}

.overdue-pill {
  background: var(--danger-soft);
  color: var(--danger);
}

.undated-pill {
  background: var(--surface-muted);
  color: var(--text-muted);
}

.task-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin: 8px 0 0;
  color: var(--brand-blue);
  font-size: 0.8rem;
}

.task-link.is-deleted {
  color: var(--danger);
  text-decoration: line-through;
}

.task-summary {
  margin: 10px 0 0;
  color: var(--text-secondary);
  font-size: 0.88rem;
  line-height: 1.6;
  white-space: pre-wrap;
}

.task-summary.is-empty {
  color: var(--text-muted);
  font-style: italic;
}

.task-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.task-actions button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  font-size: 1rem;
  cursor: pointer;
  transition: background 0.18s var(--motion-calm), color 0.18s var(--motion-calm);
}

.task-actions button:hover {
  background: var(--accent-soft);
  color: var(--accent);
}

.segment-empty {
  margin: 0;
  padding: 18px 0;
  color: var(--text-muted);
  font-size: 0.88rem;
}

.task-form {
  display: grid;
  gap: 16px;
}

.form-row {
  display: grid;
  gap: 8px;
}

.form-row > span {
  color: var(--text-muted);
  font-size: 0.82rem;
  font-weight: 700;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.form-grid :deep(.el-date-editor) {
  width: 100%;
}

.complete-hint {
  margin: 0 0 12px;
  color: var(--text-muted);
  font-size: 0.86rem;
}

@media (max-width: 860px) {
  .tasks-header {
    flex-direction: column;
  }

  .form-grid {
    grid-template-columns: 1fr;
  }

  .task-search,
  .sort-select {
    width: 100%;
  }

  .board-tools {
    width: 100%;
  }
}
</style>
