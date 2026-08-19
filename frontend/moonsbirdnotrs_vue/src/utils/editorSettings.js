export const EDITOR_SETTINGS_STORAGE_KEY = 'moonbird_editor_settings'
export const EDITOR_SETTINGS_CHANGE_EVENT = 'moonbird-editor-settings-change'
export const EDITOR_TOOLBAR_MODES = Object.freeze({
  CURRENT: 'current',
  FIXED: 'fixed',
})

const editorToolbarModes = new Set(Object.values(EDITOR_TOOLBAR_MODES))

export const DEFAULT_EDITOR_SETTINGS = {
  autoSaveEnabled: true,
  autoSaveIntervalMs: 5000,
  fontSizePx: 16,
  noteListPageSize: 10,
  toolbarMode: EDITOR_TOOLBAR_MODES.CURRENT,
}

const MIN_AUTO_SAVE_INTERVAL_MS = 3000
const MAX_AUTO_SAVE_INTERVAL_MS = 60000
export const MIN_EDITOR_FONT_SIZE_PX = 13
export const MAX_EDITOR_FONT_SIZE_PX = 22
export const MIN_NOTE_LIST_PAGE_SIZE = 5
export const MAX_NOTE_LIST_PAGE_SIZE = 50

const normalizeInterval = (value) => {
  const numericValue = Number(value)

  if (!Number.isFinite(numericValue)) {
    return DEFAULT_EDITOR_SETTINGS.autoSaveIntervalMs
  }

  return Math.min(MAX_AUTO_SAVE_INTERVAL_MS, Math.max(MIN_AUTO_SAVE_INTERVAL_MS, numericValue))
}

const normalizeFontSize = (value) => {
  const numericValue = Number(value)

  if (!Number.isFinite(numericValue)) {
    return DEFAULT_EDITOR_SETTINGS.fontSizePx
  }

  return Math.min(MAX_EDITOR_FONT_SIZE_PX, Math.max(MIN_EDITOR_FONT_SIZE_PX, Math.round(numericValue)))
}

const normalizeNoteListPageSize = (value) => {
  const numericValue = Number(value)

  if (!Number.isFinite(numericValue)) {
    return DEFAULT_EDITOR_SETTINGS.noteListPageSize
  }

  return Math.min(MAX_NOTE_LIST_PAGE_SIZE, Math.max(MIN_NOTE_LIST_PAGE_SIZE, Math.round(numericValue)))
}

const normalizeEditorSettings = (settings = {}) => ({
  autoSaveEnabled:
    typeof settings.autoSaveEnabled === 'boolean'
      ? settings.autoSaveEnabled
      : DEFAULT_EDITOR_SETTINGS.autoSaveEnabled,
  autoSaveIntervalMs: normalizeInterval(settings.autoSaveIntervalMs),
  fontSizePx: normalizeFontSize(settings.fontSizePx),
  noteListPageSize: normalizeNoteListPageSize(settings.noteListPageSize),
  toolbarMode: editorToolbarModes.has(settings.toolbarMode)
    ? settings.toolbarMode
    : DEFAULT_EDITOR_SETTINGS.toolbarMode,
})

export const getEditorSettings = () => {
  try {
    const storedSettings = JSON.parse(localStorage.getItem(EDITOR_SETTINGS_STORAGE_KEY) || '{}')
    return normalizeEditorSettings(storedSettings)
  } catch {
    return { ...DEFAULT_EDITOR_SETTINGS }
  }
}

export const saveEditorSettings = (settings) => {
  const nextSettings = normalizeEditorSettings(settings)
  localStorage.setItem(EDITOR_SETTINGS_STORAGE_KEY, JSON.stringify(nextSettings))
  window.dispatchEvent(
    new CustomEvent(EDITOR_SETTINGS_CHANGE_EVENT, {
      detail: nextSettings,
    })
  )
  return nextSettings
}

export const updateEditorSettings = (patch) => saveEditorSettings({ ...getEditorSettings(), ...patch })
