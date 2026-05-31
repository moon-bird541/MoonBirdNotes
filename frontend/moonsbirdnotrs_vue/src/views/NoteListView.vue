<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MoreFilled } from '@element-plus/icons-vue'

import WorkspaceShell from '../components/WorkspaceShell.vue'
import api from '../services/api'

const router = useRouter()
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

// 列表页继续沿用后端分页，避免笔记变多后一次性加载过重。
const fetchNotes = async (page = 1) => {
  loading.value = true

  try {
    const { data } = await api.get('/notes/', {
      params: {
        page,
      },
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

  if (command !== 'delete') {
    return
  }

  await handleDelete(note)
}

const handleDelete = async (note) => {
  try {
    await ElMessageBox.confirm(
      `确定要将《${note.title}》移入回收站吗？`,
      '删除确认',
      {
        confirmButtonText: '确认删除',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
  } catch {
    return
  }

  try {
    await api.delete(`/notes/${note.id}/delete/`)
    ElMessage.success('笔记已移入回收站。')

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

onMounted(() => {
  fetchNotes()
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
            </div>
          </div>

          <div v-loading="loading" class="stream-shell">
            <div v-if="notes.length" class="note-stream">
              <article v-for="note in notes" :key="note.id" class="note-row">
                <button class="note-main" type="button" @click="goToDetail(note)">
                  <h3>{{ note.title }}</h3>
                  <div v-if="note.tags?.length" class="note-tags" aria-label="笔记标签">
                    <span v-for="tag in note.tags" :key="tag.id || tag.name" class="note-tag">
                      {{ tag.name }}
                    </span>
                  </div>
                  <p class="note-excerpt">{{ note.excerpt }}</p>
                </button>

                <aside class="note-side">
                  <div class="note-meta">
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
                  >
                    <button class="more-button" type="button" aria-label="更多操作">
                      <el-icon><MoreFilled /></el-icon>
                    </button>

                    <template #dropdown>
                      <el-dropdown-menu>
                        <el-dropdown-item command="detail">查看详情</el-dropdown-item>
                        <el-dropdown-item command="edit">编辑</el-dropdown-item>
                        <el-dropdown-item command="delete">删除</el-dropdown-item>
                      </el-dropdown-menu>
                    </template>
                  </el-dropdown>
                </aside>
              </article>
            </div>

            <div v-else class="empty-state">
              <p>当前还没有笔记，先上传一篇 Markdown 笔记吧。</p>
              <el-button class="empty-action" type="primary" @click="goToUpload">去上传</el-button>
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
.notes-page {
  padding: 0 20px 20px 0;
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
  border-radius: 16px;
  background: linear-gradient(135deg, #1d4ed8 0%, #2563eb 46%, #f59e0b 160%);
  box-shadow: 0 18px 36px rgba(37, 99, 235, 0.24);
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
  gap: 14px;
  flex-wrap: wrap;
  color: var(--ink-soft);
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
  grid-template-columns: minmax(0, 1fr) 280px;
  gap: 28px;
  align-items: start;
  padding: 24px 6px;
  border-top: 1px solid rgba(148, 163, 184, 0.16);
}

.note-row:first-child {
  border-top: none;
  padding-top: 4px;
}

.note-main h3 {
  margin: 0;
  color: var(--brand-navy);
  font-size: clamp(1.3rem, 2vw, 2rem);
  line-height: 1.18;
  letter-spacing: -0.04em;
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
  border-radius: 14px;
  background: linear-gradient(135deg, #1d4ed8 0%, #2563eb 46%, #f59e0b 160%);
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 26px;
}

@media (max-width: 1100px) {
  .note-row {
    grid-template-columns: 1fr;
    gap: 16px;
  }

  .note-side,
  .note-meta {
    justify-content: flex-start;
  }

  .note-side {
    align-items: center;
    align-self: start;
  }

  .meta-block {
    align-items: center;
    text-align: center;
  }
}

@media (max-width: 980px) {
  .notes-page {
    padding: 0 16px 16px;
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

  .notes-actions,
  .notes-actions :deep(.el-button) {
    width: 100%;
  }

  .notes-board {
    padding: 22px 22px 18px;
    border-radius: 24px;
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
