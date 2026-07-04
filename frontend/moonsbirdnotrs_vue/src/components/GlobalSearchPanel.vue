<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Calendar, Close, Document, EditPen, Search, View } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

import api from '../services/api'
import { buildHighlightParts } from '../utils/highlight'

const props = defineProps({
  collapsed: {
    type: Boolean,
    default: false,
  },
  mobile: {
    type: Boolean,
    default: false,
  },
})

const router = useRouter()
const visible = ref(false)
const keyword = ref('')
const results = ref([])
const total = ref(0)
const loading = ref(false)
const searchInput = ref(null)
const compact = computed(() => props.collapsed && !props.mobile)
const normalizedKeyword = computed(() => keyword.value.trim())
const resultLabel = computed(() => {
  if (!normalizedKeyword.value) {
    return '最近内容'
  }

  return `${total.value} 个结果`
})

let searchTimer = null
let requestId = 0

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

const focusSearchInput = () => {
  nextTick(() => {
    searchInput.value?.focus?.()
  })
}

const fetchResults = async () => {
  const currentRequestId = requestId + 1
  requestId = currentRequestId
  loading.value = true

  try {
    const params = {
      page_size: 8,
    }

    if (normalizedKeyword.value) {
      params.search = normalizedKeyword.value
    }

    const { data } = await api.get('/notes/search/', { params })

    if (currentRequestId !== requestId) {
      return
    }

    results.value = data.results || []
    total.value = data.count || 0
  } catch (error) {
    const detail = error.response?.data?.detail || '搜索失败，请稍后重试。'
    ElMessage.error(detail)
  } finally {
    if (currentRequestId === requestId) {
      loading.value = false
    }
  }
}

const scheduleSearch = () => {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(fetchResults, 220)
}

const openSearch = () => {
  visible.value = true
  fetchResults()
  focusSearchInput()
}

const closeSearch = () => {
  visible.value = false
}

const isDiaryResult = (result) => result?.type === 'diary'

const openResult = (result, edit = false) => {
  closeSearch()
  if (isDiaryResult(result)) {
    router.push({ name: edit ? 'diary-edit' : 'diary', params: { date: result.diary_date } })
    return
  }

  router.push({ name: edit ? 'note-edit' : 'note-detail', params: { id: result.id } })
}

const openFirstResult = () => {
  if (results.value.length) {
    openResult(results.value[0])
  }
}

const resultTypeLabel = (result) => {
  if (isDiaryResult(result)) {
    return result.diary_date ? `日记 · ${result.diary_date}` : '日记'
  }

  return '笔记'
}

const handleKeydown = (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    openSearch()
  }
}

watch(keyword, () => {
  if (!visible.value) {
    return
  }

  scheduleSearch()
})

watch(visible, (isVisible) => {
  if (isVisible) {
    focusSearchInput()
  }
})

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  window.clearTimeout(searchTimer)
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <div class="global-search">
    <button
      class="global-search-button"
      :class="{ 'is-collapsed': compact }"
      type="button"
      :title="compact ? '全局搜索' : undefined"
      aria-label="全局搜索"
      @click="openSearch"
    >
      <el-icon class="search-icon"><Search /></el-icon>
      <span v-if="!compact">全局搜索</span>
    </button>

    <el-dialog
      v-model="visible"
      append-to-body
      align-center
      :show-close="false"
      width="min(92vw, 760px)"
      class="global-search-dialog"
      @opened="focusSearchInput"
    >
      <section class="search-command" aria-label="全局搜索">
        <header class="search-command-head">
          <div>
            <p>Search</p>
            <h2>全局搜索</h2>
          </div>
          <button class="search-close" type="button" aria-label="关闭搜索" @click="closeSearch">
            <el-icon><Close /></el-icon>
          </button>
        </header>

        <el-input
          ref="searchInput"
          v-model="keyword"
          class="command-input"
          clearable
          placeholder="搜索笔记、日记正文、标签或文件名"
          @keyup.enter="openFirstResult"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>

        <div class="search-summary">
          <span>{{ resultLabel }}</span>
          <span v-if="normalizedKeyword">“{{ normalizedKeyword }}”</span>
        </div>

        <section v-loading="loading" class="search-results">
          <div v-if="results.length" class="result-list">
            <article v-for="result in results" :key="`${result.type}-${result.id}`" class="result-row">
              <button class="result-main" type="button" @click="openResult(result)">
                <span class="result-icon">
                  <el-icon>
                    <Calendar v-if="isDiaryResult(result)" />
                    <Document v-else />
                  </el-icon>
                </span>
                <span class="result-copy">
                  <strong>
                    <template v-for="(part, index) in buildHighlightParts(result.title, normalizedKeyword)" :key="`title-${index}`">
                      <mark v-if="part.highlight" class="search-highlight">{{ part.text }}</mark>
                      <template v-else>{{ part.text }}</template>
                    </template>
                  </strong>
                  <span class="result-kind">{{ resultTypeLabel(result) }}</span>
                  <span v-if="!isDiaryResult(result) && result.tags?.length" class="result-tags">
                    <span v-for="tag in result.tags" :key="tag.id || tag.name">
                      <template v-for="(part, index) in buildHighlightParts(tag.name, normalizedKeyword)" :key="`tag-${tag.id || tag.name}-${index}`">
                        <mark v-if="part.highlight" class="search-highlight">{{ part.text }}</mark>
                        <template v-else>{{ part.text }}</template>
                      </template>
                    </span>
                  </span>
                  <span class="result-excerpt">
                    <template v-for="(part, index) in buildHighlightParts(result.excerpt, normalizedKeyword)" :key="`excerpt-${index}`">
                      <mark v-if="part.highlight" class="search-highlight">{{ part.text }}</mark>
                      <template v-else>{{ part.text }}</template>
                    </template>
                  </span>
                </span>
              </button>

              <div class="result-side">
                <span>{{ formatDateTime(result.updated_at) }}</span>
                <button type="button" aria-label="查看" @click="openResult(result)">
                  <el-icon><View /></el-icon>
                </button>
                <button type="button" aria-label="编辑" @click="openResult(result, true)">
                  <el-icon><EditPen /></el-icon>
                </button>
              </div>
            </article>
          </div>

          <div v-else class="search-empty">
            <el-icon><Search /></el-icon>
            <h3>{{ normalizedKeyword ? '没有找到匹配内容' : '还没有可搜索的内容' }}</h3>
            <p>{{ normalizedKeyword ? '换一个关键词再试试。' : '创建笔记或日记后会显示在这里。' }}</p>
          </div>
        </section>
      </section>
    </el-dialog>
  </div>
</template>

<style scoped>
.global-search-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  min-height: 44px;
  padding: 0 16px;
  border: 1px solid var(--border-soft);
  border-radius: 16px;
  background: var(--surface);
  color: var(--text-primary);
  font: inherit;
  font-weight: 700;
  cursor: pointer;
  transition:
    transform 0.2s ease,
    border-color 0.2s ease,
    background 0.2s ease,
    color 0.2s ease;
}

.global-search-button:hover {
  transform: translateY(-1px);
  border-color: var(--accent-border);
  background: var(--accent-soft);
  color: var(--accent);
}

.global-search-button.is-collapsed {
  width: 46px;
  height: 46px;
  min-height: 46px;
  padding: 0;
  border-radius: 18px;
}

.search-icon {
  font-size: 1rem;
  flex: 0 0 auto;
}

.search-command {
  display: grid;
  gap: 16px;
  color: var(--text-primary);
}

.search-command-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.search-command-head p,
.search-command-head h2,
.search-empty h3,
.search-empty p {
  margin: 0;
}

.search-command-head p {
  color: var(--text-muted);
  font-size: 0.76rem;
  font-weight: 800;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.search-command-head h2 {
  margin-top: 4px;
  color: var(--text-primary);
  font-size: 1.18rem;
  line-height: 1.2;
}

.search-close,
.result-side button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border-soft);
  background: var(--surface-soft);
  color: var(--text-secondary);
  cursor: pointer;
  transition:
    transform 0.18s ease,
    border-color 0.18s ease,
    background 0.18s ease,
    color 0.18s ease;
}

.search-close {
  width: 38px;
  height: 38px;
  border-radius: 14px;
}

.search-close:hover,
.result-side button:hover {
  transform: translateY(-1px);
  border-color: var(--accent-border);
  background: var(--accent-soft);
  color: var(--accent);
}

.command-input :deep(.el-input__wrapper) {
  min-height: 52px;
  border-radius: 16px;
  background: var(--surface-soft);
  box-shadow: 0 0 0 1px var(--border-soft);
}

.command-input :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px var(--accent-border);
}

.search-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: var(--text-muted);
  font-size: 0.84rem;
  font-weight: 700;
}

.search-results {
  min-height: 180px;
}

.result-list {
  display: grid;
  gap: 0;
  max-height: min(56svh, 520px);
  overflow-y: auto;
  padding-right: 6px;
}

.result-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: stretch;
  min-width: 0;
  padding: 14px 0;
  border: 0;
  border-bottom: 1px solid var(--border-soft);
  border-radius: 0;
  background: transparent;
}

.result-row:first-child {
  border-top: 1px solid var(--border-soft);
}

.result-row:hover {
  background: color-mix(in srgb, var(--surface-soft) 62%, transparent);
}

.result-main {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr);
  gap: 12px;
  align-items: flex-start;
  min-width: 0;
  padding: 0;
  border: none;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.result-icon {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: var(--accent-soft);
  color: var(--accent);
}

.result-copy {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.result-copy strong {
  overflow: hidden;
  color: var(--text-primary);
  font-size: 0.98rem;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.result-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.result-kind {
  width: fit-content;
  color: var(--text-muted);
  font-size: 0.76rem;
  font-weight: 800;
}

.result-tags span {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  background: var(--surface);
  color: var(--accent);
  font-size: 0.74rem;
  font-weight: 800;
}

.result-excerpt {
  display: -webkit-box;
  overflow: hidden;
  color: var(--text-muted);
  font-size: 0.84rem;
  line-height: 1.6;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.search-highlight {
  padding: 0 0.12em;
  border-radius: 4px;
  background: var(--search-highlight-bg);
  color: var(--search-highlight-text);
  font-weight: 800;
}

.result-side {
  display: grid;
  grid-template-columns: auto 34px 34px;
  gap: 8px;
  align-items: center;
  color: var(--text-muted);
  font-size: 0.78rem;
  font-weight: 700;
}

.result-side button {
  width: 34px;
  height: 34px;
  border-radius: 8px;
}

.search-empty {
  display: grid;
  justify-items: center;
  gap: 10px;
  padding: 42px 20px;
  border: 0;
  border-top: 1px solid var(--border-soft);
  border-bottom: 1px solid var(--border-soft);
  border-radius: 0;
  background: transparent;
  color: var(--text-muted);
  text-align: center;
}

.search-empty :deep(.el-icon) {
  color: var(--accent);
  font-size: 1.8rem;
}

.search-empty h3 {
  color: var(--text-primary);
  font-size: 1.05rem;
}

:global(.global-search-dialog.el-dialog) {
  overflow: hidden;
  border: 1px solid var(--border-soft);
  border-radius: 18px;
  background: var(--surface);
  box-shadow: var(--shadow-soft);
}

:global(.global-search-dialog.el-dialog .el-dialog__header) {
  display: none;
}

:global(.global-search-dialog.el-dialog .el-dialog__body) {
  padding: 22px;
}

@media (max-width: 640px) {
  .global-search-button {
    width: 100%;
  }

  .result-row {
    grid-template-columns: 1fr;
  }

  .result-side {
    grid-template-columns: minmax(0, 1fr) 36px 36px;
  }
}
</style>
