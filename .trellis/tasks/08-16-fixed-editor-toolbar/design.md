# 固定编辑器工具栏设计

## 1. 边界与架构

本功能仅修改前端，不改变笔记、日记、图片或 Markdown 的后端契约。

```text
SettingsPanel
    -> editorSettings.toolbarMode + localStorage/change event
        -> NoteEditView / DiaryEditView
            -> current: 原浮动格式栏与原插入控件
            -> fixed: Shared FixedEditorToolbar
                -> command / heading / link / image / table events
                    -> 各编辑页复用现有 Toast UI、上传和表格处理函数
```

新建一个编辑器专用共享组件 `FixedEditorToolbar.vue`。它只负责按钮、分组、
提示、链接弹层、表格选择器和响应式表现，不直接持有 Toast UI 实例、调用 API
或读取 localStorage。笔记和日记视图继续拥有编辑器实例及内容变更副作用。

现有 `FloatingFormatToolbar.vue` 和日记内嵌浮动栏首版不重构，避免在新增模式
时改变用户已经熟悉的现有模式。固定模式在两个页面共享同一个新组件，避免
再复制一份按钮和弹层实现。

## 2. 偏好契约

在 `src/utils/editorSettings.js` 增加受控枚举：

```js
EDITOR_TOOLBAR_MODES = {
  CURRENT: 'current',
  FIXED: 'fixed',
}

DEFAULT_EDITOR_SETTINGS.toolbarMode = EDITOR_TOOLBAR_MODES.CURRENT
```

`normalizeEditorSettings()` 只接受两个枚举值；旧对象缺字段、JSON 异常或非法
值一律回退到 `current`。`SettingsPanel.vue` 使用分段选择控件调用
`updateEditorSettings({ toolbarMode })`。既有 change event 会让两个打开的编辑页
即时更新；切换时页面主动关闭已经打开的浮动栏、链接弹层和表格选择器。

## 3. 共享组件契约

`FixedEditorToolbar.vue` 的核心 props：

- `editorReady: Boolean`：控制禁用状态；
- `toolbarState: Object`：光标/选区的粗体、斜体、删除线、代码、链接、标题、
  引用、列表和代码块状态；
- `selectedText: String`：打开链接弹层时预填文字；
- `headingOptions: Array`：沿用 H1-H3；
- `maxTableRows` / `maxTableColumns`：沿用项目表格上限。

核心 emits：

- `command(name, payload)`：粗体、斜体、删除线、行内代码、引用、三种列表、
  分隔线和代码块；
- `apply-heading(level)`；
- `insert-link({ linkUrl, linkText })`；
- `insert-image`；
- `insert-table(rows, columns)`；
- `remember-selection`：在打开会转移焦点的弹层/文件选择器之前保存选区。

按钮使用 `mousedown.prevent` 保留编辑器焦点。链接和表格弹层会转移焦点，
因此父视图在打开前保存包括折叠光标在内的 `[from, to]`，提交前恢复，再执行
Toast UI 命令。

## 4. 命令与状态同步

固定模式统一走 Toast UI 3.2.2 已注册命令：`bold`、`italic`、`strike`、
`code`、`heading`、`blockQuote`、`bulletList`、`orderedList`、`taskList`、
`thematicBreak`、`addLink`、`codeBlock` 与 `addTable`。图片继续走现有文件校验、
上传 hook 和图片插入路径。

在 `editorHelpers.js` 增加无副作用的状态投影函数，从
`editorInstance.wwEditor.view.state` 读取：

- 折叠光标使用 stored marks / `$from.marks()` 与祖先块；
- 非空选区计算部分激活和完整激活；
- 列表区分 bullet、ordered 与 task list；
- 链接读取 link mark；
- 标题、引用和代码块读取当前块祖先。

两个视图在 Toast UI `caretChange`、`focus`、`change` 及命令完成后刷新固定栏
状态。现有模式继续使用原有选区状态和定位逻辑。

## 5. 页面集成与布局

- 笔记：放入 `NoteEditorPanel` 的 editor slot，位于标题/标签/字数之后、正文
  Toast UI 容器之前。
- 日记：放在 `.editor-panel-head` 之后、正文 Toast UI 容器之前；为 sticky
  元素拆出不会建立错误滚动容器的正文裁剪层，保留当前圆角和溢出约束。
- 工具栏使用 `position: sticky`，顶部留出页面安全间距，z-index 高于正文、低于
  模态弹层和图片操作浮层。
- 内层工具带保持单行并 `overflow-x: auto`；外层不产生页面级横向滚动。
- 视觉使用现有 paper/surface/border/accent tokens 和统一的本地 Element Plus
  图标（行内代码使用文字图形）；不依赖远程图标集合，也不逐像素复制参考图
  的冷白办公软件风格。

## 6. 兼容与风险

- 默认 `current`，因此部署后现有用户界面不突变。
- `NoteEditView.vue` 当前含尚未提交的中文 IME placeholder 与标点选区修复；
  实现必须基于现状增量修改，不覆盖这些事件和 DOM 选区保护。
- 链接弹层使用 Toast UI 原生 `addLink` payload（`linkUrl`、`linkText`），不增加
  新的 HTML/Markdown 语义。
- 表格与图片复用现有上限、上传错误提示和 API，不复制验证逻辑。
- sticky 祖先的 overflow 是主要布局风险；日记页必须通过真实滚动与缩放测试，
  不能只靠静态截图判断。

## 7. 验证与回滚

- Playwright 覆盖设置即时切换/持久化、默认回退、笔记和日记两种模式、折叠
  光标与非空选区命令、链接、图片/表格入口、sticky 与窄屏横向可达性。
- 保留标点选区与空笔记中文 composition 回归。
- 运行 `npm run build` 和相关 Edge E2E。
- 回滚时删除新组件和模式分支，并从设置规范化中移除字段；默认 current 设计
  使回滚不需要数据迁移。
