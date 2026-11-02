/*
 * 编辑器正文预览的净化
 * ---------------------------------------------------------------------------
 * 预览 HTML 由 utils/markdownPreview.js 在浏览器内生成，属于不可信内容，
 * 必须先净化再交给 v-html。
 *
 * DOMPurify 默认保留 `data-*` 与 `aria-*`，而代码块扩展语法依赖
 * `data-mb-*` / `role` / `tabindex`，因此不需要额外放宽白名单；
 * 这里只显式禁止脚本类标签与内联样式。
 */

import DOMPurify from 'dompurify'

const FORBID_TAGS = ['style', 'script', 'iframe', 'object', 'embed', 'form', 'link', 'base']
const FORBID_ATTR = ['style']

/**
 * 净化编辑器预览 HTML。
 * @param {string} html
 * @returns {string}
 */
export const sanitizePreviewHtml = (html = '') => {
  if (!html) {
    return ''
  }

  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
    FORBID_TAGS,
    FORBID_ATTR,
  })
}
