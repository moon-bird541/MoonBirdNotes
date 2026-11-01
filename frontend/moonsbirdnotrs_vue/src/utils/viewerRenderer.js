/*
 * toast-ui Viewer 的渲染选项
 * ---------------------------------------------------------------------------
 * Viewer 默认的 codeBlock 转换器只保留 info-string 的第一个词
 *（`js title="a.js" {1,3-5}` → 只剩 `js`），Firefly 风格的代码块参数会全部丢失。
 * 这里接管 codeBlock，把完整 info 交给 utils/fenceInfo.js 生成规范化 HTML。
 *
 * Viewer 也不认 `:::` 容器语法，因此配合 utils/directives.js：
 * 渲染前先用 `expandDirectives()` 展开 Markdown，再用 `registry.setGroups()`
 * 把分组交给渲染器，占位注释才会被替换成真正的代码组。
 *
 * 注意：产物仍会经过 Viewer 内置的 DOMPurify 净化，因此这里只输出静态结构，
 * 交互按钮由 utils/codeBlockTools.js 在净化之后动态插入。
 */

import { matchGroupPlaceholder, renderGroupPlaceholder } from './directives'
import { buildCodeBlockHtml, parseFenceInfo } from './fenceInfo'

const renderPlaceholder = (literal, getGroups) => {
  const index = matchGroupPlaceholder(literal || '')
  if (index === null) {
    return { type: 'html', content: literal || '' }
  }
  return { type: 'html', content: renderGroupPlaceholder(getGroups(), index) }
}

/**
 * 创建一套可复用的 Viewer 渲染器。
 *
 * Viewer 实例在页面生命周期内只创建一次，而代码组内容随笔记变化，
 * 因此渲染器持有可变的分组引用，切换笔记时调用 `setGroups()` 即可。
 */
export const createViewerRendererRegistry = () => {
  let groups = []

  const options = {
    codeBlock: (node) => ({
      type: 'html',
      content: buildCodeBlockHtml(node.literal || '', parseFenceInfo(node.info || '')),
    }),
    htmlBlock: (node) => renderPlaceholder(node.literal, () => groups),
    htmlInline: (node) => renderPlaceholder(node.literal, () => groups),
  }

  return {
    options,
    setGroups(nextGroups = []) {
      groups = nextGroups
    },
  }
}
