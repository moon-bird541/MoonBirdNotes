<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CollectionTag, Connection, Delete, EditPen, Search } from '@element-plus/icons-vue'

import WorkspaceShell from '../components/WorkspaceShell.vue'
import api from '../services/api'

const loading = ref(false)
const tags = ref([])
const filterKeyword = ref('')
const mergeDialogVisible = ref(false)
const mergeSource = ref(null)
const mergeTargetId = ref('')
const merging = ref(false)

const filteredTags = computed(() => {
  const keyword = filterKeyword.value.trim().toLowerCase()

  if (!keyword) {
    return tags.value
  }

  return tags.value.filter((tag) => tag.name.toLowerCase().includes(keyword))
})

const usedTagCount = computed(() => tags.value.filter((tag) => Number(tag.note_count || 0) > 0).length)
const unusedTagCount = computed(() => tags.value.length - usedTagCount.value)
const mergeTargetOptions = computed(() => tags.value.filter((tag) => tag.id !== mergeSource.value?.id))
const selectedTargetName = computed(() => {
  const target = tags.value.find((tag) => tag.id === mergeTargetId.value)
  return target?.name || ''
})

const fetchTags = async () => {
  loading.value = true

  try {
    const { data } = await api.get('/notes/tags/')
    tags.value = data
  } catch (error) {
    const detail = error.response?.data?.detail || '获取标签列表失败，请稍后重试。'
    ElMessage.error(detail)
  } finally {
    loading.value = false
  }
}

const handleRename = async (tag) => {
  let nextName = ''

  try {
    const { value } = await ElMessageBox.prompt('请输入新的标签名称', `重命名：${tag.name}`, {
      confirmButtonText: '保存',
      cancelButtonText: '取消',
      inputValue: tag.name,
      inputPattern: /\S+/,
      inputErrorMessage: '标签名称不能为空。',
      customClass: 'beautiful-confirm-box',
    })
    nextName = value.trim()
  } catch {
    return
  }

  try {
    await api.patch(`/notes/tags/${tag.id}/`, {
      name: nextName,
    })
    ElMessage.success('标签已重命名。')
    fetchTags()
  } catch (error) {
    const detail = error.response?.data?.name?.[0] || error.response?.data?.detail || '重命名失败，请稍后重试。'
    ElMessage.error(detail)
  }
}

const handleDelete = async (tag) => {
  try {
    await ElMessageBox.confirm(
      `确定删除标签“${tag.name}”吗？笔记不会被删除，但会移除这个标签。`,
      '删除标签',
      {
        confirmButtonText: '确认删除',
        cancelButtonText: '取消',
        type: 'warning',
        customClass: 'beautiful-confirm-box',
        confirmButtonClass: 'beautiful-confirm-button',
        cancelButtonClass: 'beautiful-cancel-button',
      }
    )
  } catch {
    return
  }

  try {
    await api.delete(`/notes/tags/${tag.id}/`)
    ElMessage.success('标签已删除。')
    fetchTags()
  } catch (error) {
    const detail = error.response?.data?.detail || '删除标签失败，请稍后重试。'
    ElMessage.error(detail)
  }
}

const openMergeDialog = (tag) => {
  mergeSource.value = tag
  mergeTargetId.value = ''
  mergeDialogVisible.value = true
}

const confirmMerge = async () => {
  if (!mergeSource.value || !mergeTargetId.value) {
    ElMessage.warning('请选择要合并到的目标标签。')
    return
  }

  merging.value = true

  try {
    await api.post(`/notes/tags/${mergeSource.value.id}/merge/`, {
      target_tag_id: mergeTargetId.value,
    })
    ElMessage.success(`已合并到“${selectedTargetName.value}”。`)
    mergeDialogVisible.value = false
    fetchTags()
  } catch (error) {
    const detail =
      error.response?.data?.target_tag_id?.[0] ||
      error.response?.data?.detail ||
      '合并标签失败，请稍后重试。'
    ElMessage.error(detail)
  } finally {
    merging.value = false
  }
}

const formatNoteCount = (value) => `${Number(value || 0)} 篇`

onMounted(() => {
  fetchTags()
})
</script>

<template>
  <main class="tags-page page-shell">
    <WorkspaceShell>
      <section class="tags-stage">
        <header class="tags-header fade-rise-enter">
          <div class="header-copy">
            <p class="tags-brand">MoonBirdNotes</p>
            <h1>标签管理</h1>
            <p class="tags-subtitle">整理标签名称，合并重复分类，让笔记归档保持清晰。</p>
          </div>
        </header>

        <section class="tags-board fade-rise-enter-delay">
          <div class="board-top">
            <div>
              <p class="board-kicker">Tags</p>
              <h2>标签库</h2>
            </div>

            <div class="board-summary">
              <span>共 {{ tags.length }} 个</span>
              <span>使用中 {{ usedTagCount }} 个</span>
              <span>未使用 {{ unusedTagCount }} 个</span>
            </div>
          </div>

          <div class="tag-toolbar">
            <el-input
              v-model="filterKeyword"
              class="tag-search"
              clearable
              placeholder="搜索标签名称"
            >
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
          </div>

          <div v-loading="loading" class="tag-list-shell">
            <div v-if="filteredTags.length" class="tag-list">
              <article v-for="tag in filteredTags" :key="tag.id" class="tag-row">
                <div class="tag-main">
                  <span class="tag-icon">
                    <el-icon><CollectionTag /></el-icon>
                  </span>
                  <div>
                    <h3>{{ tag.name }}</h3>
                    <p>{{ formatNoteCount(tag.note_count) }}</p>
                  </div>
                </div>

                <div class="tag-actions">
                  <el-button :icon="EditPen" @click="handleRename(tag)">重命名</el-button>
                  <el-button :icon="Connection" :disabled="tags.length < 2" @click="openMergeDialog(tag)">合并</el-button>
                  <el-button class="danger-action" :icon="Delete" @click="handleDelete(tag)">删除</el-button>
                </div>
              </article>
            </div>

            <div v-else class="empty-state">
              <p>{{ filterKeyword ? '没有找到匹配的标签。' : '当前还没有标签。' }}</p>
            </div>
          </div>
        </section>
      </section>
    </WorkspaceShell>

    <el-dialog
      v-model="mergeDialogVisible"
      class="tag-merge-dialog"
      width="min(92vw, 460px)"
      title="合并标签"
    >
      <div class="merge-dialog-body">
        <p>
          将“{{ mergeSource?.name }}”合并到：
        </p>
        <el-select v-model="mergeTargetId" class="merge-target-select" placeholder="选择目标标签">
          <el-option
            v-for="tag in mergeTargetOptions"
            :key="tag.id"
            :label="tag.name"
            :value="tag.id"
          />
        </el-select>
      </div>

      <template #footer>
        <el-button @click="mergeDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="merging" @click="confirmMerge">确认合并</el-button>
      </template>
    </el-dialog>
  </main>
</template>

<style scoped>
.tags-page {
  padding: 20px;
}

.tags-stage {
  margin-top: 20px;
}

.tags-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
}

.header-copy {
  max-width: 700px;
}

.tags-brand,
.board-kicker {
  margin: 0 0 12px;
  color: var(--brand-blue);
  font-size: 0.84rem;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.tags-header h1 {
  margin: 0;
  color: var(--brand-navy);
  font-size: 4rem;
  line-height: 0.98;
}

.tags-subtitle {
  max-width: 560px;
  margin: 18px 0 0;
  color: var(--ink-soft);
  line-height: 1.9;
}

.tags-board {
  margin-top: 34px;
  padding: 30px 30px 24px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: var(--radius-lg);
  background: var(--surface);
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
}

.board-summary {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  color: var(--ink-soft);
}

.tag-toolbar {
  margin-top: 22px;
  padding: 14px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: var(--radius-lg);
  background: var(--surface-soft);
}

.tag-search {
  max-width: 420px;
}

.tag-search :deep(.el-input__wrapper) {
  min-height: 46px;
  border-radius: var(--radius-md);
  background: var(--control-background);
  box-shadow: none;
}

.tag-search :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px rgba(37, 99, 235, 0.26);
}

.tag-list-shell {
  margin-top: 24px;
}

.tag-list {
  display: flex;
  flex-direction: column;
}

.tag-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 18px;
  align-items: center;
  padding: 20px 6px;
  border-top: 1px solid rgba(148, 163, 184, 0.16);
}

.tag-row:first-child {
  border-top: none;
}

.tag-main {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}

.tag-icon {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  border: 1px solid rgba(37, 99, 235, 0.1);
  border-radius: var(--radius-md);
  background: rgba(37, 99, 235, 0.07);
  color: var(--brand-blue);
}

.tag-main h3 {
  overflow: hidden;
  margin: 0;
  color: var(--brand-navy);
  font-size: 1.2rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tag-main p {
  margin: 8px 0 0;
  color: var(--ink-soft);
}

.tag-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.tag-actions :deep(.el-button) {
  min-height: 40px;
  margin-left: 0;
  border-radius: var(--radius-md);
}

.danger-action {
  color: var(--danger);
}

.empty-state {
  padding: 36px 6px 12px;
  color: var(--ink-soft);
}

.empty-state p {
  margin: 0;
  line-height: 1.8;
}

.merge-dialog-body {
  display: grid;
  gap: 14px;
}

.merge-dialog-body p {
  margin: 0;
  color: var(--ink-soft);
  line-height: 1.7;
}

.merge-target-select {
  width: 100%;
}

@media (max-width: 980px) {
  .tags-page {
    padding: 16px;
  }

  .tags-stage {
    margin-top: 0;
  }
}

@media (max-width: 720px) {
  .tags-header,
  .board-top {
    flex-direction: column;
    align-items: flex-start;
  }

  .tag-row {
    grid-template-columns: 1fr;
  }

  .tags-board {
    padding: 22px 22px 18px;
    border-radius: 24px;
  }

  .tags-header h1 {
    font-size: 2.4rem;
  }

  .tag-search,
  .tag-actions,
  .tag-actions :deep(.el-button) {
    width: 100%;
  }

  .tag-actions {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
