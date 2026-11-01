/*
 * 编辑器正文预览
 * ---------------------------------------------------------------------------
 * 编辑器的所见即所得面板只排布 block 结构，Firefly 风格的代码块参数
 *（title / 行标记 / 行号 / 折叠）和代码组在 WYSIWYG 里无法完整表达，
 * 因此这里用 marked 把当前 Markdown 转成 HTML：代码块交给 utils/fenceInfo.js，
 * 代码组交给 utils/directives.js，与阅读端共用同一套结构。
 *
 * 输出仍属于不可信 HTML：调用方必须先用 utils/previewSanitizer.js 净化
 * 再交给 v-html。
 */

import { marked } from 'marked'

import { expandDirectives, matchGroupPlaceholder, renderGroupPlaceholder } from './directives'
import { buildCodeBlockHtml, parseFenceInfo } from './fenceInfo'

const createRenderer = (getGroups) => {
  const renderer = new marked.Renderer()

  renderer.code = ({ text, lang }) => buildCodeBlockHtml(text || '', parseFenceInfo(lang || ''))

  // marked 的 html 回调同样收到 token 对象，取 text 才是原始 HTML
  renderer.html = (token) => {
    const raw = typeof token === 'string' ? token : token?.text ?? ''
    const index = matchGroupPlaceholder(raw)
    if (index === null) {
      return raw
    }
    return renderGroupPlaceholder(getGroups(), index)
  }

  return renderer
}

/**
 * 把 Markdown 渲染成阅读端同构的 HTML（未净化）。
 * @param {string} markdown
 * @returns {string}
 */
export const renderMarkdownPreview = (markdown = '') => {
  if (!String(markdown || '').trim()) {
    return ''
  }

  const { markdown: prepared, groups } = expandDirectives(markdown)
  return marked.parse(prepared, {
    renderer: createRenderer(() => groups),
    gfm: true,
    breaks: false,
  })
}
