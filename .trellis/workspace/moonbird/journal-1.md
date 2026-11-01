# Journal - moonbird (Part 1)

> AI development session journal
> Started: 2026-08-16

---



## Session 1: 初始化 MoonBirdNotes Trellis 规范与项目基线

**Date**: 2026-08-16
**Task**: 初始化 MoonBirdNotes Trellis 规范与项目基线
**Branch**: `main`

### Summary

从当前源码、测试、配置、设计文档和历史开发记录中提炼项目规范，并把当前能力、未提交状态、文档偏差和验证结果写入 Trellis。

### Main Changes

- 刷新 backend 规范：目录边界、数据库/事务、错误、日志、配置与安全、质量门。
- 刷新 frontend 规范：Vue 组件、状态、运行时契约、API/安全、设计系统与质量门；删除不适用的 React Hook 模板。
- 新增 2026-08-16 当前项目基线，纠正旧 TODO 中 AI 未完成和 README 中页面/统计/Qdrant 端口等过时描述。
- 独立复核 95 个源码路径、两层索引、Markdown 链接和占位符，并修正 E2E 守卫与 Token 统计口径。

### Git Commits

(No commits - planning session)

### Testing

- [OK] Django manage.py check 通过；makemigrations --check --dry-run 通过。
- [OK] Django 全量 396 项测试通过；前端 npm run build 通过。
- [WARN] Playwright 使用系统 Edge：5/6 通过；现有 getByText('1,200') 严格定位匹配两处导致 1 项失败。

### Status

[OK] **Completed**

### Next Steps

- 修复 Playwright 重复文本定位和现有 el-radio-* 解析警告后重跑 E2E。
- 单独校正 README 的已实现页面、后续方向、Qdrant 端口与 Token 统计描述。
- 审阅并分批提交当前 Trellis 初始化和既有产品改动，再归档 00-bootstrap-guidelines。


## Session 2: Production baseline and development branch

**Date**: 2026-08-19
**Task**: Production baseline and development branch
**Branch**: `main`

### Summary

Committed the deployed MoonBirdNotes production baseline after backend, migration, frontend build, browser-flow, staged-content, and secret checks; prepared a persistent codex/develop branch for all future changes.

### Git Commits

| Hash | Message |
|------|---------|
| `1efdc2bae2f9ea6117149b7a6985352678c9994e` | (see git log) |

### Status

[OK] **Completed**

## Session 3: Firefly 风格 Markdown 扩展语法

**Date**: 2026-10-27
**Task**: 10-27-firefly-markdown-extensions
**Branch**: `main`

### Summary

把 Firefly 博客的扩展 Markdown 语法移植进 MoonBirdNotes，覆盖阅读端、编辑器预览与导出 HTML，
并补齐了写作入口（富文本即时预览、源码模式、代码块参数面板）。

### 关键决策

- 前端与后端各实现一份相同的 fence / 容器解析，HTML 结构共用一套 `moonbird-*` 契约，
  避免"阅读端与导出各写一套样式"。
- python-markdown 的 preprocessor 优先级必须排在 `normalize_whitespace`(30) 之后、
  `fenced_code`(25) 之前，否则 htmlStash 占位符会被当作正文输出。
- toast-ui Viewer 的 `customHTMLRenderer` 产物仍会过它自己的 DOMPurify，
  交互按钮只能在净化之后由 `codeBlockTools.js` 插入。
- 富文本即时预览只能用 ProseMirror `Decoration`：每次事务 ProseMirror 都会重建节点视图，
  手动 append 的 chip 会被直接移除（旧代码里语言芯片一直不显示就是这个原因）。
- toast-ui 的 `eventEmitter` 只接受内置事件类型，`listen` 自定义事件会抛错，
  widget 回调因此改为闭包传入。
- 工具栏"插入提示框"原本是 `insertText('> [!NOTE]')`，会写成纯文本，已改为构造真正的 blockQuote。

### 验证

- 后端 `manage.py test notes`：89 通过（新增 13 条扩展语法与 XSS 用例）
- 前端 `npm run build` 通过
- Playwright 全量 23 条通过，新增 `markdown-extensions`、`editor-body-preview`、
  `markdown-authoring`（4 条）、`diary-markdown-authoring`
- 导出 HTML 离线验证：Tab 切换与折叠展开可用

### Status

[OK] **Completed**

## Session 4: 修复"点按钮替换正文"的数据丢失

**Date**: 2026-10-27
**Task**: 10-27-firefly-markdown-extensions（追加）
**Branch**: `main`

### 问题

源码模式工具栏与富文本工具栏插入块级模板时，会把当前选区当成"要替换的内容"。
用户先 Ctrl+A 再点按钮，整篇笔记就被模板替换，自动保存 5 秒内落库。

### 修复

- 源码模式 `insertSnippet`：块级模板（提示框 / 代码块 / 代码组 / 块级公式）
  一律把插入点折叠到选区**末尾**，原内容原样保留；只有行内公式 `$…$` 包裹选区。
  块级模板才补前后空行，行内包裹一个字符都不能加。
- 富文本 `insertWysiwygCallout`：由 `replaceSelectionWith` 改为 `tr.insert(selection.to, …)`。
- `insertWysiwygText` 统一了同一套语义，笔记与日记编辑器共用。

### 数据修复

笔记 49 的「## 1. 项目名称」小节与 5 条要点被模板替换，已按 `.tmp/backup-notes/49.json`
逐段还原（保留用户此前对 "禁用" 错别字与结尾 "XX" 的修正）。

### 追加修复：选中内容应被"包起来"，而不是"插到下面"

第一版把块级模板改成"插到选区末尾"：虽然不再丢数据，但用户选中的那段正文
并不会变成提示框，体验仍然不对。正确语义是：

- 有选区 + 块级模板 → 用模板**包裹**选中内容（提示框逐行加 `> `，代码块用 fence 包住）
- 有选区 + 行内模板（`$…$`）→ 原地包裹
- 无选区 → 插入占位模板并选中占位文字

源码模式通过 `snippet.wrap(selected)` 实现，富文本通过
`tr.wrap(range, [{ type: blockQuoteType }])` 再插入标记段实现。

### 验证

- `e2e/markdown-insert-safety.spec.js`（5 条）：全选后逐个点块级模板，断言原正文
  被包进结构；提示框逐行 `>` 形状；行内公式包裹；无选区插入占位；富文本工具栏同路径。
- Playwright 全量 28 条通过；后端 `notes` 89 条通过；`npm run build` 通过。

### Status

[OK] **Completed**

## Session 5: 源码模式改成悬浮工具栏

**Date**: 2026-10-27
**Branch**: `main`

### 背景

源码模式原来是顶部一整条文字按钮（`注意 / 提示 / 重要 / 警告 / 危险 / 带标题代码块 / …`），
与用户期望的"选中正文 → 就地浮出工具栏"不一致；而且一长排按钮挤压编辑区。

### 改动

- 新增 `SourceInsertToolbar.vue`：body teleport 的 `position: fixed` 浮层，
  图标 + 气泡（提示框类型、代码块模板），与富文本模式的悬浮工具条同一套视觉。
- 新增 `textareaCaret.js`：用隐藏镜像 div 复刻 textarea 换行，量选区在视口里的坐标，
  工具栏贴在选区上方（`getTextareaSelectionAnchor`）。
- `MarkdownSourceEditor.vue`：只在"存在非空选区"时浮出；顶部只保留
  「选中正文后会浮出工具栏…」提示、「代码块设置…」与预览开关。
- 新增行内模板：加粗 / 斜体 / 删除线 / 行内代码 / H1-H3 / 引用 / 分割线，
  全部通过 `snippet.wrap(selected)` 或 `wrapSelection` 包裹选区，不替换正文。

### 关键坑

不能用 textarea 的 `blur` 收起浮层：Element Plus 气泡 teleport 到 body，
点类型按钮必然先触发 blur，按钮会在点击瞬间消失。改为 document 级
`pointerdown`，目标在 `.source-floating-toolbar` / `.source-insert-popover` 内则忽略。

### 验证

- `e2e/source-floating-toolbar.spec.js`（5 条）：定位、隐藏、提示框包裹、
  代码块包裹、行内按钮、无选区行为。
- `e2e/markdown-insert-safety.spec.js` 改为走浮层路径。
- Playwright 全量 33 条通过；后端 `notes` 89 条通过；`npm run build` 通过。

### Status

[OK] **Completed**

## Session 6: 只保留富文本，工具条常驻悬浮框，提示框改为切换语义

**Date**: 2026-10-28
**Branch**: `main`

### 需求

1. 去掉「富文本 / 源码」切换，只保留富文本页面。
2. 插入按钮全部放进选区悬浮工具条。
3. 提示框再次点击同一类型 = 取消，而不是嵌套；点其它类型 = 改类型。

### 改动

- 删除源码模式：`MarkdownSourceEditor.vue`、`SourceInsertToolbar.vue`、`textareaCaret.js`、
  `markdownSnippets.js` 及对应 e2e；`NoteEditHeader` 去掉模式切换；`NoteEditView` 清理
  `editorMode` 分支。
- `wysiwygBlocks.js` 的 `applyWysiwygCallout` 实现三态：
  - 选区在同类提示框内 → `unwrapCallout`（删标记段 + lift 出引用块）
  - 选区在异类提示框内 → `retypeCallout`（只替换标记段文字）
  - 其它 → 包裹选中 blocks / 插入占位提示框
- `FloatingFormatToolbar.vue` 增加提示框气泡（当前类型标「取消」）、代码块设置、行内 / 块级公式。
- 修 `findCalloutAncestor` 与 `getSelectedCodeBlockInfo`：`Ctrl+A` 时 `$from` 在文档开头，
  必须先看祖先链、再用 `doc.nodesBetween` 兜底，否则"全选后点按钮"会静默无反应。
- e2e 改用稳定的 `data-action` 定位按钮（aria-label 会随状态变化）。

### 验证

- `e2e/markdown-authoring.spec.js`（5 条）：包裹、同类取消、异类改类型、代码块设置、固定工具栏。
- Playwright 全量 24 条 × 2 轮通过；后端 `notes` 89 条通过；`npm run build` 通过。

### Status

[OK] **Completed**

## Session 7: 顶部固定工具栏成为唯一入口，去掉选区悬浮框

**Date**: 2026-10-29
**Branch**: `main`

### 需求

「在顶部固定一排工具栏」——编辑器正文上方常驻一排按钮，滚动时吸顶；用户选择彻底去掉
「选中文字才浮出」的悬浮框，只保留顶部这一排。

### 改动

- 删除 `FloatingFormatToolbar.vue` 与 `SideTableToolbar.vue`：插入动作全部搬到
  `FixedEditorToolbar.vue`，新增提示框气泡（当前类型标「取消」）、代码块设置、行内/块级公式。
- `editorSettings.js` 去掉 `EDITOR_TOOLBAR_MODES` 与 `toolbarMode`；`SettingsPanel.vue`
  删掉「正文工具栏」切换项，老用户 localStorage 里的 `toolbarMode` 被直接忽略。
- `NoteEditView.vue` / `DiaryEditView.vue` 删除整块悬浮工具条逻辑（定位、隐藏、选区矩形、
  表格选择器），只保留 `updateFixedToolbarSnapshot` + `activeCalloutType` 的轻量同步。
- `FixedEditorToolbar.vue` 增加稳定的 `data-action`（`callout` / `code-block` /
  `code-block-options` / `block-quote` / `bold`…），避免 aria-label 随状态变化导致测试脆弱。

### 关键坑

`.edit-page { overflow-x: hidden }` 会把 `overflow-y` 隐式变成 `auto`，这一层就成了滚动容器，
`position: sticky` 的工具栏随之滚走（实测滚动 1400px 后 `top = -804`）。改用
`overflow-x: clip` 后工具栏稳定停在 `top = 12px`。

### 验证

- Playwright 全量 26 条通过；`npm run test:unit` 108 条通过；后端 `notes` 89 条通过；
  `npm run build` 通过。
- 真实环境（笔记 54）截图确认：滚动时工具栏吸顶、提示框气泡标出当前类型。

### Status

[OK] **Completed**

## Session 8: 工具栏视觉重做（吸顶状态 + 去掉鼠标跟随标签）

**Date**: 2026-10-29
**Branch**: `main`

### 反馈

「UI 太丑了，改一改，尤其是向下滑动时」。旧实现是一条通栏横条：上下都有边框、
半透明背景 + 模糊，滑动时正文从缝隙里透出来，而且工具栏本身是全宽通栏，和下面的
圆角正文卡片对不齐。

### 改动

- 工具栏改成两态：
  - 未滚动：无边框 / 无背景 / 无阴影，和正文浑然一体；
  - 吸顶（`.is-pinned`）：贴视口顶部，`--overlay-background` 不透明底 + 细下边框 +
    柔和投影，正文从底下平滑滑过。
- 用 `.fixed-toolbar-sentinel` + `IntersectionObserver` 判断吸顶，不用 scroll 监听
  （不用节流，嵌套滚动容器里也准）。
- 按钮从 34px 收到 30px、间距 6→2、分割线 26→18px，整条更紧凑；
  标题按钮改用无衬线小字号，行内代码/公式字形也重新调了大小。
- 图标的 hover / active 改成纯色块（去掉边框 + 底部内阴影那种"按钮框"感）。
- 提示框气泡加了「提示框」小标题，选项内边距收紧。
- 删掉鼠标跟随的 `hover-block-hint`「正文/引用/代码块」小标签 —— 它在滚动和
  移动鼠标时一直闪，是"滑动时很脏"的主要来源；`EditorTableOverlays.vue` 里对应的
  props / 模板 / CSS 一并移除。

### 验证

- Playwright 全量 27 条通过（新增「吸顶后变不透明页眉」用例，含背景 alpha 断言）。
- `npm run test:unit` 108 条通过；`npm run build` 通过。

### Status

[OK] **Completed**
