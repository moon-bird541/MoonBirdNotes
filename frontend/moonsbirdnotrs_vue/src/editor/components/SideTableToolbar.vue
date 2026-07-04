<script setup>
import { computed, reactive } from 'vue'
import { Picture } from '@element-plus/icons-vue'
import { MAX_TABLE_COLUMN_COUNT, MAX_TABLE_ROW_COUNT } from '../../utils/tableLayout'

defineProps({
  visible: {
    type: Boolean,
    default: false,
  },
  editorReady: {
    type: Boolean,
    default: false,
  },
})

defineEmits(['update:visible', 'remember-selection', 'toggle', 'select', 'insert-image'])

const tablePickerRows = Array.from({ length: MAX_TABLE_ROW_COUNT }, (_, index) => index + 1)
const tablePickerColumns = Array.from({ length: MAX_TABLE_COLUMN_COUNT }, (_, index) => index + 1)
const tablePickerPreview = reactive({
  rows: 3,
  columns: 3,
})
const tablePickerLabel = computed(
  () => `${tablePickerPreview.rows}行 * ${tablePickerPreview.columns}列 表格`
)

const previewTablePickerSize = (rows, columns) => {
  tablePickerPreview.rows = rows
  tablePickerPreview.columns = columns
}

const isTablePickerCellActive = (rows, columns) =>
  rows <= tablePickerPreview.rows && columns <= tablePickerPreview.columns
</script>

<template>
  <Teleport to="body">
    <div class="editor-side-toolbar" aria-label="正文编辑器工具栏">
      <button
        type="button"
        class="side-tool-button"
        :disabled="!editorReady"
        aria-label="插入图片"
        title="插入图片"
        @mousedown.prevent="$emit('remember-selection')"
        @click.stop="$emit('insert-image')"
      >
        <el-icon><Picture /></el-icon>
        <span class="button-label">图片</span>
      </button>

      <el-popover
        :visible="visible"
        trigger="manual"
        placement="left-end"
        :width="326"
        :disabled="!editorReady"
        popper-class="side-table-picker-popover"
        @update:visible="$emit('update:visible', $event)"
        @show="previewTablePickerSize(3, 3)"
      >
        <template #reference>
          <button
            type="button"
            class="side-tool-button"
            :disabled="!editorReady"
            aria-label="插入表格"
            title="插入表格"
            @mousedown.prevent="$emit('remember-selection')"
            @click.stop="$emit('toggle')"
          >
            <span class="toolbar-table-icon">T</span>
            <span class="button-label">表格</span>
          </button>
        </template>

        <div class="side-table-picker" @mousedown.prevent>
          <div class="side-table-picker-head">
            <strong>{{ tablePickerLabel }}</strong>
          </div>
          <div
            class="side-table-picker-grid"
            :style="{ gridTemplateColumns: `repeat(${tablePickerColumns.length}, 26px)` }"
          >
            <template v-for="row in tablePickerRows" :key="row">
              <button
                v-for="column in tablePickerColumns"
                :key="`${row}-${column}`"
                type="button"
                class="side-table-picker-cell"
                :class="{ 'is-active': isTablePickerCellActive(row, column) }"
                :aria-label="`插入 ${row} 行 ${column} 列表格`"
                @mouseenter="previewTablePickerSize(row, column)"
                @focus="previewTablePickerSize(row, column)"
                @mousedown.prevent
                @click="$emit('select', row, column)"
              ></button>
            </template>
          </div>
        </div>
      </el-popover>
    </div>
  </Teleport>
</template>

<style scoped>
.editor-side-toolbar {
  position: fixed;
  right: 28px;
  bottom: 122px;
  z-index: 198;
  display: grid;
  gap: 10px;
  justify-items: end;
}

.side-tool-button {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  justify-content: center;
  min-width: 72px;
  padding: 14px 12px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 18px;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.96), rgba(248, 250, 252, 0.94));
  box-shadow:
    0 12px 32px rgba(15, 23, 42, 0.12),
    0 4px 12px rgba(37, 99, 235, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.9);
  color: var(--brand-blue);
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  backdrop-filter: blur(12px);
}

.side-tool-button:hover:not(:disabled),
.side-tool-button:focus-visible {
  transform: translateY(-3px);
  border-color: rgba(37, 99, 235, 0.3);
  box-shadow:
    0 18px 48px rgba(15, 23, 42, 0.18),
    0 8px 20px rgba(37, 99, 235, 0.16),
    inset 0 1px 0 rgba(255, 255, 255, 1);
  outline: none;
}

.side-tool-button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.side-tool-button .toolbar-table-icon {
  width: 24px;
  height: 24px;
}

.side-tool-button :deep(.el-icon) {
  font-size: 24px;
}

.side-tool-button .button-label {
  font-size: 0.85rem;
  font-weight: 700;
  letter-spacing: 0.02em;
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
  content: '';
  background: currentColor;
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

.side-table-picker {
  display: grid;
  gap: 16px;
  padding: 2px;
}

.side-table-picker-head {
  min-height: 28px;
  color: var(--brand-navy);
  font-size: 1rem;
  line-height: 1.4;
}

.side-table-picker-head strong {
  font-weight: 800;
}

.side-table-picker-grid {
  display: grid;
  gap: 7px;
}

.side-table-picker-cell {
  width: 26px;
  height: 26px;
  padding: 0;
  border: 1px solid rgba(15, 23, 42, 0.72);
  border-radius: 0;
  background: #ffffff;
  cursor: pointer;
  transition:
    background-color 0.12s ease,
    border-color 0.12s ease;
}

.side-table-picker-cell.is-active {
  border-color: rgba(15, 23, 42, 0.84);
  background: #f2b385;
}

.side-table-picker-cell:focus-visible {
  outline: 2px solid rgba(37, 99, 235, 0.3);
  outline-offset: 2px;
}

:global(.side-table-picker-popover.el-popper) {
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 8px;
  box-shadow: 0 22px 48px rgba(15, 23, 42, 0.16);
}

@media (max-width: 720px) {
  .editor-side-toolbar {
    right: 16px;
    bottom: 112px;
  }
}

@media (max-width: 520px) {
  .editor-side-toolbar {
    right: 16px;
    bottom: 100px;
  }

  .side-tool-button {
    min-width: 64px;
    padding: 12px 10px;
  }

  .side-tool-button .toolbar-table-icon {
    width: 22px;
    height: 22px;
  }

  .side-tool-button .button-label {
    font-size: 0.8rem;
  }
}
</style>
