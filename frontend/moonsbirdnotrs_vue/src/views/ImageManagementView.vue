<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Calendar, CopyDocument, Delete, EditPen, Picture, Upload, View } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import WorkspaceShell from '../components/WorkspaceShell.vue'
import api from '../services/api'

const router = useRouter()

const loading = ref(false)
const uploading = ref(false)
const cleaningOrphans = ref(false)
const images = ref([])
const imageGroups = ref([])
const notes = ref([])
const diaries = ref([])
const currentPage = ref(1)
const pageSize = ref(24)
const total = ref(0)
const imageStats = ref({
  imageCount: 0,
  contentCount: 0,
  totalSize: 0,
})
const selectedNoteId = ref('')
const uploadNoteId = ref('')
const searchKeyword = ref('')
const imageScope = ref('all')
const groupMode = ref('content')
const usageFilter = ref('all')
const imageFileInput = ref(null)

let imageSearchTimer = null

const groupedImages = computed(() => {
  const groupsByKey = new Map(imageGroups.value.map((group) => [group.key, group]))
  const imagesByGroupKey = new Map()

  images.value.forEach((image) => {
    const key = resolveImageGroupKey(image)
    if (!imagesByGroupKey.has(key)) {
      imagesByGroupKey.set(key, [])
    }

    imagesByGroupKey.get(key).push(image)
  })

  const orderedGroups = imageGroups.value
    .filter((group) => imagesByGroupKey.has(group.key))
    .map((group) => ({
      ...group,
      images: imagesByGroupKey.get(group.key),
    }))

  imagesByGroupKey.forEach((groupImages, key) => {
    if (groupsByKey.has(key)) {
      return
    }

    const firstImage = groupImages[0]
    orderedGroups.push({
      key,
      type: firstImage?.note?.type || 'note',
      note_id: firstImage?.note?.id,
      title: firstImage?.note?.title || '未关联内容',
      diary_date: firstImage?.note?.diary_date || null,
      image_count: groupImages.length,
      total_size: groupImages.reduce((sum, image) => sum + (image.file_size || 0), 0),
      latest_at: groupImages[0]?.created_at || null,
      images: groupImages,
    })
  })

  return orderedGroups
})

const contentOptions = computed(() => [
  ...notes.value.map((note) => ({
    ...note,
    type: 'note',
  })),
  ...diaries.value.map((diary) => ({
    id: diary.note_id,
    title: diary.title,
    type: 'diary',
    diary_date: diary.diary_date,
  })),
])

const filteredContentOptions = computed(() => {
  if (imageScope.value === 'note') {
    return contentOptions.value.filter((content) => content.type === 'note')
  }

  if (imageScope.value === 'diary') {
    return contentOptions.value.filter((content) => content.type === 'diary')
  }

  return contentOptions.value
})

const scopeOptions = [
  { label: '全部图片', value: 'all' },
  { label: '笔记图片', value: 'note' },
  { label: '日记图片', value: 'diary' },
]

const groupModeOptions = [
  { label: '按笔记分组', value: 'content' },
  { label: '按日记日期', value: 'diary_date' },
]

const usageOptions = [
  { label: '全部素材', value: 'all' },
  { label: '孤儿图片', value: 'orphan' },
]

const imageCountLabel = computed(() => (usageFilter.value === 'orphan' ? '孤儿图片' : '全部图片'))

const isDiaryContent = (content) => content?.type === 'diary'

const contentTypeLabel = (content) => {
  if (isDiaryContent(content)) {
    return content.diary_date ? `日记 · ${content.diary_date}` : '日记'
  }

  return '笔记'
}

const contentOptionLabel = (content) => {
  const prefix = isDiaryContent(content) ? '日记' : '笔记'
  const suffix = isDiaryContent(content) && content.diary_date ? ` · ${content.diary_date}` : ''
  return `${prefix} · ${content.title}${suffix}`
}

const resolveImageGroupKey = (image) => {
  if (groupMode.value === 'diary_date' && image.note?.type === 'diary') {
    return `diary:${image.note.diary_date || 'unknown'}`
  }

  return `content:${image.note?.id || 'unknown'}`
}

const groupTypeLabel = (group) => {
  if (group.type === 'diary_date') {
    return group.diary_date ? `日记日期 · ${group.diary_date}` : '日记日期'
  }

  if (group.type === 'diary') {
    return group.diary_date ? `日记 · ${group.diary_date}` : '日记'
  }

  return '笔记'
}

const formatFileSize = (size = 0) => {
  if (size < 1024) {
    return `${size} B`
  }

  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`
  }

  return `${(size / 1024 / 1024).toFixed(2)} MB`
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

const fetchImages = async (page = 1) => {
  loading.value = true
  try {
    const params = {
      page,
      page_size: pageSize.value,
    }
    const keyword = searchKeyword.value.trim()

    if (keyword) {
      params.search = keyword
    }

    if (selectedNoteId.value) {
      params.note_id = selectedNoteId.value
    }

    params.scope = imageScope.value
    params.group_by = groupMode.value
    params.usage = usageFilter.value

    const { data } = await api.get('/notes/images/', { params })
    images.value = data.results || []
    imageGroups.value = data.groups || []
    total.value = data.count || 0
    imageStats.value = {
      imageCount: data.stats?.image_count || data.count || 0,
      contentCount: data.stats?.content_count || 0,
      totalSize: data.stats?.total_size || 0,
    }
    currentPage.value = page
  } catch (error) {
    const detail = error.response?.data?.detail || '获取图片列表失败，请稍后重试。'
    ElMessage.error(detail)
  } finally {
    loading.value = false
  }
}

const scheduleImageFetch = () => {
  window.clearTimeout(imageSearchTimer)
  imageSearchTimer = window.setTimeout(() => {
    fetchImages(1)
  }, 260)
}

const handleImagePageChange = (page) => {
  fetchImages(page)
}

const resolveImageNextPage = () => {
  return images.value.length === 1 && currentPage.value > 1
    ? currentPage.value - 1
    : currentPage.value
}

const fetchNotes = async () => {
  try {
    const [noteResponse, diaryResponse] = await Promise.all([
      api.get('/notes/', {
        params: {
          page_size: 50,
        },
      }),
      api.get('/notes/diaries/'),
    ])

    notes.value = noteResponse.data.results || []
    diaries.value = diaryResponse.data || []

    if (!uploadNoteId.value && contentOptions.value.length) {
      uploadNoteId.value = contentOptions.value[0].id
    }
  } catch (error) {
    const detail = error.response?.data?.detail || '获取内容列表失败，请稍后重试。'
    ElMessage.error(detail)
  }
}

const openUploadPicker = () => {
  if (!uploadNoteId.value) {
    ElMessage.warning('请先选择图片所属内容')
    return
  }

  imageFileInput.value?.click()
}

const uploadImage = async (file) => {
  if (!file) {
    return
  }

  if (!file.type?.startsWith('image/')) {
    ElMessage.warning('请选择图片文件')
    return
  }

  if (file.size > 8 * 1024 * 1024) {
    ElMessage.warning('图片大小不能超过 8 MB')
    return
  }

  const formData = new FormData()
  formData.append('note_id', uploadNoteId.value)
  formData.append('image', file)
  formData.append('alt_text', file.name.replace(/\.[^.]+$/, ''))

  uploading.value = true
  try {
    await api.post('/notes/images/', formData)
    ElMessage.success('图片已上传')
    await fetchImages(1)
  } catch (error) {
    const detail =
      error.response?.data?.image?.[0] ||
      error.response?.data?.note_id?.[0] ||
      error.response?.data?.detail ||
      '图片上传失败，请稍后重试。'
    ElMessage.error(detail)
  } finally {
    uploading.value = false
  }
}

const handleUploadChange = async (event) => {
  const file = event.target.files?.[0]
  event.target.value = ''
  await uploadImage(file)
}

const buildMarkdownReference = (image) => `![${image.alt_text || image.original_filename || 'image'}](${image.image_url})`

const copyMarkdown = async (image) => {
  try {
    await navigator.clipboard.writeText(buildMarkdownReference(image))
    ElMessage.success('已复制 Markdown 引用')
  } catch {
    ElMessage.error('复制失败，请检查浏览器剪贴板权限')
  }
}

const deleteImage = async (image) => {
  try {
    await ElMessageBox.confirm(`确定删除图片「${image.original_filename}」吗？`, '删除图片', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
      customClass: 'beautiful-confirm-box',
      confirmButtonClass: 'beautiful-confirm-button',
      cancelButtonClass: 'beautiful-cancel-button',
      closeOnClickModal: false,
    })
  } catch {
    return
  }

  try {
    await api.delete(`/notes/images/${image.id}/`)
    ElMessage.success('图片已删除')
    await fetchImages(resolveImageNextPage())
  } catch (error) {
    const detail = error.response?.data?.detail || '删除图片失败，请稍后重试。'
    ElMessage.error(detail)
  }
}

const openContent = (content) => {
  const noteId = content?.id || content?.note_id
  if (!noteId) {
    return
  }

  if (content.type === 'diary_date' || isDiaryContent(content)) {
    router.push({ name: 'diary', params: { date: content.diary_date } })
    return
  }

  router.push({ name: 'note-detail', params: { id: noteId } })
}

const cleanupOrphanImages = async () => {
  if (usageFilter.value !== 'orphan') {
    usageFilter.value = 'orphan'
    return
  }

  if (!imageStats.value.imageCount) {
    ElMessage.info('当前筛选范围内没有孤儿图片')
    return
  }

  try {
    await ElMessageBox.confirm(
      `将清理当前筛选范围内的 ${imageStats.value.imageCount} 张孤儿图片，释放 ${formatFileSize(imageStats.value.totalSize)}。该操作会删除文件和图片记录，确定继续吗？`,
      '清理孤儿图片',
      {
        confirmButtonText: '清理',
        cancelButtonText: '取消',
        type: 'warning',
        customClass: 'beautiful-confirm-box',
        confirmButtonClass: 'beautiful-confirm-button',
        cancelButtonClass: 'beautiful-cancel-button',
        closeOnClickModal: false,
      },
    )
  } catch {
    return
  }

  const params = {
    scope: imageScope.value,
  }
  const keyword = searchKeyword.value.trim()

  if (keyword) {
    params.search = keyword
  }

  if (selectedNoteId.value) {
    params.note_id = selectedNoteId.value
  }

  cleaningOrphans.value = true
  try {
    const { data } = await api.post('/notes/images/orphans/cleanup/', null, { params })
    ElMessage.success(`已清理 ${data.cleaned_count || 0} 张孤儿图片，释放 ${formatFileSize(data.released_size || 0)}`)
    await fetchImages(1)
  } catch (error) {
    const detail = error.response?.data?.detail || '清理孤儿图片失败，请稍后重试。'
    ElMessage.error(detail)
  } finally {
    cleaningOrphans.value = false
  }
}

const editContent = (content) => {
  const noteId = content?.id || content?.note_id
  if (!noteId) {
    return
  }

  if (content.type === 'diary_date' || isDiaryContent(content)) {
    router.push({ name: 'diary-edit', params: { date: content.diary_date } })
    return
  }

  router.push({ name: 'note-edit', params: { id: noteId } })
}

onMounted(() => {
  fetchNotes()
  fetchImages()
})

onBeforeUnmount(() => {
  window.clearTimeout(imageSearchTimer)
})

watch(searchKeyword, scheduleImageFetch)
watch(imageScope, () => {
  selectedNoteId.value = ''
  if (imageScope.value === 'diary') {
    groupMode.value = 'diary_date'
  } else if (imageScope.value === 'note') {
    groupMode.value = 'content'
  }
  fetchImages(1)
})
watch(groupMode, () => {
  fetchImages(1)
})
watch(usageFilter, () => {
  fetchImages(1)
})
watch(selectedNoteId, () => {
  fetchImages(1)
})
</script>

<template>
  <main class="images-page page-shell">
    <WorkspaceShell>
      <section class="images-stage">
        <header class="images-header fade-rise-enter">
          <div class="header-copy">
            <p class="images-brand">Assets</p>
            <h1>图片管理</h1>
            <p class="images-subtitle">按笔记和日记整理上传图片，复制引用后可直接写入 Markdown。</p>
          </div>

          <div class="stats-strip">
            <div>
              <span>{{ imageCountLabel }}</span>
              <strong>{{ imageStats.imageCount }}</strong>
            </div>
            <div>
              <span>关联内容</span>
              <strong>{{ imageStats.contentCount }}</strong>
            </div>
            <div>
              <span>总占用</span>
              <strong>{{ formatFileSize(imageStats.totalSize) }}</strong>
            </div>
          </div>
        </header>

        <section class="asset-controls fade-rise-enter-delay">
          <div class="filter-group">
            <el-input
              v-model="searchKeyword"
              clearable
              placeholder="搜索图片、笔记或日记"
            />
            <el-select v-model="selectedNoteId" clearable filterable placeholder="按内容筛选">
              <el-option
                v-for="content in filteredContentOptions"
                :key="`${content.type}-${content.id}`"
                :label="contentOptionLabel(content)"
                :value="content.id"
              />
            </el-select>
            <el-radio-group v-model="imageScope" class="scope-toggle">
              <el-radio-button
                v-for="option in scopeOptions"
                :key="option.value"
                :label="option.value"
              >
                {{ option.label }}
              </el-radio-button>
            </el-radio-group>
            <el-radio-group v-model="groupMode" class="group-toggle">
              <el-radio-button
                v-for="option in groupModeOptions"
                :key="option.value"
                :label="option.value"
                :disabled="imageScope === 'note' && option.value === 'diary_date'"
              >
                {{ option.label }}
              </el-radio-button>
            </el-radio-group>
            <el-radio-group v-model="usageFilter" class="usage-toggle">
              <el-radio-button
                v-for="option in usageOptions"
                :key="option.value"
                :label="option.value"
              >
                {{ option.label }}
              </el-radio-button>
            </el-radio-group>
          </div>

          <div class="upload-group">
            <el-select v-model="uploadNoteId" filterable placeholder="选择所属内容">
              <el-option
                v-for="content in contentOptions"
                :key="`${content.type}-${content.id}`"
                :label="contentOptionLabel(content)"
                :value="content.id"
              />
            </el-select>
            <input
              ref="imageFileInput"
              class="image-file-input"
              type="file"
              accept="image/png,image/jpeg,image/gif,image/webp"
              @change="handleUploadChange"
            />
            <el-button type="primary" :loading="uploading" @click="openUploadPicker">
              <el-icon><Upload /></el-icon>
              <span>上传图片</span>
            </el-button>
            <el-button
              class="cleanup-button"
              :loading="cleaningOrphans"
              :disabled="usageFilter === 'orphan' && !imageStats.imageCount"
              @click="cleanupOrphanImages"
            >
              <el-icon><Delete /></el-icon>
              <span>{{ usageFilter === 'orphan' ? '一键清理' : '查看孤儿' }}</span>
            </el-button>
          </div>
        </section>

        <section v-loading="loading" class="image-library fade-rise-enter-delay">
          <div v-if="groupedImages.length" class="note-groups">
            <section v-for="group in groupedImages" :key="group.key" class="note-group">
              <div class="note-group-head">
                <div>
                  <span>
                    {{ group.image_count }} 张图片 · {{ formatFileSize(group.total_size) }} · 最近 {{ formatDateTime(group.latest_at) }}
                  </span>
                  <h2>
                    <el-icon v-if="group.type === 'diary' || group.type === 'diary_date'"><Calendar /></el-icon>
                    <span>{{ group.title }}</span>
                  </h2>
                  <p class="content-kind">{{ groupTypeLabel(group) }}</p>
                </div>
                <div class="note-actions">
                  <button type="button" @click="openContent(group)">
                    <el-icon><View /></el-icon>
                    <span>查看</span>
                  </button>
                  <button type="button" @click="editContent(group)">
                    <el-icon><EditPen /></el-icon>
                    <span>编辑</span>
                  </button>
                </div>
              </div>

              <div class="image-grid">
                <article v-for="image in group.images" :key="image.id" class="image-item">
                  <figure>
                    <img :src="image.image_url" :alt="image.alt_text || image.original_filename" loading="lazy" />
                  </figure>
                  <div class="image-meta">
                    <strong>{{ image.alt_text || image.original_filename }}</strong>
                    <span>{{ formatFileSize(image.file_size) }} / {{ formatDateTime(image.created_at) }}</span>
                  </div>
                  <div class="image-actions">
                    <button type="button" @click="copyMarkdown(image)">
                      <el-icon><CopyDocument /></el-icon>
                      <span>复制引用</span>
                    </button>
                    <a :href="image.image_url" target="_blank" rel="noreferrer">
                      <el-icon><Picture /></el-icon>
                      <span>打开</span>
                    </a>
                    <button type="button" class="danger" @click="deleteImage(image)">
                      <el-icon><Delete /></el-icon>
                      <span>删除</span>
                    </button>
                  </div>
                </article>
              </div>
            </section>
          </div>

          <div v-else class="empty-images">
            <el-icon><Picture /></el-icon>
            <h2>还没有图片</h2>
            <p>选择一篇笔记或日记后上传图片，素材会自动归入对应内容。</p>
          </div>

          <div class="pagination-wrap" v-if="total > pageSize">
            <el-pagination
              background
              layout="prev, pager, next"
              :current-page="currentPage"
              :page-size="pageSize"
              :total="total"
              @current-change="handleImagePageChange"
            />
          </div>
        </section>
      </section>
    </WorkspaceShell>
  </main>
</template>

<style scoped>
.images-page {
  padding: 20px;
  background: var(--page-bg);
  color: var(--text-primary);
}

.images-stage {
  min-height: calc(100vh - 20px);
  min-height: calc(100svh - 20px);
  margin-top: 20px;
}

.images-header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 28px;
  align-items: end;
}

.header-copy {
  max-width: 760px;
}

.images-brand {
  margin: 0 0 12px;
  color: var(--accent);
  font-size: 0.84rem;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.header-copy h1 {
  margin: 0;
  color: var(--text-primary);
  font-size: clamp(2.4rem, 5vw, 5.4rem);
  line-height: 0.98;
  letter-spacing: -0.05em;
}

.images-subtitle {
  max-width: 560px;
  margin: 18px 0 0;
  color: var(--text-muted);
  font-size: 1rem;
  line-height: 1.8;
}

.stats-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(92px, auto));
  gap: 10px;
  align-items: stretch;
}

.stats-strip div {
  display: grid;
  gap: 8px;
  min-width: 0;
  padding: 14px 16px;
  border: 1px solid var(--border-soft);
  border-radius: 8px;
  background: var(--surface);
}

.stats-strip span {
  color: var(--text-muted);
  font-size: 0.78rem;
  font-weight: 700;
}

.stats-strip strong {
  color: var(--text-primary);
  font-size: 1.08rem;
}

.asset-controls {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 14px;
  align-items: center;
  margin-top: 30px;
  padding: 16px;
  border: 1px solid var(--border-soft);
  border-radius: 8px;
  background: var(--surface);
  box-shadow: var(--shadow-soft);
}

.filter-group,
.upload-group {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  min-width: 0;
}

.filter-group :deep(.el-input) {
  width: min(320px, 42vw);
}

.filter-group :deep(.el-select),
.upload-group :deep(.el-select) {
  width: 220px;
}

.scope-toggle,
.group-toggle,
.usage-toggle {
  flex: 0 0 auto;
}

.scope-toggle :deep(.el-radio-button__inner),
.group-toggle :deep(.el-radio-button__inner),
.usage-toggle :deep(.el-radio-button__inner) {
  min-height: 36px;
  border-color: var(--border-soft);
  background: var(--surface-soft);
  color: var(--text-secondary);
  font-weight: 700;
}

.scope-toggle :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner),
.group-toggle :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner),
.usage-toggle :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  border-color: var(--accent-border);
  background: var(--accent-soft);
  color: var(--accent);
  box-shadow: none;
}

.cleanup-button {
  border-color: color-mix(in srgb, var(--danger) 28%, transparent);
  background: var(--danger-soft);
  color: var(--danger);
}

.cleanup-button:hover {
  border-color: color-mix(in srgb, var(--danger) 42%, transparent);
  background: color-mix(in srgb, var(--danger-soft) 78%, transparent);
  color: var(--danger);
}

.image-file-input {
  display: none;
}

.image-library {
  min-height: 320px;
  margin-top: 18px;
}

.note-groups {
  display: grid;
  gap: 20px;
}

.note-group {
  display: grid;
  gap: 14px;
  padding: 18px;
  border: 1px solid var(--border-soft);
  border-radius: 8px;
  background: var(--surface);
  box-shadow: var(--shadow-soft);
}

.note-group-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--border-soft);
}

.note-group-head span {
  color: var(--accent);
  font-size: 0.78rem;
  font-weight: 800;
}

.note-group-head h2 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 6px 0 0;
  color: var(--text-primary);
  font-size: 1.24rem;
  line-height: 1.3;
}

.note-group-head h2 :deep(.el-icon) {
  color: var(--accent);
  font-size: 1rem;
}

.content-kind {
  margin: 6px 0 0;
  color: var(--text-muted);
  font-size: 0.8rem;
  font-weight: 700;
}

.note-actions,
.image-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.note-actions button,
.image-actions button,
.image-actions a {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 34px;
  padding: 0 10px;
  border: 1px solid var(--border-soft);
  border-radius: 8px;
  background: var(--surface-soft);
  color: var(--text-primary);
  font: inherit;
  font-size: 0.82rem;
  font-weight: 700;
  text-decoration: none;
  cursor: pointer;
  transition:
    transform 0.18s ease,
    border-color 0.18s ease,
    background-color 0.18s ease,
    color 0.18s ease;
}

.note-actions button:hover,
.image-actions button:hover,
.image-actions a:hover {
  transform: translateY(-1px);
  border-color: var(--accent-border);
  background: var(--accent-soft);
  color: var(--accent);
}

.image-actions .danger:hover {
  border-color: color-mix(in srgb, var(--danger) 32%, transparent);
  background: var(--danger-soft);
  color: var(--danger);
}

.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
  gap: 14px;
}

.image-item {
  display: grid;
  grid-template-rows: auto minmax(58px, auto) auto;
  gap: 12px;
  min-width: 0;
  padding: 10px;
  border: 1px solid var(--border-soft);
  border-radius: 8px;
  background: var(--surface-soft);
}

.image-item figure {
  display: grid;
  place-items: center;
  aspect-ratio: 4 / 3;
  margin: 0;
  overflow: hidden;
  border: 1px solid var(--border-soft);
  border-radius: 6px;
  background: var(--surface-muted);
}

.image-item img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.image-meta {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.image-meta strong {
  overflow: hidden;
  color: var(--text-primary);
  font-size: 0.92rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.image-meta span {
  color: var(--text-muted);
  font-size: 0.78rem;
}

.empty-images {
  display: grid;
  justify-items: center;
  gap: 12px;
  padding: 72px 20px;
  border: 1px dashed var(--border-soft);
  border-radius: 8px;
  background: var(--surface);
  color: var(--text-muted);
  text-align: center;
}

.empty-images :deep(.el-icon) {
  color: var(--accent);
  font-size: 2rem;
}

.empty-images h2,
.empty-images p {
  margin: 0;
}

.empty-images h2 {
  color: var(--text-primary);
  font-size: 1.3rem;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 22px;
}

@media (max-width: 1080px) {
  .images-header,
  .asset-controls {
    grid-template-columns: 1fr;
  }

  .stats-strip {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .filter-group,
  .upload-group {
    flex-wrap: wrap;
  }

  .filter-group :deep(.el-input),
  .filter-group :deep(.el-select),
  .upload-group :deep(.el-select) {
    width: min(100%, 320px);
  }
}

@media (max-width: 640px) {
  .images-page {
    padding: 16px;
  }

  .images-stage {
    min-height: auto;
    margin-top: 0;
  }

  .header-copy h1 {
    font-size: 2.2rem;
  }

  .stats-strip,
  .image-grid {
    grid-template-columns: 1fr;
  }

  .asset-controls,
  .note-group {
    padding: 14px;
  }

  .pagination-wrap {
    justify-content: center;
  }

  .filter-group,
  .upload-group,
  .filter-group :deep(.el-input),
  .filter-group :deep(.el-select),
  .upload-group :deep(.el-select),
  .upload-group :deep(.el-button) {
    width: 100%;
  }

  .note-group-head {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
