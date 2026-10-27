# 扩展语法写作入口

## 背景

第一轮把 Firefly 的扩展语法做进了阅读端（toast-ui Viewer + 客户端增强）、后端 `rendered_html`
与导出 HTML，但编辑器只有纯富文本面板：`> [!NOTE]`、```js title="…" {1}```、`::: code-group`
在写作时既没有输入入口，也不会显示最终外观。

## 实现

### 1. 富文本即时预览（decoration）

`src/utils/editorDecorations.js` 导出的 `createRichBlockPreview(handlers)` 是 toast-ui 插件，
用 ProseMirror `Decoration` 就地改造已有节点：

- `blockQuote` 首行匹配 `[!TYPE]` 时加提示框配色类，隐藏标记行并插入标题 widget
- `codeBlock` 前插入信息栏 widget（语言胶囊 / 标题 / 参数徽标 / 设置按钮）
- 以 `:::` 开头的段落加弱化样式

要点：

- 必须用 decoration。ProseMirror 每次事务都按文档重建节点视图，手动 append 的子节点会被移除
  （这正是旧版 `.inline-code-language-chip` 一直不出现的原因）。
- `Plugin` / `Decoration` 必须从 toast-ui 注入的 `context.pmState` / `context.pmView` 取，
  直接用项目里 import 的 prosemirror 会类身份不一致。
- toast-ui 的 `eventEmitter` 只允许内置事件类型，自定义事件在 `listen` 时直接抛错，
  因此交互回调通过闭包传入（`onEditLanguage` / `onEditOptions`）。
- 光标停在提示框标记行且编辑器有焦点时保留原文，否则无法修改类型与标题。

### 2. 提示框写入

`src/utils/wysiwygBlocks.js` 的 `insertWysiwygCallout(view, { kind })` 直接构造
`blockQuote(paragraph(marker), paragraph(body))`，并与空段落替换逻辑配合，避免留下空行。
笔记与日记两个编辑器共用。

工具栏原来的实现是 `insertText('> [!NOTE]\n> ')`，会在正文里留下 `>[!NOTE]` 纯文本，
本轮已修正。

### 3. 源码模式

`src/editor/components/MarkdownSourceEditor.vue`：左 textarea / 右实时预览。

- 预览走 `renderMarkdownPreview` + `sanitizePreviewHtml`，与阅读端同构，且先净化后 `v-html`
- 工具栏来自 `src/utils/markdownSnippets.js`，模板会选中占位文字
- `editorRoot` 始终挂载，切到源码只 `v-show` 隐藏；否则 Toast UI 实例会指向旧 DOM

### 4. 代码块参数面板

`src/editor/components/CodeBlockOptionsDialog.vue` 支持语言、标题、高亮 / 折叠 / 新增 / 删除行、
框架、起始行号、行号与换行，产出 `buildFenceInfo()` 的 info-string。

- 富文本：面板写回 `codeBlock.attrs.language`
- 源码：`findFenceAtOffset()` 定位光标所在围栏代码块，只替换 info 行

### 5. 模式切换

`NoteEditHeader.vue` 增加「富文本 / 源码」分段控件；`NoteEditView.vue` 的
`changeEditorMode()` 在两个面板间搬运 Markdown，切换本身不产生历史版本。
`getCurrentMarkdownWithTableLayouts()` 与 `saveNote` / `autoSave` 都已区分当前模式。

## 验证

- `npm run build` 通过
- 后端 `manage.py test notes`：89 通过
- Playwright：`markdown-authoring.spec.js`（4 条）、`diary-markdown-authoring.spec.js`、
  `markdown-extensions.spec.js`、`editor-body-preview.spec.js`，全量 23 条通过
