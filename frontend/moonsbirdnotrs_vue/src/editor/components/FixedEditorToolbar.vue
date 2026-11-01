<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import {
  Checked,
  Document,
  Grid,
  Link,
  List,
  Minus,
  Operation,
  Picture,
  Setting,
  Tickets,
} from '@element-plus/icons-vue'

const props = defineProps({
  editorReady: {
    type: Boolean,
    default: false,
  },
  toolbarState: {
    type: Object,
    required: true,
  },
  selectedText: {
    type: String,
    default: '',
  },
  headingOptions: {
    type: Array,
    default: () => [],
  },
  maxTableRows: {
    type: Number,
    default: 10,
  },
  maxTableColumns: {
    type: Number,
    default: 10,
  },
  /** 选区当前所在提示框的类型（小写 canonical），不在提示框内为空串 */
  activeCallout: {
    type: String,
    default: '',
  },
})

const emit = defineEmits([
  'command',
  'apply-heading',
  'insert-link',
  'insert-image',
  'insert-table',
  'insert-math',
  'insert-callout',
  'open-code-block-options',
  'apply-code-block-auto-format',
  'remember-selection',
])

const linkPopoverVisible = ref(false)
const tablePopoverVisible = ref(false)
const calloutPopoverVisible = ref(false)
const linkUrlInput = ref(null)
const linkForm = reactive({
  text: '',
  url: '',
  error: '',
})
const tablePreview = reactive({
  rows: 3,
  columns: 3,
})

const inlineButtons = [
  { command: 'bold', action: 'bold', stateKey: 'strong', label: '加粗', text: 'B', textClass: 'is-bold' },
  { command: 'italic', action: 'italic', stateKey: 'italic', label: '斜体', text: 'I', textClass: 'is-italic' },
  { command: 'strike', action: 'strike', stateKey: 'strike', label: '删除线', text: 'S', textClass: 'is-strike' },
  { command: 'code', action: 'inline-code', stateKey: 'code', label: '行内代码', text: '</>', textClass: 'is-code' },
]

const blockButtons = [
  { command: 'blockQuote', action: 'block-quote', stateKey: 'blockQuote', label: '引用', icon: Tickets },
  { command: 'bulletList', action: 'bullet-list', stateKey: 'bulletList', label: '无序列表', icon: List },
  { command: 'orderedList', action: 'ordered-list', stateKey: 'orderedList', label: '有序列表', icon: Operation },
  { command: 'taskList', action: 'task-list', stateKey: 'taskList', label: '任务列表', icon: Checked },
  { command: 'codeBlock', action: 'code-block', stateKey: 'codeBlock', label: '代码块', icon: Document },
]

// 提示框类型，与阅读端 utils/richContent.js 的解析保持一致
const calloutKinds = [
  { kind: 'note', label: '注意' },
  { kind: 'tip', label: '提示' },
  { kind: 'important', label: '重要' },
  { kind: 'warning', label: '警告' },
  { kind: 'caution', label: '危险' },
]

const tableRows = computed(() =>
  Array.from({ length: Math.max(1, props.maxTableRows) }, (_, index) => index + 1)
)
const tableColumns = computed(() =>
  Array.from({ length: Math.max(1, props.maxTableColumns) }, (_, index) => index + 1)
)
const tablePreviewLabel = computed(() => `${tablePreview.rows} 行 × ${tablePreview.columns} 列`)

const isActive = (stateKey) => Boolean(props.toolbarState?.[stateKey]?.active)
const isHeadingActive = (level) => Boolean(props.toolbarState?.headings?.[level]?.active)

const runCommand = (command) => {
  if (props.editorReady) {
    emit('command', command)
  }
}

const applyHeading = (level) => {
  if (props.editorReady) {
    emit('apply-heading', level)
  }
}

const rememberSelection = () => {
  if (props.editorReady) {
    emit('remember-selection')
  }
}

const openLinkPopover = () => {
  if (!props.editorReady) {
    return
  }

  linkForm.text = props.selectedText
  linkForm.url = ''
  linkForm.error = ''
  linkPopoverVisible.value = true
  nextTick(() => linkUrlInput.value?.focus?.())
}

const closeLinkPopover = () => {
  linkPopoverVisible.value = false
  linkForm.error = ''
}

const hasUnsupportedLinkScheme = (linkUrl) => {
  const scheme = linkUrl.match(/^([a-z][a-z\d+.-]*):/i)?.[1]?.toLowerCase()
  return Boolean(scheme && !['http', 'https', 'mailto', 'tel'].includes(scheme))
}

const submitLink = () => {
  const linkUrl = linkForm.url.trim()
  const linkText = linkForm.text.trim()

  if (!linkUrl) {
    linkForm.error = '请输入链接地址'
    return
  }

  if (!linkText) {
    linkForm.error = '没有选中文字时，请填写链接文字'
    return
  }

  if (hasUnsupportedLinkScheme(linkUrl)) {
    linkForm.error = '链接仅支持 http、https、mailto、tel 或相对地址'
    return
  }

  emit('insert-link', { linkUrl, linkText })
  closeLinkPopover()
}

const openTablePopover = () => {
  if (!props.editorReady) {
    return
  }

  tablePreview.rows = Math.min(3, props.maxTableRows)
  tablePreview.columns = Math.min(3, props.maxTableColumns)
  tablePopoverVisible.value = true
}

const previewTableSize = (rows, columns) => {
  tablePreview.rows = rows
  tablePreview.columns = columns
}

const isTableCellActive = (rows, columns) =>
  rows <= tablePreview.rows && columns <= tablePreview.columns

const insertTable = (rows, columns) => {
  emit('insert-table', rows, columns)
  tablePopoverVisible.value = false
}

const insertMath = (displayMode) => {
  if (!props.editorReady) {
    return
  }
  emit('insert-math', displayMode)
}

const openCalloutPopover = () => {
  if (!props.editorReady) {
    return
  }
  calloutPopoverVisible.value = true
}

const insertCallout = (kind) => {
  emit('insert-callout', kind)
  calloutPopoverVisible.value = false
}

/*
 * 吸顶状态
 * ---------------------------------------------------------------------------
 * 工具栏在正文顶部时和正文是一体的（无边框、无阴影）；一旦被滚动「顶住」，
 * 就切换成浮起的小卡片，避免长笔记下滑时一排按钮悬在半空显得很脏。
 *
 * 用哨兵元素 + IntersectionObserver 判断，比监听 scroll 更稳（不需要节流，
 * 也不会在嵌套滚动容器里算错位置）。
 */
const isPinned = ref(false)
const pinSentinel = ref(null)
let pinObserver = null

const observePinnedState = () => {
  if (typeof IntersectionObserver !== 'function' || !pinSentinel.value) {
    return
  }

  pinObserver?.disconnect()
  pinObserver = new IntersectionObserver(
    ([entry]) => {
      isPinned.value = !entry.isIntersecting
    },
    { threshold: 0, rootMargin: '-16px 0px 0px 0px' }
  )
  pinObserver.observe(pinSentinel.value)
}

onMounted(observePinnedState)
onBeforeUnmount(() => {
  pinObserver?.disconnect()
  pinObserver = null
})

watch(
  () => props.editorReady,
  (ready) => {
    if (!ready) {
      linkPopoverVisible.value = false
      tablePopoverVisible.value = false
      calloutPopoverVisible.value = false
    }

    nextTick(observePinnedState)
  }
)
</script>

<template>
  <div ref="pinSentinel" class="fixed-toolbar-sentinel" aria-hidden="true"></div>

  <nav
    class="fixed-editor-toolbar"
    :class="{ 'is-pinned': isPinned }"
    aria-label="固定正文工具栏"
  >
    <div class="fixed-editor-toolbar-track">
      <div class="fixed-toolbar-group" aria-label="标题">
        <button
          v-for="option in headingOptions"
          :key="option.value"
          type="button"
          class="fixed-toolbar-button fixed-toolbar-heading"
          :class="{ 'is-active': isHeadingActive(option.value) }"
          :disabled="!editorReady"
          :aria-label="`标题 ${option.label}`"
          :aria-pressed="isHeadingActive(option.value)"
          :title="`标题 ${option.label}`"
          @mousedown.prevent="rememberSelection"
          @click="applyHeading(option.value)"
        >
          {{ option.label }}
        </button>
      </div>

      <span class="fixed-toolbar-divider" aria-hidden="true"></span>

      <div class="fixed-toolbar-group" aria-label="文字格式">
        <button
          v-for="button in inlineButtons"
          :key="button.command"
          type="button"
          class="fixed-toolbar-button"
          :data-action="button.action"
          :class="{ 'is-active': isActive(button.stateKey) }"
          :disabled="!editorReady"
          :aria-label="button.label"
          :aria-pressed="isActive(button.stateKey)"
          :title="button.label"
          @mousedown.prevent="rememberSelection"
          @click="runCommand(button.command)"
        >
          <el-icon v-if="button.icon"><component :is="button.icon" /></el-icon>
          <span v-else :class="button.textClass">{{ button.text }}</span>
        </button>
      </div>

      <span class="fixed-toolbar-divider" aria-hidden="true"></span>

      <div class="fixed-toolbar-group" aria-label="段落格式">
        <button
          v-for="button in blockButtons"
          :key="button.command"
          type="button"
          class="fixed-toolbar-button"
          :data-action="button.action"
          :class="{ 'is-active': isActive(button.stateKey) }"
          :disabled="!editorReady"
          :aria-label="button.label"
          :aria-pressed="isActive(button.stateKey)"
          :title="button.label"
          @mousedown.prevent="rememberSelection"
          @click="runCommand(button.command)"
        >
          <el-icon><component :is="button.icon" /></el-icon>
        </button>
      </div>

      <span class="fixed-toolbar-divider" aria-hidden="true"></span>

      <div class="fixed-toolbar-group" aria-label="富文本">
        <button
          type="button"
          class="fixed-toolbar-button"
          :disabled="!editorReady"
          aria-label="插入行内公式"
          title="行内公式 $…$"
          @mousedown.prevent="rememberSelection"
          @click="insertMath(false)"
        >
          <span class="is-math">∑</span>
        </button>

        <button
          type="button"
          class="fixed-toolbar-button"
          :disabled="!editorReady"
          aria-label="插入块级公式"
          title="块级公式 $$…$$"
          @mousedown.prevent="rememberSelection"
          @click="insertMath(true)"
        >
          <span class="is-math-block">∑</span>
        </button>

        <el-popover
          :visible="calloutPopoverVisible"
          trigger="manual"
          placement="bottom-end"
          :width="190"
          popper-class="fixed-callout-popover"
          @update:visible="calloutPopoverVisible = $event"
        >
          <template #reference>
            <button
              type="button"
              class="fixed-toolbar-button"
              :class="{ 'is-active': Boolean(activeCallout) || calloutPopoverVisible }"
              :disabled="!editorReady"
              :aria-label="activeCallout ? '修改或取消提示框' : '插入提示框'"
              :title="activeCallout ? '再次点击当前类型可取消' : '插入提示框'"
              data-action="callout"
              @mousedown.prevent="rememberSelection"
              @click.stop="openCalloutPopover"
            >
              <span class="is-callout">❢</span>
            </button>
          </template>

          <div class="fixed-callout-picker" @mousedown.prevent>
            <p class="fixed-popover-title">提示框</p>
            <button
              v-for="item in calloutKinds"
              :key="item.kind"
              type="button"
              class="fixed-callout-option"
              :class="[`is-${item.kind}`, { 'is-current': activeCallout === item.kind }]"
              @click="insertCallout(item.kind)"
            >
              <span class="fixed-callout-dot" aria-hidden="true"></span>
              {{ item.label }}
              <span v-if="activeCallout === item.kind" class="fixed-callout-hint">取消</span>
            </button>
          </div>
        </el-popover>

        <el-tooltip content="代码块设置：标题 / 行号 / 标记 / 折叠" placement="bottom" :show-after="120">
          <button
            type="button"
            class="fixed-toolbar-button"
            :class="{ 'is-active': Boolean(toolbarState.codeBlock?.active) }"
            :disabled="!editorReady"
            aria-label="代码块设置"
            title="代码块设置"
            data-action="code-block-options"
            @mousedown.prevent="rememberSelection"
            @click="emit('open-code-block-options')"
          >
            <el-icon><Setting /></el-icon>
          </button>
        </el-tooltip>
      </div>

      <span class="fixed-toolbar-divider" aria-hidden="true"></span>

      <div class="fixed-toolbar-group" aria-label="插入">
        <button
          type="button"
          class="fixed-toolbar-button"
          :disabled="!editorReady"
          aria-label="插入分割线"
          title="插入分割线"
          @mousedown.prevent="rememberSelection"
          @click="runCommand('thematicBreak')"
        >
          <el-icon><Minus /></el-icon>
        </button>

        <el-popover
          :visible="linkPopoverVisible"
          trigger="manual"
          placement="bottom"
          :width="320"
          popper-class="fixed-link-popover"
          @update:visible="linkPopoverVisible = $event"
        >
          <template #reference>
            <button
              type="button"
              class="fixed-toolbar-button"
              :class="{ 'is-active': isActive('link') || linkPopoverVisible }"
              :disabled="!editorReady"
              aria-label="插入链接"
              :aria-pressed="isActive('link')"
              title="插入链接"
              @mousedown.prevent="rememberSelection"
              @click.stop="openLinkPopover"
            >
              <el-icon><Link /></el-icon>
            </button>
          </template>

          <form class="fixed-link-form" @submit.prevent="submitLink">
            <div>
              <label for="fixed-link-text">链接文字</label>
              <el-input id="fixed-link-text" v-model="linkForm.text" placeholder="显示文字" />
            </div>
            <div>
              <label for="fixed-link-url">链接地址</label>
              <el-input
                id="fixed-link-url"
                ref="linkUrlInput"
                v-model="linkForm.url"
                placeholder="https://example.com"
                @input="linkForm.error = ''"
              />
            </div>
            <p v-if="linkForm.error" class="fixed-link-error">{{ linkForm.error }}</p>
            <div class="fixed-popover-actions">
              <el-button size="small" @click="closeLinkPopover">取消</el-button>
              <el-button size="small" type="primary" native-type="submit">插入</el-button>
            </div>
          </form>
        </el-popover>

        <button
          type="button"
          class="fixed-toolbar-button"
          :disabled="!editorReady"
          aria-label="上传图片"
          title="上传图片"
          @mousedown.prevent="rememberSelection"
          @click="emit('insert-image')"
        >
          <el-icon><Picture /></el-icon>
        </button>

        <el-popover
          :visible="tablePopoverVisible"
          trigger="manual"
          placement="bottom-end"
          :width="326"
          popper-class="fixed-table-popover"
          @update:visible="tablePopoverVisible = $event"
        >
          <template #reference>
            <button
              type="button"
              class="fixed-toolbar-button"
              :class="{ 'is-active': tablePopoverVisible }"
              :disabled="!editorReady"
              aria-label="插入表格"
              title="插入表格"
              @mousedown.prevent="rememberSelection"
              @click.stop="openTablePopover"
            >
              <el-icon><Grid /></el-icon>
            </button>
          </template>

          <div class="fixed-table-picker" @mousedown.prevent>
            <strong>{{ tablePreviewLabel }}</strong>
            <div
              class="fixed-table-picker-grid"
              :style="{ gridTemplateColumns: `repeat(${tableColumns.length}, 24px)` }"
            >
              <template v-for="row in tableRows" :key="row">
                <button
                  v-for="column in tableColumns"
                  :key="`${row}-${column}`"
                  type="button"
                  class="fixed-table-picker-cell"
                  :class="{ 'is-active': isTableCellActive(row, column) }"
                  :aria-label="`插入 ${row} 行 ${column} 列表格`"
                  @mouseenter="previewTableSize(row, column)"
                  @focus="previewTableSize(row, column)"
                  @click="insertTable(row, column)"
                ></button>
              </template>
            </div>
          </div>
        </el-popover>
      </div>
    </div>
  </nav>
</template>

<style scoped>
/* 顶部占位：IntersectionObserver 用它判断工具栏是否已经吸顶 */
.fixed-toolbar-sentinel {
  height: 1px;
  margin-bottom: -1px;
  pointer-events: none;
}

.fixed-editor-toolbar {
  position: sticky;
  z-index: 90;
  top: 0;
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
  padding: 0 14px;
  border: none;
  border-bottom: 1px solid transparent;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  transition:
    background-color 0.18s ease,
    border-color 0.18s ease,
    box-shadow 0.18s ease;
}

/*
 * 吸顶后贴住视口顶部，变成正文卡片的一条「页眉」：
 * 接近不透明的纸色 + 细分割线，正文从下面滑过而不会从缝隙里透出来。
 */
.fixed-editor-toolbar.is-pinned {
  border-bottom-color: var(--border-soft);
  background-color: var(--overlay-background);
  box-shadow: 0 8px 18px -12px rgba(70, 48, 32, 0.5);
  backdrop-filter: blur(18px) saturate(1.05);
}

.fixed-editor-toolbar-track {
  display: flex;
  align-items: center;
  gap: 2px;
  min-width: 0;
  padding: 7px 0;
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: none;
}

.fixed-editor-toolbar-track::-webkit-scrollbar {
  height: 0;
}

.fixed-toolbar-group {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 2px;
}

.fixed-toolbar-divider {
  flex: 0 0 auto;
  width: 1px;
  height: 18px;
  margin: 0 7px;
  background: color-mix(in srgb, var(--border-soft) 70%, transparent);
}

.fixed-toolbar-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  width: 30px;
  min-width: 30px;
  height: 30px;
  padding: 0;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: color-mix(in srgb, var(--text-primary) 82%, transparent);
  font: inherit;
  font-size: 0.9rem;
  cursor: pointer;
  transition:
    background-color 0.15s ease,
    color 0.15s ease;
}

.fixed-toolbar-button svg {
  width: 17px;
  height: 17px;
}

.fixed-toolbar-button:hover:not(:disabled),
.fixed-toolbar-button:focus-visible {
  outline: none;
  background: color-mix(in srgb, var(--accent) 9%, transparent);
  color: var(--accent);
}

.fixed-toolbar-button.is-active {
  background: color-mix(in srgb, var(--accent) 13%, transparent);
  color: var(--accent);
}

.fixed-toolbar-button:disabled {
  cursor: not-allowed;
  opacity: 0.35;
}

.fixed-toolbar-heading {
  width: 32px;
  min-width: 32px;
  color: color-mix(in srgb, var(--text-primary) 74%, transparent);
  font-family: 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  font-size: 0.76rem;
  font-weight: 700;
  letter-spacing: 0.01em;
}

.fixed-toolbar-heading.is-active {
  color: var(--accent);
}

.is-bold {
  font-size: 0.9rem;
  font-weight: 900;
}

.is-italic {
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 0.95rem;
  font-style: italic;
  font-weight: 700;
}

.is-strike {
  font-size: 0.88rem;
  font-weight: 700;
  text-decoration: line-through;
}

.is-code {
  font-family: 'SFMono-Regular', Consolas, monospace;
  font-size: 0.62rem;
  font-weight: 800;
  letter-spacing: -0.06em;
}

.is-math {
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 1rem;
  font-style: italic;
  font-weight: 700;
}

.is-math-block {
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 1rem;
  font-style: italic;
  font-weight: 700;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.is-callout {
  font-size: 0.9rem;
  font-weight: 800;
}

.fixed-callout-picker {
  display: grid;
  gap: 1px;
}

.fixed-popover-title {
  margin: 0 0 6px;
  padding: 0 4px;
  color: var(--text-muted);
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.fixed-callout-option {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  padding: 7px 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text-primary);
  font: inherit;
  font-size: 0.86rem;
  font-weight: 600;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}

.fixed-callout-option:hover,
.fixed-callout-option:focus-visible {
  outline: none;
  background: var(--accent-soft);
  color: var(--accent);
}

.fixed-callout-option.is-current {
  background: var(--accent-soft);
  color: var(--accent);
}

.fixed-callout-hint {
  margin-left: auto;
  color: var(--text-muted);
  font-size: 0.72rem;
  font-weight: 600;
}

.fixed-callout-dot {
  flex: 0 0 auto;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--callout-dot, var(--brand-blue));
}

.fixed-callout-option.is-note {
  --callout-dot: var(--brand-blue);
}

.fixed-callout-option.is-tip {
  --callout-dot: var(--moss);
}

.fixed-callout-option.is-important {
  --callout-dot: var(--brand-gold);
}

.fixed-callout-option.is-warning,
.fixed-callout-option.is-caution {
  --callout-dot: var(--danger);
}

.fixed-link-form {
  display: grid;
  gap: 12px;
}

.fixed-link-form > div:not(.fixed-popover-actions) {
  display: grid;
  gap: 6px;
}

.fixed-link-form label {
  color: var(--text-primary);
  font-size: 0.8rem;
  font-weight: 800;
}

.fixed-link-error {
  margin: -4px 0 0;
  color: var(--danger);
  font-size: 0.78rem;
}

.fixed-popover-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.fixed-table-picker {
  display: grid;
  gap: 12px;
}

.fixed-table-picker strong {
  color: var(--text-primary);
  font-size: 0.86rem;
}

.fixed-table-picker-grid {
  display: grid;
  gap: 5px;
}

.fixed-table-picker-cell {
  width: 24px;
  height: 22px;
  padding: 0;
  border: 1px solid var(--border-strong);
  border-radius: 4px;
  background: var(--surface-soft);
  cursor: pointer;
}

.fixed-table-picker-cell:hover,
.fixed-table-picker-cell:focus-visible,
.fixed-table-picker-cell.is-active {
  border-color: var(--accent-border);
  outline: none;
  background: var(--accent-soft);
}

@media (max-width: 720px) {
  .fixed-editor-toolbar {
    top: 8px;
  }

  .fixed-editor-toolbar-track {
    padding-inline: 8px;
  }
}
</style>
