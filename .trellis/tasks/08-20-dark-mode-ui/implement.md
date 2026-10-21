# 黑夜模式 UI 实施计划

## Change Boundary

- 最小行为差距：黑夜模式已能切换，但大量组件仍使用固定浅色表面，导致界面看起来仍像白天模式且局部可读性不足。
- 根因位置：全局主题变量不完整，以及各 SFC 后置视觉规则中的固定浅色、边框和阴影值。
- 预计修改：`src/style.css`、工作区共享组件、主要 route views、编辑器共享组件、`styles/markdown.css` 和聚焦 Playwright 测试。
- 明确不做：不改模板层级、业务逻辑、接口、路由、资源图片和主题存储契约。
- 行为保护：修改前后运行同一生产构建和现有 E2E；新增测试只验证主题行为与可观察样式，不依赖内部实现。

## Implementation Checklist

1. [x] 建立 light/dark 语义表面、控件、代码和深度 token；修正 body 与 Element Plus 的暗色基础。
2. [x] 迁移工作区侧栏、设置和全局搜索，确保导航/弹层无浅色孤岛。
3. [x] 迁移首页、笔记列表/详情和日记阅读主流程，保留现有布局与状态色。
4. [x] 迁移笔记/日记编辑器、Toast UI、Markdown 和编辑器浮层。
5. [x] 迁移知识对话、RAG/Token、标签、图片、上传、回收站等辅助路由。
6. [x] 增加主题切换、刷新持久化和代表性暗色表面的 Playwright 覆盖。
7. [x] 运行生产构建、聚焦 E2E、现有 E2E 与对比度检查。
8. [x] 生成桌面/移动暗色截图并逐页检查白色孤岛、对比度、溢出和交互状态；发现问题后迭代。
9. [x] 复查白天模式与 Git 差异，只保留主题相关改动。

## Validation Commands

从 `frontend/moonsbirdnotrs_vue/` 运行：

```powershell
npm run build
$env:PLAYWRIGHT_CHANNEL='msedge'; npm run test:e2e
```

补充执行聚焦的暗色模式 spec、CSS token 对比度脚本，以及 Playwright 桌面/移动截图检查。

## Risky Files and Rollback Points

- `src/style.css`：全局影响最大；先验证 Element Plus 和 body，再迁移页面。
- `views/NoteListView.vue`、`views/DiaryView.vue`：样式量大且存在后置覆盖，按选择器区块分段验证。
- `views/NoteEditView.vue`、`views/DiaryEditView.vue` 和 `editor/components/`：Toast UI/ProseMirror 内部 DOM 需要聚焦 E2E。
- `styles/markdown.css`、`views/NoteDetailView.vue`：阅读器与编辑器共享内容样式，必须同时检查表格、代码与分割线。

每完成一个用户路径就保留可独立检查的差异；若出现回归，先撤回对应路径的主题替换，不回滚全局已验证 token。
