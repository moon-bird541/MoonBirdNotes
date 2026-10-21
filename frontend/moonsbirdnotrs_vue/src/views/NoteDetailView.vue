<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeftBold, ArrowRightBold, Back, DocumentCopy, Download, EditPen, Reading } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import Viewer from '@toast-ui/editor/viewer'

import '@toast-ui/editor/dist/toastui-editor-viewer.css'

import WorkspaceShell from '../components/WorkspaceShell.vue'
import api from '../services/api'
import { EDITOR_SETTINGS_CHANGE_EVENT, getEditorSettings } from '../utils/editorSettings'
import { exportNoteFile, getNoteExportErrorDetail } from '../utils/noteExport'
import { enhanceRichContent } from '../utils/richContent'
import { applyTableLayoutsToTables, extractTableLayoutMetadata } from '../utils/tableLayout'
import '../styles/markdown.css'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const note = ref(null)
const articleViewer = ref(null)
const readerMetaCollapsed = ref(false)
const editorSettings = ref(getEditorSettings())
const exportingFormat = ref('')

let viewerInstance = null
let viewerTableLayouts = []

const tagNames = computed(() => note.value?.tags?.map((tag) => tag.name) || [])
const readerFontSizeStyle = computed(() => ({
  '--reader-font-size': `${editorSettings.value.fontSizePx}px`,
}))
const importanceRateColors = ['var(--brand-blue)', 'var(--brand-blue)', 'var(--brand-blue)']

const fetchNote = async () => {
  loading.value = true

  try {
    const { data } = await api.get(`/notes/${route.params.id}/`)
    note.value = data
    await nextTick()
    renderViewerContent()
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

const exportNote = async (format) => {
  if (!note.value || exportingFormat.value) {
    return
  }

  exportingFormat.value = format

  try {
    await exportNoteFile(note.value, format)
    ElMessage.success('笔记导出已开始。')
  } catch (error) {
    const detail = await getNoteExportErrorDetail(error) || '导出失败，请稍后重试。'
    ElMessage.error(detail)
  } finally {
    exportingFormat.value = ''
  }
}

const toggleReaderMeta = () => {
  readerMetaCollapsed.value = !readerMetaCollapsed.value
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
const normalizeImportance = (value) => Number(value || 0)

const renderViewerContent = () => {
  if (!articleViewer.value) {
    return
  }

  const parsedMarkdown = extractTableLayoutMetadata(note.value?.markdown_content || '')
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
      // 表格布局应用完再增强，避免公式/提示框改变布局后表格被重排
      enhanceRichContent(articleViewer.value)
      window.requestAnimationFrame(applyViewerTableLayouts)
    })
  }

  if (!viewerInstance) {
    viewerInstance = new Viewer({
      el: articleViewer.value,
      initialValue: parsedMarkdown.markdown,
      usageStatistics: false,
    })
    scheduleViewerTableLayouts()
    return
  }

  viewerInstance.setMarkdown(parsedMarkdown.markdown)
  scheduleViewerTableLayouts()
}

const handleEditorSettingsChange = (event) => {
  editorSettings.value = event.detail || getEditorSettings()
}

onMounted(async () => {
  window.addEventListener(EDITOR_SETTINGS_CHANGE_EVENT, handleEditorSettingsChange)
  await fetchNote()
})

onBeforeUnmount(() => {
  window.removeEventListener(EDITOR_SETTINGS_CHANGE_EVENT, handleEditorSettingsChange)
  viewerInstance?.destroy()
  viewerInstance = null
})
</script>

<template>
  <main class="detail-page page-shell">
    <WorkspaceShell>
      <section class="detail-stage" v-loading="loading" :style="readerFontSizeStyle">
        <template v-if="note">
          <header class="detail-header fade-rise-enter">
            <div class="detail-actions">
              <button class="back-button" type="button" @click="goBack">
                <el-icon><Back /></el-icon>
                <span>返回列表</span>
              </button>

              <div class="detail-action-group">
                <el-button class="edit-button" type="primary" @click="goToEdit">
                  <el-icon><EditPen /></el-icon>
                  <span>编辑</span>
                </el-button>

                <el-dropdown trigger="click" popper-class="export-dropdown-popper" @command="exportNote">
                  <el-button class="export-button" :loading="Boolean(exportingFormat)">
                    <el-icon><Download /></el-icon>
                    <span>导出</span>
                  </el-button>

                  <template #dropdown>
                    <el-dropdown-menu class="export-dropdown-menu">
                      <el-dropdown-item command="markdown" class="export-dropdown-item">
                        <el-icon><DocumentCopy /></el-icon>
                        <span>Markdown</span>
                      </el-dropdown-item>
                      <el-dropdown-item command="html" class="export-dropdown-item">
                        <el-icon><Download /></el-icon>
                        <span>HTML</span>
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
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

          <section
            class="reader-layout fade-rise-enter-delay"
            :class="{ 'is-meta-collapsed': readerMetaCollapsed }"
          >
            <article class="reader-main">
              <div class="article-toolbar">
                <div>
                  <p>HTML Preview</p>
                  <span>{{ note.source_filename }}</span>
                </div>
                <button
                  v-if="readerMetaCollapsed"
                  type="button"
                  class="reader-meta-toggle"
                  @click="toggleReaderMeta"
                >
                  <el-icon><ArrowLeftBold /></el-icon>
                  <span>显示信息</span>
                </button>
              </div>

              <div ref="articleViewer" class="article-content detail-viewer blog-prose"></div>
            </article>

            <aside v-show="!readerMetaCollapsed" class="reader-meta">
              <button
                type="button"
                class="reader-meta-toggle reader-meta-toggle-hide"
                @click="toggleReaderMeta"
              >
                <el-icon><ArrowRightBold /></el-icon>
                <span>隐藏信息</span>
              </button>

              <div class="meta-block">
                <el-icon><Reading /></el-icon>
                <span>字数</span>
                <strong>{{ formatWordCount(note.word_count) }}</strong>
              </div>

              <div class="meta-block detail-importance-block">
                <span>重要程度</span>
                <el-rate
                  :model-value="normalizeImportance(note.importance)"
                  :max="5"
                  allow-half
                  disabled
                  :colors="importanceRateColors"
                  void-color="var(--border-soft)"
                />
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
  padding: 20px;
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

.detail-action-group {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.back-button {
  display: inline-flex;
  width: fit-content;
  align-items: center;
  gap: 8px;
  min-height: 42px;
  padding: 0 14px;
  border: 1px solid var(--border-soft);
  border-radius: 14px;
  background: var(--control-background);
  color: var(--brand-navy);
  cursor: pointer;
  transition:
    transform 0.2s ease,
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.back-button:hover {
  transform: translateY(-1px);
  border-color: var(--accent-border);
  box-shadow: var(--shadow-subtle);
}

.edit-button {
  min-height: 42px;
  padding-inline: 18px;
  border: none;
  border-radius: var(--radius-md);
  background: var(--brand-blue);
  box-shadow: none;
}

.export-button {
  min-height: 42px;
  padding-inline: 16px;
  border: 1px solid var(--border-soft);
  border-radius: 14px;
  background: var(--control-background);
  color: var(--brand-navy);
  font-weight: 700;
}

.export-button:hover,
.export-button:focus {
  border-color: var(--accent-border);
  background: var(--accent-soft);
  color: var(--brand-blue);
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
  background: var(--accent-soft);
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

.reader-layout.is-meta-collapsed {
  grid-template-columns: minmax(0, 1fr);
}

.reader-main {
  min-width: 0;
  padding: 30px;
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-lg);
  background: var(--panel-background);
  box-shadow: var(--shadow-soft);
}

.article-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 22px;
  border-bottom: 1px solid var(--divider);
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

.reader-meta-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 38px;
  padding: 0 12px;
  border: 1px solid var(--border-soft);
  border-radius: 8px;
  background: var(--control-background);
  color: var(--brand-navy);
  font-size: 0.84rem;
  font-weight: 700;
  cursor: pointer;
  transition:
    transform 0.18s ease,
    border-color 0.18s ease,
    background-color 0.18s ease,
    color 0.18s ease,
    box-shadow 0.18s ease;
}

.reader-meta-toggle:hover,
.reader-meta-toggle:focus-visible {
  transform: translateY(-1px);
  border-color: var(--accent-border);
  background: var(--accent-soft);
  color: var(--brand-blue);
  box-shadow: var(--shadow-subtle);
  outline: none;
}

.reader-meta-toggle :deep(.el-icon) {
  font-size: 0.88rem;
}

.article-content {
  margin-top: 28px;
}

/* 阅读区排版统一由全局 styles/blog-prose.css 提供（对齐博客），
   这里只保留 toast-ui 结构相关的必要修正。 */
.detail-viewer :deep(.toastui-editor-contents) {
  max-width: 100%;
  overflow-x: hidden;
  font-size: var(--reader-font-size, 1rem);
}

/* toast-ui 为表格布局生成的辅助列，不应展示 */
.detail-viewer :deep(.toastui-editor-contents th[extended]),
.detail-viewer :deep(.toastui-editor-contents td[extended]) {
  display: none;
}

/* toast-ui 的所见即所得代码块自带内边距，交由 blog-prose 统一外观 */
.detail-viewer :deep(.toastui-editor-contents .toastui-editor-ww-code-block pre) {
  margin: 0;
  border: none;
  border-radius: 0;
  background: transparent;
}

.reader-meta {
  position: sticky;
  top: 22px;
  display: grid;
  gap: 14px;
  align-self: start;
}

.reader-meta-toggle-hide {
  width: 100%;
  background: var(--control-background);
}

.meta-block,
.meta-line {
  padding: 18px;
  border: 1px solid var(--border-soft);
  border-radius: 22px;
  background: var(--panel-background-soft);
}

.meta-block {
  display: grid;
  gap: 8px;
}

.meta-block :deep(.el-icon) {
  color: var(--brand-blue);
  font-size: 1.25rem;
}

.detail-importance-block :deep(.el-rate) {
  --el-rate-icon-size: 17px;
  height: 22px;
}

.detail-importance-block :deep(.el-rate__item) {
  margin-right: 2px;
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
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 980px) {
  .detail-page {
    padding: 16px;
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
  .back-button,
  .detail-action-group {
    width: 100%;
    justify-content: center;
  }

  .detail-action-group :deep(.el-button),
  .detail-action-group :deep(.el-dropdown) {
    width: 100%;
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

<style>
.export-dropdown-popper {
  min-width: 172px !important;
  padding: 8px !important;
  border: 1px solid var(--border-soft) !important;
  border-radius: 18px !important;
  background: var(--overlay-background) !important;
  box-shadow: var(--shadow-soft), var(--inset-highlight) !important;
  backdrop-filter: blur(18px) !important;
  overflow: visible !important;
}

.export-dropdown-popper .el-popper__arrow::before {
  border-color: var(--overlay-background) !important;
  background: var(--overlay-background) !important;
}

.export-dropdown-popper .el-dropdown-menu,
.export-dropdown-popper .export-dropdown-menu {
  padding: 0 !important;
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
}

.export-dropdown-popper .el-dropdown-menu__item.export-dropdown-item {
  display: flex !important;
  align-items: center !important;
  gap: 10px !important;
  min-height: 44px !important;
  margin: 2px 0 !important;
  padding: 0 12px !important;
  border-radius: 12px !important;
  color: var(--text-primary) !important;
  font-size: 0.95rem !important;
  font-weight: 700 !important;
  transition:
    background-color 0.18s ease,
    color 0.18s ease,
    transform 0.18s ease !important;
}

.export-dropdown-popper .el-dropdown-menu__item.export-dropdown-item .el-icon {
  color: var(--brand-blue) !important;
  font-size: 17px !important;
}

.export-dropdown-popper .el-dropdown-menu__item.export-dropdown-item:hover,
.export-dropdown-popper .el-dropdown-menu__item.export-dropdown-item:focus {
  transform: translateY(-1px);
  background: var(--accent-soft) !important;
  color: var(--brand-blue) !important;
}
</style>
