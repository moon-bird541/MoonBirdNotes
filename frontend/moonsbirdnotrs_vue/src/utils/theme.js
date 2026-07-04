export const THEME_STORAGE_KEY = 'moonbird_theme'
export const THEME_CHANGE_EVENT = 'moonbird-theme-change'
export const THEMES = {
  SYSTEM: 'system',
  LIGHT: 'light',
  DARK: 'dark',
}

const isTheme = (theme) => Object.values(THEMES).includes(theme)

const getSystemThemeMedia = () =>
  typeof window !== 'undefined' && window.matchMedia
    ? window.matchMedia('(prefers-color-scheme: dark)')
    : null

export const getSystemTheme = () =>
  getSystemThemeMedia()?.matches ? THEMES.DARK : THEMES.LIGHT

export const resolveTheme = (theme) => (theme === THEMES.SYSTEM ? getSystemTheme() : theme)

const applyEffectiveTheme = (theme) => {
  const effectiveTheme = resolveTheme(isTheme(theme) ? theme : THEMES.LIGHT)
  document.documentElement.dataset.theme = effectiveTheme
  document.documentElement.style.colorScheme = effectiveTheme
  return effectiveTheme
}

const emitThemeChange = (theme, effectiveTheme) => {
  window.dispatchEvent(
    new CustomEvent(THEME_CHANGE_EVENT, {
      detail: {
        theme,
        effectiveTheme,
      },
    })
  )
}

export const getStoredTheme = () => {
  const storedTheme = localStorage.getItem(THEME_STORAGE_KEY)
  return isTheme(storedTheme) ? storedTheme : THEMES.LIGHT
}

export const applyTheme = (theme) => {
  const nextTheme = isTheme(theme) ? theme : THEMES.LIGHT
  const effectiveTheme = applyEffectiveTheme(nextTheme)
  localStorage.setItem(THEME_STORAGE_KEY, nextTheme)
  emitThemeChange(nextTheme, effectiveTheme)
  return nextTheme
}

export const getEffectiveTheme = () => resolveTheme(getStoredTheme())

export const initTheme = () => {
  const nextTheme = getStoredTheme()
  const effectiveTheme = applyEffectiveTheme(nextTheme)
  const systemThemeMedia = getSystemThemeMedia()
  const handleSystemThemeChange = () => {
    if (getStoredTheme() !== THEMES.SYSTEM) {
      return
    }

    const nextEffectiveTheme = applyEffectiveTheme(THEMES.SYSTEM)
    emitThemeChange(THEMES.SYSTEM, nextEffectiveTheme)
  }

  if (systemThemeMedia?.addEventListener) {
    systemThemeMedia.addEventListener('change', handleSystemThemeChange)
  } else {
    systemThemeMedia?.addListener?.(handleSystemThemeChange)
  }
  emitThemeChange(nextTheme, effectiveTheme)
  return nextTheme
}

export const toggleTheme = (theme) => applyTheme(theme === THEMES.DARK ? THEMES.LIGHT : THEMES.DARK)
