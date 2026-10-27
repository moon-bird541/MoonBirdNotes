# Firefly 风格 Markdown 扩展语法

## 目标

把 [Firefly](https://github.com/CuteLeaf/Firefly) 的 Markdown 扩展能力移植到 MoonBirdNotes，
并在阅读端、编辑器、导出 HTML 三处表现一致。

范围（按用户选择）：

1. 提醒框（Callouts）：GitHub / Obsidian 全类型 + 自定义标题，兼容 `> [!TYPE]` 与 `:::type[标题]` 两种写法。
2. 代码块增强：`title="..."`、行高亮 `{1,3-5}`、`ins={..}` / `del={..}` / `"文本"` / `/regex/`、
   `showLineNumbers`、`startLineNumber=N`、`collapse={..}`、`diff` 增删着色、`lang=`、`frame=none`、`wrap=false`。
3. 代码组：`::: code-group labels=[a.js, b.py]` 多代码块合并为标签页。

不包含（明确排除）：Mermaid、PlantUML、GitHub 仓库卡片、`[[Wiki 双链]]`、`[grid]` 图片网格、`:spoiler[]`。

## 关键约束

- 阅读端使用 toast-ui `Viewer` 在浏览器内渲染 Markdown，后端渲染只用于上传预览、版本预览和导出 HTML。
  两条链路都必须产出**同一套 canonical HTML**，样式与交互只写一次。
- toast-ui `Viewer` 的默认 `codeBlock` 转换器只保留 info 的第一个词，其余全部丢弃。
  因此阅读端必须注册 `customHTMLRenderer.codeBlock`，把完整 info 写入 `data-mb-info` 再交给增强器。
- toast-ui `Editor`（WYSIWYG）在 markdown → ProseMirror 时把**完整 info 字符串**存进 `language` 属性，
  回写时原样输出，因此编辑器不需要额外存储，只要解析 `data-language` 即可。
- 安全边界不变：后端 `rendered_html` 仍由 Bleach 净化；客户端生成的 HTML 仍在本地净化。
  新增标签/属性必须同步加入白名单，且不允许 `style`、`on*`、`javascript:`。

## Canonical HTML 契约

### 提醒框

```html
<blockquote class="moonbird-callout moonbird-callout-tip" data-mb-callout="tip">
  <p class="moonbird-callout-title" data-mb-callout-custom="true">提示 · 自定义标题</p>
  <p>正文…</p>
</blockquote>
```

- `data-mb-callout` = 归一化后的类型（`abstract/summary/tldr` → `abstract`，`hint` → `tip`，`danger/error` → `danger` 等）。
- 无自定义标题时 `data-mb-callout-custom` 不存在，标题文本为 `图标 + 默认中文名`。

### 代码块

```html
<div class="moonbird-code" data-mb-info="js title=&quot;a.js&quot; {1,3-5}"
     data-mb-collapse="3-4" data-mb-start="1" data-mb-ready="1">
  <div class="moonbird-code-head">
    <span class="moonbird-code-lang">js</span>
    <span class="moonbird-code-title">a.js</span>
  </div>
  <pre class="moonbird-code-pre has-line-numbers"><code class="language-js"><span class="moonbird-code-line" data-mb-line="1">const a = 1</span><span class="moonbird-code-line" data-mb-line="2" data-mb-mark="ins">const b = 2</span>…</code></pre>
</div>
```

- 行元素一律 `display:block`，行与行之间**不能**出现换行文本节点，否则会多出空行。
- `data-mb-mark` ∈ `mark | ins | del`，`data-mb-note` 存放行标记的标签文本。
- `data-mb-collapse` 存放被折叠的行号表达式；默认展开，由脚本（或应用内增强器）折叠，禁止 JS 时内容不丢。

### 代码组

```html
<div class="moonbird-code-group" data-mb-ready="1">
  <div class="moonbird-code-tabs" role="tablist">
    <button type="button" class="moonbird-code-tab is-active" role="tab" data-mb-tab="0">a.js</button>
    <button type="button" class="moonbird-code-tab" role="tab" data-mb-tab="1">b.py</button>
  </div>
  <div class="moonbird-code-panels">
    <div class="moonbird-code-panel is-active" data-mb-panel="0">…代码块…</div>
    <div class="moonbird-code-panel" data-mb-panel="1">…代码块…</div>
  </div>
</div>
```

## 实现位置

| 层 | 文件 | 职责 |
| --- | --- | --- |
| 后端 | `backend/notes/markdown_extensions.py` | 解析 fence info、::: 容器、代码组，产出 canonical HTML |
| 后端 | `backend/notes/serializers.py` | 接入扩展、放宽 Bleach 白名单 |
| 后端 | `backend/notes/export_assets.py` | 导出 HTML 用的样式与交互脚本（离线自包含） |
| 前端 | `src/utils/fenceInfo.js` | fence info 解析/序列化（编辑器与增强器共用） |
| 前端 | `src/utils/markdownExtensions.js` | Viewer 渲染器 + DOM 增强器 + 编辑器代码块装饰 |
| 前端 | `src/styles/blog-prose.css` | 全部新结构样式 |

## 验收

- 后端：`python manage.py test notes` 全绿，新增用例覆盖提醒框、代码行标记、代码组、XSS 白名单。
- 前端：`npm run build` 通过。
- 手工：Firefly 的 `markdown-extended.md`、`code-examples.md` 两篇样例粘进笔记后，详情页、编辑页、导出 HTML 三处外观一致。
