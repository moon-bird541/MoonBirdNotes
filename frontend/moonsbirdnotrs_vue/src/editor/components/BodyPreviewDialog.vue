<script setup>
import { computed, nextTick, ref, watch } from 'vue'

import { enhanceRichContent } from '../../utils/richContent'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false,
  },
  html: {
    type: String,
    default: '',
  },
  title: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['update:visible'])

const bodyRef = ref(null)

const dialogVisible = computed({
  get: () => props.visible,
  set: (value) => emit('update:visible', value),
})

watch(
  () => [props.visible, props.html],
  async () => {
    if (!props.visible) {
      return
    }
    await nextTick()
    // 预览与阅读端共用同一套增强器：提示框、代码块折叠、Tab 代码组、公式
    enhanceRichContent(bodyRef.value)
  }
)
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    title="正文预览"
    width="80%"
    :close-on-click-modal="false"
  >
    <div class="body-preview-meta">
      <span>{{ title || '未命名笔记' }}</span>
      <span>预览会应用与详情页一致的排版、提示框与代码块效果</span>
    </div>
    <div ref="bodyRef" class="body-preview markdown-body blog-prose" v-html="html"></div>
  </el-dialog>
</template>

<style scoped>
.body-preview-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
  color: var(--ink-soft);
  font-size: 0.86rem;
}

.body-preview {
  max-height: 62vh;
  padding: 4px 6px 12px;
  overflow: auto;
}
</style>
