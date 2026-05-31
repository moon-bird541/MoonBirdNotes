<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Back, DocumentCopy, EditPen, Reading } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

import WorkspaceShell from '../components/WorkspaceShell.vue'
import api from '../services/api'
import '../styles/markdown.css'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const note = ref(null)

const tagNames = computed(() => note.value?.tags?.map((tag) => tag.name) || [])

const fetchNote = async () => {
  loading.value = true

  try {
    const { data } = await api.get(`/notes/${route.params.id}/`)
    note.value = data
  } catch (error) {
    const detail = error.response?.data?.detail || '获取笔记详情失败，请稍后重试。'
    ElMessage.error(detail)
  } finally {
    loading.value = false
  }
}

const goBack = () => {
  router.push('/notes')
}

const goToEdit = () => {
  router.push({ name: 'note-edit', params: { id: route.params.id } })
}

const formatDateTime = (value) => {
  if (!value) {
    return '-'
  }

  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

const formatWordCount = (value) => `${value || 0} 字`

onMounted(() => {
  fetchNote()
})
</script>

<template>
  <main class="detail-page page-shell">
    <WorkspaceShell>
      <section class="detail-stage" v-loading="loading">
        <template v-if="note">
          <header class="detail-header fade-rise-enter">
            <div class="detail-actions">
              <button class="back-button" type="button" @click="goBack">
                <el-icon><Back /></el-icon>
                <span>返回列表</span>
              </button>

              <el-button class="edit-button" type="primary" @click="goToEdit">
                <el-icon><EditPen /></el-icon>
                <span>编辑</span>
              </el-button>
            </div>

            <div class="title-block">
              <p class="detail-brand">Note Detail</p>
              <h1>{{ note.title }}</h1>

              <div class="tag-list" v-if="tagNames.length">
                <span v-for="tagName in tagNames" :key="tagName" class="tag-pill">
                  {{ tagName }}
                </span>
              </div>
            </div>
          </header>

          <section class="reader-layout fade-rise-enter-delay">
            <article class="reader-main">
              <div class="article-toolbar">
                <div>
                  <p>HTML Preview</p>
                  <span>{{ note.source_filename }}</span>
                </div>
              </div>

              <div class="article-content markdown-body" v-html="note.rendered_html"></div>
            </article>

            <aside class="reader-meta">
              <div class="meta-block">
                <el-icon><Reading /></el-icon>
                <span>字数</span>
                <strong>{{ formatWordCount(note.word_count) }}</strong>
              </div>

              <div class="meta-block">
                <el-icon><DocumentCopy /></el-icon>
                <span>原始文件</span>
                <a v-if="note.file_url" :href="note.file_url" target="_blank" rel="noreferrer">
                  {{ note.source_filename }}
                </a>
                <strong v-else>{{ note.source_filename }}</strong>
              </div>

              <div class="meta-line">
                <span>创建时间</span>
                <strong>{{ formatDateTime(note.created_at) }}</strong>
              </div>

              <div class="meta-line">
                <span>更新时间</span>
                <strong>{{ formatDateTime(note.updated_at) }}</strong>
              </div>
            </aside>
          </section>
        </template>

        <div v-else-if="!loading" class="empty-state fade-rise-enter">
          <h1>没有找到这篇笔记</h1>
          <p>它可能已经被移入回收站，或者当前账号没有访问权限。</p>
          <el-button type="primary" @click="goBack">返回笔记列表</el-button>
        </div>
      </section>
    </WorkspaceShell>
  </main>
</template>

<style scoped>
.detail-page {
  padding: 0 20px 20px 0;
}

.detail-stage {
  min-height: calc(100vh - 20px);
  min-height: calc(100svh - 20px);
  margin-top: 20px;
}

.detail-header {
  display: grid;
  gap: 24px;
}

.detail-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
}

.back-button {
  display: inline-flex;
  width: fit-content;
  align-items: center;
  gap: 8px;
  min-height: 42px;
  padding: 0 14px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.82);
  color: var(--brand-navy);
  cursor: pointer;
  transition:
    transform 0.2s ease,
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.back-button:hover {
  transform: translateY(-1px);
  border-color: rgba(37, 99, 235, 0.24);
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.08);
}

.edit-button {
  min-height: 42px;
  padding-inline: 18px;
  border: none;
  border-radius: 14px;
  background: linear-gradient(135deg, #1d4ed8 0%, #2563eb 52%, #f59e0b 170%);
  box-shadow: 0 14px 28px rgba(37, 99, 235, 0.2);
}

.title-block {
  max-width: 980px;
}

.detail-brand {
  margin: 0 0 12px;
  color: var(--brand-blue);
  font-size: 0.84rem;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.title-block h1 {
  margin: 0;
  color: var(--brand-navy);
  font-size: clamp(2.3rem, 4.5vw, 5.2rem);
  line-height: 0.98;
  letter-spacing: -0.06em;
}

.tag-list {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 22px;
}

.tag-pill {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 0 12px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.08);
  color: var(--brand-blue);
  font-size: 0.86rem;
  font-weight: 700;
}

.reader-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: 26px;
  align-items: start;
  margin-top: 34px;
}

.reader-main {
  min-width: 0;
  padding: 30px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 30px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.9), rgba(255, 255, 255, 0.72)),
    rgba(255, 255, 255, 0.72);
  box-shadow: var(--shadow-soft);
}

.article-toolbar {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 22px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.16);
}

.article-toolbar p {
  margin: 0 0 6px;
  color: var(--brand-navy);
  font-weight: 700;
}

.article-toolbar span {
  color: var(--ink-soft);
  font-size: 0.9rem;
  word-break: break-all;
}

.article-content {
  margin-top: 28px;
}

.reader-meta {
  position: sticky;
  top: 22px;
  display: grid;
  gap: 14px;
}

.meta-block,
.meta-line {
  padding: 18px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.78);
}

.meta-block {
  display: grid;
  gap: 8px;
}

.meta-block :deep(.el-icon) {
  color: var(--brand-blue);
  font-size: 1.25rem;
}

.meta-block span,
.meta-line span {
  color: var(--ink-soft);
  font-size: 0.86rem;
}

.meta-block strong,
.meta-block a,
.meta-line strong {
  color: var(--brand-navy);
  font-weight: 700;
  word-break: break-all;
}

.meta-block a {
  color: var(--brand-blue);
}

.meta-line {
  display: grid;
  gap: 8px;
}

.empty-state {
  display: grid;
  gap: 14px;
  max-width: 560px;
  padding: 48px 0;
}

.empty-state h1 {
  margin: 0;
  color: var(--brand-navy);
  font-size: 2.4rem;
  letter-spacing: -0.04em;
}

.empty-state p {
  margin: 0;
  color: var(--ink-soft);
  line-height: 1.8;
}

@media (max-width: 1320px) {
  .reader-layout {
    grid-template-columns: 1fr;
  }

  .reader-meta {
    position: static;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 980px) {
  .detail-page {
    padding: 0 16px 16px;
  }

  .detail-stage {
    min-height: auto;
    margin-top: 0;
  }
}

@media (max-width: 720px) {
  .detail-actions {
    align-items: stretch;
  }

  .detail-actions :deep(.el-button),
  .back-button {
    width: 100%;
    justify-content: center;
  }

  .title-block h1 {
    font-size: 2.1rem;
  }

  .reader-main {
    padding: 22px;
    border-radius: 24px;
  }

  .reader-meta {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 520px) {
  .reader-main {
    padding: 18px 16px;
    border-radius: 20px;
  }

  .meta-block,
  .meta-line {
    padding: 16px;
    border-radius: 18px;
  }

  .article-toolbar {
    padding-bottom: 18px;
  }

  .article-content {
    margin-top: 22px;
  }
}
</style>
