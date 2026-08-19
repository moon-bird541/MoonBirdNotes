import DOMPurify from 'dompurify'
import { marked } from 'marked'

marked.setOptions({
  breaks: false,
  gfm: true,
})

export const renderAgentAnswer = (content = '') => {
  if (typeof content !== 'string' || !content.trim()) {
    return ''
  }

  // Agent 回答属于不可信文本，Markdown 转换后必须再次净化才能交给 v-html。
  const sanitized = DOMPurify.sanitize(marked.parse(content), {
    USE_PROFILES: { html: true },
    FORBID_TAGS: ['style', 'script', 'iframe', 'object', 'embed', 'form'],
    FORBID_ATTR: ['style', 'onerror', 'onclick', 'onload'],
  })

  // 只在净化完成后添加固定代码栏；复制时从 code.textContent 读取，不把正文写入属性。
  return sanitized.replace(
    /<pre><code(?: class="language-([a-z0-9_+-]+)")?>([\s\S]*?)<\/code><\/pre>/gi,
    (_match, language = 'code', code) => `
      <div class="agent-code-block">
        <div class="agent-code-toolbar">
          <span>${language.toUpperCase()}</span>
          <button class="agent-code-copy" type="button">复制代码</button>
        </div>
        <pre><code class="language-${language}">${code}</code></pre>
      </div>
    `,
  )
}
