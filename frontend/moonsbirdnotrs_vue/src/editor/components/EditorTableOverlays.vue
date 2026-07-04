<script setup>
import { Tickets } from '@element-plus/icons-vue'

defineProps({
  hoverBlockHintVisible: {
    type: Boolean,
    default: false,
  },
  hoverBlockHint: {
    type: Object,
    required: true,
  },
  tableHoverControlVisible: {
    type: Boolean,
    default: false,
  },
  tableHoverControlPosition: {
    type: Object,
    required: true,
  },
  tableSelectionOverlay: {
    type: Object,
    required: true,
  },
  tableResizeHandleVisible: {
    type: Boolean,
    default: false,
  },
  tableResizeHandle: {
    type: Object,
    required: true,
  },
  tableResizeHandleDragging: {
    type: Boolean,
    default: false,
  },
  tableResizeSizeHint: {
    type: Object,
    required: true,
  },
})

defineEmits(['open-action-panel', 'start-resize'])
</script>

<template>
  <Teleport to="body">
    <div
      v-show="hoverBlockHintVisible"
      class="hover-block-hint"
      :style="{
        top: `${hoverBlockHint.top}px`,
        left: `${hoverBlockHint.left}px`,
      }"
    >
      {{ hoverBlockHint.label }}
    </div>
  </Teleport>

  <Teleport to="body">
    <button
      v-show="tableHoverControlVisible"
      type="button"
      class="table-hover-control"
      :style="{
        top: `${tableHoverControlPosition.top}px`,
        left: `${tableHoverControlPosition.left}px`,
      }"
      aria-label="打开表格操作"
      title="表格操作"
      @mousedown.prevent.stop="$emit('open-action-panel')"
      @click.prevent.stop
    >
      <el-icon><Tickets /></el-icon>
    </button>
  </Teleport>

  <Teleport to="body">
    <div
      v-show="tableSelectionOverlay.visible"
      class="table-selection-overlay"
      :style="{
        top: `${tableSelectionOverlay.top}px`,
        left: `${tableSelectionOverlay.left}px`,
        width: `${tableSelectionOverlay.width}px`,
        height: `${tableSelectionOverlay.height}px`,
      }"
    ></div>
  </Teleport>

  <Teleport to="body">
    <div
      v-show="tableResizeHandleVisible"
      class="table-resize-handle"
      :class="{
        'is-table-width': tableResizeHandle.kind === 'table',
        'is-table-height': tableResizeHandle.kind === 'table-height',
        'is-table-row': tableResizeHandle.kind === 'row',
        'is-dragging': tableResizeHandleDragging,
      }"
      :style="{
        top: `${tableResizeHandle.top}px`,
        left: `${tableResizeHandle.left}px`,
        width: `${tableResizeHandle.width}px`,
        height: `${tableResizeHandle.height}px`,
      }"
      aria-hidden="true"
      @mousedown.prevent.stop="$emit('start-resize', $event)"
    ></div>
  </Teleport>

  <Teleport to="body">
    <div
      v-show="tableResizeSizeHint.visible"
      class="table-resize-size-hint"
      :style="{
        top: `${tableResizeSizeHint.top}px`,
        left: `${tableResizeSizeHint.left}px`,
      }"
    >
      {{ tableResizeSizeHint.text }}
    </div>
  </Teleport>
</template>

<style scoped>
.hover-block-hint {
  position: fixed;
  z-index: 199;
  min-height: 26px;
  padding: 0 10px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.14);
  color: var(--brand-navy);
  font-size: 0.75rem;
  font-weight: 700;
  line-height: 24px;
  pointer-events: none;
  white-space: nowrap;
  backdrop-filter: blur(10px);
}

.table-hover-control {
  position: fixed;
  z-index: 210;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  padding: 0;
  border: 1px solid rgba(37, 99, 235, 0.24);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow:
    0 12px 28px rgba(15, 23, 42, 0.14),
    0 0 0 3px rgba(37, 99, 235, 0.08);
  color: var(--brand-blue);
  cursor: pointer;
  backdrop-filter: blur(10px);
  transition:
    background-color 0.18s ease,
    border-color 0.18s ease,
    box-shadow 0.18s ease,
    transform 0.18s ease;
}

.table-hover-control:hover,
.table-hover-control:focus-visible {
  transform: translateY(-1px);
  border-color: rgba(37, 99, 235, 0.38);
  background: #ffffff;
  box-shadow:
    0 16px 34px rgba(15, 23, 42, 0.18),
    0 0 0 4px rgba(37, 99, 235, 0.12);
  outline: none;
}

.table-hover-control :deep(.el-icon) {
  font-size: 1rem;
}

.table-selection-overlay {
  position: fixed;
  z-index: 209;
  border: 2px solid rgba(37, 99, 235, 0.78);
  border-radius: 8px;
  box-shadow:
    0 0 0 3px rgba(37, 99, 235, 0.12),
    inset 0 0 0 1px rgba(255, 255, 255, 0.8);
  pointer-events: none;
}

.table-selection-overlay::before,
.table-selection-overlay::after {
  position: absolute;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #2563eb;
  box-shadow: 0 0 0 2px #ffffff;
  content: '';
}

.table-selection-overlay::before {
  top: -5px;
  left: -5px;
}

.table-selection-overlay::after {
  right: -5px;
  bottom: -5px;
}

.table-resize-handle {
  position: fixed;
  z-index: 215;
  width: 22px;
  height: 100%;
  min-height: 28px;
  cursor: col-resize;
  transform: translateX(-11px);
  touch-action: none;
}

.table-resize-handle::before {
  position: absolute;
  top: 0;
  left: 10px;
  width: 2px;
  height: 100%;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.64);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
  content: '';
}

.table-resize-handle.is-table-width::before {
  width: 3px;
  background: rgba(15, 23, 42, 0.68);
  box-shadow:
    0 0 0 3px rgba(15, 23, 42, 0.1),
    0 10px 24px rgba(15, 23, 42, 0.18);
}

.table-resize-handle.is-table-width::after {
  position: absolute;
  top: 50%;
  left: 5px;
  width: 12px;
  height: 36px;
  border: 1px solid rgba(15, 23, 42, 0.18);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 10px 20px rgba(15, 23, 42, 0.12);
  content: '';
  transform: translateY(-50%);
}

.table-resize-handle.is-table-width::before {
  z-index: 1;
}

.table-resize-handle.is-table-height,
.table-resize-handle.is-table-row {
  min-height: 22px;
  cursor: row-resize;
  transform: translateY(-11px);
}

.table-resize-handle.is-table-height::before,
.table-resize-handle.is-table-row::before {
  top: 10px;
  left: 0;
  width: 100%;
  height: 2px;
  background: rgba(37, 99, 235, 0.7);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}

.table-resize-handle.is-table-height::after,
.table-resize-handle.is-table-row::after {
  position: absolute;
  top: 5px;
  left: 50%;
  width: 40px;
  height: 12px;
  border: 1px solid rgba(15, 23, 42, 0.16);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 10px 20px rgba(15, 23, 42, 0.12);
  content: '';
  transform: translateX(-50%);
}

.table-resize-handle.is-dragging::before {
  background: rgba(37, 99, 235, 0.82);
  box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.16);
}

.table-resize-size-hint {
  position: fixed;
  z-index: 216;
  min-width: 58px;
  height: 30px;
  padding: 0 10px;
  border: 1px solid rgba(15, 23, 42, 0.18);
  border-radius: 8px;
  background: rgba(15, 23, 42, 0.9);
  box-shadow: 0 12px 26px rgba(15, 23, 42, 0.2);
  color: #ffffff;
  font-size: 0.78rem;
  font-weight: 800;
  line-height: 28px;
  text-align: center;
  white-space: nowrap;
  pointer-events: none;
  backdrop-filter: blur(10px);
}
</style>
