# 固定编辑器工具栏实施计划

## 1. 偏好与设置

- 在 `editorSettings.js` 增加 `toolbarMode` 枚举、默认值和非法值规范化。
- 在 `SettingsPanel.vue` 的编辑器设置区增加“现有工具栏 / 固定工具栏”分段
  选择，沿用 `updateEditorSettings()` 即时分发事件。
- 验证旧 localStorage 对象不会丢失其他设置，非法模式回退为 current。

## 2. 共享工具栏与状态投影

- 新建 `editor/components/FixedEditorToolbar.vue`，实现首版按钮分组、激活/禁用
  状态、中文 tooltip/aria-label、链接弹层和表格选择器。
- 在 `editorHelpers.js` 增加折叠光标和选区均可用的固定工具栏状态投影及默认
  状态工厂；不把编辑器实例或 API 调用放进组件。
- 使用现有 `tableLayout` 上限，不重复硬编码。

## 3. 笔记编辑器集成

- 根据 `editorSettings.toolbarMode` 计算固定模式并响应 change event。
- 保存/恢复包括折叠光标在内的固定栏选区；通过专用适配器执行 Toast UI
  命令，并复用现有图片上传、表格插入和内容/预览同步。
- 固定模式挂载 sticky 工具栏，隐藏浮动格式栏和 `SideTableToolbar`；current
  模式保持原样。
- 保留当前 placeholder、IME、标点选区、表格和图片事件代码。

## 4. 日记编辑器集成

- 接入同一固定工具栏、状态投影和偏好事件。
- 复用日记现有图片上传、表格插入、Markdown 同步与自动保存。
- 固定模式隐藏原内嵌浮动工具栏；current 模式不改变。
- 调整编辑器面板裁剪层，使 sticky 在真实页面滚动中生效且圆角/溢出不回归。

## 5. 样式与响应式

- 使用现有设计 tokens 完成纸面式固定栏、分组分隔与激活状态。
- 桌面单行；窄屏/高缩放仅工具带横向滚动，并提供可见焦点和稳定滚动条行为。
- 检查 sticky 不遮挡标题、正文、表格菜单、图片工具栏或 Element Plus 弹层。

## 6. 验证

- 新增聚焦 Playwright：设置切换/持久化/非法值回退；笔记和日记固定模式；
  current 模式回归；光标与选区格式；链接、表格、图片入口；窄屏可达性。
- 复跑 `note-punctuation-selection.spec.js`，确保 IME/选区修复保留。
- 使用系统 Edge 运行聚焦 E2E，运行 `npm run build` 与 `git diff --check`。
- 人工滚动长笔记和长日记，检查 sticky、浏览器缩放和工具栏横向滚动。

## 风险与回滚点

- 首个回滚点：偏好字段与设置 UI；必须先验证旧存储兼容。
- 第二个回滚点：共享组件与命令适配；必须在两个编辑器分别通过光标/选区测试。
- 第三个回滚点：sticky 布局；若 overflow 调整影响日记圆角或表格，限制改动到
  新增正文裁剪层，不扩大为页面重构。
- 不提交或覆盖本任务之外的既有工作区变化。

## 验证记录（2026-08-17）

- `npm run build`：通过（Vite 8.0.11，1751 modules transformed）。
- 系统 Edge 聚焦回归：`fixed-editor-toolbar.spec.js` 与
  `note-punctuation-selection.spec.js` 共 7 项全部通过。
- 完整 Edge E2E：13 项中 12 项通过；唯一失败是已有 Token 页面用例
  `getByText('1,200')` 同时命中汇总和表格两个元素的严格定位冲突，本任务未
  修改该页面或测试。
- `git diff --check` 与新增文件尾随空白检查通过。
- 已真实截图检查桌面固定栏；发现并修复远程 Iconify 集合不可用时按钮图标
  为空的问题，固定栏改用本地 Element Plus 图标。
- `trellis-finish-work` 未归档：本任务改动尚未提交，且工作区存在大量并行
  未提交内容；保留 `in_progress`，等待明确提交范围。
