# PRD: Firefly 风格 Markdown 扩展语法

## 背景

MoonBirdNotes 的阅读端使用 toast-ui Viewer 在浏览器内渲染 Markdown，后端则用 python-markdown 生成
`rendered_html` 供上传预览、版本预览和导出 HTML 使用。两条链路都只支持 GFM 基础语法，
Firefly 博客中常见的提醒框、代码块参数与 Tab 代码组在这里全部失效。

## 目标

把 Firefly 的扩展语法移植进来，并保证**阅读端、编辑器预览、导出 HTML** 三处外观一致：

1. 提醒框：GitHub / Obsidian 全类型 + 自定义标题，兼容 `> [!TYPE]` 与 `:::type[标题]`。
2. 代码块：`title`、行高亮 `{1,3-5}`、`ins` / `del` / `"文本"` / `/正则/`、`showLineNumbers`、
   `startLineNumber`、`collapse`、`wrap=false`、`frame`、`diff` 增删着色。
3. 代码组：`::: code-group labels=[…]` 多代码块合并成标签页。

## 非目标

Mermaid、PlantUML、GitHub 仓库卡片、`[[Wiki 双链]]`、`[grid]` 图片网格、`:spoiler[]`。

## 约束

- 不改变既有安全契约：后端 `rendered_html` 仍由 Bleach 净化；客户端生成的 HTML 仍先净化后 `v-html`。
- 不引入新的运行时依赖（Mermaid 等排除后无需新增包）。
- 普通代码块的既有 HTML 形状（`<pre><code class="language-x">`）必须保持不变。

## 验收标准

- [x] `python manage.py test notes` 通过，新增 13 条扩展语法与 XSS 用例。
- [x] `npm run build` 通过。
- [x] Playwright：`e2e/markdown-extensions.spec.js`、`e2e/editor-body-preview.spec.js` 通过，全量 18 条 E2E 通过。
- [x] 导出 HTML 离线打开时，Tab 切换与折叠展开可用。
- [x] 未闭合的 `:::` 容器按普通文本回退，不吞掉后文。

## 第二轮：写作入口

第一轮只解决了"看得见"，写的时候没有输入入口。第二轮补齐：

- [x] 编辑器「富文本 / 源码」模式切换，两侧共用同一份 Markdown
- [x] 富文本内即时预览：提示框配色与标题、代码块参数信息栏、`:::` 容器行弱化
- [x] 修复工具栏「插入提示框」：写入真正的引用块，而不是 `>[!NOTE]` 纯文本
- [x] 源码模式左右分栏 + 实时预览 + 模板工具栏
- [x] 代码块参数面板（title / 行标记 / 行号 / 折叠 / 框架）
- [x] 日记编辑器同样接入提示框插入与即时预览
- [x] Playwright 新增 `markdown-authoring.spec.js`（4 条）与 `diary-markdown-authoring.spec.js`；全量 23 条通过

实现细节见 [authoring.md](./authoring.md)。

## 技术设计

见 [design.md](./design.md)。
