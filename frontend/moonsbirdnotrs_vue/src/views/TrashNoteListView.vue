<script setup>
import { computed, onMounted, ref } from 'vue'
import { DeleteFilled, RefreshRight, WarningFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import WorkspaceShell from '../components/WorkspaceShell.vue'
import api from '../services/api'

const loading = ref(false)
const notes = ref([])
const currentPage = ref(1)
const pageSize = ref(10)
const total = ref(0)

const totalPages = computed(() => {
  if (!total.value) {
    return 0
  }
  return Math.ceil(total.value / pageSize.value)
})

const fetchTrashNotes = async (page = 1) => {
  loading.value = true

  try {
    const { data } = await api.get('/notes/trash/', {
      params: { page },
    })

    notes.value = data.results
    total.value = data.count
    currentPage.value = page
  } catch (error) {
    const detail = error.response?.data?.detail || '获取回收站列表失败，请稍后重试。'
    ElMessage.error(detail)
  } finally {
    loading.value = false
  }
}

const handlePageChange = (page) => {
  fetchTrashNotes(page)
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

const resolveNextPage = () => {
  return notes.value.length === 1 && currentPage.value > 1
    ? currentPage.value - 1
    : currentPage.value
}

const restoreNote = async (note) => {
  try {
    await ElMessageBox.confirm(
      `确定要恢复《${note.title}》吗？`,
      '恢复确认',
      {
        confirmButtonText: '确认恢复',
        cancelButtonText: '取消',
        type: 'info',
      }
    )
  } catch {
    return
  }

  try {
    await api.put(`/notes/trash/${note.id}/restore/`)
    ElMessage.success('笔记已恢复到正常列表。')
    fetchTrashNotes(resolveNextPage())
  } catch (error) {
    const detail = error.response?.data?.detail || '恢复笔记失败，请稍后重试。'
    ElMessage.error(detail)
  }
}

const destroyNote = async (note) => {
  try {
    await ElMessageBox.confirm(
      `确定要彻底删除《${note.title}》吗？此操作不可恢复。`,
      '彻底删除确认',
      {
        confirmButtonText: '彻底删除',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
  } catch {
    return
  }

  try {
    await api.delete(`/notes/trash/${note.id}/destroy/`)
    ElMessage.success('笔记已彻底删除。')
    fetchTrashNotes(resolveNextPage())
  } catch (error) {
    const detail = error.response?.data?.detail || '彻底删除失败，请稍后重试。'
    ElMessage.error(detail)
  }
}

onMounted(() => {
  fetchTrashNotes()
})
</script>

<template>
  <main class="trash-page page-shell">
    <WorkspaceShell>
      <section class="trash-stage">
        <header class="trash-header fade-rise-enter">
          <div class="header-copy">
            <p class="trash-brand">Recycle Zone</p>
            <h1>回收站</h1>
            <p class="trash-subtitle">
              这里不是阅读区，而是待处理区。被移入回收站的笔记暂时保留，你可以选择恢复，或彻底删除。
            </p>
          </div>

          <div class="status-panel">
            <div class="status-chip">
              <el-icon><WarningFilled /></el-icon>
              <span>高风险操作区</span>
            </div>
            <p>彻底删除后，数据库记录与原始 Markdown 文件都会被移除，且无法恢复。</p>
          </div>
        </header>

        <section class="trash-board fade-rise-enter-delay">
          <div class="board-top">
            <div class="board-title">
              <p class="board-kicker">Pending Disposal</p>
              <h2>待处理内容</h2>
            </div>

            <div class="board-summary">
              <div class="summary-card">
                <span>当前数量</span>
                <strong>{{ total }}</strong>
              </div>
              <div class="summary-card" v-if="totalPages">
                <span>当前页</span>
                <strong>{{ currentPage }} / {{ totalPages }}</strong>
              </div>
            </div>
          </div>

          <div v-loading="loading" class="trash-list-shell">
            <div v-if="notes.length" class="trash-list">
              <article v-for="note in notes" :key="note.id" class="trash-row">
                <div class="row-mark">
                  <span class="mark-dot"></span>
                </div>

                <div class="row-main">
                  <div class="row-head">
                    <h3>{{ note.title }}</h3>
                    <span class="danger-tag">已删除</span>
                  </div>

                  <p class="row-excerpt">{{ note.excerpt }}</p>

                  <div class="row-meta">
                    <span>删除前更新：{{ formatDateTime(note.updated_at) }}</span>
                    <span>字数：{{ formatWordCount(note.word_count) }}</span>
                  </div>
                </div>

                <div class="row-actions">
                  <el-button class="restore-button" plain @click="restoreNote(note)">
                    <el-icon><RefreshRight /></el-icon>
                    <span>恢复</span>
                  </el-button>

                  <el-button class="destroy-button" type="danger" @click="destroyNote(note)">
                    <el-icon><DeleteFilled /></el-icon>
                    <span>彻底删除</span>
                  </el-button>
                </div>
              </article>
            </div>

            <div v-else class="empty-state">
              <div class="empty-badge">Clear</div>
              <h3>回收站为空</h3>
              <p>当前没有需要恢复或彻底删除的笔记。</p>
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
  </main>
</template>

<style scoped>
.trash-page {
  padding: 0 20px 20px 0;
}

.trash-stage {
  margin-top: 20px;
}

.trash-header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 24px;
  align-items: stretch;
}

.header-copy {
  max-width: 760px;
}

.trash-brand,
.board-kicker {
  margin: 0 0 12px;
  color: #dc2626;
  font-size: 0.84rem;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.trash-header h1 {
  margin: 0;
  color: #1f2937;
  font-size: clamp(2.5rem, 4vw, 4.9rem);
  line-height: 0.96;
  letter-spacing: -0.07em;
}

.trash-subtitle {
  max-width: 620px;
  margin: 18px 0 0;
  color: #6b7280;
  line-height: 1.9;
}

.status-panel {
  display: grid;
  align-content: start;
  gap: 12px;
  padding: 22px 22px 18px;
  border: 1px solid rgba(220, 38, 38, 0.16);
  border-radius: 24px;
  background:
    linear-gradient(180deg, rgba(255, 245, 245, 0.96), rgba(255, 250, 250, 0.9)),
    rgba(255, 255, 255, 0.72);
  box-shadow: 0 18px 36px rgba(127, 29, 29, 0.08);
}

.status-chip {
  display: inline-flex;
  width: fit-content;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(220, 38, 38, 0.08);
  color: #b91c1c;
  font-size: 0.9rem;
  font-weight: 700;
}

.status-panel p {
  margin: 0;
  color: #7f1d1d;
  line-height: 1.75;
}

.trash-board {
  margin-top: 34px;
  padding: 28px;
  border: 1px solid rgba(248, 113, 113, 0.18);
  border-radius: 30px;
  background:
    linear-gradient(180deg, rgba(255, 250, 250, 0.98), rgba(255, 255, 255, 0.92)),
    rgba(255, 255, 255, 0.82);
  box-shadow: 0 22px 42px rgba(15, 23, 42, 0.08);
}

.board-top {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
}

.board-title h2 {
  margin: 0;
  color: #111827;
  font-size: 1.9rem;
  line-height: 1.04;
  letter-spacing: -0.05em;
}

.board-summary {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.summary-card {
  min-width: 114px;
  padding: 12px 14px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.88);
}

.summary-card span {
  display: block;
  margin-bottom: 8px;
  color: #6b7280;
  font-size: 0.8rem;
}

.summary-card strong {
  color: #111827;
  font-size: 1rem;
}

.trash-list-shell {
  margin-top: 26px;
}

.trash-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.trash-row {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr) 210px;
  gap: 18px;
  align-items: center;
  padding: 20px 20px 20px 18px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 24px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.94), rgba(255, 248, 248, 0.92)),
    rgba(255, 255, 255, 0.92);
}

.row-mark {
  display: flex;
  justify-content: center;
}

.mark-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: linear-gradient(135deg, #ef4444, #f59e0b);
  box-shadow: 0 0 0 6px rgba(239, 68, 68, 0.08);
}

.row-head {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.row-head h3 {
  margin: 0;
  color: #111827;
  font-size: 1.18rem;
  line-height: 1.25;
  letter-spacing: -0.03em;
}

.danger-tag {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(220, 38, 38, 0.08);
  color: #b91c1c;
  font-size: 0.76rem;
  font-weight: 700;
}

.row-excerpt {
  margin: 10px 0 0;
  color: #6b7280;
  font-size: 0.95rem;
  line-height: 1.75;
}

.row-meta {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
  margin-top: 14px;
  color: #9ca3af;
  font-size: 0.86rem;
}

.row-actions {
  display: grid;
  gap: 10px;
}

.restore-button,
.destroy-button {
  min-height: 42px;
  border-radius: 14px;
}

.destroy-button {
  box-shadow: 0 14px 28px rgba(220, 38, 38, 0.16);
}

.empty-state {
  display: grid;
  justify-items: start;
  gap: 10px;
  padding: 42px 4px 18px;
}

.empty-badge {
  display: inline-flex;
  align-items: center;
  padding: 7px 12px;
  border-radius: 999px;
  background: rgba(16, 185, 129, 0.1);
  color: #047857;
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.empty-state h3 {
  margin: 0;
  color: #111827;
  font-size: 1.4rem;
}

.empty-state p {
  margin: 0;
  color: #6b7280;
  line-height: 1.8;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 26px;
}

@media (max-width: 1120px) {
  .trash-header {
    grid-template-columns: 1fr;
  }

  .trash-row {
    grid-template-columns: 18px 1fr;
  }

  .row-actions {
    grid-column: 2;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 980px) {
  .trash-page {
    padding: 0 16px 16px;
  }

  .trash-stage {
    margin-top: 0;
  }
}

@media (max-width: 720px) {
  .board-top {
    flex-direction: column;
    align-items: flex-start;
  }

  .trash-board {
    padding: 22px;
    border-radius: 24px;
  }

  .trash-row {
    padding: 18px 16px;
  }

  .row-actions {
    grid-template-columns: 1fr;
  }

  .row-meta {
    gap: 10px;
  }
}

@media (max-width: 520px) {
  .status-panel,
  .trash-board {
    padding-inline: 16px;
    border-radius: 20px;
  }

  .trash-row {
    grid-template-columns: 1fr;
    gap: 14px;
    padding: 16px;
  }

  .row-mark {
    display: none;
  }

  .row-actions {
    grid-column: auto;
  }

  .row-actions :deep(.el-button) {
    width: 100%;
  }

  .pagination-wrap {
    justify-content: center;
  }
}
</style>
