<script setup>
import { Back, Check, Clock } from '@element-plus/icons-vue'

defineProps({
  saving: {
    type: Boolean,
    default: false,
  },
  autoSaveEnabled: {
    type: Boolean,
    default: true,
  },
  autoSaveStatusText: {
    type: String,
    default: '',
  },
})

defineEmits(['back', 'save'])
</script>

<template>
  <header class="edit-header fade-rise-enter">
    <button class="back-button" type="button" @click="$emit('back')">
      <el-icon><Back /></el-icon>
      <span>返回详情</span>
    </button>

    <div class="auto-save-badge" :class="{ 'is-disabled': !autoSaveEnabled }">
      <el-icon><Clock /></el-icon>
      <span>{{ autoSaveStatusText }}</span>
    </div>

    <el-button class="save-button" type="primary" :loading="saving" @click="$emit('save')">
      <el-icon><Check /></el-icon>
      <span>创建版本</span>
    </el-button>
  </header>
</template>

<style scoped>
.edit-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 20px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 20px;
  background: var(--panel-background-raised);
  box-shadow: var(--shadow-soft);
}

.back-button {
  display: inline-flex;
  width: fit-content;
  align-items: center;
  gap: 8px;
  min-height: 42px;
  padding: 0 14px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 14px;
  background: var(--control-background);
  color: var(--brand-navy);
  cursor: pointer;
  transition:
    transform 0.2s ease,
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.back-button:hover {
  transform: translateY(-1px);
  border-color: rgba(37, 99, 235, 0.24);
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.08);
}

.auto-save-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.08);
  color: var(--brand-blue);
  font-size: 0.9rem;
  font-weight: 600;
}

.auto-save-badge.is-disabled {
  background: var(--surface-soft);
  color: var(--text-muted);
}

.auto-save-badge :deep(.el-icon) {
  font-size: 1rem;
}

.save-button {
  min-height: 44px;
  padding-inline: 20px;
  border: none;
  border-radius: var(--radius-md);
  background: var(--brand-blue);
  box-shadow: none;
}

@media (max-width: 720px) {
  .edit-header {
    flex-wrap: wrap;
    padding: 14px 16px;
  }

  .back-button {
    order: 1;
  }

  .auto-save-badge {
    order: 3;
    width: 100%;
    justify-content: center;
    font-size: 0.85rem;
  }

  .save-button {
    order: 2;
    margin-left: auto;
  }
}
</style>
