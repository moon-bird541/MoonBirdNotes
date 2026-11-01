<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { RefreshRight } from '@element-plus/icons-vue'

import { enhanceRichContent } from '../../utils/richContent'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false,
  },
  version: {
    type: Object,
    default: null,
  },
  formatDateTime: {
    type: Function,
    required: true,
  },
})

const emit = defineEmits(['update:visible', 'close', 'restore'])

const previewContent = ref(null)

const dialogVisible = computed({
  get: () => props.visible,
  set: (value) => emit('update:visible', value),
})

// 历史版本的 rendered_html 同样由后端生成并净化；这里补客户端增强，
// 保证提示框、代码块折叠、Tab 代码组、公式在版本预览里与详情页一致。
watch(
  () => [props.visible, props.version?.rendered_html],
  async () => {
    if (!props.visible) {
      return
    }
    await nextTick()
    enhanceRichContent(previewContent.value)
  }
)
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    title="版本预览"
    width="80%"
    :close-on-click-modal="false"
  >
    <template v-if="version">
      <div class="version-preview-header">
        <h3>{{ version.title }}</h3>
        <p>
          <span>{{ formatDateTime(version.created_at) }}</span>
          <span>{{ version.word_count }} 字</span>
        </p>
        <p v-if="version.note_text" class="preview-note">
          备注：{{ version.note_text }}
        </p>
      </div>
      <div
        ref="previewContent"
        class="version-preview-content markdown-body blog-prose"
        v-html="version.rendered_html"
      ></div>
    </template>

    <template #footer>
      <el-button @click="$emit('close')">关闭</el-button>
      <el-button type="primary" @click="$emit('restore', version)">
        <el-icon><RefreshRight /></el-icon>
        恢复此版本
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.version-preview-header {
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.2);
}

.version-preview-header h3 {
  margin: 0 0 8px;
  color: var(--brand-navy);
  font-size: 1.5rem;
}

.version-preview-header p {
  margin: 4px 0;
  color: var(--ink-soft);
  font-size: 0.9rem;
}

.version-preview-header p span {
  margin-right: 16px;
}

.version-preview-header .preview-note {
  margin-top: 12px;
  padding: 10px 14px;
  border-radius: 8px;
  background: rgba(37, 99, 235, 0.08);
  color: var(--brand-blue);
  font-size: 0.95rem;
  font-style: normal;
}

.version-preview-content {
  max-height: 60vh;
  overflow-y: auto;
  padding: 20px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 12px;
  background: var(--panel-background-soft);
}
</style>
