<script setup>
import { Delete, Minus, Plus, RefreshRight, Tickets } from '@element-plus/icons-vue'

defineProps({
  visible: {
    type: Boolean,
    default: false,
  },
  position: {
    type: Object,
    required: true,
  },
  activeTableInfo: {
    type: Object,
    default: null,
  },
  activeTableAlignment: {
    type: String,
    default: 'left',
  },
  canAddSelectedTableRow: {
    type: Boolean,
    default: false,
  },
  canAddSelectedTableColumn: {
    type: Boolean,
    default: false,
  },
  canMergeSelectedTableCells: {
    type: Boolean,
    default: false,
  },
  canSplitSelectedTableCell: {
    type: Boolean,
    default: false,
  },
  canDeleteSelectedTableRow: {
    type: Boolean,
    default: false,
  },
  canDeleteSelectedTableColumn: {
    type: Boolean,
    default: false,
  },
})

defineEmits([
  'add-row',
  'add-column',
  'merge-cells',
  'split-cell',
  'delete-row',
  'delete-column',
  'delete-table',
  'reset-layout',
  'align-table',
])
</script>

<template>
  <Teleport to="body">
    <div
      v-show="visible"
      class="table-action-panel"
      :style="{
        top: `${position.top}px`,
        left: `${position.left}px`,
      }"
      @mousedown.prevent.stop
      @click.stop
    >
      <div class="table-action-panel-head">
        <strong>表格</strong>
        <span v-if="activeTableInfo">
          {{ activeTableInfo.rowCount }} 行 / {{ activeTableInfo.columnCount }} 列
        </span>
      </div>

      <div class="table-align-control" aria-label="表格整体对齐">
        <button
          type="button"
          class="table-align-button"
          :class="{ 'is-active': activeTableAlignment === 'left' }"
          :disabled="!activeTableInfo"
          @mousedown.prevent.stop
          @click.stop="$emit('align-table', 'left')"
        >
          <span class="table-align-icon is-left" aria-hidden="true"></span>
          <span>左对齐</span>
        </button>
        <button
          type="button"
          class="table-align-button"
          :class="{ 'is-active': activeTableAlignment === 'center' }"
          :disabled="!activeTableInfo"
          @mousedown.prevent.stop
          @click.stop="$emit('align-table', 'center')"
        >
          <span class="table-align-icon is-center" aria-hidden="true"></span>
          <span>居中</span>
        </button>
        <button
          type="button"
          class="table-align-button"
          :class="{ 'is-active': activeTableAlignment === 'right' }"
          :disabled="!activeTableInfo"
          @mousedown.prevent.stop
          @click.stop="$emit('align-table', 'right')"
        >
          <span class="table-align-icon is-right" aria-hidden="true"></span>
          <span>右对齐</span>
        </button>
      </div>

      <div class="table-action-grid">
        <button
          type="button"
          class="table-action-button"
          :disabled="!canAddSelectedTableRow"
          @mousedown.prevent.stop
          @click.stop="$emit('add-row', 'above')"
        >
          <el-icon><Plus /></el-icon>
          <span>上方插入行</span>
        </button>
        <button
          type="button"
          class="table-action-button"
          :disabled="!canAddSelectedTableRow"
          @mousedown.prevent.stop
          @click.stop="$emit('add-row', 'below')"
        >
          <el-icon><Plus /></el-icon>
          <span>下方插入行</span>
        </button>
        <button
          type="button"
          class="table-action-button"
          :disabled="!canAddSelectedTableColumn"
          @mousedown.prevent.stop
          @click.stop="$emit('add-column', 'left')"
        >
          <el-icon><Plus /></el-icon>
          <span>左侧插入列</span>
        </button>
        <button
          type="button"
          class="table-action-button"
          :disabled="!canAddSelectedTableColumn"
          @mousedown.prevent.stop
          @click.stop="$emit('add-column', 'right')"
        >
          <el-icon><Plus /></el-icon>
          <span>右侧插入列</span>
        </button>
      </div>

      <div class="table-action-divider"></div>

      <div class="table-action-grid">
        <button
          type="button"
          class="table-action-button"
          :disabled="!canMergeSelectedTableCells"
          @mousedown.prevent.stop
          @click.stop="$emit('merge-cells')"
        >
          <el-icon><Tickets /></el-icon>
          <span>合并单元格</span>
        </button>
        <button
          type="button"
          class="table-action-button"
          :disabled="!canSplitSelectedTableCell"
          @mousedown.prevent.stop
          @click.stop="$emit('split-cell')"
        >
          <el-icon><Tickets /></el-icon>
          <span>拆分单元格</span>
        </button>
        <button
          type="button"
          class="table-action-button"
          :disabled="!canDeleteSelectedTableRow"
          @mousedown.prevent.stop
          @click.stop="$emit('delete-row')"
        >
          <el-icon><Minus /></el-icon>
          <span>删除行</span>
        </button>
        <button
          type="button"
          class="table-action-button"
          :disabled="!canDeleteSelectedTableColumn"
          @mousedown.prevent.stop
          @click.stop="$emit('delete-column')"
        >
          <el-icon><Minus /></el-icon>
          <span>删除列</span>
        </button>
      </div>

      <div class="table-action-footer">
        <button
          type="button"
          class="table-action-button is-wide"
          @mousedown.prevent.stop
          @click.stop="$emit('reset-layout')"
        >
          <el-icon><RefreshRight /></el-icon>
          <span>恢复默认宽高</span>
        </button>
        <button
          type="button"
          class="table-action-button is-danger"
          :disabled="!activeTableInfo"
          @mousedown.prevent.stop
          @click.stop="$emit('delete-table')"
        >
          <el-icon><Delete /></el-icon>
          <span>删除表格</span>
        </button>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.table-action-panel {
  position: fixed;
  z-index: 220;
  display: grid;
  gap: 8px;
  width: 304px;
  padding: 12px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.98);
  box-shadow:
    0 18px 42px rgba(15, 23, 42, 0.14),
    inset 0 1px 0 rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(14px);
}

.table-action-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 24px;
  gap: 12px;
  padding: 0 2px 2px;
  color: var(--brand-navy);
}

.table-action-panel-head strong {
  font-size: 0.96rem;
  font-weight: 800;
}

.table-action-panel-head span {
  color: rgba(15, 23, 42, 0.54);
  font-size: 0.78rem;
  font-weight: 700;
}

.table-align-control {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 3px;
  padding: 3px;
  border: 1px solid rgba(148, 163, 184, 0.15);
  border-radius: 8px;
  background: rgba(248, 250, 252, 0.78);
}

.table-action-grid,
.table-action-footer {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
}

.table-action-divider {
  height: 1px;
  margin: 1px 2px;
  background: rgba(148, 163, 184, 0.16);
}

.table-align-button,
.table-action-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 0;
  height: 34px;
  gap: 5px;
  padding: 0 8px;
  border: 1px solid transparent;
  border-radius: 7px;
  background: transparent;
  color: var(--brand-navy);
  font-size: 0.8rem;
  font-weight: 700;
  line-height: 1;
  white-space: nowrap;
  cursor: pointer;
  transition:
    transform 0.16s ease,
    border-color 0.16s ease,
    background-color 0.16s ease,
    color 0.16s ease,
    box-shadow 0.16s ease;
}

.table-action-button {
  justify-content: flex-start;
  border-color: rgba(148, 163, 184, 0.13);
  background: rgba(248, 250, 252, 0.52);
}

.table-align-button {
  padding: 0 6px;
}

.table-align-button:hover:not(:disabled),
.table-align-button:focus-visible,
.table-action-button:hover:not(:disabled),
.table-action-button:focus-visible {
  transform: translateY(-1px);
  border-color: rgba(37, 99, 235, 0.24);
  background: rgba(37, 99, 235, 0.06);
  color: var(--brand-blue);
  outline: none;
}

.table-align-button.is-active {
  border-color: rgba(37, 99, 235, 0.28);
  background: #ffffff;
  color: var(--brand-blue);
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.1);
}

.table-action-button.is-wide {
  grid-column: span 1;
}

.table-align-button:disabled,
.table-action-button:disabled {
  cursor: not-allowed;
  opacity: 0.42;
}

.table-action-button.is-danger {
  border-color: rgba(239, 68, 68, 0.14);
  color: #dc2626;
}

.table-action-button.is-danger:hover:not(:disabled),
.table-action-button.is-danger:focus-visible {
  border-color: rgba(239, 68, 68, 0.3);
  background: rgba(254, 226, 226, 0.72);
  color: #b91c1c;
}

.table-action-button :deep(.el-icon) {
  flex: 0 0 auto;
  font-size: 0.9rem;
  opacity: 0.9;
}

.table-align-icon {
  position: relative;
  display: inline-flex;
  width: 15px;
  height: 13px;
  flex: 0 0 auto;
}

.table-align-icon::before,
.table-align-icon::after {
  position: absolute;
  left: 0;
  height: 2px;
  border-radius: 999px;
  background: currentColor;
  content: '';
}

.table-align-icon::before {
  top: 1px;
  width: 15px;
  box-shadow: 0 5px 0 currentColor;
}

.table-align-icon::after {
  top: 11px;
  width: 9px;
}

.table-align-icon.is-center::after {
  left: 3px;
}

.table-align-icon.is-right::after {
  right: 0;
  left: auto;
}
</style>
