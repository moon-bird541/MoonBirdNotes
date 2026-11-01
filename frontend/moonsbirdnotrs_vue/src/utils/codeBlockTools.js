/*
 * 代码块扩展语法的 DOM 增强
 * ---------------------------------------------------------------------------
 * 负责 Firefly / Expressive Code 风格代码块在阅读端的交互部分：
 *   1. 折叠代码段（collapse={…}）：默认收起，点击展开
 *   2. Tab 代码组（::: code-group）：点击/键盘切换面板
 *
 * 结构本身由后端 `notes/markdown_extensions.py` 或前端
 * `buildCodeBlockHtml()`（utils/fenceInfo.js）产出，这里只做幂等增强，
 * 可以安全地在每次内容更新后重复调用。
 */

const COLLAPSED_CLASS = 'is-collapsed'
const EXPANDED_CLASS = 'is-expanded'
const READY_CLASS = 'has-collapse-ready'

/** 折叠：把标记为 is-collapsed 的行收起，并提供展开/收起开关。 */
const enhanceCollapsibleBlocks = (root) => {
  const blocks = root.querySelectorAll('.moonbird-code.has-collapse')

  blocks.forEach((block) => {
    if (block.dataset.mbCollapseReady === 'true') {
      return
    }

    const collapsedLines = block.querySelectorAll(`.${COLLAPSED_CLASS}`)
    if (!collapsedLines.length) {
      return
    }

    const toggle = document.createElement('button')
    toggle.type = 'button'
    toggle.className = 'moonbird-code-toggle'

    const sync = () => {
      const expanded = block.classList.contains(EXPANDED_CLASS)
      toggle.setAttribute('aria-expanded', expanded ? 'true' : 'false')
      toggle.textContent = expanded
        ? '收起折叠代码'
        : `展开折叠的 ${collapsedLines.length} 行`
    }

    toggle.addEventListener('click', () => {
      block.classList.toggle(EXPANDED_CLASS)
      sync()
    })

    block.appendChild(toggle)
    block.dataset.mbCollapseReady = 'true'
    block.classList.add(READY_CLASS)
    sync()
  })
}

/** 代码组：标签页切换。 */
const activatePanel = (group, index) => {
  const tabs = group.querySelectorAll('.moonbird-code-tab')
  const panels = group.querySelectorAll('.moonbird-code-panel')

  tabs.forEach((tab, tabIndex) => {
    const active = tabIndex === index
    tab.classList.toggle('is-active', active)
    tab.setAttribute('aria-selected', active ? 'true' : 'false')
    tab.tabIndex = active ? 0 : -1
  })

  panels.forEach((panel, panelIndex) => {
    panel.classList.toggle('is-active', panelIndex === index)
  })
}

const enhanceCodeGroups = (root) => {
  const groups = root.querySelectorAll('.moonbird-code-group')

  groups.forEach((group) => {
    if (group.dataset.mbGroupReady === 'true') {
      return
    }

    const tabs = Array.from(group.querySelectorAll('.moonbird-code-tab'))
    if (!tabs.length) {
      return
    }

    tabs.forEach((tab, index) => {
      tab.addEventListener('click', () => activatePanel(group, index))
      tab.addEventListener('keydown', (event) => {
        const lastIndex = tabs.length - 1
        let nextIndex = null

        if (event.key === 'ArrowRight') {
          nextIndex = index >= lastIndex ? 0 : index + 1
        } else if (event.key === 'ArrowLeft') {
          nextIndex = index <= 0 ? lastIndex : index - 1
        } else if (event.key === 'Home') {
          nextIndex = 0
        } else if (event.key === 'End') {
          nextIndex = lastIndex
        } else if (event.key === 'Enter' || event.key === ' ') {
          nextIndex = index
        }

        if (nextIndex === null) {
          return
        }

        event.preventDefault()
        const nextTab = tabs[nextIndex]
        activatePanel(group, nextIndex)
        nextTab?.focus()
      })
    })

    group.dataset.mbGroupReady = 'true'
    activatePanel(group, 0)
  })
}

/**
 * 对容器内的代码块与代码组做一次幂等增强。
 * @param {HTMLElement | null | undefined} root
 */
export const enhanceCodeBlocks = (root) => {
  if (!root) {
    return
  }

  enhanceCodeGroups(root)
  enhanceCollapsibleBlocks(root)
}
