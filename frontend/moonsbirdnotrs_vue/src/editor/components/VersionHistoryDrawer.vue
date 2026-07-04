<script setup>
import { Clock, Close, Document } from '@element-plus/icons-vue'

defineProps({
  visible: {
    type: Boolean,
    default: false,
  },
  versions: {
    type: Array,
    default: () => [],
  },
  formatDateTime: {
    type: Function,
    required: true,
  },
})

defineEmits(['close', 'preview', 'toggle'])
</script>

<template>
  <transition name="drawer-mask">
    <div v-show="visible" class="drawer-mask" @click="$emit('close')"></div>
  </transition>

  <transition name="drawer-slide">
    <aside v-show="visible" class="version-drawer">
      <div class="version-drawer-header">
        <div>
          <p>Versions</p>
          <h2>历史版本</h2>
        </div>
        <button class="drawer-close-btn" type="button" @click="$emit('close')">
          <el-icon><Close /></el-icon>
        </button>
      </div>

      <div class="version-drawer-body">
        <div v-if="versions.length" class="version-list">
          <article
            v-for="version in versions"
            :key="version.id"
            class="version-item"
            @click="$emit('preview', version)"
          >
            <div class="version-icon">
              <el-icon><Clock /></el-icon>
            </div>
            <div class="version-copy">
              <strong>{{ version.title }}</strong>
              <span>{{ formatDateTime(version.created_at) }} / {{ version.word_count }} 字</span>
              <p v-if="version.note_text" class="version-note">{{ version.note_text }}</p>
              <p v-if="version.tag_names?.length">{{ version.tag_names.join(' / ') }}</p>
            </div>
          </article>
        </div>

        <div v-else class="version-empty">
          <p>还没有历史版本。</p>
          <span>点击"创建版本"后，当前内容会进入版本记录。</span>
        </div>
      </div>
    </aside>
  </transition>

  <button class="floating-version-button" type="button" @click="$emit('toggle')">
    <el-icon><Document /></el-icon>
    <span class="button-label">版本</span>
    <span v-if="versions.length" class="version-count">{{ versions.length }}</span>
  </button>
</template>

<style scoped>
.version-note {
  margin-top: 6px;
  padding: 6px 10px;
  border-radius: 8px;
  background: rgba(37, 99, 235, 0.08);
  color: var(--brand-blue);
  font-size: 0.85rem;
  font-style: italic;
}

.drawer-mask {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 100;
  background: rgba(15, 23, 42, 0.5);
  backdrop-filter: blur(4px);
}

.drawer-mask-enter-active,
.drawer-mask-leave-active {
  transition: all 0.3s ease;
}

.drawer-mask-enter-from,
.drawer-mask-leave-to {
  opacity: 0;
}

.version-drawer {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 101;
  display: flex;
  flex-direction: column;
  width: min(420px, 85vw);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(255, 255, 255, 0.96));
  backdrop-filter: blur(20px);
  box-shadow: -8px 0 48px rgba(15, 23, 42, 0.15);
}

.drawer-slide-enter-active,
.drawer-slide-leave-active {
  transition: transform 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}

.drawer-slide-enter-from,
.drawer-slide-leave-to {
  transform: translateX(100%);
}

.version-drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 28px 26px 22px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.16);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.9), transparent);
}

.version-drawer-header p {
  margin: 0 0 8px;
  color: var(--brand-blue);
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.version-drawer-header h2 {
  margin: 0;
  color: var(--brand-navy);
  font-size: 1.8rem;
  font-weight: 800;
  letter-spacing: -0.04em;
}

.drawer-close-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.8);
  color: var(--brand-navy);
  cursor: pointer;
  transition: all 0.2s ease;
}

.drawer-close-btn:hover {
  border-color: rgba(37, 99, 235, 0.3);
  background: rgba(255, 255, 255, 1);
  transform: scale(1.05);
}

.version-drawer-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px 26px 30px;
}

.version-list {
  display: grid;
  gap: 12px;
  overflow-y: auto;
  overflow-x: hidden;
  padding-right: 4px;
}

.version-item {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 12px;
  padding: 14px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.72);
  cursor: pointer;
  transition: all 180ms ease;
}

.version-item:hover {
  border-color: var(--brand-blue);
  background: rgba(37, 99, 235, 0.04);
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.08);
}

.version-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 12px;
  background: rgba(37, 99, 235, 0.08);
  color: var(--brand-blue);
}

.version-copy {
  min-width: 0;
}

.version-copy strong {
  display: block;
  overflow: hidden;
  color: var(--brand-navy);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.version-copy span,
.version-copy p {
  color: var(--ink-soft);
  font-size: 0.86rem;
}

.version-copy span {
  display: block;
  margin-top: 6px;
}

.version-copy p {
  margin: 8px 0 0;
}

.version-empty {
  display: grid;
  gap: 6px;
  padding: 8px 0;
}

.version-empty p {
  margin: 0;
  color: var(--brand-navy);
  font-weight: 700;
}

.version-empty span {
  color: var(--ink-soft);
  line-height: 1.7;
}

.floating-version-button {
  position: fixed;
  right: 28px;
  bottom: 28px;
  z-index: 198;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
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

.floating-version-button:hover {
  transform: translateY(-3px);
  border-color: rgba(37, 99, 235, 0.3);
  box-shadow:
    0 18px 48px rgba(15, 23, 42, 0.18),
    0 8px 20px rgba(37, 99, 235, 0.16),
    inset 0 1px 0 rgba(255, 255, 255, 1);
}

.floating-version-button :deep(.el-icon) {
  font-size: 26px;
}

.floating-version-button .button-label {
  font-size: 0.85rem;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.floating-version-button .version-count {
  position: absolute;
  top: 8px;
  right: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 22px;
  padding: 0 6px;
  border-radius: 999px;
  background: linear-gradient(135deg, #1d4ed8, #2563eb);
  color: #ffffff;
  font-size: 0.75rem;
  font-weight: 700;
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.4);
}

@media (max-width: 520px) {
  .version-drawer {
    width: 100vw;
  }

  .floating-version-button {
    right: 16px;
    bottom: 16px;
    min-width: 64px;
  }

  .floating-version-button :deep(.el-icon) {
    font-size: 22px;
  }

  .floating-version-button .button-label {
    font-size: 0.8rem;
  }

  .version-item {
    grid-template-columns: 1fr;
  }

  .version-icon {
    display: none;
  }
}
</style>
