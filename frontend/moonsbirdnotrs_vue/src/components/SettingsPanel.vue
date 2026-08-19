<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Icon } from '@iconify/vue'

import {
  EDITOR_TOOLBAR_MODES,
  MAX_EDITOR_FONT_SIZE_PX,
  MAX_NOTE_LIST_PAGE_SIZE,
  MIN_EDITOR_FONT_SIZE_PX,
  MIN_NOTE_LIST_PAGE_SIZE,
  getEditorSettings,
  updateEditorSettings,
} from '../utils/editorSettings'
import { THEME_CHANGE_EVENT, THEMES, applyTheme, getEffectiveTheme, getStoredTheme } from '../utils/theme'

const props = defineProps({
  collapsed: {
    type: Boolean,
    default: false,
  },
  mobile: {
    type: Boolean,
    default: false,
  },
})

const currentTheme = ref(getStoredTheme())
const effectiveTheme = ref(getEffectiveTheme())
const editorSettings = ref(getEditorSettings())
const compact = computed(() => props.collapsed && !props.mobile)
const isDarkTheme = computed(() => effectiveTheme.value === THEMES.DARK)
const toolbarModeStatusText = computed(() =>
  editorSettings.value.toolbarMode === EDITOR_TOOLBAR_MODES.FIXED ? '固定工具栏' : '选区工具栏'
)
const themeStatusText = computed(() => {
  if (currentTheme.value === THEMES.SYSTEM) {
    return `跟随系统：${isDarkTheme.value ? '黑夜模式' : '白天模式'}`
  }

  return isDarkTheme.value ? '黑夜模式' : '白天模式'
})
const autoSaveIntervalSeconds = computed({
  get: () => Math.round(editorSettings.value.autoSaveIntervalMs / 1000),
  set: (value) => {
    editorSettings.value = updateEditorSettings({
      autoSaveIntervalMs: Number(value || 5) * 1000,
    })
  },
})
const editorFontSizePx = computed({
  get: () => editorSettings.value.fontSizePx,
  set: (value) => {
    editorSettings.value = updateEditorSettings({
      fontSizePx: value,
    })
  },
})
const noteListPageSize = computed({
  get: () => editorSettings.value.noteListPageSize,
  set: (value) => {
    editorSettings.value = updateEditorSettings({
      noteListPageSize: value,
    })
  },
})

const setTheme = (theme) => {
  currentTheme.value = applyTheme(theme)
  effectiveTheme.value = getEffectiveTheme()
}

const setAutoSaveEnabled = (value) => {
  editorSettings.value = updateEditorSettings({
    autoSaveEnabled: value,
  })
}

const setToolbarMode = (toolbarMode) => {
  editorSettings.value = updateEditorSettings({ toolbarMode })
}

const handleThemeChange = (event) => {
  currentTheme.value = event.detail?.theme || getStoredTheme()
  effectiveTheme.value = event.detail?.effectiveTheme || getEffectiveTheme()
}

onMounted(() => {
  window.addEventListener(THEME_CHANGE_EVENT, handleThemeChange)
})

onBeforeUnmount(() => {
  window.removeEventListener(THEME_CHANGE_EVENT, handleThemeChange)
})
</script>

<template>
  <el-popover
    placement="right-end"
    trigger="click"
    :width="compact ? 300 : 340"
    popper-class="settings-popover"
  >
    <template #reference>
      <button
        class="settings-button"
        :class="{ 'is-collapsed': compact }"
        type="button"
        :title="compact ? '设置' : undefined"
        aria-label="设置"
      >
        <Icon class="settings-icon" icon="ph:gear-six" />
        <span v-if="!compact">设置</span>
      </button>
    </template>

    <section class="settings-panel" aria-label="设置">
      <header class="settings-head">
        <p>Settings</p>
        <h3>偏好设置</h3>
      </header>

      <div class="settings-row">
        <div class="settings-row-copy">
          <strong>外观模式</strong>
          <span>{{ themeStatusText }}</span>
        </div>

        <div class="theme-segment" role="group" aria-label="外观模式">
          <button
            type="button"
            class="theme-option"
            :class="{ 'is-active': currentTheme === THEMES.SYSTEM }"
            @click="setTheme(THEMES.SYSTEM)"
          >
            <Icon icon="ph:monitor" />
            <span>跟随系统</span>
            <Icon v-if="currentTheme === THEMES.SYSTEM" class="check-icon" icon="ph:check" />
          </button>
          <button
            type="button"
            class="theme-option"
            :class="{ 'is-active': currentTheme === THEMES.LIGHT }"
            @click="setTheme(THEMES.LIGHT)"
          >
            <Icon icon="ph:sun" />
            <span>白天</span>
            <Icon v-if="currentTheme === THEMES.LIGHT" class="check-icon" icon="ph:check" />
          </button>
          <button
            type="button"
            class="theme-option"
            :class="{ 'is-active': currentTheme === THEMES.DARK }"
            @click="setTheme(THEMES.DARK)"
          >
            <Icon icon="ph:moon" />
            <span>黑夜</span>
            <Icon v-if="currentTheme === THEMES.DARK" class="check-icon" icon="ph:check" />
          </button>
        </div>
      </div>

      <div class="settings-row">
        <div class="settings-row-copy">
          <strong>列表设置</strong>
          <span>每页 {{ noteListPageSize }} 篇笔记</span>
        </div>

        <div class="setting-line">
          <div>
            <strong>每页笔记数</strong>
            <span>范围 {{ MIN_NOTE_LIST_PAGE_SIZE }}-{{ MAX_NOTE_LIST_PAGE_SIZE }} 篇</span>
          </div>
          <el-input-number
            v-model="noteListPageSize"
            class="page-size-input"
            :min="MIN_NOTE_LIST_PAGE_SIZE"
            :max="MAX_NOTE_LIST_PAGE_SIZE"
            :step="1"
            controls-position="right"
          />
        </div>
      </div>

      <div class="settings-row">
        <div class="settings-row-copy">
          <strong>编辑器设置</strong>
          <span>{{ toolbarModeStatusText }}</span>
        </div>

        <div class="setting-line setting-line-stack">
          <div>
            <strong>正文工具栏</strong>
            <span>固定模式会在笔记和日记正文上方常驻显示</span>
          </div>
          <div class="toolbar-mode-segment" role="group" aria-label="正文工具栏模式">
            <button
              type="button"
              class="toolbar-mode-option"
              :class="{ 'is-active': editorSettings.toolbarMode === EDITOR_TOOLBAR_MODES.CURRENT }"
              :aria-pressed="editorSettings.toolbarMode === EDITOR_TOOLBAR_MODES.CURRENT"
              @click="setToolbarMode(EDITOR_TOOLBAR_MODES.CURRENT)"
            >
              当前模式
            </button>
            <button
              type="button"
              class="toolbar-mode-option"
              :class="{ 'is-active': editorSettings.toolbarMode === EDITOR_TOOLBAR_MODES.FIXED }"
              :aria-pressed="editorSettings.toolbarMode === EDITOR_TOOLBAR_MODES.FIXED"
              @click="setToolbarMode(EDITOR_TOOLBAR_MODES.FIXED)"
            >
              固定工具栏
            </button>
          </div>
        </div>

        <div class="setting-line">
          <div>
            <strong>自动保存</strong>
            <span>定时保存当前笔记，不生成版本记录</span>
          </div>
          <el-switch
            :model-value="editorSettings.autoSaveEnabled"
            @update:model-value="setAutoSaveEnabled"
          />
        </div>

        <div class="setting-line">
          <div>
            <strong>保存间隔</strong>
            <span>范围 3-60 秒</span>
          </div>
          <el-input-number
            v-model="autoSaveIntervalSeconds"
            class="interval-input"
            :min="3"
            :max="60"
            :step="1"
            :disabled="!editorSettings.autoSaveEnabled"
            controls-position="right"
          />
        </div>

        <div class="setting-line setting-line-stack">
          <div class="setting-line-head">
            <div>
              <strong>正文字号</strong>
              <span>只调整编辑和阅读显示，Markdown 内容保持纯净</span>
            </div>
            <strong class="font-size-value">{{ editorFontSizePx }}px</strong>
          </div>
          <div class="font-size-control">
            <el-slider
              v-model="editorFontSizePx"
              :min="MIN_EDITOR_FONT_SIZE_PX"
              :max="MAX_EDITOR_FONT_SIZE_PX"
              :step="1"
              :show-tooltip="false"
            />
            <el-input-number
              v-model="editorFontSizePx"
              class="font-size-input"
              :min="MIN_EDITOR_FONT_SIZE_PX"
              :max="MAX_EDITOR_FONT_SIZE_PX"
              :step="1"
              controls-position="right"
            />
          </div>
        </div>
      </div>
    </section>
  </el-popover>
</template>

<style scoped>
.settings-button {
  display: inline-flex;
  align-items: center;
  justify-content: flex-start;
  gap: 12px;
  width: 100%;
  min-height: 58px;
  padding: 0 16px;
  border: 1px solid rgba(123, 83, 58, 0.13);
  border-radius: 12px;
  background: rgba(255, 250, 241, 0.76);
  color: #2f3430;
  font: inherit;
  font-weight: 700;
  cursor: pointer;
  transition:
    transform 0.2s var(--motion-snappy),
    border-color 0.2s var(--motion-calm),
    background 0.2s var(--motion-calm),
    color 0.2s var(--motion-calm);
}

.settings-button:hover {
  transform: translateY(-1px);
  border-color: var(--accent-border);
  background: var(--accent-soft);
  color: var(--accent);
}

.settings-button.is-collapsed {
  width: 46px;
  height: 46px;
  min-height: 46px;
  padding: 0;
  justify-content: center;
  border-radius: 12px;
}

.settings-icon {
  width: 1rem;
  height: 1rem;
  flex: 0 0 auto;
}

.settings-panel {
  display: grid;
  gap: 18px;
  color: var(--text-primary);
}

.settings-head {
  display: grid;
  gap: 4px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-soft);
}

.settings-head p,
.settings-head h3 {
  margin: 0;
}

.settings-head p {
  color: var(--text-muted);
  font-size: 0.76rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.settings-head h3 {
  font-size: 1.05rem;
  line-height: 1.2;
}

.settings-row {
  display: grid;
  gap: 12px;
}

.settings-row-copy {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.settings-row-copy strong {
  color: var(--text-primary);
  font-size: 0.94rem;
}

.settings-row-copy span {
  color: var(--text-muted);
  font-size: 0.84rem;
  font-weight: 700;
}

.setting-line {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 16px;
  align-items: center;
  min-width: 0;
  padding: 10px 0;
  border: 0;
  border-radius: 0;
  background: transparent;
}

.setting-line + .setting-line {
  border-top: 1px solid var(--border-soft);
}

.setting-line-stack {
  grid-template-columns: minmax(0, 1fr);
}

.setting-line-head,
.font-size-control {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 14px;
  align-items: center;
}

.setting-line > div:first-child {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.setting-line strong {
  color: var(--text-primary);
  font-size: 0.9rem;
}

.setting-line span {
  color: var(--text-muted);
  font-size: 0.78rem;
  line-height: 1.5;
}

.interval-input {
  width: 104px;
}

.page-size-input {
  width: 112px;
}

.font-size-value {
  min-width: 44px;
  color: var(--accent) !important;
  text-align: right;
}

.font-size-input {
  width: 96px;
}

.interval-input :deep(.el-input__wrapper) {
  background: var(--surface);
}

.page-size-input :deep(.el-input__wrapper) {
  background: var(--surface);
}

.font-size-input :deep(.el-input__wrapper) {
  background: var(--surface);
}

.font-size-control :deep(.el-slider) {
  --el-slider-main-bg-color: var(--accent);
  --el-slider-runway-bg-color: var(--border-soft);
  --el-slider-button-size: 16px;
}

.toolbar-mode-segment {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
  padding: 4px;
  border: 1px solid var(--border-soft);
  border-radius: 12px;
  background: var(--surface-soft);
}

.toolbar-mode-option {
  min-height: 36px;
  padding: 0 12px;
  border: 1px solid transparent;
  border-radius: 9px;
  background: transparent;
  color: var(--text-muted);
  font: inherit;
  font-size: 0.82rem;
  font-weight: 800;
  cursor: pointer;
  transition:
    background 0.16s ease,
    border-color 0.16s ease,
    color 0.16s ease,
    box-shadow 0.16s ease;
}

.toolbar-mode-option:hover,
.toolbar-mode-option:focus-visible {
  border-color: var(--accent-border);
  outline: none;
  color: var(--accent);
}

.toolbar-mode-option.is-active {
  border-color: var(--accent-border);
  background: var(--surface);
  color: var(--accent);
  box-shadow: 0 4px 12px rgba(78, 54, 38, 0.08);
}

.theme-segment {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.theme-option {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  min-width: 0;
  min-height: 42px;
  padding: 0 8px;
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-md);
  background: var(--surface-soft);
  color: var(--text-secondary);
  font: inherit;
  font-size: 0.9rem;
  font-weight: 700;
  cursor: pointer;
  transition:
    border-color 0.18s var(--motion-calm),
    background 0.18s var(--motion-calm),
    color 0.18s var(--motion-calm),
    transform 0.18s var(--motion-snappy);
}

.theme-option span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.theme-option:hover,
.theme-option.is-active {
  border-color: var(--accent-border);
  background: var(--accent-soft);
  color: var(--accent);
}

.theme-option:hover {
  transform: translateY(-1px);
}

.check-icon {
  width: 0.88rem;
  height: 0.88rem;
}

:global(.settings-popover.el-popper) {
  border-color: var(--border-soft);
  border-radius: var(--radius-md);
  background:
    linear-gradient(180deg, rgba(250, 244, 233, 0.96), rgba(232, 219, 199, 0.82)),
    var(--surface);
  box-shadow: var(--shadow-soft);
}

:global(.settings-popover.el-popper .el-popper__arrow::before) {
  border-color: var(--border-soft);
  background: var(--surface);
}

@media (max-width: 640px) {
  .settings-button {
    width: 100%;
  }

  :global(.settings-popover.el-popper) {
    width: calc(100vw - 24px) !important;
    max-width: 340px;
  }

  .setting-line,
  .setting-line-head,
  .font-size-control {
    gap: 10px;
  }

  .theme-segment {
    grid-template-columns: 1fr;
  }
}
</style>
