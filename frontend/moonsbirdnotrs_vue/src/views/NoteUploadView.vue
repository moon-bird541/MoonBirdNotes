<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import WorkspaceShell from '../components/WorkspaceShell.vue'
import api from '../services/api'
import '../styles/markdown.css'

const router = useRouter()
const uploading = ref(false)
const selectedFile = ref(null)
const uploadedNote = ref(null)
const tagOptions = ref([])
const selectedTagNames = ref([])

const selectedFileInfo = computed(() => {
  if (!selectedFile.value) {
    return null
  }

  return {
    name: selectedFile.value.name,
    size: `${(selectedFile.value.size / 1024).toFixed(1)} KB`,
    type: selectedFile.value.type || 'text/markdown',
  }
})

const fetchTagOptions = async () => {
  try {
    const { data } = await api.get('/notes/tags/')
    tagOptions.value = data.map((tag) => tag.name)
  } catch (error) {
    const detail = error.response?.data?.detail || '获取标签列表失败，请稍后重试。'
    ElMessage.error(detail)
  }
}

// 阻止组件自动上传，统一交给页面主按钮触发。
const handleFileChange = (uploadFile) => {
  const rawFile = uploadFile.raw

  if (!rawFile) {
    return
  }

  if (!rawFile.name.toLowerCase().endsWith('.md')) {
    ElMessage.error('只能选择 .md 文件。')
    return
  }

  selectedFile.value = rawFile
  uploadedNote.value = null
}

const handleTagChange = (value) => {
  const normalized = [...new Set(value.map((item) => item.trim()).filter(Boolean))]

  if (normalized.length > 2) {
    ElMessage.warning('每篇笔记最多只能填写两个标签。')
    selectedTagNames.value = normalized.slice(0, 2)
    return
  }

  selectedTagNames.value = normalized
}

const clearSelection = () => {
  selectedFile.value = null
}

const submitUpload = async () => {
  if (!selectedFile.value) {
    ElMessage.warning('请先选择一个 Markdown 文件。')
    return
  }

  if (!selectedTagNames.value.length) {
    ElMessage.warning('请至少填写一个标签。')
    return
  }

  uploading.value = true

  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    selectedTagNames.value.forEach((tagName) => {
      formData.append('tag_names', tagName)
    })

    const { data } = await api.post('/notes/upload/', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })

    uploadedNote.value = data
    tagOptions.value = [...new Set([...tagOptions.value, ...data.tags.map((tag) => tag.name)])].sort()
    ElMessage.success('笔记上传成功。')
  } catch (error) {
    const detail =
      error.response?.data?.tag_names?.[0] ||
      error.response?.data?.file?.[0] ||
      error.response?.data?.detail ||
      '上传失败，请稍后重试。'

    ElMessage.error(detail)
  } finally {
    uploading.value = false
  }
}

const goToNotes = () => {
  router.push('/notes')
}

onMounted(() => {
  fetchTagOptions()
})
</script>

<template>
  <main class="upload-page page-shell">
    <WorkspaceShell>
      <section class="upload-stage">
        <header class="upload-header fade-rise-enter">
          <div class="header-copy">
            <p class="upload-brand">MoonBirdNotes</p>
            <h1>上传 Markdown 笔记</h1>
            <p class="upload-subtitle">
              上传后系统会保留原始 <code>.md</code> 文件，并同步生成可直接展示的 HTML 内容，方便后续整理、预览和展示。
            </p>
          </div>

          <div class="upload-actions">
            <el-button plain @click="goToNotes">返回笔记列表</el-button>
          </div>
        </header>

        <section class="upload-workspace">
          <div class="upload-main fade-rise-enter-delay">
            <div class="section-copy">
              <p class="section-tag">Primary Action</p>
              <h2>选择文件并填写标签</h2>
            </div>

            <el-upload
              class="upload-dropzone"
              drag
              :auto-upload="false"
              :show-file-list="false"
              accept=".md"
              :on-change="handleFileChange"
            >
              <div class="dropzone-content">
                <span class="dropzone-badge">.md</span>
                <strong>拖拽文件到这里</strong>
                <p>或者点击这块区域，选择本地 Markdown 文件</p>
              </div>
            </el-upload>

            <div class="upload-hint">
              <span>建议使用 UTF-8 编码的 Markdown 文件，标题会优先读取一级标题。</span>
            </div>

            <div class="tag-section">
              <div class="tag-head">
                <p>笔记标签</p>
                <span>必填，最多 2 个，可直接输入新标签</span>
              </div>

              <el-select
                v-model="selectedTagNames"
                class="tag-select"
                multiple
                filterable
                allow-create
                default-first-option
                :reserve-keyword="false"
                collapse-tags
                collapse-tags-tooltip
                placeholder="选择已有标签，或输入新标签后回车"
                @change="handleTagChange"
              >
                <el-option
                  v-for="tagName in tagOptions"
                  :key="tagName"
                  :label="tagName"
                  :value="tagName"
                />
              </el-select>
            </div>

            <div v-if="selectedFileInfo" class="selected-file-card">
              <div class="selected-file-head">
                <p>已选择文件</p>
                <strong>{{ selectedFileInfo.name }}</strong>
              </div>

              <div class="selected-file-meta">
                <div class="meta-pill">
                  <span>大小</span>
                  <strong>{{ selectedFileInfo.size }}</strong>
                </div>
                <div class="meta-pill">
                  <span>类型</span>
                  <strong>{{ selectedFileInfo.type }}</strong>
                </div>
                <div class="meta-pill" v-if="selectedTagNames.length">
                  <span>标签</span>
                  <strong>{{ selectedTagNames.join(' / ') }}</strong>
                </div>
              </div>
            </div>

            <div class="button-row">
              <el-button class="upload-button" type="primary" :loading="uploading" @click="submitUpload">
                上传笔记
              </el-button>
              <el-button v-if="selectedFile" plain @click="clearSelection">清空选择</el-button>
            </div>
          </div>

          <aside class="upload-side fade-rise-enter-delay-2">
            <div class="section-copy">
              <p class="section-tag">Preview</p>
              <h2>上传结果预览</h2>
            </div>

            <div class="preview-scroll">
              <div v-if="uploadedNote" class="preview-card">
                <div class="preview-meta">
                  <div class="preview-row">
                    <span>标题</span>
                    <strong>{{ uploadedNote.title }}</strong>
                  </div>
                  <div class="preview-row">
                    <span>标签</span>
                    <div class="preview-tags">
                      <span v-for="tag in uploadedNote.tags" :key="tag.id" class="preview-tag">
                        {{ tag.name }}
                      </span>
                    </div>
                  </div>
                  <div class="preview-row">
                    <span>文件地址</span>
                    <a :href="uploadedNote.file_url" target="_blank" rel="noreferrer">
                      {{ uploadedNote.file_url }}
                    </a>
                  </div>
                </div>

                <!-- 后端已经完成 Markdown 到 HTML 的渲染，这里直接显示结果。 -->
                <article class="html-preview markdown-body" v-html="uploadedNote.rendered_html"></article>
              </div>

              <div v-else class="preview-empty">
                <div class="preview-empty-mark">HTML</div>
                <h3>这里会出现渲染结果</h3>
                <p>上传成功后，将展示标题、标签、文件地址以及 Markdown 转换后的 HTML 预览。</p>
              </div>
            </div>
          </aside>
        </section>
      </section>
    </WorkspaceShell>
  </main>
</template>

<style scoped>
.upload-page {
  padding: 20px;
}

.upload-stage {
  margin-top: 20px;
}

.upload-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 32px;
}

.header-copy {
  max-width: 760px;
}

.upload-brand,
.section-tag {
  margin: 0 0 12px;
  color: var(--brand-blue);
  font-size: 0.84rem;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.upload-header h1 {
  margin: 0;
  color: var(--brand-navy);
  font-size: clamp(2.5rem, 4.5vw, 5rem);
  line-height: 0.96;
  letter-spacing: -0.06em;
}

.upload-subtitle {
  max-width: 680px;
  margin: 18px 0 0;
  color: var(--ink-soft);
  font-size: 1rem;
  line-height: 1.9;
}

.upload-subtitle code {
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.08);
  color: var(--brand-blue);
}

.upload-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.upload-workspace {
  display: grid;
  grid-template-columns: minmax(0, 0.95fr) minmax(360px, 0.75fr);
  gap: 28px;
  margin-top: 36px;
}

.upload-main,
.upload-side {
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 30px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.8), rgba(255, 255, 255, 0.64)),
    rgba(255, 255, 255, 0.68);
  box-shadow: var(--shadow-soft);
  backdrop-filter: blur(20px);
}

.upload-main {
  padding: 30px;
}

.upload-side {
  padding: 28px;
  display: flex;
  flex-direction: column;
}

.section-copy h2 {
  margin: 0;
  color: var(--brand-navy);
  font-size: 1.9rem;
  line-height: 1.08;
  letter-spacing: -0.04em;
}

.upload-dropzone {
  margin-top: 28px;
}

.upload-dropzone :deep(.el-upload-dragger) {
  min-height: 320px;
  border: 1px dashed rgba(37, 99, 235, 0.28);
  border-radius: 28px;
  background:
    radial-gradient(circle at top, rgba(37, 99, 235, 0.08), transparent 42%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.88), rgba(245, 247, 251, 0.72));
  transition:
    border-color 0.2s ease,
    transform 0.2s ease,
    box-shadow 0.2s ease;
}

.upload-dropzone :deep(.el-upload-dragger:hover) {
  border-color: rgba(37, 99, 235, 0.48);
  transform: translateY(-2px);
  box-shadow: 0 24px 56px rgba(37, 99, 235, 0.12);
}

.dropzone-content {
  display: grid;
  justify-items: center;
  gap: 14px;
  padding: 24px;
  color: var(--ink-soft);
  text-align: center;
}

.dropzone-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 76px;
  min-height: 36px;
  padding: 0 14px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.1);
  color: var(--brand-blue);
  font-weight: 700;
  letter-spacing: 0.08em;
}

.dropzone-content strong {
  color: var(--brand-navy);
  font-size: 1.28rem;
  font-weight: 700;
}

.dropzone-content p {
  max-width: 360px;
  margin: 0;
  line-height: 1.8;
}

.upload-hint {
  margin-top: 18px;
  color: var(--ink-soft);
  font-size: 0.94rem;
  line-height: 1.7;
}

.tag-section {
  margin-top: 24px;
  padding: 22px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.74);
}

.tag-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.tag-head p {
  margin: 0;
  color: var(--brand-navy);
  font-weight: 700;
}

.tag-head span {
  color: var(--ink-soft);
  font-size: 0.9rem;
}

.tag-select {
  width: 100%;
}

.tag-select :deep(.el-select__wrapper) {
  min-height: 52px;
  border-radius: 16px;
  box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.18) inset;
}

.selected-file-card {
  margin-top: 24px;
  padding: 22px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.74);
}

.selected-file-head p {
  margin: 0 0 8px;
  color: var(--ink-soft);
  font-size: 0.92rem;
}

.selected-file-head strong {
  color: var(--brand-navy);
  font-size: 1.08rem;
  word-break: break-all;
}

.selected-file-meta {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 18px;
}

.meta-pill {
  min-width: 138px;
  padding: 14px 16px;
  border-radius: 18px;
  background: rgba(15, 23, 42, 0.04);
}

.meta-pill span {
  display: block;
  margin-bottom: 6px;
  color: var(--ink-soft);
  font-size: 0.84rem;
}

.meta-pill strong {
  color: var(--brand-navy);
}

.button-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 24px;
}

.upload-button {
  min-height: 52px;
  padding-inline: 28px;
  border: none;
  border-radius: 16px;
  background: linear-gradient(135deg, #1d4ed8 0%, #2563eb 48%, #f59e0b 170%);
  box-shadow: 0 18px 36px rgba(37, 99, 235, 0.24);
}

.preview-card,
.preview-empty {
  margin-top: 26px;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.76);
}

.preview-scroll {
  flex: 1;
  min-height: 0;
  max-height: 760px;
  overflow-y: auto;
  padding-right: 6px;
}

.preview-scroll::-webkit-scrollbar {
  width: 8px;
}

.preview-scroll::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: rgba(91, 100, 120, 0.28);
}

.preview-scroll::-webkit-scrollbar-track {
  background: transparent;
}

.preview-card {
  padding: 24px;
  border: 1px solid rgba(148, 163, 184, 0.16);
}

.preview-meta {
  display: grid;
  gap: 16px;
}

.preview-row {
  padding-bottom: 16px;
  border-bottom: 1px solid rgba(15, 23, 42, 0.08);
}

.preview-row:last-child {
  padding-bottom: 0;
  border-bottom: none;
}

.preview-row span {
  display: block;
  margin-bottom: 8px;
  color: var(--ink-soft);
  font-size: 0.9rem;
}

.preview-row strong,
.preview-row a {
  color: var(--brand-navy);
  word-break: break-all;
}

.preview-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.preview-tag {
  display: inline-flex;
  align-items: center;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.08);
  color: var(--brand-blue);
  font-size: 0.84rem;
  font-weight: 600;
}

.html-preview {
  margin-top: 30px;
  padding-top: 24px;
  border-top: 1px solid rgba(15, 23, 42, 0.08);
}

.preview-empty {
  min-height: 520px;
  display: grid;
  place-items: center;
  padding: 36px;
  border: 1px dashed rgba(148, 163, 184, 0.28);
  text-align: center;
}

.preview-empty-mark {
  margin-bottom: 18px;
  color: var(--brand-blue);
  font-size: 0.82rem;
  font-weight: 700;
  letter-spacing: 0.22em;
  text-transform: uppercase;
}

.preview-empty h3 {
  margin: 0;
  color: var(--brand-navy);
  font-size: 1.5rem;
  line-height: 1.1;
  letter-spacing: -0.03em;
}

.preview-empty p {
  max-width: 320px;
  margin: 14px 0 0;
  color: var(--ink-soft);
  line-height: 1.8;
}

@media (max-width: 1100px) {
  .upload-workspace {
    grid-template-columns: 1fr;
  }

  .preview-scroll {
    max-height: 520px;
  }
}

@media (max-width: 980px) {
  .upload-page {
    padding: 16px;
  }

  .upload-stage {
    margin-top: 0;
  }
}

@media (max-width: 720px) {
  .upload-header {
    flex-direction: column;
  }

  .upload-actions,
  .upload-actions :deep(.el-button) {
    width: 100%;
  }

  .upload-main,
  .upload-side {
    padding: 22px;
    border-radius: 24px;
  }

  .upload-actions,
  .button-row,
  .selected-file-meta {
    flex-wrap: wrap;
  }

  .tag-head {
    flex-direction: column;
    align-items: flex-start;
  }

  .upload-dropzone :deep(.el-upload-dragger) {
    min-height: 260px;
    border-radius: 22px;
  }

  .preview-empty {
    min-height: 360px;
    padding: 28px;
  }

  .preview-scroll {
    max-height: 460px;
    padding-right: 2px;
  }
}

@media (max-width: 520px) {
  .upload-main,
  .upload-side {
    padding: 18px 16px;
    border-radius: 20px;
  }

  .section-copy h2 {
    font-size: 1.5rem;
  }

  .tag-section,
  .selected-file-card,
  .preview-card {
    padding: 18px 16px;
    border-radius: 18px;
  }

  .meta-pill {
    min-width: 0;
    width: 100%;
  }

  .button-row :deep(.el-button) {
    width: 100%;
  }

  .preview-empty {
    min-height: 280px;
    padding: 22px 18px;
  }
}
</style>
