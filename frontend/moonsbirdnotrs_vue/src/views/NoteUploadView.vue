<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Icon } from '@iconify/vue'

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
    const detail = error.response?.data?.detail || '标签没拿到。再试一次。'
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
    ElMessage.error('这里只吃 .md 文件。')
    return
  }

  selectedFile.value = rawFile
  uploadedNote.value = null
}

const handleTagChange = (value) => {
  const normalized = [...new Set(value.map((item) => item.trim()).filter(Boolean))]

  if (normalized.length > 4) {
    ElMessage.warning('最多 4 个标签。')
    selectedTagNames.value = normalized.slice(0, 4)
    return
  }

  selectedTagNames.value = normalized
}

const clearSelection = () => {
  selectedFile.value = null
}

const submitUpload = async () => {
  if (!selectedFile.value) {
    ElMessage.warning('先选一个 .md 文件。')
    return
  }

  if (!selectedTagNames.value.length) {
    ElMessage.warning('至少给 1 个标签。')
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
    ElMessage.success('收进书桌了。')
  } catch (error) {
    const detail =
      error.response?.data?.tag_names?.[0] ||
      error.response?.data?.file?.[0] ||
      error.response?.data?.detail ||
      '上传没成。再试一次。'

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
            <h1>把 .md 收进来</h1>
            <p class="upload-subtitle">
              原文件会留下。
              <br />
              预览也会生成。
            </p>
          </div>

          <div class="upload-actions">
            <el-button plain @click="goToNotes">
              <Icon icon="ph:arrow-left" />
              返回列表
            </el-button>
          </div>
        </header>

        <section class="upload-workspace">
          <div class="upload-main fade-rise-enter-delay">
            <div class="section-copy">
              <p class="section-tag">Upload</p>
              <h2>选文件，贴标签</h2>
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
                <span class="dropzone-badge"><Icon icon="ph:file-md" /> .md</span>
                <strong>拖拽文件到这里</strong>
                <p>点一下也行。</p>
              </div>
            </el-upload>

            <div class="upload-hint">
              <span>UTF-8 最省心。标题优先读一级标题。</span>
            </div>

            <div class="tag-section">
              <div class="tag-head">
                <p>笔记标签</p>
                <span>必填。最多 4 个。</span>
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
                placeholder="选标签，或输入新标签"
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
                <Icon icon="ph:upload-simple" />
                上传笔记
              </el-button>
              <el-button v-if="selectedFile" plain @click="clearSelection">清空选择</el-button>
            </div>
          </div>

          <aside class="upload-side fade-rise-enter-delay-2">
            <div class="section-copy">
              <p class="section-tag">Preview</p>
              <h2>收进去之后</h2>
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
                <p>上传成功后。这里给你看一眼。</p>
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
  background: transparent;
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
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.upload-header h1 {
  margin: 0;
  color: var(--brand-navy);
  font-size: clamp(2.5rem, 4.5vw, 5rem);
  line-height: 0.96;
  letter-spacing: 0;
}

.upload-subtitle {
  max-width: 680px;
  margin: 18px 0 0;
  color: var(--ink-soft);
  font-size: 1rem;
  line-height: 1.8;
}

.upload-subtitle code {
  padding: 2px 8px;
  border-radius: var(--radius-md);
  background: var(--accent-soft);
  color: var(--brand-blue);
}

.upload-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.upload-actions :deep(.el-button) {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.upload-workspace {
  display: grid;
  grid-template-columns: minmax(0, 0.95fr) minmax(360px, 0.75fr);
  gap: 28px;
  margin-top: 36px;
  align-items: start;
}

.upload-main,
.upload-side {
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-md);
  background:
    linear-gradient(160deg, rgba(250, 244, 233, 0.9), rgba(232, 219, 199, 0.68)),
    var(--surface);
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
  letter-spacing: 0;
}

.upload-dropzone {
  margin-top: 28px;
}

.upload-dropzone :deep(.el-upload-dragger) {
  min-height: 320px;
  border: 1px dashed var(--accent-border);
  border-radius: var(--radius-md);
  background:
    linear-gradient(135deg, rgba(247, 240, 227, 0.9), rgba(232, 219, 199, 0.52)),
    var(--surface);
  transition:
    border-color 0.2s var(--motion-calm),
    transform 0.2s var(--motion-snappy),
    box-shadow 0.2s var(--motion-calm);
}

.upload-dropzone :deep(.el-upload-dragger:hover) {
  border-color: var(--brand-blue);
  transform: translateY(-2px) rotate(-0.25deg);
  box-shadow: 0 24px 56px rgba(143, 63, 35, 0.12);
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
  gap: 8px;
  min-width: 76px;
  min-height: 36px;
  padding: 0 14px;
  border-radius: var(--radius-md);
  background: var(--accent-soft);
  color: var(--brand-blue);
  font-weight: 700;
  letter-spacing: 0;
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
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-md);
  background: rgba(250, 244, 233, 0.72);
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
  border-radius: var(--radius-md);
  box-shadow: 0 0 0 1px var(--border-soft) inset;
}

.selected-file-card {
  margin-top: 24px;
  padding: 22px;
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-md);
  background: rgba(250, 244, 233, 0.72);
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
  border-radius: var(--radius-md);
  background: var(--surface-muted);
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
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 52px;
  padding-inline: 28px;
  border: none;
  border-radius: var(--radius-md);
  background: var(--brand-blue);
  box-shadow: none;
}

.preview-card,
.preview-empty {
  margin-top: 26px;
  border-radius: var(--radius-md);
  background: rgba(250, 244, 233, 0.76);
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
  background: rgba(88, 73, 58, 0.28);
}

.preview-scroll::-webkit-scrollbar-track {
  background: transparent;
}

.preview-card {
  padding: 24px;
  border: 1px solid var(--border-soft);
}

.preview-meta {
  display: grid;
  gap: 16px;
}

.preview-row {
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-soft);
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
  border-radius: var(--radius-md);
  background: var(--accent-soft);
  color: var(--brand-blue);
  font-size: 0.84rem;
  font-weight: 600;
}

.html-preview {
  margin-top: 30px;
  padding-top: 24px;
  border-top: 1px solid var(--border-soft);
}

.preview-empty {
  min-height: 520px;
  display: grid;
  place-items: center;
  padding: 36px;
  border: 1px dashed var(--border-soft);
  text-align: center;
}

.preview-empty-mark {
  margin-bottom: 18px;
  color: var(--brand-blue);
  font-size: 0.82rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.preview-empty h3 {
  margin: 0;
  color: var(--brand-navy);
  font-size: 1.5rem;
  line-height: 1.1;
  letter-spacing: 0;
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
