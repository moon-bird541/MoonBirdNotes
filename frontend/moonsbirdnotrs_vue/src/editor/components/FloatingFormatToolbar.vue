<script setup>
import { ref } from 'vue'
import { Document, MagicStick, Minus, Tickets } from '@element-plus/icons-vue'

defineProps({
  visible: {
    type: Boolean,
    default: false,
  },
  position: {
    type: Object,
    required: true,
  },
  toolbarState: {
    type: Object,
    required: true,
  },
  selectionInTable: {
    type: Boolean,
    default: false,
  },
  headingOptions: {
    type: Array,
    default: () => [],
  },
})

defineEmits([
  'command',
  'apply-heading',
  'apply-block-quote',
  'apply-code-block',
  'apply-code-block-auto-format',
  'apply-horizontal-rule',
])

const toolbarElement = ref(null)

defineExpose({
  getBoundingClientRect: () =>
    toolbarElement.value?.getBoundingClientRect() || { width: 0, height: 0 },
  contains: (target) => Boolean(toolbarElement.value?.contains(target)),
})
</script>

<template>
  <Teleport to="body">
    <div
      v-show="visible"
      ref="toolbarElement"
      class="floating-toolbar"
      :style="{
        top: `${position.top}px`,
        left: `${position.left}px`,
      }"
    >
      <div class="toolbar-group">
        <el-tooltip content="加粗" placement="top" :show-after="120">
          <button
            type="button"
            class="toolbar-button"
            :class="{
              'is-active': toolbarState.strong.active,
              'is-full': toolbarState.strong.full,
            }"
            @mousedown.prevent
            @click="$emit('command', 'strong')"
          >
            <strong>B</strong>
          </button>
        </el-tooltip>
        <el-tooltip content="斜体" placement="top" :show-after="120">
          <button
            type="button"
            class="toolbar-button"
            :class="{
              'is-active': toolbarState.italic.active,
              'is-full': toolbarState.italic.full,
            }"
            @mousedown.prevent
            @click="$emit('command', 'italic')"
          >
            <em>I</em>
          </button>
        </el-tooltip>
        <el-tooltip content="删除线" placement="top" :show-after="120">
          <button
            type="button"
            class="toolbar-button"
            :class="{
              'is-active': toolbarState.strike.active,
              'is-full': toolbarState.strike.full,
            }"
            @mousedown.prevent
            @click="$emit('command', 'strike')"
          >
            <span class="toolbar-strike">S</span>
          </button>
        </el-tooltip>
        <el-tooltip content="行内代码" placement="top" :show-after="120">
          <button
            type="button"
            class="toolbar-button"
            :class="{
              'is-active': toolbarState.code.active,
              'is-full': toolbarState.code.full,
            }"
            @mousedown.prevent
            @click="$emit('command', 'code')"
          >
            <span class="toolbar-code">&lt;/&gt;</span>
          </button>
        </el-tooltip>
      </div>

      <div v-if="selectionInTable" class="toolbar-divider"></div>

      <div v-if="selectionInTable" class="toolbar-group">
        <el-tooltip content="文字左对齐" placement="top" :show-after="120">
          <button
            type="button"
            class="toolbar-button"
            :class="{
              'is-active': toolbarState.cellAlignLeft.active,
              'is-full': toolbarState.cellAlignLeft.full,
            }"
            @mousedown.prevent
            @click="$emit('command', 'tableCellAlignLeft')"
          >
            <span class="toolbar-align-icon is-left" aria-hidden="true"></span>
          </button>
        </el-tooltip>
        <el-tooltip content="文字居中" placement="top" :show-after="120">
          <button
            type="button"
            class="toolbar-button"
            :class="{
              'is-active': toolbarState.cellAlignCenter.active,
              'is-full': toolbarState.cellAlignCenter.full,
            }"
            @mousedown.prevent
            @click="$emit('command', 'tableCellAlignCenter')"
          >
            <span class="toolbar-align-icon is-center" aria-hidden="true"></span>
          </button>
        </el-tooltip>
        <el-tooltip content="文字右对齐" placement="top" :show-after="120">
          <button
            type="button"
            class="toolbar-button"
            :class="{
              'is-active': toolbarState.cellAlignRight.active,
              'is-full': toolbarState.cellAlignRight.full,
            }"
            @mousedown.prevent
            @click="$emit('command', 'tableCellAlignRight')"
          >
            <span class="toolbar-align-icon is-right" aria-hidden="true"></span>
          </button>
        </el-tooltip>
      </div>

      <div v-if="!selectionInTable" class="toolbar-divider"></div>

      <div v-if="!selectionInTable" class="toolbar-group heading-group">
        <el-tooltip
          v-for="option in headingOptions"
          :key="option.value"
          :content="`标题 ${option.label}`"
          placement="top"
          :show-after="120"
        >
          <button
            type="button"
            class="toolbar-chip"
            :class="{
              'is-active': toolbarState.headings[option.value].active,
              'is-full': toolbarState.headings[option.value].full,
            }"
            @mousedown.prevent
            @click="$emit('apply-heading', option.value)"
          >
            {{ option.label }}
          </button>
        </el-tooltip>
      </div>

      <div v-if="!selectionInTable" class="toolbar-divider"></div>

      <div v-if="!selectionInTable" class="toolbar-group">
        <el-tooltip content="引用" placement="top" :show-after="120">
          <button
            type="button"
            class="toolbar-button with-icon"
            :class="{
              'is-active': toolbarState.blockQuote.active,
              'is-full': toolbarState.blockQuote.full,
            }"
            @mousedown.prevent
            @click="$emit('apply-block-quote')"
          >
            <el-icon><Tickets /></el-icon>
          </button>
        </el-tooltip>
        <el-tooltip content="代码块" placement="top" :show-after="120">
          <button
            type="button"
            class="toolbar-button with-icon"
            :class="{
              'is-active': toolbarState.codeBlock.active,
              'is-full': toolbarState.codeBlock.full,
            }"
            @mousedown.prevent
            @click="$emit('apply-code-block')"
          >
            <el-icon><Document /></el-icon>
          </button>
        </el-tooltip>
        <el-tooltip
          v-if="toolbarState.codeBlock.full"
          content="AI 自动排版代码块"
          placement="top"
          :show-after="120"
        >
          <button
            type="button"
            class="toolbar-button with-icon ai-format-button"
            @mousedown.prevent
            @click="$emit('apply-code-block-auto-format')"
          >
            <el-icon><MagicStick /></el-icon>
          </button>
        </el-tooltip>
        <el-tooltip content="分割线" placement="top" :show-after="120">
          <button
            type="button"
            class="toolbar-button with-icon"
            :class="{
              'is-active': toolbarState.horizontalRule.active,
              'is-full': toolbarState.horizontalRule.full,
            }"
            @mousedown.prevent
            @click="$emit('apply-horizontal-rule')"
          >
            <el-icon><Minus /></el-icon>
          </button>
        </el-tooltip>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
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
  border: 1px solid rgba(148, 163, 184, 0.1);
  border-radius: 13px;
  background: rgba(255, 255, 255, 0.68);
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
  background: linear-gradient(180deg, rgba(37, 99, 235, 0.12), rgba(255, 255, 255, 0.82));
  color: var(--brand-blue);
  box-shadow:
    0 10px 20px rgba(15, 23, 42, 0.1),
    inset 0 1px 0 rgba(255, 255, 255, 0.72);
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
  border-color: rgba(37, 99, 235, 0.18);
  background: linear-gradient(180deg, rgba(37, 99, 235, 0.09), rgba(255, 255, 255, 0.82));
  color: var(--brand-blue);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.72);
}

.toolbar-button.is-full,
.toolbar-chip.is-full {
  border-color: rgba(37, 99, 235, 0.24);
  background: linear-gradient(180deg, rgba(37, 99, 235, 0.16), rgba(255, 255, 255, 0.88));
  color: var(--brand-blue);
  box-shadow:
    0 10px 22px rgba(37, 99, 235, 0.12),
    inset 0 1px 0 rgba(255, 255, 255, 0.82);
}

.toolbar-chip {
  min-width: 44px;
  font-size: 0.76rem;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.toolbar-strike {
  text-decoration: line-through;
}

.toolbar-code {
  font-size: 0.78rem;
  font-family: 'Cascadia Code', 'Consolas', monospace;
}

.toolbar-align-icon {
  position: relative;
  display: inline-flex;
  width: 18px;
  height: 14px;
}

.toolbar-align-icon::before {
  position: absolute;
  top: 1px;
  width: 14px;
  height: 2px;
  border-radius: 999px;
  background: currentColor;
  content: '';
}

.toolbar-align-icon::after {
  position: absolute;
  top: 6px;
  width: 10px;
  height: 2px;
  border-radius: 999px;
  background: currentColor;
  box-shadow: 0 5px 0 currentColor;
  content: '';
}

.toolbar-align-icon.is-left::before,
.toolbar-align-icon.is-left::after {
  left: 1px;
}

.toolbar-align-icon.is-center::before {
  left: 2px;
}

.toolbar-align-icon.is-center::after {
  left: 4px;
}

.toolbar-align-icon.is-right::before {
  right: 1px;
}

.toolbar-align-icon.is-right::after {
  right: 1px;
}

.with-icon :deep(.el-icon) {
  font-size: 0.95rem;
}

@media (max-width: 720px) {
  .floating-toolbar {
    gap: 8px;
    flex-wrap: wrap;
    width: min(320px, calc(100vw - 32px));
  }

  .heading-group {
    flex-wrap: wrap;
  }
}
</style>
