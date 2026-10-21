<script setup>
import { nextTick, ref, watch } from 'vue'
import { Close, Plus } from '@element-plus/icons-vue'

const props = defineProps({
  title: {
    type: String,
    default: '',
  },
  tags: {
    type: Array,
    default: () => [],
  },
  tagInputVisible: {
    type: Boolean,
    default: false,
  },
  tagInputValue: {
    type: String,
    default: '',
  },
  wordCount: {
    type: Number,
    default: 0,
  },
})

defineEmits([
  'update:title',
  'update:tag-input-value',
  'remove-tag',
  'show-tag-input',
  'confirm-tag-input',
  'cancel-tag-input',
])

const tagInput = ref(null)

watch(
  () => props.tagInputVisible,
  (visible) => {
    if (!visible) {
      return
    }

    nextTick(() => {
      tagInput.value?.focus()
    })
  }
)
</script>

<template>
  <section class="editor-panel">
    <div class="editor-meta">
      <input
        :value="title"
        class="title-input"
        type="text"
        placeholder="无标题"
        maxlength="255"
        @input="$emit('update:title', $event.target.value)"
      />
      <div class="title-count">{{ title.length }}/255</div>
    </div>

    <div class="editor-meta tags-section">
      <div class="tags-list">
        <div v-for="tag in tags" :key="tag" class="tag-pill">
          <span class="tag-icon">#</span>
          <span class="tag-text">{{ tag }}</span>
          <button
            type="button"
            class="tag-remove"
            aria-label="移除标签"
            @click="$emit('remove-tag', tag)"
          >
            <el-icon><Close /></el-icon>
          </button>
        </div>

        <div v-if="tagInputVisible" class="tag-input-wrapper">
          <span class="tag-icon">#</span>
          <input
            ref="tagInput"
            :value="tagInputValue"
            class="tag-input-field"
            type="text"
            placeholder="输入标签名"
            maxlength="20"
            @input="$emit('update:tag-input-value', $event.target.value)"
            @keyup.enter="$emit('confirm-tag-input')"
            @blur="$emit('confirm-tag-input')"
            @keyup.esc="$emit('cancel-tag-input')"
          />
        </div>

        <button v-else type="button" class="tag-add-btn" @click="$emit('show-tag-input')">
          <el-icon><Plus /></el-icon>
          <span>添加标签</span>
        </button>
      </div>
    </div>

    <div class="editor-divider"></div>

    <div class="editor-stats">
      <span>{{ wordCount }} 字</span>
    </div>

    <div class="editor-shell">
      <slot name="editor"></slot>
    </div>
  </section>
</template>

<style scoped>
.editor-panel {
  display: grid;
  gap: 0;
  padding: 30px 32px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-soft);
}

.editor-meta {
  position: relative;
  margin-bottom: 16px;
}

.title-input {
  width: 100%;
  padding: 12px 0;
  border: none;
  background: transparent;
  color: var(--brand-navy);
  font-size: 2.2rem;
  font-weight: 700;
  line-height: 1.2;
  outline: none;
  transition: color 0.2s ease;
}

.title-input::placeholder {
  color: rgba(100, 116, 139, 0.3);
}

.title-input:focus {
  color: var(--brand-blue);
}

.title-count {
  position: absolute;
  right: 0;
  bottom: 8px;
  color: var(--ink-soft);
  font-size: 0.75rem;
  opacity: 0;
  transition: opacity 0.2s ease;
}

.title-input:focus + .title-count {
  opacity: 1;
}

.tags-section {
  margin-bottom: 16px;
}

.tags-list {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.tag-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border: 1px solid rgba(37, 99, 235, 0.2);
  border-radius: var(--radius-md);
  background: var(--accent-soft);
  color: var(--brand-blue);
  font-size: 0.95rem;
  font-weight: 600;
  transition: all 0.2s ease;
}

.tag-pill:hover {
  transform: translateY(-1px);
  border-color: rgba(37, 99, 235, 0.3);
  background: var(--accent-soft);
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.15);
}

.tag-icon {
  color: var(--brand-blue);
  font-size: 1rem;
  font-weight: 700;
  opacity: 0.7;
}

.tag-text {
  color: var(--brand-navy);
}

.tag-remove {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: rgba(37, 99, 235, 0.12);
  color: var(--brand-blue);
  cursor: pointer;
  transition: all 0.2s ease;
}

.tag-remove:hover {
  transform: scale(1.1);
  background: rgba(239, 68, 68, 0.15);
  color: var(--danger);
}

.tag-remove :deep(.el-icon) {
  font-size: 12px;
}

.tag-input-wrapper {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border: 1px solid var(--brand-blue);
  border-radius: 999px;
  background: var(--overlay-background);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
}

.tag-input-field {
  width: 120px;
  border: none;
  background: transparent;
  color: var(--brand-navy);
  font-size: 0.95rem;
  font-weight: 600;
  outline: none;
}

.tag-input-field::placeholder {
  color: rgba(100, 116, 139, 0.5);
}

.tag-add-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border: 1px dashed rgba(148, 163, 184, 0.3);
  border-radius: 999px;
  background: var(--control-background);
  color: var(--ink-soft);
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.tag-add-btn:hover {
  transform: translateY(-1px);
  border-color: var(--brand-blue);
  border-style: solid;
  background: rgba(37, 99, 235, 0.06);
  color: var(--brand-blue);
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.1);
}

.tag-add-btn :deep(.el-icon) {
  font-size: 14px;
}

.editor-divider {
  height: 1px;
  margin: 24px 0 16px;
  background: linear-gradient(
    90deg,
    transparent,
    rgba(148, 163, 184, 0.2) 20%,
    rgba(148, 163, 184, 0.2) 80%,
    transparent
  );
}

.editor-stats {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 16px;
}

.editor-stats span {
  color: var(--ink-soft);
  font-size: 0.9rem;
  font-weight: 600;
}

.editor-shell {
  position: relative;
}

@media (max-width: 720px) {
  .editor-panel {
    padding: 24px 20px;
    border-radius: 20px;
  }

  .title-input {
    padding: 10px 0;
    font-size: 1.8rem;
  }

  .editor-divider {
    margin: 20px 0 14px;
  }
}

@media (max-width: 520px) {
  .editor-panel {
    padding: 16px;
    border-radius: 18px;
  }
}
</style>
