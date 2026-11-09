<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowLeftBold,
  ArrowRightBold,
  Back,
  Calendar,
  Check,
  Clock,
  Minus,
  Picture,
  Reading,
  Tickets,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import Editor from '@toast-ui/editor'
import '@toast-ui/editor/dist/i18n/zh-cn'

import '@toast-ui/editor/dist/toastui-editor.css'

import WorkspaceShell from '../components/WorkspaceShell.vue'
import FixedEditorToolbar from '../editor/components/FixedEditorToolbar.vue'
import {
  createFixedToolbarState,
  getFixedToolbarSnapshot,
  headingOptions,
} from '../editor/editorHelpers'
import api from '../services/api'
import {
  EDITOR_SETTINGS_CHANGE_EVENT,
  getEditorSettings,
} from '../utils/editorSettings'
import {
  MAX_TABLE_COLUMN_COUNT,
  MAX_TABLE_ROW_COUNT,
  extractTableLayoutMetadata,
  serializeMarkdownWithTableLayouts,
} from '../utils/tableLayout'
import { getFenceLanguage, replaceFenceLanguage } from '../utils/fenceInfo'
import { createRichBlockPreview } from '../utils/editorDecorations'
import { applyWysiwygCallout, getActiveCalloutType, insertWysiwygText } from '../utils/wysiwygBlocks'
import '../styles/markdown.css'

const route = useRoute()
const router = useRouter()

const editorRoot = ref(null)
const imageInput = ref(null)
const imageReplaceInput = ref(null)
const loading = ref(false)
const saving = ref(false)
const editorReady = ref(false)
const diaryFieldsCollapsed = ref(false)
const activeCalloutType = ref('')
const fixedToolbarSelectionRange = ref(null)
const fixedToolbarSelectedText = ref('')
const entry = ref(null)
const currentMarkdown = ref('')
const editorSettings = ref(getEditorSettings())
const imageToolbarVisible = ref(false)
const activeEditorImage = ref(null)
const imageToolbarPosition = reactive({
  top: -9999,
  left: -9999,
})
const fixedToolbarState = reactive(createFixedToolbarState())

const form = reactive({
  title: '',
  mood: '',
  weather: '',
  summary: '',
})

let editorInstance = null
let tableLayoutMetadata = []
let autoSaveTimer = null
let lastSavedContent = ''
let pendingImageSelectionRange = null
let cleanupEditorImageListeners = null

const padDatePart = (value) => String(value).padStart(2, '0')

const toDateKey = (date) =>
  `${date.getFullYear()}-${padDatePart(date.getMonth() + 1)}-${padDatePart(date.getDate())}`

const todayDateKey = () => toDateKey(new Date())

const parseDateKey = (dateKey) => {
  const parts = String(dateKey || '').split('-').map((part) => Number(part))

  if (parts.length !== 3 || parts.some((part) => Number.isNaN(part))) {
    return null
  }

  const [year, month, day] = parts
  const date = new Date(year, month - 1, day)

  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) {
    return null
  }

  return date
}

const normalizeDateKey = (dateKey) => {
  const parsed = parseDateKey(dateKey)
  return parsed ? toDateKey(parsed) : todayDateKey()
}

const selectedDate = computed(() => normalizeDateKey(route.params.date))

const selectedDateLabel = computed(() => {
  const parsed = parseDateKey(selectedDate.value) || new Date()
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    weekday: 'long',
  }).format(parsed)
})

const wordCount = computed(() =>
  currentMarkdown.value
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/`([^`]*)`/g, '$1')
    .replace(/!\[[^\]]*\]\([^)]+\)/g, ' ')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/^\s{0,3}#{1,6}\s*/gm, '')
    .replace(/^\s*[-*+]\s+/gm, '')
    .replace(/^\s*\d+\.\s+/gm, '')
    .replace(/[*_~>#-]+/g, ' ')
    .replace(/\s+/g, '')
    .length
)
const autoSaveStatusText = computed(() => {
  if (!editorSettings.value.autoSaveEnabled) {
    return '自动保存已关闭'
  }

  return `自动保存：${Math.round(editorSettings.value.autoSaveIntervalMs / 1000)} 秒`
})
const addDaysToSelected = (days) => {
  const date = parseDateKey(selectedDate.value) || new Date()
  date.setDate(date.getDate() + days)
  return toDateKey(date)
}

const createDiarySaveSnapshot = ({
  title = '',
  mood = '',
  weather = '',
  summary = '',
  markdownContent = '',
} = {}) =>
  JSON.stringify({
    title,
    mood,
    weather,
    summary,
    markdownContent,
  })

const setFormFromEntry = (diaryEntry) => {
  entry.value = diaryEntry
  form.title = diaryEntry.title || ''
  form.mood = diaryEntry.mood || ''
  form.weather = diaryEntry.weather || ''
  form.summary = diaryEntry.summary || ''
  currentMarkdown.value = diaryEntry.markdown_content || ''
  lastSavedContent = createDiarySaveSnapshot({
    title: form.title,
    mood: form.mood,
    weather: form.weather,
    summary: form.summary,
    markdownContent: currentMarkdown.value,
  })

  const parsedMarkdown = extractTableLayoutMetadata(currentMarkdown.value)
  tableLayoutMetadata = parsedMarkdown.layouts
  currentMarkdown.value = parsedMarkdown.markdown
}

const fetchOrCreateEntry = async () => {
  loading.value = true

  try {
    let diaryEntry = null

    try {
      const { data } = await api.get(`/notes/diaries/by-date/${selectedDate.value}/`)
      diaryEntry = data
    } catch (error) {
      if (error.response?.status !== 404) {
        throw error
      }

      const { data } = await api.post('/notes/diaries/', {
        diary_date: selectedDate.value,
      })
      diaryEntry = data
    }

    setFormFromEntry(diaryEntry)
  } catch (error) {
    const detail = error.response?.data?.detail || '日记加载失败，请稍后重试。'
    ElMessage.error(detail)
  } finally {
    loading.value = false
  }
}

const getCurrentMarkdownWithTableLayouts = () => {
  const markdown = editorInstance?.getMarkdown() || currentMarkdown.value || ''
  return serializeMarkdownWithTableLayouts(markdown, tableLayoutMetadata)
}

const getCurrentDiarySaveSnapshot = (markdownContent = getCurrentMarkdownWithTableLayouts()) =>
  createDiarySaveSnapshot({
    title: form.title,
    mood: form.mood,
    weather: form.weather,
    summary: form.summary,
    markdownContent,
  })

const syncMarkdownFromEditor = () => {
  currentMarkdown.value = editorInstance?.getMarkdown() || ''
}

const getWysiwygView = () => editorInstance?.wwEditor?.view || null

const updateFixedToolbarSnapshot = () => {
  const view = getWysiwygView()
  const snapshot = getFixedToolbarSnapshot(view)
  Object.assign(fixedToolbarState, snapshot.state)
  fixedToolbarSelectedText.value = snapshot.selectedText
  activeCalloutType.value = view ? getActiveCalloutType(view.state).toLowerCase() : ''

  if (snapshot.range) {
    fixedToolbarSelectionRange.value = snapshot.range
  }
}

const getSelectedCodeBlockPos = (view) => {
  const selection = view?.state?.selection
  if (!view || !selection) {
    return null
  }

  for (let depth = selection.$from.depth; depth >= 0; depth -= 1) {
    if (selection.$from.node(depth)?.type?.name === 'codeBlock') {
      return depth === 0 ? 0 : selection.$from.before(depth)
    }
  }

  let found = null
  view.state.doc.nodesBetween(selection.from, selection.to, (node, pos) => {
    if (found !== null) {
      return false
    }
    if (node.type.name === 'codeBlock') {
      found = pos
      return false
    }
    return true
  })

  return found
}

/** 顶部工具栏「⋯」：对光标所在代码块修改语言（日记不提供完整参数面板）。 */
const openFixedToolbarCodeBlockOptions = () => {
  const view = getWysiwygView()
  const selection = view?.state?.selection
  const pos = getSelectedCodeBlockPos(view)

  if (!view || !selection || pos === null) {
    ElMessage.info('把光标放进一个代码块里，再改代码块语言。')
    return
  }

  promptDiaryCodeBlockLanguage(pos)
}

const rememberFixedToolbarSelection = () => {
  updateFixedToolbarSnapshot()
}

const restoreFixedToolbarSelection = () => {
  if (!editorInstance || !fixedToolbarSelectionRange.value) {
    return false
  }

  const view = getWysiwygView()
  const docSize = view?.state?.doc?.content?.size
  if (!view || !Number.isFinite(docSize)) {
    return false
  }

  const [start, end] = fixedToolbarSelectionRange.value
  const safeStart = Math.max(0, Math.min(start, docSize))
  const safeEnd = Math.max(0, Math.min(end, docSize))
  editorInstance.focus()
  editorInstance.setSelection(safeStart, safeEnd)
  return true
}

const syncAfterFixedToolbarCommand = () => {
  syncMarkdownFromEditor()
  nextTick(updateFixedToolbarSnapshot)
}

const runFixedToolbarCommand = (command, payload) => {
  if (!editorInstance) {
    return
  }

  if (!restoreFixedToolbarSelection()) {
    editorInstance.focus()
  }
  editorInstance.exec(command, payload)
  syncAfterFixedToolbarCommand()
}

const applyFixedToolbarHeading = (level) => {
  runFixedToolbarCommand('heading', { level })
}

const insertFixedToolbarLink = (payload) => {
  runFixedToolbarCommand('addLink', payload)
}

const insertFixedToolbarTable = (rows, columns) => {
  if (rows > MAX_TABLE_ROW_COUNT || columns > MAX_TABLE_COLUMN_COUNT) {
    ElMessage.warning(`表格最多支持 ${MAX_TABLE_ROW_COUNT} 行 * ${MAX_TABLE_COLUMN_COUNT} 列`)
    return
  }

  runFixedToolbarCommand('addTable', {
    rowCount: rows,
    columnCount: columns,
  })
}

/** 提示框与公式是扩展语法，toast-ui 没有对应命令，直接写入文本/引用块。 */
const insertFixedToolbarMath = (displayMode) => {
  const view = getWysiwygView()
  if (!view) {
    return
  }

  restoreFixedToolbarSelection()

  if (displayMode) {
    // 块级公式不替换选中正文（默认插入到选区末尾）
    insertWysiwygText(view, '$$\nE = mc^2\n$$')
  } else {
    // 行内公式包住选中文字；没有选区时写入占位符
    insertWysiwygText(view, '$x^2$', {
      wrapSelection: true,
      before: '$',
      after: '$',
    })
  }
  syncAfterFixedToolbarCommand()
}

const insertFixedToolbarCallout = (kind = 'note') => {
  const view = getWysiwygView()
  if (!view) {
    ElMessage.warning('编辑器尚未准备好，请稍后重试。')
    return
  }

  restoreFixedToolbarSelection()

  if (!applyWysiwygCallout(view, { kind })) {
    ElMessage.warning('编辑器尚未准备好，请稍后重试。')
    return
  }

  syncAfterFixedToolbarCommand()
}

/** 代码块语言：只替换 info-string 的第一个词，保留标题与行标记。 */
const promptDiaryCodeBlockLanguage = async (pos) => {
  const view = getWysiwygView()
  const node = view?.state.doc.nodeAt(pos)
  if (!view || !node || node.type?.name !== 'codeBlock') {
    return
  }

  const currentInfo = node.attrs.language || ''
  let nextLanguage = ''
  try {
    const { value } = await ElMessageBox.prompt('只修改语言，标题、行号与行标记会保留。', '代码块语言', {
      confirmButtonText: '保存',
      cancelButtonText: '取消',
      inputValue: getFenceLanguage(currentInfo) === 'text' ? '' : getFenceLanguage(currentInfo),
      inputPlaceholder: 'js / py / bash（留空表示 text）',
    })
    nextLanguage = value
  } catch {
    return
  }

  const nextInfo = replaceFenceLanguage(currentInfo, String(nextLanguage || '').trim())
  if (nextInfo === currentInfo) {
    return
  }

  view.dispatch(
    view.state.tr.setNodeMarkup(pos, null, {
      ...node.attrs,
      language: nextInfo,
    })
  )
  syncAfterFixedToolbarCommand()
}

const getImageUploadErrorDetail = (error) =>
  error.response?.data?.image?.[0] ||
  error.response?.data?.note_id?.[0] ||
  error.response?.data?.non_field_errors?.[0] ||
  error.response?.data?.detail ||
  '图片上传失败，请检查文件格式、大小或稍后重试。'

const validateEditorImageFile = (file) => {
  if (!file?.type?.startsWith('image/')) {
    return '请选择 PNG、JPEG、GIF 或 WebP 图片文件。'
  }

  if (file.size > 8 * 1024 * 1024) {
    return `图片大小不能超过 8 MB，当前文件：${(file.size / 1024 / 1024).toFixed(2)} MB。`
  }

  return ''
}

const uploadEditorImageFile = async (file) => {
  const validationMessage = validateEditorImageFile(file)
  if (validationMessage) {
    ElMessage.warning(validationMessage)
    return null
  }

  if (!entry.value?.note_id) {
    ElMessage.warning('日记尚未准备好，请稍后再插入图片。')
    return null
  }

  const altText = file.name?.replace(/\.[^.]+$/, '') || 'image'
  const formData = new FormData()
  formData.append('note_id', entry.value.note_id)
  formData.append('image', file)
  formData.append('alt_text', altText)

  try {
    const { data } = await api.post('/notes/images/', formData)
    return {
      ...data,
      alt_text: data.alt_text || altText,
    }
  } catch (error) {
    ElMessage.error(getImageUploadErrorDetail(error))
    return null
  }
}

const uploadEditorImage = async (blob, callback) => {
  const data = await uploadEditorImageFile(blob)
  if (data) {
    callback(data.image_url, data.alt_text)
    ElMessage.success('图片已插入日记。')
  }

  return false
}

const normalizeImageReferenceValue = (value = '') => {
  try {
    return decodeURI(value).replace(/\\/g, '/')
  } catch {
    return value.replace(/\\/g, '/')
  }
}

const buildImageReferenceCandidates = (src = '') => {
  const normalizedSrc = normalizeImageReferenceValue(src)
  const candidates = new Set([src, normalizedSrc])

  try {
    const url = new URL(src, window.location.origin)
    candidates.add(url.href)
    candidates.add(url.pathname)
    candidates.add(`${url.pathname}${url.search}`)
    candidates.add(url.pathname.replace(/^\//, ''))
  } catch {
    // 非 URL 字符串只使用原始候选。
  }

  return Array.from(candidates).filter(Boolean)
}

const findMarkdownImageMatch = (markdown, imageSrc) => {
  const candidates = buildImageReferenceCandidates(imageSrc)
  const imagePattern = /!\[([^\]]*)\]\(([^)\s]+)(?:\s+["'][^"']*["'])?\)/g
  let match = imagePattern.exec(markdown)

  while (match) {
    const referenceUrl = normalizeImageReferenceValue(match[2])
    if (candidates.some((candidate) => referenceUrl === normalizeImageReferenceValue(candidate))) {
      return {
        start: match.index,
        end: match.index + match[0].length,
        alt: match[1],
        url: match[2],
      }
    }

    match = imagePattern.exec(markdown)
  }

  const fallbackCandidate = candidates.find((candidate) => markdown.includes(candidate))
  if (fallbackCandidate) {
    const start = markdown.indexOf(fallbackCandidate)
    return {
      start,
      end: start + fallbackCandidate.length,
      alt: '',
      url: fallbackCandidate,
    }
  }

  return null
}

const updateEditorMarkdown = (markdown) => {
  const extracted = extractTableLayoutMetadata(markdown)
  tableLayoutMetadata = extracted.layouts
  currentMarkdown.value = extracted.markdown
  editorInstance?.setMarkdown(extracted.markdown)
}

const replaceActiveImageMarkdown = (replacementMarkdown) => {
  if (!activeEditorImage.value?.src || !editorInstance) {
    return false
  }

  const markdown = getCurrentMarkdownWithTableLayouts()
  const match = findMarkdownImageMatch(markdown, activeEditorImage.value.src)
  if (!match) {
    ElMessage.warning('没有在正文中找到这张图片的引用。')
    return false
  }

  const nextMarkdown = `${markdown.slice(0, match.start)}${replacementMarkdown}${markdown.slice(match.end)}`
  updateEditorMarkdown(nextMarkdown)
  hideImageToolbar()
  return true
}

const findImageRecordBySrc = async (src) => {
  let page = 1

  while (page <= 20) {
    const { data } = await api.get('/notes/images/', {
      params: {
        note_id: entry.value?.note_id,
        page,
        page_size: 60,
      },
    })
    const candidates = buildImageReferenceCandidates(src).map(normalizeImageReferenceValue)
    const imageRecord = (data.results || []).find((image) =>
      candidates.includes(normalizeImageReferenceValue(image.image_url || ''))
    )

    if (imageRecord || !data.next) {
      return imageRecord || null
    }

    page += 1
  }

  return null
}

const hideImageToolbar = () => {
  imageToolbarVisible.value = false
  activeEditorImage.value = null
  imageToolbarPosition.top = -9999
  imageToolbarPosition.left = -9999
}

const showImageToolbar = (imageElement) => {
  const rect = imageElement.getBoundingClientRect()
  activeEditorImage.value = {
    src: imageElement.getAttribute('src') || '',
    alt: imageElement.getAttribute('alt') || '',
  }
  imageToolbarPosition.top = Math.max(12, rect.top - 48)
  imageToolbarPosition.left = Math.min(
    Math.max(12, rect.left),
    Math.max(12, window.innerWidth - 236)
  )
  imageToolbarVisible.value = true
}

const getImageElementFromEvent = (event) => {
  const target = event.target instanceof Element ? event.target : null
  const imageElement = target?.closest?.('.toastui-editor-contents img')
  return imageElement instanceof HTMLImageElement ? imageElement : null
}

const viewActiveImage = () => {
  if (!activeEditorImage.value?.src) {
    return
  }

  window.open(activeEditorImage.value.src, '_blank', 'noopener,noreferrer')
}

const triggerImageReplacement = () => {
  if (!activeEditorImage.value?.src) {
    return
  }

  imageReplaceInput.value?.click()
}

const handleImageReplacementChange = async (event) => {
  const file = event.target.files?.[0]
  event.target.value = ''

  if (!file || !activeEditorImage.value?.src) {
    return
  }

  const data = await uploadEditorImageFile(file)
  if (!data) {
    return
  }

  const safeAltText = (data.alt_text || activeEditorImage.value.alt || 'image').replaceAll(']', '\\]')
  if (replaceActiveImageMarkdown(`![${safeAltText}](${data.image_url})`)) {
    ElMessage.success('图片已替换，旧图片可在孤儿图片中清理。')
  }
}

const deleteActiveImage = async () => {
  if (!activeEditorImage.value?.src) {
    return
  }

  let shouldDeleteFile = false
  try {
    await ElMessageBox.confirm(
      '要同时删除这张图片的文件吗？',
      '删除图片',
      {
        confirmButtonText: '删除引用和文件',
        cancelButtonText: '只删除引用',
        distinguishCancelAndClose: true,
        type: 'warning',
      }
    )
    shouldDeleteFile = true
  } catch (action) {
    if (action === 'cancel') {
      shouldDeleteFile = false
    } else {
      return
    }
  }

  const imageSrc = activeEditorImage.value.src
  const deletedReference = replaceActiveImageMarkdown('')
  if (!deletedReference) {
    return
  }

  if (!shouldDeleteFile) {
    ElMessage.success('已删除正文中的图片引用。')
    return
  }

  try {
    const imageRecord = await findImageRecordBySrc(imageSrc)
    if (!imageRecord) {
      ElMessage.warning('已删除引用，但未找到对应图片文件记录。')
      return
    }

    await api.delete(`/notes/images/${imageRecord.id}/`)
    ElMessage.success('已删除图片引用和文件。')
  } catch (error) {
    const detail = error.response?.data?.detail || '已删除引用，但图片文件删除失败。'
    ElMessage.warning(detail)
  }
}

const triggerFixedToolbarImageUpload = () => {
  if (!editorInstance) {
    return
  }

  rememberFixedToolbarSelection()
  pendingImageSelectionRange = fixedToolbarSelectionRange.value
    ? [...fixedToolbarSelectionRange.value]
    : null
  imageInput.value?.click()
}

const handleToolbarImageChange = async (event) => {
  const file = event.target.files?.[0]
  event.target.value = ''

  if (!file) {
    pendingImageSelectionRange = null
    return
  }

  try {
    await uploadEditorImage(file, (imageUrl, altText) => {
      runFixedToolbarCommand('addImage', {
        imageUrl,
        altText,
      })
    })
  } finally {
    pendingImageSelectionRange = null
  }
}

const bindEditorImageListeners = () => {
  const rootElement = editorRoot.value
  if (!rootElement) {
    return null
  }

  const handleEditorClick = (event) => {
    const imageElement = getImageElementFromEvent(event)
    if (imageElement) {
      event.preventDefault()
      showImageToolbar(imageElement)
      return
    }

    hideImageToolbar()
  }

  const handleEditorKeydown = (event) => {
    if (!imageToolbarVisible.value || !['Backspace', 'Delete'].includes(event.key)) {
      return
    }

    event.preventDefault()
    event.stopImmediatePropagation()
    deleteActiveImage()
  }

  rootElement.addEventListener('click', handleEditorClick)
  rootElement.addEventListener('keydown', handleEditorKeydown, true)

  return () => {
    rootElement.removeEventListener('click', handleEditorClick)
    rootElement.removeEventListener('keydown', handleEditorKeydown, true)
  }
}

const buildEditor = () => {
  if (!editorRoot.value || editorInstance) {
    return
  }

  editorInstance = new Editor({
    el: editorRoot.value,
    height: '620px',
    initialEditType: 'wysiwyg',
    previewStyle: 'vertical',
    initialValue: currentMarkdown.value,
    language: 'zh-CN',
    usageStatistics: false,
    toolbarItems: [],
    hideModeSwitch: true,
    // 富文本面板里的提示框 / 代码块即时预览（decoration，不改变文档内容）
    plugins: [
      createRichBlockPreview({
        onEditLanguage: (pos) => promptDiaryCodeBlockLanguage(pos),
      }),
    ],
    hooks: {
      addImageBlobHook: uploadEditorImage,
    },
    events: {
      change: () => {
        currentMarkdown.value = editorInstance?.getMarkdown() || ''
        updateFixedToolbarSnapshot()
      },
      caretChange: () => {
        nextTick(updateFixedToolbarSnapshot)
      },
      focus: () => {
        nextTick(updateFixedToolbarSnapshot)
      },
    },
  })
  editorReady.value = true
  nextTick(updateFixedToolbarSnapshot)
  cleanupEditorImageListeners?.()
  cleanupEditorImageListeners = bindEditorImageListeners()
}

const saveDiary = async (viewAfterSave = false) => {
  if (!entry.value?.id) {
    ElMessage.warning('日记尚未加载完成。')
    return
  }

  if (!form.title.trim()) {
    ElMessage.warning('请填写日记标题。')
    return
  }

  saving.value = true

  try {
    const markdownContent = getCurrentMarkdownWithTableLayouts()
    const { data } = await api.patch(`/notes/diaries/${entry.value.id}/`, {
      title: form.title,
      mood: form.mood,
      weather: form.weather,
      summary: form.summary,
      markdown_content: markdownContent,
      create_version: false,
    })

    setFormFromEntry(data)
    editorInstance?.setMarkdown(currentMarkdown.value)
    ElMessage.success('日记已保存。')

    if (viewAfterSave) {
      router.push({ name: 'diary', params: { date: selectedDate.value } })
    }
  } catch (error) {
    const detail =
      error.response?.data?.title?.[0] ||
      error.response?.data?.summary?.[0] ||
      error.response?.data?.detail ||
      '日记保存失败，请稍后重试。'
    ElMessage.error(detail)
  } finally {
    saving.value = false
  }
}

const autoSaveDiary = async () => {
  if (!editorInstance || !entry.value?.id || !editorSettings.value.autoSaveEnabled || saving.value) {
    return
  }

  if (!form.title.trim()) {
    return
  }

  const markdownContent = getCurrentMarkdownWithTableLayouts()
  const currentSnapshot = getCurrentDiarySaveSnapshot(markdownContent)

  if (currentSnapshot === lastSavedContent) {
    return
  }

  try {
    await api.patch(`/notes/diaries/${entry.value.id}/`, {
      title: form.title,
      mood: form.mood,
      weather: form.weather,
      summary: form.summary,
      markdown_content: markdownContent,
      create_version: false,
    })

    lastSavedContent = currentSnapshot
  } catch (error) {
    console.error('自动保存日记失败', error)
  }
}

const stopAutoSave = () => {
  if (autoSaveTimer) {
    clearInterval(autoSaveTimer)
    autoSaveTimer = null
  }
}

const startAutoSave = () => {
  stopAutoSave()

  if (!editorSettings.value.autoSaveEnabled) {
    return
  }

  autoSaveTimer = setInterval(() => {
    autoSaveDiary()
  }, editorSettings.value.autoSaveIntervalMs)
}

const handleEditorSettingsChange = (event) => {
  editorSettings.value = event.detail || getEditorSettings()
  nextTick(updateFixedToolbarSnapshot)
  startAutoSave()
}

const goToDiary = () => {
  router.push({ name: 'diary', params: { date: selectedDate.value } })
}

const goToNeighbourDate = (days) => {
  router.push({ name: 'diary-edit', params: { date: addDaysToSelected(days) } })
}

const toggleDiaryFields = () => {
  diaryFieldsCollapsed.value = !diaryFieldsCollapsed.value
  hideImageToolbar()
}

const handleDocumentSelection = () => {
  nextTick(updateFixedToolbarSnapshot)
}

onMounted(async () => {
  await fetchOrCreateEntry()
  await nextTick()
  buildEditor()
  startAutoSave()

  document.addEventListener('selectionchange', handleDocumentSelection)
  window.addEventListener(EDITOR_SETTINGS_CHANGE_EVENT, handleEditorSettingsChange)
  window.addEventListener('resize', hideImageToolbar)
  window.addEventListener('scroll', hideImageToolbar, true)
  document.addEventListener('scroll', hideImageToolbar, true)
})

onBeforeUnmount(() => {
  document.removeEventListener('selectionchange', handleDocumentSelection)
  window.removeEventListener(EDITOR_SETTINGS_CHANGE_EVENT, handleEditorSettingsChange)
  window.removeEventListener('resize', hideImageToolbar)
  window.removeEventListener('scroll', hideImageToolbar, true)
  document.removeEventListener('scroll', hideImageToolbar, true)
  stopAutoSave()
  cleanupEditorImageListeners?.()
  cleanupEditorImageListeners = null
  hideImageToolbar()
  editorInstance?.destroy()
  editorInstance = null
  editorReady.value = false
})
</script>

<template>
  <main class="diary-edit-page page-shell">
    <WorkspaceShell>
      <section class="diary-edit-stage">
        <header class="diary-edit-header fade-rise-enter">
          <button type="button" class="back-button" @click="goToDiary">
            <el-icon><Back /></el-icon>
            <span>返回日记</span>
          </button>

          <div class="date-switcher">
            <button type="button" class="date-nav-button" aria-label="切换到前一天" @click="goToNeighbourDate(-1)">
              <el-icon><ArrowLeftBold /></el-icon>
              <span>前一天</span>
            </button>
            <div>
              <p>Writing</p>
              <h1>{{ selectedDateLabel }}</h1>
            </div>
            <button type="button" class="date-nav-button" aria-label="切换到后一天" @click="goToNeighbourDate(1)">
              <span>后一天</span>
              <el-icon><ArrowRightBold /></el-icon>
            </button>
          </div>

          <div class="save-actions">
            <div class="auto-save-badge" :class="{ 'is-disabled': !editorSettings.autoSaveEnabled }">
              <el-icon><Clock /></el-icon>
              <span>{{ autoSaveStatusText }}</span>
            </div>
            <el-button :loading="saving" @click="saveDiary(false)">
              <el-icon><Check /></el-icon>
              <span>保存</span>
            </el-button>
            <el-button type="primary" :loading="saving" @click="saveDiary(true)">
              <el-icon><Reading /></el-icon>
              <span>保存并查看</span>
            </el-button>
          </div>
        </header>

        <section
          class="diary-edit-layout fade-rise-enter-delay"
          :class="{ 'is-fields-collapsed': diaryFieldsCollapsed }"
          v-loading="loading"
        >
          <aside class="diary-fields" :class="{ 'is-collapsed': diaryFieldsCollapsed }">
            <button
              type="button"
              class="fields-toggle-button"
              :aria-label="diaryFieldsCollapsed ? '展开日记信息' : '收起日记信息'"
              :title="diaryFieldsCollapsed ? '展开日记信息' : '收起日记信息'"
              @click="toggleDiaryFields"
            >
              <el-icon>
                <ArrowRightBold v-if="diaryFieldsCollapsed" />
                <ArrowLeftBold v-else />
              </el-icon>
            </button>

            <template v-if="!diaryFieldsCollapsed">
              <div class="field-group">
                <label for="diary-title">标题</label>
                <el-input id="diary-title" v-model="form.title" maxlength="255" />
              </div>

              <div class="compact-fields">
                <div class="field-group">
                  <label for="diary-mood">心情</label>
                  <el-input id="diary-mood" v-model="form.mood" maxlength="30" placeholder="平静" />
                </div>

                <div class="field-group">
                  <label for="diary-weather">天气</label>
                  <el-input id="diary-weather" v-model="form.weather" maxlength="30" placeholder="晴" />
                </div>
              </div>

              <div class="field-group">
                <label for="diary-summary">摘要</label>
                <el-input
                  id="diary-summary"
                  v-model="form.summary"
                  type="textarea"
                  maxlength="200"
                  :autosize="{ minRows: 3, maxRows: 5 }"
                  show-word-limit
                />
              </div>

              <div class="diary-stats">
                <span>
                  <el-icon><Calendar /></el-icon>
                  {{ selectedDate }}
                </span>
                <strong>{{ wordCount }} 字</strong>
              </div>
            </template>

            <div v-else class="diary-fields-collapsed-summary" aria-hidden="true">
              <el-icon><Calendar /></el-icon>
              <span>{{ wordCount }}</span>
            </div>
          </aside>

          <article class="diary-editor-panel">
            <div class="editor-panel-head">
              <div>
                <p>Markdown</p>
                <h2>正文</h2>
              </div>
              <span>{{ saving ? '保存中' : '可编辑' }}</span>
            </div>

            <FixedEditorToolbar
              :editor-ready="editorReady"
              :toolbar-state="fixedToolbarState"
              :selected-text="fixedToolbarSelectedText"
              :heading-options="headingOptions"
              :max-table-rows="MAX_TABLE_ROW_COUNT"
              :max-table-columns="MAX_TABLE_COLUMN_COUNT"
              :active-callout="activeCalloutType"
              @remember-selection="rememberFixedToolbarSelection"
              @command="runFixedToolbarCommand"
              @apply-heading="applyFixedToolbarHeading"
              @insert-link="insertFixedToolbarLink"
              @insert-image="triggerFixedToolbarImageUpload"
              @insert-table="insertFixedToolbarTable"
              @insert-math="insertFixedToolbarMath"
              @insert-callout="insertFixedToolbarCallout"
              @open-code-block-options="openFixedToolbarCodeBlockOptions"
            />


            <div class="diary-editor-body">
              <div ref="editorRoot" class="diary-editor-root"></div>
              <input
                ref="imageInput"
                class="toolbar-image-input"
                type="file"
                accept="image/png,image/jpeg,image/gif,image/webp"
                @change="handleToolbarImageChange"
              />
              <input
                ref="imageReplaceInput"
                class="toolbar-image-input"
                type="file"
                accept="image/png,image/jpeg,image/gif,image/webp"
                @change="handleImageReplacementChange"
              />
            </div>
          </article>

          <div
            v-if="imageToolbarVisible"
            class="editor-image-toolbar"
            :style="{ top: `${imageToolbarPosition.top}px`, left: `${imageToolbarPosition.left}px` }"
            @mousedown.prevent
          >
            <button type="button" @click="viewActiveImage">查看</button>
            <button type="button" @click="triggerImageReplacement">替换</button>
            <button type="button" class="danger" @click="deleteActiveImage">删除</button>
          </div>
        </section>
      </section>
    </WorkspaceShell>
  </main>
</template>

<style scoped>
.diary-edit-stage {
  width: min(1440px, 100%);
  margin: 0 auto;
  padding: 34px clamp(20px, 4vw, 54px) 54px;
}

.diary-edit-header {
  display: grid;
  grid-template-columns: minmax(138px, 200px) minmax(0, 1fr) minmax(200px, auto);
  align-items: center;
  gap: 14px;
  margin-bottom: 24px;
}

.back-button,
.date-nav-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border-soft);
  background: var(--surface);
  color: var(--brand-navy);
  cursor: pointer;
  transition:
    transform 0.2s ease,
    border-color 0.2s ease,
    background 0.2s ease,
    color 0.2s ease;
}

.back-button {
  gap: 8px;
  min-height: 42px;
  padding: 0 14px;
  border-radius: var(--radius-md);
  font-weight: 800;
}

.date-nav-button {
  gap: 7px;
  min-height: 42px;
  padding: 0 13px;
  border-radius: var(--radius-md);
  color: var(--ink-soft);
  font: inherit;
  font-size: 0.88rem;
  font-weight: 800;
  white-space: nowrap;
}

.back-button:hover,
.date-nav-button:hover {
  transform: translateY(-1px);
  border-color: var(--accent-border);
  background: var(--accent-soft);
  color: var(--brand-blue);
}

.date-switcher {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  min-width: 0;
  text-align: center;
}

.date-switcher p,
.editor-panel-head p {
  margin: 0 0 6px;
  color: var(--brand-blue);
  font-size: 0.76rem;
  font-weight: 800;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.date-switcher h1,
.editor-panel-head h2 {
  margin: 0;
  color: var(--brand-navy);
  letter-spacing: -0.04em;
}

.date-switcher h1 {
  overflow: hidden;
  font-size: 2rem;
  letter-spacing: 0;
  line-height: 1.08;
  text-overflow: clip;
  white-space: nowrap;
  word-break: keep-all;
}

.save-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
}

.auto-save-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 38px;
  padding: 0 14px;
  border-radius: var(--radius-md);
  background: rgba(37, 99, 235, 0.08);
  color: var(--brand-blue);
  font-size: 0.86rem;
  font-weight: 700;
  white-space: nowrap;
}

.auto-save-badge.is-disabled {
  background: var(--surface-soft);
  color: var(--ink-soft);
}

.auto-save-badge :deep(.el-icon) {
  font-size: 1rem;
}

.save-actions :deep(.el-button) {
  min-height: 42px;
  border-radius: var(--radius-md);
  font-weight: 800;
}

.diary-edit-layout {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 22px;
  align-items: start;
}

.diary-fields,
.diary-editor-panel {
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-soft);
  backdrop-filter: blur(18px);
}

.diary-fields {
  position: sticky;
  top: 26px;
  display: grid;
  gap: 18px;
  box-sizing: border-box;
  width: clamp(280px, 24vw, 360px);
  padding: 22px;
  overflow: hidden;
  transition:
    width 0.3s cubic-bezier(0.2, 0.8, 0.2, 1),
    padding 0.24s ease,
    min-height 0.24s ease,
    border-radius 0.24s ease;
  will-change: width;
}

.diary-fields.is-collapsed {
  width: 76px;
  min-height: 76px;
  padding: 14px;
  justify-items: center;
}

.fields-toggle-button {
  position: absolute;
  top: 14px;
  right: 14px;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 1px solid var(--border-soft);
  border-radius: 12px;
  background: var(--control-background);
  color: var(--brand-navy);
  cursor: pointer;
  transition:
    transform 0.18s ease,
    border-color 0.18s ease,
    background 0.18s ease,
    color 0.18s ease,
    box-shadow 0.18s ease;
}

.fields-toggle-button:hover {
  transform: translateY(-1px);
  border-color: var(--accent-border);
  background: var(--accent-soft);
  color: var(--brand-blue);
  box-shadow: 0 10px 22px rgba(15, 23, 42, 0.1);
}

.diary-fields.is-collapsed .fields-toggle-button {
  position: static;
}

.diary-fields-collapsed-summary {
  display: grid;
  justify-items: center;
  gap: 8px;
  color: var(--ink-soft);
  font-size: 0.76rem;
  font-weight: 800;
  line-height: 1;
}

.diary-fields-collapsed-summary :deep(.el-icon) {
  color: var(--brand-blue);
  font-size: 1rem;
}

.field-group {
  display: grid;
  gap: 8px;
}

.field-group label {
  color: var(--brand-navy);
  font-size: 0.86rem;
  font-weight: 800;
}

.field-group :deep(.el-input__wrapper),
.field-group :deep(.el-textarea__inner) {
  border-radius: var(--radius-md);
  box-shadow: 0 0 0 1px var(--border-soft) inset;
}

.field-group :deep(.el-input__wrapper.is-focus),
.field-group :deep(.el-textarea__inner:focus) {
  box-shadow: 0 0 0 1px var(--accent-border) inset;
}

.compact-fields {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.diary-stats {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  min-height: 46px;
  padding: 0 14px;
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-md);
  background: var(--surface-soft);
}

.diary-stats span {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  overflow: hidden;
  color: var(--ink-soft);
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.diary-stats strong {
  flex: 0 0 auto;
  color: var(--brand-navy);
}

.diary-editor-panel {
  min-width: 0;
  overflow: visible;
}

.diary-editor-body {
  min-width: 0;
  overflow: hidden;
  border-radius: 0 0 var(--radius-lg) var(--radius-lg);
}

.editor-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 22px 24px;
  border-bottom: 1px solid var(--border-soft);
}

.editor-panel-head h2 {
  font-size: 1.36rem;
}

.editor-panel-head span {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 0 12px;
  border-radius: var(--radius-md);
  background: var(--accent-soft);
  color: var(--brand-blue);
  font-size: 0.82rem;
  font-weight: 800;
}

.floating-toolbar {
  position: fixed;
  z-index: 200;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 11px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-soft);
  backdrop-filter: blur(16px);
}

.toolbar-group {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.heading-group {
  flex-wrap: wrap;
}

.toolbar-divider {
  width: 1px;
  height: 28px;
  background: linear-gradient(180deg, rgba(148, 163, 184, 0), rgba(148, 163, 184, 0.32), rgba(148, 163, 184, 0));
}

.toolbar-button,
.toolbar-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 36px;
  height: 36px;
  padding: 0 11px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 13px;
  background: var(--control-background);
  color: var(--brand-navy);
  cursor: pointer;
  transition:
    transform 0.18s ease,
    background-color 0.18s ease,
    border-color 0.18s ease,
    color 0.18s ease,
    box-shadow 0.18s ease;
}

.toolbar-button:hover,
.toolbar-chip:hover {
  transform: translateY(-1px);
  border-color: rgba(37, 99, 235, 0.2);
  background: var(--control-selected-background);
  color: var(--brand-blue);
  box-shadow:
    0 10px 20px rgba(15, 23, 42, 0.1),
    var(--inset-highlight);
}

.toolbar-button:active,
.toolbar-chip:active {
  transform: translateY(0);
  background: rgba(37, 99, 235, 0.14);
  border-color: rgba(37, 99, 235, 0.24);
  color: var(--brand-blue);
}

.toolbar-button.is-active,
.toolbar-chip.is-active {
  border-color: rgba(37, 99, 235, 0.28);
  background: rgba(37, 99, 235, 0.12);
  color: var(--brand-blue);
  box-shadow: inset 0 0 0 1px rgba(37, 99, 235, 0.08);
}

.toolbar-button:disabled,
.toolbar-chip:disabled {
  cursor: not-allowed;
  opacity: 0.48;
  transform: none;
  box-shadow: none;
}

.toolbar-chip {
  min-width: 44px;
  font-size: 0.76rem;
  font-weight: 800;
}

.toolbar-strike {
  text-decoration: line-through;
}

.with-icon :deep(.el-icon) {
  font-size: 1rem;
}

.toolbar-table-icon {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border: 1px solid currentColor;
  border-radius: 3px;
  font-size: 0;
}

.toolbar-table-icon::before,
.toolbar-table-icon::after {
  position: absolute;
  background: currentColor;
  content: '';
}

.toolbar-table-icon::before {
  top: 50%;
  left: 0;
  width: 100%;
  height: 1px;
  transform: translateY(-50%);
}

.toolbar-table-icon::after {
  top: 0;
  left: 50%;
  width: 1px;
  height: 100%;
  transform: translateX(-50%);
}

.toolbar-image-input {
  display: none;
}

.editor-image-toolbar {
  position: fixed;
  z-index: 230;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 10px;
  background: var(--overlay-background);
  box-shadow: var(--shadow-soft);
  backdrop-filter: blur(12px);
}

.editor-image-toolbar button {
  min-width: 44px;
  height: 30px;
  padding: 0 10px;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: var(--brand-navy);
  font: inherit;
  font-size: 0.82rem;
  font-weight: 800;
  cursor: pointer;
  transition:
    background 0.16s ease,
    color 0.16s ease;
}

.editor-image-toolbar button:hover {
  background: var(--accent-soft);
  color: var(--brand-blue);
}

.editor-image-toolbar button.danger {
  color: var(--danger);
}

.editor-image-toolbar button.danger:hover {
  background: rgba(180, 35, 24, 0.08);
  color: var(--danger);
}

.diary-editor-root {
  min-height: 620px;
}

.diary-editor-root :deep(.toastui-editor-defaultUI) {
  border: none;
  background: transparent;
}

.diary-editor-root :deep(.toastui-editor-toolbar) {
  display: none;
}

.diary-editor-root :deep(.toastui-editor-defaultUI-toolbar) {
  display: none;
}

.diary-editor-root :deep(.toastui-editor-contents) {
  min-height: 620px;
  max-width: 100%;
  overflow-x: hidden;
  padding: 26px 30px;
  font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
  color: var(--text-primary);
  font-size: var(--editor-font-size, 1rem);
  line-height: 1.9;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.diary-editor-root :deep(.toastui-editor-contents h1),
.diary-editor-root :deep(.toastui-editor-contents h2),
.diary-editor-root :deep(.toastui-editor-contents h3),
.diary-editor-root :deep(.toastui-editor-contents h4),
.diary-editor-root :deep(.toastui-editor-contents h5),
.diary-editor-root :deep(.toastui-editor-contents h6) {
  border-bottom: none;
  color: var(--brand-navy);
  letter-spacing: 0;
  line-height: 1.18;
  padding-bottom: 0;
}

.diary-editor-root :deep(.toastui-editor-contents h1) {
  margin: 0 0 22px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-soft);
  font-size: clamp(1.9rem, 3vw, 2.8rem);
  font-weight: 800;
}

.diary-editor-root :deep(.toastui-editor-contents h2) {
  position: relative;
  margin: 34px 0 14px;
  padding-left: 18px;
  font-size: clamp(1.24rem, 2vw, 1.62rem);
  font-weight: 800;
}

.diary-editor-root :deep(.toastui-editor-contents h2::before) {
  position: absolute;
  top: 0.62em;
  left: 0;
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: var(--brand-blue);
  box-shadow: 0 0 0 5px rgba(37, 99, 235, 0.1);
  content: '';
}

.diary-editor-root :deep(.toastui-editor-contents p),
.diary-editor-root :deep(.toastui-editor-contents li),
.diary-editor-root :deep(.toastui-editor-contents blockquote) {
  color: var(--brand-navy);
}

.diary-editor-root :deep(.toastui-editor-contents pre),
.diary-editor-root :deep(.toastui-editor-contents code),
.diary-editor-root :deep(.toastui-editor-contents .toastui-editor-ww-code-block),
.diary-editor-root :deep(.toastui-editor-contents .toastui-editor-ww-code-block code) {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.diary-editor-root :deep(.toastui-editor-contents pre),
.diary-editor-root :deep(.toastui-editor-contents .toastui-editor-ww-code-block) {
  max-width: 100%;
  overflow-x: hidden;
  border: 1px solid var(--table-border);
  border-radius: 18px;
  background: var(--code-background) !important;
  color: var(--code-text) !important;
}

.diary-editor-root :deep(.toastui-editor-contents pre code),
.diary-editor-root :deep(.toastui-editor-contents .toastui-editor-ww-code-block code) {
  background: transparent !important;
  color: inherit !important;
}

.diary-editor-root :deep(.toastui-editor-contents blockquote) {
  margin: 0 0 26px;
  padding: 18px 20px;
  border-left-color: var(--brand-blue);
  border-radius: 0 18px 18px 0;
  background: var(--quote-background);
  color: var(--ink-soft);
}

.diary-editor-root :deep(.toastui-editor-contents ul),
.diary-editor-root :deep(.toastui-editor-contents ol) {
  padding-left: 1.28em;
}

.diary-editor-root :deep(.toastui-editor-contents li + li) {
  margin-top: 0.4em;
}

.diary-editor-root :deep(.toastui-editor-contents table) {
  width: 100%;
  inline-size: 100%;
  max-width: 100%;
  max-inline-size: 100%;
  min-width: 0;
  min-inline-size: 0;
  margin: 16px 0 26px;
  overflow: hidden;
  box-sizing: border-box;
  border: 1px solid rgba(100, 116, 139, 0.28);
  border-collapse: collapse;
  border-radius: 18px;
  background: var(--surface-soft);
  table-layout: fixed;
}

.diary-editor-root :deep(.toastui-editor-contents thead th) {
  background: rgba(37, 99, 235, 0.08);
}

.diary-editor-root :deep(.toastui-editor-contents th),
.diary-editor-root :deep(.toastui-editor-contents td) {
  min-width: 0;
  max-width: 0;
  padding: 12px 14px;
  border-right: 1px solid rgba(100, 116, 139, 0.24);
  border-bottom: 1px solid rgba(100, 116, 139, 0.24);
  color: var(--brand-navy);
  overflow-wrap: anywhere;
  word-break: break-word;
  vertical-align: top;
}

.diary-editor-root :deep(.toastui-editor-contents th:not([align])),
.diary-editor-root :deep(.toastui-editor-contents td:not([align])) {
  text-align: left;
}

/* toast-ui 把表头单元格内的 <p> 硬编码成白色，表头是浅色底，需要取回正文色 */
.diary-editor-root :deep(.toastui-editor-contents th p) {
  color: var(--brand-navy);
}

.diary-editor-root :deep(.toastui-editor-contents th:last-child),
.diary-editor-root :deep(.toastui-editor-contents td:last-child) {
  border-right: none;
}

.diary-editor-root :deep(.toastui-editor-contents tr:last-child td) {
  border-bottom: none;
}

.diary-table-picker-panel {
  position: fixed;
  z-index: 220;
  display: grid;
  gap: 12px;
  width: max-content;
  padding: 14px 15px 16px;
  border: 1px solid var(--border-soft);
  border-radius: 18px;
  background: var(--surface);
  box-shadow: 0 20px 50px rgba(15, 23, 42, 0.16);
  backdrop-filter: blur(16px);
}

.toolbar-table-picker-head {
  color: var(--brand-navy);
  font-size: 0.9rem;
}

.toolbar-table-picker-grid {
  display: grid;
  gap: 6px;
}

.toolbar-table-picker-cell {
  width: 26px;
  height: 24px;
  border: 1px solid rgba(148, 163, 184, 0.28);
  border-radius: 6px;
  background: var(--surface-soft);
  cursor: pointer;
  transition:
    background 0.16s ease,
    border-color 0.16s ease,
    transform 0.16s ease;
}

.toolbar-table-picker-cell:hover,
.toolbar-table-picker-cell.is-active {
  border-color: rgba(37, 99, 235, 0.34);
  background: var(--accent-soft);
}

@media (max-width: 1180px) {
  .diary-edit-header,
  .diary-edit-layout {
    grid-template-columns: 1fr;
  }

  .diary-edit-layout.is-fields-collapsed {
    grid-template-columns: 1fr;
  }

  .date-switcher {
    order: -1;
  }

  .save-actions {
    justify-content: stretch;
  }

  .auto-save-badge {
    flex: 1 1 100%;
    justify-content: center;
  }

  .save-actions :deep(.el-button),
  .back-button {
    flex: 1 1 160px;
  }

  .diary-fields {
    position: static;
    width: 100%;
  }

  .diary-fields.is-collapsed {
    grid-template-columns: auto auto;
    justify-content: start;
    justify-items: start;
    width: 100%;
    min-height: 64px;
  }

  .diary-fields.is-collapsed .diary-fields-collapsed-summary {
    grid-auto-flow: column;
    align-items: center;
    justify-items: start;
  }
}

@media (max-width: 720px) {
  .diary-edit-stage {
    padding: 24px 16px 40px;
  }

  .diary-edit-header {
    gap: 12px;
  }

  .date-switcher {
    grid-template-columns: auto minmax(0, 1fr) auto;
    gap: 6px;
  }

  .date-switcher h1 {
    font-size: 1.56rem;
  }

  .date-nav-button {
    min-height: 38px;
    padding: 0 8px;
    font-size: 0.78rem;
  }

  .compact-fields {
    grid-template-columns: 1fr;
  }

  .editor-panel-head {
    align-items: flex-start;
    flex-direction: column;
  }

  .floating-toolbar {
    flex-wrap: wrap;
    width: min(320px, calc(100vw - 32px));
  }

  .diary-editor-root,
  .diary-editor-root :deep(.toastui-editor-defaultUI) {
    min-height: 560px;
  }
}

@media (max-width: 520px) {
  .date-switcher h1 {
    font-size: 1.3rem;
  }

  .date-nav-button {
    width: 34px;
    min-height: 34px;
    padding: 0;
  }

  .date-nav-button span {
    display: none;
  }
}
</style>
