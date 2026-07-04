<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Close, CollectionTag, Delete, Download, EditPen, MoreFilled, Search, Star, StarFilled, View } from '@element-plus/icons-vue'

import WorkspaceShell from '../components/WorkspaceShell.vue'
import api from '../services/api'
import { EDITOR_SETTINGS_CHANGE_EVENT, getEditorSettings } from '../utils/editorSettings'
import { buildHighlightParts } from '../utils/highlight'
import { exportNoteBatchFile, exportNoteFile, getNoteExportErrorDetail } from '../utils/noteExport'

const router = useRouter()
const loading = ref(false)
const notes = ref([])
const currentPage = ref(1)
const editorSettings = ref(getEditorSettings())
const total = ref(0)
const searchKeyword = ref('')
const activeSearchKeyword = ref('')
const tags = ref([])
const selectedTagId = ref('')
const selectedSort = ref('pinned_created')
const exportingNoteId = ref(null)
const exportDialogVisible = ref(false)
const exportTargetNote = ref(null)
const selectedNoteIds = ref([])
const batchDeleting = ref(false)
const batchMode = ref(false)
const batchExportDialogVisible = ref(false)
const batchExporting = ref(false)
const batchTagDialogVisible = ref(false)
const batchTagUpdating = ref(false)
const batchTagMode = ref('add')
const batchTagNames = ref([])
const pinningNoteId = ref(null)
const updatingImportanceNoteId = ref(null)
const importanceRateColors = ['var(--brand-blue)', 'var(--brand-blue)', 'var(--brand-blue)']
const sortOptions = [
  { label: '置顶优先 · 最新创建', value: 'pinned_created' },
  { label: '置顶优先 · 最近更新', value: 'pinned_updated' },
  { label: '重要程度优先', value: 'importance' },
  { label: '标题 A-Z', value: 'title' },
]
const batchTagModeOptions = [
  { label: '添加标签', value: 'add' },
  { label: '移除标签', value: 'remove' },
  { label: '替换标签', value: 'replace' },
]

let searchTimer = null

const totalPages = computed(() => {
  if (!total.value) {
    return 0
  }
  return Math.ceil(total.value / pageSize.value)
})
const pageSize = computed(() => editorSettings.value.noteListPageSize)
const hasActiveFilters = computed(() => Boolean(activeSearchKeyword.value || selectedTagId.value))
const selectedTagName = computed(() => {
  const tag = tags.value.find((item) => String(item.id) === String(selectedTagId.value))
  return tag?.name || ''
})
const selectedCount = computed(() => selectedNoteIds.value.length)
const batchTagPlaceholder = computed(() => {
  if (batchTagMode.value === 'remove') {
    return '选择要移除的标签'
  }

  if (batchTagMode.value === 'replace') {
    return '选择替换后的标签'
  }

  return '选择或创建要添加的标签'
})
const currentPageNoteIds = computed(() => notes.value.map((note) => note.id))
const isCurrentPageAllSelected = computed(() => (
  currentPageNoteIds.value.length > 0
  && currentPageNoteIds.value.every((noteId) => selectedNoteIds.value.includes(noteId))
))
const isCurrentPagePartiallySelected = computed(() => (
  currentPageNoteIds.value.some((noteId) => selectedNoteIds.value.includes(noteId))
  && !isCurrentPageAllSelected.value
))

// 列表页继续沿用后端分页，避免笔记变多后一次性加载过重。
const fetchNotes = async (page = 1) => {
  loading.value = true

  try {
    const params = {
      page,
      page_size: pageSize.value,
      sort: selectedSort.value,
    }
    const keyword = activeSearchKeyword.value.trim()

    if (keyword) {
      params.search = keyword
    }

    if (selectedTagId.value) {
      params.tag = selectedTagId.value
    }

    const { data } = await api.get('/notes/', {
      params,
    })

    notes.value = data.results
    total.value = data.count
    currentPage.value = page
  } catch (error) {
    const detail = error.response?.data?.detail || '获取笔记列表失败，请稍后重试。'
    ElMessage.error(detail)
  } finally {
    loading.value = false
  }
}

const fetchTags = async () => {
  try {
    const { data } = await api.get('/notes/tags/')
    tags.value = data
  } catch (error) {
    const detail = error.response?.data?.detail || '获取标签列表失败，请稍后重试。'
    ElMessage.error(detail)
  }
}

const runSearch = () => {
  const nextKeyword = searchKeyword.value.trim()

  if (nextKeyword === activeSearchKeyword.value) {
    return
  }

  activeSearchKeyword.value = nextKeyword
  fetchNotes(1)
}

const scheduleSearch = () => {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(runSearch, 260)
}

const handleSearch = () => {
  window.clearTimeout(searchTimer)
  runSearch()
}

const clearSearch = () => {
  searchKeyword.value = ''
}

const handleTagChange = () => {
  fetchNotes(1)
}

const handleSortChange = () => {
  fetchNotes(1)
}

const clearFilters = () => {
  const hadFilters = hasActiveFilters.value

  searchKeyword.value = ''
  activeSearchKeyword.value = ''
  selectedTagId.value = ''

  if (hadFilters) {
    fetchNotes(1)
  }
}

const toggleNoteSelection = (noteId, checked) => {
  if (checked) {
    selectedNoteIds.value = Array.from(new Set([...selectedNoteIds.value, noteId]))
    return
  }

  selectedNoteIds.value = selectedNoteIds.value.filter((selectedId) => selectedId !== noteId)
}

const toggleCurrentPageSelection = (checked) => {
  if (checked) {
    selectedNoteIds.value = Array.from(new Set([...selectedNoteIds.value, ...currentPageNoteIds.value]))
    return
  }

  const currentIds = new Set(currentPageNoteIds.value)
  selectedNoteIds.value = selectedNoteIds.value.filter((noteId) => !currentIds.has(noteId))
}

const clearSelection = () => {
  selectedNoteIds.value = []
}

const enterBatchMode = () => {
  batchMode.value = true
}

const exitBatchMode = () => {
  batchMode.value = false
  clearSelection()
}

const handleNoteMainClick = (note) => {
  if (batchMode.value) {
    toggleNoteSelection(note.id, !selectedNoteIds.value.includes(note.id))
    return
  }

  goToDetail(note)
}

const resolveBatchDeleteNextPage = () => {
  const selectedIds = new Set(selectedNoteIds.value)
  const deletedOnCurrentPage = notes.value.filter((note) => selectedIds.has(note.id)).length

  return notes.value.length === deletedOnCurrentPage && currentPage.value > 1
    ? currentPage.value - 1
    : currentPage.value
}

const handlePageChange = (page) => {
  fetchNotes(page)
}

const goToUpload = () => {
  router.push('/notes/upload')
}

const goToDetail = (note) => {
  router.push({ name: 'note-detail', params: { id: note.id } })
}

const goToEdit = (note) => {
  router.push({ name: 'note-edit', params: { id: note.id } })
}

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

const formatWordCount = (value) => `${value || 0} 字`

const handleAction = async (command, note) => {
  if (command === 'detail') {
    goToDetail(note)
    return
  }

  if (command === 'edit') {
    goToEdit(note)
    return
  }

  if (command === 'export') {
    openExportFormatDialog(note)
    return
  }

  if (command === 'pin') {
    await togglePinNote(note)
    return
  }

  if (command !== 'delete') {
    return
  }

  await handleDelete(note)
}

const openExportFormatDialog = (note) => {
  exportTargetNote.value = note
  exportDialogVisible.value = true
}

const exportNote = async (note, format) => {
  if (exportingNoteId.value) {
    return
  }

  exportingNoteId.value = note.id

  try {
    await exportNoteFile(note, format)
    ElMessage.success('笔记导出已开始。')
  } catch (error) {
    const detail = await getNoteExportErrorDetail(error) || '导出失败，请稍后重试。'
    ElMessage.error(detail)
  } finally {
    exportingNoteId.value = null
  }
}

const handleExportFormat = async (format) => {
  if (!exportTargetNote.value) {
    return
  }

  await exportNote(exportTargetNote.value, format)
  exportDialogVisible.value = false
  exportTargetNote.value = null
}

const togglePinNote = async (note) => {
  if (pinningNoteId.value) {
    return
  }

  const nextPinnedState = !note.is_pinned
  pinningNoteId.value = note.id

  try {
    await api.post(`/notes/${note.id}/pin/`, {
      is_pinned: nextPinnedState,
    })
    ElMessage.success(nextPinnedState ? '笔记已置顶。' : '已取消置顶。')
    fetchNotes(currentPage.value)
  } catch (error) {
    const detail = error.response?.data?.detail || error.response?.data?.is_pinned?.[0] || '置顶操作失败，请稍后重试。'
    ElMessage.error(detail)
  } finally {
    pinningNoteId.value = null
  }
}

const normalizeImportance = (value) => Number(value || 0)

const updateNoteImportance = async (note, value) => {
  if (updatingImportanceNoteId.value) {
    return
  }

  const nextImportance = normalizeImportance(value)
  if (nextImportance === normalizeImportance(note.importance)) {
    return
  }

  updatingImportanceNoteId.value = note.id

  try {
    const { data } = await api.post(`/notes/${note.id}/importance/`, {
      importance: nextImportance,
    })
    if (selectedSort.value === 'importance' || selectedSort.value === 'pinned_updated') {
      fetchNotes(currentPage.value)
      ElMessage.success('重要程度已更新。')
      return
    }

    const noteIndex = notes.value.findIndex((item) => item.id === note.id)
    if (noteIndex >= 0) {
      notes.value[noteIndex] = data
    }
    ElMessage.success('重要程度已更新。')
  } catch (error) {
    const detail = error.response?.data?.detail || error.response?.data?.importance?.[0] || '更新重要程度失败，请稍后重试。'
    ElMessage.error(detail)
    fetchNotes(currentPage.value)
  } finally {
    updatingImportanceNoteId.value = null
  }
}

const handleBatchDelete = async () => {
  if (!selectedCount.value || batchDeleting.value || batchExporting.value) {
    return
  }

  try {
    await ElMessageBox.confirm(
      `确定要将选中的 ${selectedCount.value} 篇笔记移入回收站吗？笔记会在回收站保留 30 天，在此期间可以随时恢复。`,
      '批量移入回收站',
      {
        confirmButtonText: '确认删除',
        cancelButtonText: '取消',
        type: 'warning',
        customClass: 'beautiful-confirm-box',
        confirmButtonClass: 'beautiful-confirm-button',
        cancelButtonClass: 'beautiful-cancel-button',
        closeOnClickModal: false,
        closeOnPressEscape: true,
        showClose: true,
        center: false,
        draggable: false,
        lockScroll: true,
      }
    )
  } catch {
    return
  }

  const nextPage = resolveBatchDeleteNextPage()
  batchDeleting.value = true

  try {
    const { data } = await api.post('/notes/batch-delete/', {
      note_ids: selectedNoteIds.value,
    })
    ElMessage.success(data.detail || '已批量移入回收站。')
    clearSelection()
    batchMode.value = false
    fetchNotes(nextPage)
  } catch (error) {
    const detail = error.response?.data?.detail || error.response?.data?.note_ids?.[0] || '批量删除失败，请稍后重试。'
    ElMessage.error(detail)
  } finally {
    batchDeleting.value = false
  }
}

const openBatchExportDialog = () => {
  if (!selectedCount.value || batchExporting.value) {
    return
  }

  batchExportDialogVisible.value = true
}

const handleBatchExportFormat = async (format) => {
  if (!selectedCount.value || batchExporting.value) {
    return
  }

  batchExporting.value = true

  try {
    await exportNoteBatchFile(selectedNoteIds.value, format)
    ElMessage.success('批量导出已开始。')
    batchExportDialogVisible.value = false
  } catch (error) {
    const detail = await getNoteExportErrorDetail(error) || '批量导出失败，请稍后重试。'
    ElMessage.error(detail)
  } finally {
    batchExporting.value = false
  }
}

const resetBatchTagForm = () => {
  batchTagMode.value = 'add'
  batchTagNames.value = []
}

const openBatchTagDialog = () => {
  if (!selectedCount.value || batchTagUpdating.value || batchDeleting.value || batchExporting.value) {
    return
  }

  resetBatchTagForm()
  batchTagDialogVisible.value = true
}

const handleBatchTagModeChange = () => {
  batchTagNames.value = []
}

const handleBatchTagUpdate = async () => {
  if (!selectedCount.value || batchTagUpdating.value) {
    return
  }

  const normalizedTagNames = batchTagNames.value
    .map((tagName) => String(tagName).trim())
    .filter(Boolean)

  if (!normalizedTagNames.length) {
    ElMessage.warning('请选择至少一个标签。')
    return
  }

  batchTagUpdating.value = true

  try {
    const { data } = await api.post('/notes/batch-tags/', {
      note_ids: selectedNoteIds.value,
      action: batchTagMode.value,
      tag_names: normalizedTagNames,
    })
    ElMessage.success(data.detail || '标签已批量更新。')
    batchTagDialogVisible.value = false
    batchMode.value = false
    clearSelection()
    resetBatchTagForm()
    await fetchTags()
    fetchNotes(currentPage.value)
  } catch (error) {
    const detail =
      error.response?.data?.detail ||
      error.response?.data?.tag_names?.[0] ||
      error.response?.data?.note_ids?.[0] ||
      error.response?.data?.action?.[0] ||
      '批量修改标签失败，请稍后重试。'
    ElMessage.error(detail)
  } finally {
    batchTagUpdating.value = false
  }
}

const handleDelete = async (note) => {
  try {
    await ElMessageBox.confirm(
      `确定要将《${note.title}》移入回收站吗？笔记会在回收站保留 30 天，在此期间可以随时恢复。`,
      '移入回收站',
      {
        confirmButtonText: '确认删除',
        cancelButtonText: '取消',
        type: 'warning',
        customClass: 'beautiful-confirm-box',
        confirmButtonClass: 'beautiful-confirm-button',
        cancelButtonClass: 'beautiful-cancel-button',
        closeOnClickModal: false,
        closeOnPressEscape: true,
        showClose: true,
        center: false,
        draggable: false,
        lockScroll: true,
      }
    )
  } catch {
    return
  }

  try {
    await api.delete(`/notes/${note.id}/delete/`)
    ElMessage.success('笔记已移入回收站。')
    selectedNoteIds.value = selectedNoteIds.value.filter((noteId) => noteId !== note.id)

    // 删除后如果当前页被删空了，就自动回到上一页，避免出现空白分页。
    const nextPage =
      notes.value.length === 1 && currentPage.value > 1
        ? currentPage.value - 1
        : currentPage.value

    fetchNotes(nextPage)
  } catch (error) {
    const detail = error.response?.data?.detail || '删除笔记失败，请稍后重试。'
    ElMessage.error(detail)
  }
}

const handleEditorSettingsChange = (event) => {
  const nextSettings = event.detail || getEditorSettings()
  const pageSizeChanged = nextSettings.noteListPageSize !== editorSettings.value.noteListPageSize

  editorSettings.value = nextSettings

  if (pageSizeChanged) {
    clearSelection()
    fetchNotes(1)
  }
}

onMounted(() => {
  fetchTags()
  fetchNotes()
  window.addEventListener(EDITOR_SETTINGS_CHANGE_EVENT, handleEditorSettingsChange)
})

watch(searchKeyword, scheduleSearch)

onBeforeUnmount(() => {
  window.clearTimeout(searchTimer)
  window.removeEventListener(EDITOR_SETTINGS_CHANGE_EVENT, handleEditorSettingsChange)
})
</script>

<template>
  <main class="notes-page page-shell">
    <WorkspaceShell>
      <section class="notes-stage">
        <header class="notes-header fade-rise-enter">
          <div class="header-copy">
            <p class="notes-brand">MoonBirdNotes</p>
            <h1>笔记列表</h1>
            <p class="notes-subtitle">
              按创建时间倒序浏览最近新建的笔记，优先看到最新上传的内容。
            </p>
          </div>

          <div class="notes-actions">
            <el-button class="upload-button" type="primary" @click="goToUpload">上传笔记</el-button>
          </div>
        </header>

        <section class="notes-board fade-rise-enter-delay">
          <div class="board-top">
            <div>
              <p class="board-kicker">Notebook</p>
              <h2>最近创建</h2>
            </div>

            <div class="board-summary">
              <span>共 {{ total }} 篇</span>
              <span v-if="totalPages">第 {{ currentPage }} / {{ totalPages }} 页</span>
              <span v-if="selectedTagName">标签：{{ selectedTagName }}</span>
              <el-button
                v-if="notes.length && !batchMode"
                class="batch-mode-toggle"
                @click="enterBatchMode"
              >
                <el-icon><Delete /></el-icon>
                <span>批量管理</span>
              </el-button>
              <el-button
                v-else-if="batchMode"
                class="batch-mode-toggle is-active"
                @click="exitBatchMode"
              >
                退出批量
              </el-button>
            </div>
          </div>

          <form class="search-panel" @submit.prevent="handleSearch">
            <el-input
              v-model="searchKeyword"
              class="search-input"
              clearable
              placeholder="搜索标题、正文、标签或文件名"
              @clear="clearSearch"
            >
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>

            <el-select
              v-model="selectedTagId"
              class="tag-filter-select"
              popper-class="tag-select-dropdown"
              clearable
              placeholder="按标签筛选"
              @change="handleTagChange"
            >
              <el-option
                v-for="tag in tags"
                :key="tag.id"
                :label="tag.name"
                :value="tag.id"
              />
            </el-select>

            <el-select
              v-model="selectedSort"
              class="sort-select"
              popper-class="sort-select-dropdown"
              placeholder="排序方式"
              @change="handleSortChange"
            >
              <el-option
                v-for="option in sortOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>

            <el-button
              v-if="hasActiveFilters"
              class="clear-search-button"
              :icon="Close"
              @click="clearFilters"
            >
              清空
            </el-button>
          </form>

          <div v-if="batchMode" class="batch-action-bar">
            <div class="batch-selection-info">
              <el-checkbox
                :model-value="isCurrentPageAllSelected"
                :indeterminate="isCurrentPagePartiallySelected"
                @change="toggleCurrentPageSelection"
              >
                本页全选
              </el-checkbox>
              <span>{{ selectedCount ? `已选 ${selectedCount} 篇` : '选择要移入回收站的笔记' }}</span>
            </div>

            <div class="batch-actions">
              <el-button class="batch-clear-button" @click="clearSelection">清空选择</el-button>
              <el-button
                class="batch-tag-button"
                :disabled="!selectedCount"
                :loading="batchTagUpdating"
                @click="openBatchTagDialog"
              >
                <el-icon><CollectionTag /></el-icon>
                <span>修改标签</span>
              </el-button>
              <el-button
                class="batch-export-button"
                :disabled="!selectedCount"
                :loading="batchExporting"
                @click="openBatchExportDialog"
              >
                <el-icon><Download /></el-icon>
                <span>批量导出</span>
              </el-button>
              <el-button
                class="batch-delete-button"
                type="danger"
                :disabled="!selectedCount"
                :loading="batchDeleting"
                @click="handleBatchDelete"
              >
                <el-icon><Delete /></el-icon>
                <span>批量删除</span>
              </el-button>
            </div>
          </div>

          <div v-loading="loading" class="stream-shell">
            <div v-if="notes.length" class="note-stream">
              <article
                v-for="note in notes"
                :key="note.id"
                class="note-row"
                :class="{
                  'is-batch-mode': batchMode,
                  'is-selected': selectedNoteIds.includes(note.id),
                  'is-pinned': note.is_pinned,
                }"
              >
                <div v-if="batchMode" class="note-select-cell" @click.stop>
                  <el-checkbox
                    :model-value="selectedNoteIds.includes(note.id)"
                    :aria-label="`选择 ${note.title}`"
                    @change="(checked) => toggleNoteSelection(note.id, checked)"
                  />
                </div>

                <button class="note-main" type="button" @click="handleNoteMainClick(note)">
                  <h3>
                    <span v-if="note.is_pinned" class="pin-badge">
                      <el-icon><StarFilled /></el-icon>
                      <span>置顶</span>
                    </span>
                    <span class="note-title-text">
                      <template v-for="(part, index) in buildHighlightParts(note.title, activeSearchKeyword)" :key="`title-${index}`">
                        <mark v-if="part.highlight" class="search-highlight">{{ part.text }}</mark>
                        <template v-else>{{ part.text }}</template>
                      </template>
                    </span>
                  </h3>
                  <div v-if="note.tags?.length" class="note-tags" aria-label="笔记标签">
                    <span v-for="tag in note.tags" :key="tag.id || tag.name" class="note-tag">
                      <template v-for="(part, index) in buildHighlightParts(tag.name, activeSearchKeyword)" :key="`tag-${tag.id || tag.name}-${index}`">
                        <mark v-if="part.highlight" class="search-highlight">{{ part.text }}</mark>
                        <template v-else>{{ part.text }}</template>
                      </template>
                    </span>
                  </div>
                  <p class="note-excerpt">
                    <template v-for="(part, index) in buildHighlightParts(note.excerpt, activeSearchKeyword)" :key="`excerpt-${index}`">
                      <mark v-if="part.highlight" class="search-highlight">{{ part.text }}</mark>
                      <template v-else>{{ part.text }}</template>
                    </template>
                  </p>
                </button>

                <aside class="note-side">
                  <div class="note-meta">
                    <div class="meta-block importance-block" @click.stop>
                      <span class="meta-label">重要程度</span>
                      <el-rate
                        :model-value="normalizeImportance(note.importance)"
                        :max="5"
                        allow-half
                        clearable
                        :colors="importanceRateColors"
                        void-color="var(--border-soft)"
                        :disabled="updatingImportanceNoteId === note.id"
                        @change="(value) => updateNoteImportance(note, value)"
                      />
                    </div>

                    <div class="meta-block">
                      <span class="meta-label">创建时间</span>
                      <strong>{{ formatDateTime(note.created_at) }}</strong>
                    </div>

                    <div class="meta-block">
                      <span class="meta-label">字数</span>
                      <strong>{{ formatWordCount(note.word_count) }}</strong>
                    </div>
                  </div>

                  <el-dropdown
                    trigger="click"
                    placement="bottom-end"
                    @command="(command) => handleAction(command, note)"
                    popper-class="beautiful-dropdown"
                  >
                    <button class="more-button" type="button" aria-label="更多操作">
                      <el-icon><MoreFilled /></el-icon>
                    </button>

                    <template #dropdown>
                      <el-dropdown-menu class="custom-dropdown-menu">
                        <el-dropdown-item command="detail" class="dropdown-item-with-icon">
                          <el-icon><View /></el-icon>
                          <span>查看详情</span>
                        </el-dropdown-item>
                        <el-dropdown-item command="edit" class="dropdown-item-with-icon">
                          <el-icon><EditPen /></el-icon>
                          <span>编辑</span>
                        </el-dropdown-item>
                        <el-dropdown-item
                          command="export"
                          class="dropdown-item-with-icon"
                          :disabled="exportingNoteId === note.id"
                        >
                          <el-icon><Download /></el-icon>
                          <span>导出</span>
                        </el-dropdown-item>
                        <el-dropdown-item
                          command="pin"
                          class="dropdown-item-with-icon dropdown-item-pin"
                          :disabled="pinningNoteId === note.id"
                        >
                          <el-icon>
                            <StarFilled v-if="note.is_pinned" />
                            <Star v-else />
                          </el-icon>
                          <span>{{ note.is_pinned ? '取消置顶' : '置顶' }}</span>
                        </el-dropdown-item>
                        <el-dropdown-item command="delete" class="dropdown-item-with-icon dropdown-item-danger">
                          <el-icon><Delete /></el-icon>
                          <span>删除</span>
                        </el-dropdown-item>
                      </el-dropdown-menu>
                    </template>
                  </el-dropdown>
                </aside>
              </article>
            </div>

            <div v-else class="empty-state">
              <p>
                {{
                  hasActiveFilters
                    ? '没有找到符合当前筛选条件的笔记。'
                    : '当前还没有笔记，先上传一篇 Markdown 笔记吧。'
                }}
              </p>
              <el-button
                v-if="hasActiveFilters"
                class="empty-action"
                type="primary"
                @click="clearFilters"
              >
                清空筛选
              </el-button>
              <el-button v-else class="empty-action" type="primary" @click="goToUpload">去上传</el-button>
            </div>
          </div>

          <div class="pagination-wrap" v-if="total > pageSize">
            <el-pagination
              background
              layout="prev, pager, next"
              :current-page="currentPage"
              :page-size="pageSize"
              :total="total"
              @current-change="handlePageChange"
            />
          </div>
        </section>
      </section>
    </WorkspaceShell>

    <el-dialog
      v-model="exportDialogVisible"
      class="export-format-dialog"
      width="360px"
      title="选择导出格式"
      align-center
      @closed="exportTargetNote = null"
    >
      <div class="export-format-options">
        <button
          type="button"
          class="export-format-option"
          :disabled="Boolean(exportingNoteId)"
          @click="handleExportFormat('markdown')"
        >
          <el-icon><Download /></el-icon>
          <span>Markdown</span>
        </button>

        <button
          type="button"
          class="export-format-option"
          :disabled="Boolean(exportingNoteId)"
          @click="handleExportFormat('html')"
        >
          <el-icon><Download /></el-icon>
          <span>HTML</span>
        </button>
      </div>
    </el-dialog>

    <el-dialog
      v-model="batchExportDialogVisible"
      class="export-format-dialog"
      width="360px"
      title="选择批量导出格式"
      align-center
    >
      <div class="export-format-options">
        <button
          type="button"
          class="export-format-option"
          :disabled="batchExporting"
          @click="handleBatchExportFormat('markdown')"
        >
          <el-icon><Download /></el-icon>
          <span>Markdown 压缩包</span>
        </button>

        <button
          type="button"
          class="export-format-option"
          :disabled="batchExporting"
          @click="handleBatchExportFormat('html')"
        >
          <el-icon><Download /></el-icon>
          <span>HTML 压缩包</span>
        </button>
      </div>
    </el-dialog>

    <el-dialog
      v-model="batchTagDialogVisible"
      class="batch-tag-dialog"
      width="440px"
      title="批量修改标签"
      align-center
      @closed="resetBatchTagForm"
    >
      <div class="batch-tag-form">
        <el-radio-group
          v-model="batchTagMode"
          class="batch-tag-mode-group"
          @change="handleBatchTagModeChange"
        >
          <el-radio-button
            v-for="option in batchTagModeOptions"
            :key="option.value"
            :label="option.value"
          >
            {{ option.label }}
          </el-radio-button>
        </el-radio-group>

        <el-select
          v-model="batchTagNames"
          class="batch-tag-select"
          popper-class="tag-select-dropdown"
          multiple
          filterable
          allow-create
          default-first-option
          collapse-tags
          collapse-tags-tooltip
          :max-collapse-tags="2"
          :placeholder="batchTagPlaceholder"
        >
          <el-option
            v-for="tag in tags"
            :key="tag.id"
            :label="tag.name"
            :value="tag.name"
          />
        </el-select>
      </div>

      <template #footer>
        <div class="batch-tag-footer">
          <el-button class="batch-tag-cancel" @click="batchTagDialogVisible = false">取消</el-button>
          <el-button
            class="batch-tag-confirm"
            type="primary"
            :loading="batchTagUpdating"
            @click="handleBatchTagUpdate"
          >
            确认修改
          </el-button>
        </div>
      </template>
    </el-dialog>
  </main>
</template>

<style scoped>
.notes-page {
  padding: 20px;
}

.notes-stage {
  margin-top: 20px;
}

.notes-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
}

.header-copy {
  max-width: 700px;
}

.notes-brand,
.board-kicker {
  margin: 0 0 12px;
  color: var(--brand-blue);
  font-size: 0.84rem;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.notes-header h1 {
  margin: 0;
  color: var(--brand-navy);
  font-size: clamp(2.4rem, 4vw, 4.8rem);
  line-height: 0.98;
  letter-spacing: -0.06em;
}

.notes-subtitle {
  max-width: 560px;
  margin: 18px 0 0;
  color: var(--ink-soft);
  line-height: 1.9;
}

.upload-button {
  min-height: 50px;
  padding-inline: 24px;
  border: none;
  border-radius: var(--radius-md);
  background: var(--brand-blue);
  box-shadow: none;
}

.notes-board {
  margin-top: 34px;
  padding: 30px 30px 24px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 30px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.82), rgba(255, 255, 255, 0.64)),
    rgba(255, 255, 255, 0.68);
  box-shadow: var(--shadow-soft);
}

.board-top {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
}

.board-top h2 {
  margin: 0;
  color: var(--brand-navy);
  font-size: 1.9rem;
  line-height: 1.04;
  letter-spacing: -0.05em;
}

.board-summary {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  color: var(--ink-soft);
}

.batch-mode-toggle {
  min-height: 36px;
  margin-left: 2px;
  padding-inline: 12px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.82);
  color: var(--brand-navy);
  font-weight: 800;
}

.batch-mode-toggle:hover,
.batch-mode-toggle:focus {
  border-color: rgba(220, 38, 38, 0.28);
  background: rgba(220, 38, 38, 0.07);
  color: #dc2626;
}

.batch-mode-toggle.is-active {
  border-color: rgba(37, 99, 235, 0.24);
  background: rgba(37, 99, 235, 0.08);
  color: var(--brand-blue);
}

.board-summary :deep(.el-button + .el-button) {
  margin-left: 0;
}

.search-panel {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(180px, 220px) minmax(180px, 230px) auto;
  gap: 12px;
  align-items: center;
  margin-top: 22px;
  padding: 14px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.72);
}

.search-input :deep(.el-input__wrapper),
.tag-filter-select :deep(.el-select__wrapper),
.sort-select :deep(.el-select__wrapper) {
  min-height: 46px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.9);
  box-shadow: none;
}

.search-input :deep(.el-input__wrapper.is-focus),
.tag-filter-select :deep(.el-select__wrapper.is-focused),
.sort-select :deep(.el-select__wrapper.is-focused) {
  box-shadow: 0 0 0 1px rgba(37, 99, 235, 0.26);
}

.tag-filter-select,
.sort-select {
  width: 100%;
}

.clear-search-button {
  min-height: 46px;
  border-color: rgba(148, 163, 184, 0.24);
  border-radius: 14px;
  color: var(--brand-navy);
}

.search-panel :deep(.el-button + .el-button) {
  margin-left: 0;
}

.batch-action-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-top: 14px;
  padding: 12px 14px;
  border: 1px solid rgba(37, 99, 235, 0.16);
  border-radius: 18px;
  background:
    linear-gradient(180deg, rgba(239, 246, 255, 0.92), rgba(255, 255, 255, 0.78)),
    rgba(255, 255, 255, 0.78);
}

.batch-selection-info,
.batch-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.batch-selection-info span {
  color: var(--brand-navy);
  font-weight: 800;
}

.batch-clear-button,
.batch-tag-button,
.batch-export-button,
.batch-delete-button {
  min-height: 40px;
  border-radius: 12px;
}

.batch-clear-button {
  border-color: rgba(148, 163, 184, 0.24);
  color: var(--brand-navy);
}

.batch-tag-button,
.batch-export-button {
  border-color: rgba(37, 99, 235, 0.2);
  background: rgba(37, 99, 235, 0.08);
  color: var(--brand-blue);
  font-weight: 800;
}

.batch-tag-button:hover,
.batch-tag-button:focus,
.batch-export-button:hover,
.batch-export-button:focus {
  border-color: rgba(37, 99, 235, 0.32);
  background: rgba(37, 99, 235, 0.12);
  color: var(--brand-blue);
}

.batch-delete-button {
  border: none;
  background: var(--danger);
  box-shadow: none;
}

.batch-action-bar :deep(.el-button + .el-button) {
  margin-left: 0;
}

.stream-shell {
  margin-top: 26px;
}

.note-stream {
  display: flex;
  flex-direction: column;
}

.note-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 400px;
  gap: 28px;
  align-items: start;
  padding: 24px 6px;
  border-top: 1px solid rgba(148, 163, 184, 0.16);
  transition:
    background-color 0.18s ease,
    box-shadow 0.18s ease,
    padding 0.18s ease,
    border-radius 0.18s ease;
}

.note-row.is-batch-mode {
  grid-template-columns: 44px minmax(0, 1fr) 400px;
  gap: 18px;
  padding-inline: 14px;
  border-radius: 18px;
  cursor: pointer;
}

.note-row.is-batch-mode:hover {
  background: rgba(37, 99, 235, 0.04);
}

.note-row.is-pinned {
  background:
    linear-gradient(90deg, var(--accent-soft), rgba(255, 255, 255, 0) 46%);
  box-shadow: inset 3px 0 0 var(--brand-blue);
}

.note-row.is-selected {
  background:
    linear-gradient(180deg, rgba(239, 246, 255, 0.78), rgba(255, 255, 255, 0.72)),
    rgba(255, 255, 255, 0.76);
  box-shadow: inset 0 0 0 1px rgba(37, 99, 235, 0.16);
}

.note-row:first-child {
  border-top: none;
  padding-top: 4px;
}

.note-main h3 {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0;
  color: var(--brand-navy);
  font-size: clamp(1.3rem, 2vw, 2rem);
  line-height: 1.18;
  letter-spacing: -0.04em;
}

.note-select-cell {
  display: flex;
  justify-content: center;
  padding-top: 4px;
}

.note-select-cell :deep(.el-checkbox) {
  height: 32px;
}

.note-select-cell :deep(.el-checkbox__inner) {
  width: 18px;
  height: 18px;
  border-radius: 6px;
  border-color: rgba(148, 163, 184, 0.42);
}

.note-select-cell :deep(.el-checkbox__input.is-checked .el-checkbox__inner) {
  border-color: var(--brand-blue);
  background-color: var(--brand-blue);
}

.note-main {
  min-width: 0;
  padding: 0;
  border: none;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.note-main h3,
.note-main .note-excerpt {
  transition: color 0.2s ease;
}

.note-main:hover h3 {
  color: var(--brand-blue);
}

.note-title-text {
  min-width: 0;
}

.pin-badge {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  gap: 4px;
  min-height: 24px;
  padding: 0 8px;
  border: 1px solid var(--accent-border);
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--brand-blue);
  font-size: 0.78rem;
  font-weight: 800;
  line-height: 1;
}

.pin-badge .el-icon {
  font-size: 13px;
}

.note-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.note-tag {
  display: inline-flex;
  align-items: center;
  min-height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.08);
  color: var(--brand-blue);
  font-size: 0.82rem;
  font-weight: 600;
  line-height: 1;
  white-space: nowrap;
}

.note-excerpt {
  max-width: 920px;
  margin: 12px 0 0;
  color: var(--ink-soft);
  font-size: 0.98rem;
  line-height: 1.85;
}

.search-highlight {
  padding: 0 0.12em;
  border-radius: 4px;
  background: var(--search-highlight-bg);
  color: var(--search-highlight-text);
  font-weight: 800;
}

.note-side {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  align-self: center;
}

.note-meta {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 14px;
}

.meta-block {
  min-width: 92px;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.importance-block {
  min-width: 124px;
}

.importance-block :deep(.el-rate) {
  --el-rate-icon-size: 16px;
  height: 20px;
}

.importance-block :deep(.el-rate__item) {
  margin-right: 2px;
}

.meta-label {
  display: block;
  margin-bottom: 8px;
  color: var(--ink-soft);
  font-size: 0.82rem;
}

.meta-block strong {
  color: var(--brand-navy);
  font-size: 1rem;
  font-weight: 700;
}

.more-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.9);
  color: var(--brand-navy);
  cursor: pointer;
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease,
    border-color 0.2s ease;
}

.more-button:hover {
  transform: translateY(-1px);
  border-color: rgba(37, 99, 235, 0.24);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 16px;
  padding: 36px 6px 12px;
  color: var(--ink-soft);
}

.empty-state p {
  margin: 0;
  line-height: 1.8;
}

.empty-action {
  border: none;
  border-radius: var(--radius-md);
  background: var(--brand-blue);
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 26px;
}

.export-format-options {
  display: grid;
  gap: 10px;
}

.export-format-option {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 48px;
  width: 100%;
  padding: 0 14px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.92);
  color: var(--brand-navy);
  font-size: 0.96rem;
  font-weight: 700;
  cursor: pointer;
  transition:
    transform 0.18s ease,
    border-color 0.18s ease,
    background-color 0.18s ease,
    color 0.18s ease,
    box-shadow 0.18s ease;
}

.export-format-option:hover,
.export-format-option:focus-visible {
  transform: translateY(-1px);
  border-color: rgba(37, 99, 235, 0.28);
  background: rgba(37, 99, 235, 0.08);
  color: var(--brand-blue);
  box-shadow: 0 10px 22px rgba(15, 23, 42, 0.08);
  outline: none;
}

.export-format-option:disabled {
  cursor: not-allowed;
  opacity: 0.62;
  transform: none;
  box-shadow: none;
}

.batch-tag-form {
  display: grid;
  gap: 16px;
}

.batch-tag-mode-group {
  display: flex;
  width: 100%;
  overflow: hidden;
  border: 1px solid var(--border-soft);
  border-radius: 12px;
  background: var(--surface);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}

.batch-tag-mode-group :deep(.el-radio-button) {
  flex: 1;
}

.batch-tag-mode-group :deep(.el-radio-button__inner) {
  width: 100%;
  min-height: 42px;
  border: none;
  border-radius: 0;
  background: transparent;
  color: var(--text-secondary);
  font-weight: 700;
  box-shadow: none;
  transition:
    background-color 0.16s ease,
    color 0.16s ease;
}

.batch-tag-mode-group :deep(.el-radio-button:not(:last-child) .el-radio-button__inner) {
  border-right: 1px solid var(--border-soft);
}

.batch-tag-mode-group :deep(.el-radio-button__inner:hover) {
  background: var(--surface-soft);
  color: var(--brand-blue);
}

.batch-tag-mode-group :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background: color-mix(in srgb, var(--brand-blue) 10%, transparent);
  color: var(--brand-blue);
  box-shadow: none;
}

.batch-tag-select {
  width: 100%;
}

.batch-tag-select :deep(.el-select__wrapper) {
  min-height: 46px;
  border-radius: 12px;
  background: var(--surface);
  box-shadow: 0 0 0 1px var(--border-soft);
}

.batch-tag-select :deep(.el-select__wrapper.is-focused) {
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--brand-blue) 42%, transparent);
}

.batch-tag-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.batch-tag-cancel,
.batch-tag-confirm {
  min-height: 40px;
  border-radius: 10px;
  font-weight: 700;
}

.batch-tag-cancel {
  border-color: var(--border-soft);
  background: var(--surface);
  color: var(--text-secondary);
}

.batch-tag-confirm {
  border: none;
  background: var(--brand-blue);
}

@media (max-width: 1100px) {
  .note-row {
    grid-template-columns: 1fr;
    gap: 16px;
  }

  .note-row.is-batch-mode {
    grid-template-columns: 44px 1fr;
  }

  .note-side,
  .note-meta {
    justify-content: flex-start;
  }

  .note-side {
    align-items: center;
    align-self: start;
  }

  .note-row.is-batch-mode .note-side {
    grid-column: 2;
  }

  .meta-block {
    align-items: center;
    text-align: center;
  }
}

@media (max-width: 980px) {
  .notes-page {
    padding: 16px;
  }

  .notes-stage {
    margin-top: 0;
  }
}

@media (max-width: 720px) {
  .notes-header,
  .board-top {
    flex-direction: column;
    align-items: flex-start;
  }

  .board-summary {
    align-items: flex-start;
  }

  .notes-actions,
  .notes-actions :deep(.el-button) {
    width: 100%;
  }

  .notes-board {
    padding: 22px 22px 18px;
    border-radius: 24px;
  }

  .search-panel {
    grid-template-columns: 1fr;
  }

  .tag-filter-select,
  .sort-select,
  .clear-search-button {
    width: 100%;
  }

  .batch-action-bar,
  .batch-actions {
    align-items: stretch;
    flex-direction: column;
  }

  .batch-actions,
  .batch-actions :deep(.el-button) {
    width: 100%;
  }

  .note-row {
    padding: 20px 0;
  }

  .note-main h3 {
    font-size: 1.2rem;
  }

  .note-excerpt {
    font-size: 0.94rem;
  }

  .note-side,
  .note-meta {
    width: 100%;
    justify-content: space-between;
  }

  .meta-block {
    min-width: 0;
    align-items: flex-start;
    text-align: left;
  }
}

@media (max-width: 520px) {
  .notes-board {
    padding: 18px 16px 16px;
    border-radius: 20px;
  }

  .note-row {
    gap: 14px;
  }

  .note-row.is-batch-mode {
    grid-template-columns: 36px 1fr;
    padding-inline: 10px;
  }

  .note-side {
    flex-direction: column;
    align-items: stretch;
  }

  .note-meta {
    gap: 10px;
  }

  .meta-block {
    padding: 12px 14px;
    border: 1px solid rgba(148, 163, 184, 0.14);
    border-radius: 16px;
    background: rgba(255, 255, 255, 0.7);
  }

  .more-button {
    align-self: flex-end;
  }

  .pagination-wrap {
    justify-content: center;
  }
}
</style>

<style>
/* 美化下拉菜单样式 - 必须是非 scoped 样式才能作用于 popper */
.beautiful-dropdown {
  border-radius: 18px !important;
  border: 1px solid rgba(148, 163, 184, 0.2) !important;
  box-shadow: 0 20px 48px rgba(15, 23, 42, 0.15), 0 0 0 1px rgba(255, 255, 255, 0.1) !important;
  padding: 8px !important;
  background: rgba(255, 255, 255, 0.98) !important;
  backdrop-filter: blur(20px) !important;
  overflow-x: hidden !important;
}

.beautiful-dropdown .el-dropdown-menu,
.beautiful-dropdown .custom-dropdown-menu {
  box-sizing: border-box !important;
  overflow-x: hidden !important;
}

.beautiful-dropdown .el-scrollbar,
.beautiful-dropdown .el-scrollbar__wrap,
.beautiful-dropdown .el-scrollbar__view {
  max-height: none !important;
  overflow: visible !important;
}

.beautiful-dropdown .el-scrollbar__bar {
  display: none !important;
}

.beautiful-dropdown .el-dropdown-menu__item {
  box-sizing: border-box !important;
  width: 100% !important;
  padding: 12px 16px !important;
  border-radius: 12px !important;
  margin: 4px 0 !important;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
  color: #0f172a !important;
  font-weight: 500 !important;
}

.beautiful-dropdown .dropdown-item-with-icon {
  display: flex !important;
  align-items: center !important;
  gap: 10px !important;
}

.beautiful-dropdown .dropdown-item-with-icon .el-icon {
  font-size: 16px !important;
  color: #2563eb !important;
  transition: all 0.2s ease !important;
}

.beautiful-dropdown .el-dropdown-menu__item:hover {
  background: rgba(37, 99, 235, 0.08) !important;
  color: #2563eb !important;
}

.beautiful-dropdown .dropdown-item-danger {
  color: #dc2626 !important;
}

.beautiful-dropdown .dropdown-item-pin .el-icon {
  color: var(--brand-blue) !important;
}

.beautiful-dropdown .dropdown-item-pin:hover {
  background: var(--accent-soft) !important;
  color: var(--brand-blue) !important;
}

.beautiful-dropdown .dropdown-item-pin:hover .el-icon {
  color: var(--brand-blue) !important;
}

.beautiful-dropdown .dropdown-item-danger .el-icon {
  color: #dc2626 !important;
}

.beautiful-dropdown .dropdown-item-danger:hover {
  background: rgba(220, 38, 38, 0.08) !important;
  color: #b91c1c !important;
}

.beautiful-dropdown .dropdown-item-danger:hover .el-icon {
  color: #b91c1c !important;
}

.sort-select-dropdown,
.tag-select-dropdown {
  min-width: 230px !important;
  padding: 0 !important;
  border: 1px solid var(--border-soft) !important;
  border-radius: 12px !important;
  background: var(--surface) !important;
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.12) !important;
  backdrop-filter: blur(18px) !important;
  overflow: hidden !important;
}

.sort-select-dropdown .el-select-dropdown,
.tag-select-dropdown .el-select-dropdown {
  margin: 0 !important;
  border: none !important;
  border-radius: 0 !important;
  background: transparent !important;
  box-shadow: none !important;
}

.sort-select-dropdown .el-popper__arrow,
.tag-select-dropdown .el-popper__arrow {
  display: none !important;
}

.sort-select-dropdown .el-select-dropdown__wrap {
  max-height: none !important;
}

.tag-select-dropdown .el-select-dropdown__wrap {
  max-height: 260px !important;
}

.sort-select-dropdown .el-scrollbar__bar,
.tag-select-dropdown .el-scrollbar__bar {
  display: none !important;
}

.sort-select-dropdown .el-select-dropdown__list,
.tag-select-dropdown .el-select-dropdown__list {
  display: block !important;
  padding: 0 !important;
}

.sort-select-dropdown .el-select-dropdown__item,
.tag-select-dropdown .el-select-dropdown__item {
  position: relative !important;
  display: flex !important;
  align-items: center !important;
  min-height: 48px !important;
  padding: 0 20px !important;
  border-radius: 0 !important;
  background: transparent !important;
  color: var(--text-secondary) !important;
  font-size: 0.92rem !important;
  font-weight: 600 !important;
  line-height: 1.2 !important;
  transition:
    background-color 0.18s ease,
    color 0.18s ease !important;
}

.sort-select-dropdown .el-select-dropdown__item span,
.tag-select-dropdown .el-select-dropdown__item span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sort-select-dropdown .el-select-dropdown__item.hover,
.sort-select-dropdown .el-select-dropdown__item:hover,
.tag-select-dropdown .el-select-dropdown__item.hover,
.tag-select-dropdown .el-select-dropdown__item:hover {
  background: transparent !important;
  color: var(--brand-blue) !important;
}

.sort-select-dropdown .el-select-dropdown__item.selected,
.tag-select-dropdown .el-select-dropdown__item.selected {
  background: transparent !important;
  color: var(--brand-blue) !important;
  font-weight: 700 !important;
}

/* 美化确认对话框样式 */
.beautiful-confirm-box {
  border-radius: 24px !important;
  border: 1px solid rgba(148, 163, 184, 0.2) !important;
  box-shadow: 0 24px 64px rgba(15, 23, 42, 0.18), 0 0 0 1px rgba(255, 255, 255, 0.1) !important;
  padding: 32px !important;
  background: rgba(255, 255, 255, 0.98) !important;
  backdrop-filter: blur(24px) !important;
}

.beautiful-confirm-box .el-message-box__header {
  padding: 0 0 20px 0 !important;
  border-bottom: 1px solid rgba(148, 163, 184, 0.12) !important;
}

.beautiful-confirm-box .el-message-box__title {
  color: #0f172a !important;
  font-size: 1.4rem !important;
  font-weight: 700 !important;
  letter-spacing: -0.02em !important;
}

.beautiful-confirm-box .el-message-box__content {
  padding: 24px 0 !important;
  color: #64748b !important;
  font-size: 1rem !important;
  line-height: 1.8 !important;
}

.beautiful-confirm-box .el-message-box__btns {
  display: flex !important;
  gap: 12px !important;
  padding: 20px 0 0 0 !important;
  border-top: 1px solid rgba(148, 163, 184, 0.12) !important;
}

.beautiful-confirm-button {
  min-height: 44px !important;
  padding: 0 24px !important;
  border: none !important;
  border-radius: var(--radius-md) !important;
  background: var(--danger) !important;
  color: white !important;
  font-weight: 600 !important;
  box-shadow: none !important;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
}

.beautiful-confirm-button:hover {
  transform: translateY(-2px) !important;
  box-shadow: none !important;
  background: #b91c1c !important;
}

.beautiful-cancel-button {
  min-height: 44px !important;
  padding: 0 24px !important;
  border: 1px solid rgba(148, 163, 184, 0.24) !important;
  border-radius: 14px !important;
  background: rgba(255, 255, 255, 0.9) !important;
  color: #0f172a !important;
  font-weight: 600 !important;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
}

.beautiful-cancel-button:hover {
  transform: translateY(-1px) !important;
  border-color: rgba(37, 99, 235, 0.3) !important;
  background: rgba(255, 255, 255, 1) !important;
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.1) !important;
}

.beautiful-confirm-box .el-message-box__status {
  font-size: 28px !important;
  margin-right: 12px !important;
}

.beautiful-confirm-box .el-message-box__status.el-icon {
  color: var(--brand-blue) !important;
}

.export-format-dialog {
  border-radius: 20px !important;
  padding: 22px !important;
}

.export-format-dialog .el-dialog__header {
  padding-bottom: 14px !important;
}

.export-format-dialog .el-dialog__title {
  color: #0f172a !important;
  font-weight: 800 !important;
}

.batch-tag-dialog {
  border-radius: 20px !important;
  padding: 22px !important;
}

.batch-tag-dialog .el-dialog__header {
  padding-bottom: 14px !important;
}

.batch-tag-dialog .el-dialog__title {
  color: #0f172a !important;
  font-weight: 800 !important;
}

.batch-tag-dialog .el-dialog__footer {
  padding-top: 18px !important;
}
</style>
