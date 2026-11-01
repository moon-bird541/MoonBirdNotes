<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { buildFenceInfo, parseFenceInfo } from '../../utils/fenceInfo'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false,
  },
  /** 当前代码块的完整 info-string 与代码内容 */
  info: {
    type: String,
    default: '',
  },
  code: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['update:visible', 'apply'])

const dialogVisible = computed({
  get: () => props.visible,
  set: (value) => emit('update:visible', value),
})

const form = reactive({
  lang: '',
  title: '',
  highlight: '',
  ins: '',
  del: '',
  collapse: '',
  showLineNumbers: false,
  startLineNumber: 1,
  wrap: true,
  frame: 'auto',
})

const errors = reactive({ ranges: '' })
const lineCount = ref(0)

const frameOptions = [
  { value: 'auto', label: '自动' },
  { value: 'code', label: '代码窗口' },
  { value: 'terminal', label: '终端窗口' },
  { value: 'none', label: '无外框' },
]

/** `1,3-5` → 解析并校验 */
const readRanges = (raw) => {
  const text = String(raw || '').trim()
  if (!text) {
    return { ranges: [], error: '' }
  }

  const ranges = []
  for (const chunk of text.split(',')) {
    const piece = chunk.trim()
    if (!piece) {
      continue
    }
    const match = piece.match(/^(\d+)(?:\s*-\s*(\d+))?$/)
    if (!match) {
      return { ranges: [], error: `无法识别的行号范围：${piece}` }
    }
    const start = Number(match[1])
    const end = match[2] ? Number(match[2]) : start
    if (start < 1) {
      return { ranges: [], error: '行号从 1 开始' }
    }
    if (lineCount.value && Math.max(start, end) > lineCount.value) {
      return { ranges: [], error: `超出代码行数（共 ${lineCount.value} 行）` }
    }
    ranges.push({ start, end: Math.max(start, end) })
  }

  return { ranges, error: '' }
}

const rangesToText = (ranges = []) =>
  ranges.map((range) => (range.end > range.start ? `${range.start}-${range.end}` : `${range.start}`)).join(',')

watch(
  () => [props.visible, props.info, props.code],
  () => {
    if (!props.visible) {
      return
    }

    const parsed = parseFenceInfo(props.info)
    lineCount.value = String(props.code || '').split('\n').length

    form.lang = parsed.lang || ''
    form.title = parsed.title || ''
    form.showLineNumbers = Boolean(parsed.showLineNumbers)
    form.startLineNumber = parsed.startLineNumber || 1
    form.collapse = rangesToText(parsed.collapse)
    form.wrap = parsed.wrap !== false
    form.frame = parsed.frame || 'auto'

    const bucket = { mark: [], ins: [], del: [] }
    parsed.marks.forEach((mark) => {
      if (mark.kind !== 'lines') {
        return
      }
      bucket[mark.type]?.push(...(mark.ranges || []))
    })
    form.highlight = rangesToText(bucket.mark)
    form.ins = rangesToText(bucket.ins)
    form.del = rangesToText(bucket.del)
    errors.ranges = ''
  },
  { immediate: true }
)

const submit = () => {
  const highlight = readRanges(form.highlight)
  const ins = readRanges(form.ins)
  const del = readRanges(form.del)
  const collapse = readRanges(form.collapse)

  const failure = highlight.error || ins.error || del.error || collapse.error
  if (failure) {
    errors.ranges = failure
    ElMessage.warning(failure)
    return
  }

  errors.ranges = ''
  emit(
    'apply',
    buildFenceInfo({
      lang: form.lang,
      title: form.title,
      highlight: highlight.ranges,
      ins: ins.ranges,
      del: del.ranges,
      collapse: collapse.ranges,
      showLineNumbers: form.showLineNumbers,
      startLineNumber: form.startLineNumber,
      wrap: form.wrap,
      frame: form.frame,
    })
  )
  dialogVisible.value = false
}
</script>

<template>
  <el-dialog v-model="dialogVisible" title="代码块设置" width="560px" :close-on-click-modal="false">
    <div class="code-options">
      <p class="code-options-hint">
        这些参数会写入 fence 的 info-string，阅读端、预览与导出 HTML 都会应用。
      </p>

      <div class="code-options-row is-two">
        <label class="code-options-field">
          <span>语言</span>
          <el-input v-model="form.lang" placeholder="js / py / bash" />
        </label>
        <label class="code-options-field">
          <span>标题栏</span>
          <el-input v-model="form.title" placeholder="app.js（留空则不显示）" />
        </label>
      </div>

      <div class="code-options-row is-two">
        <label class="code-options-field">
          <span>高亮行</span>
          <el-input v-model="form.highlight" placeholder="1,3-5" />
        </label>
        <label class="code-options-field">
          <span>折叠行</span>
          <el-input v-model="form.collapse" placeholder="1-4" />
        </label>
      </div>

      <div class="code-options-row is-two">
        <label class="code-options-field">
          <span>新增行</span>
          <el-input v-model="form.ins" placeholder="2" />
        </label>
        <label class="code-options-field">
          <span>删除行</span>
          <el-input v-model="form.del" placeholder="6-7" />
        </label>
      </div>

      <p v-if="errors.ranges" class="code-options-error">{{ errors.ranges }}</p>

      <div class="code-options-row is-two">
        <label class="code-options-field">
          <span>窗口框架</span>
          <el-select v-model="form.frame">
            <el-option
              v-for="option in frameOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </label>
        <label class="code-options-field">
          <span>起始行号</span>
          <el-input-number v-model="form.startLineNumber" :min="1" :max="9999" controls-position="right" />
        </label>
      </div>

      <div class="code-options-row is-switches">
        <label class="code-options-switch">
          <el-switch v-model="form.showLineNumbers" />
          <span>显示行号</span>
        </label>
        <label class="code-options-switch">
          <el-switch v-model="form.wrap" />
          <span>自动换行</span>
        </label>
      </div>

      <pre class="code-options-preview">{{ buildFenceInfo({
        lang: form.lang,
        title: form.title,
        highlight: readRanges(form.highlight).ranges,
        ins: readRanges(form.ins).ranges,
        del: readRanges(form.del).ranges,
        collapse: readRanges(form.collapse).ranges,
        showLineNumbers: form.showLineNumbers,
        startLineNumber: form.startLineNumber,
        wrap: form.wrap,
        frame: form.frame,
      }) || '（无参数）' }}</pre>
    </div>

    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" @click="submit">应用</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.code-options {
  display: grid;
  gap: 14px;
}

.code-options-hint {
  margin: 0;
  color: var(--ink-soft);
  font-size: 0.84rem;
  line-height: 1.6;
}

.code-options-row {
  display: grid;
  gap: 12px;
}

.code-options-row.is-two {
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
}

.code-options-row.is-switches {
  grid-template-columns: repeat(2, max-content);
  gap: 24px;
}

.code-options-field {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.code-options-field > span {
  color: var(--ink-soft);
  font-size: 0.8rem;
  font-weight: 600;
}

.code-options-switch {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--brand-navy);
  font-size: 0.86rem;
  font-weight: 600;
}

.code-options-error {
  margin: 0;
  color: var(--danger);
  font-size: 0.82rem;
}

.code-options-preview {
  margin: 0;
  padding: 10px 12px;
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-sm);
  background: var(--surface-soft);
  color: var(--ink-soft);
  font-family: "Cascadia Code", "Consolas", monospace;
  font-size: 0.78rem;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

@media (max-width: 640px) {
  .code-options-row.is-two {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
