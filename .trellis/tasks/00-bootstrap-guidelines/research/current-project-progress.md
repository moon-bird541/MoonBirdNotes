# MoonBirdNotes 当前项目基线

> 快照日期：2026-08-16  
> 用途：为 Trellis 规范初始化任务保存当前项目能力、工作区状态和后续判断依据。本文记录事实，不替代产品路线图。

## 1. 证据来源

- 当前工作树中的 `README.md`、`Function.md`、`PRODUCT_RULES.md` 和 `FRONTEND_DESIGN_GUIDELINES.md`。
- `backend/`、`frontend/moonsbirdnotrs_vue/` 的当前源码、测试、迁移与配置。
- `agent开发/开发记录/` 中 2026-07-13 至 2026-07-16 的 RAG / Agent 开发记录。
- Git `HEAD` 中已被当前工作区删除的 `TODO.md`、`CODE_LEARNINGS.md` 与安全审查文档。旧文档只作为历史线索；与当前代码冲突时，以当前代码和测试为准。

## 2. 当前架构

- 后端：Django 6 + Django REST Framework + Simple JWT，MySQL 持久化。
- 前端：Vue 3 + Vite + Element Plus，页面与后端通过 `/api` 交互。
- 知识检索：MySQL 关键词检索、SiliconFlow BGE-M3 Embedding 与 Qdrant Dense 检索组成混合检索。
- Knowledge Agent：DeepSeek 兼容 LLM 适配层、只读知识工具、会话记忆、运行轨迹与 Token 用量账本。
- 部署：后端与前端 Dockerfile、Compose 中的 Qdrant 服务、前端 Caddy 配置。

## 3. 已实现能力

### 笔记与日记

- 管理员登录、Markdown 上传、标签、分页/搜索/排序、置顶与重要程度。
- 笔记详情、所见即所得编辑、图片管理、自动保存、版本快照与恢复。
- 批量标签、批量导出、软删除、回收站恢复/彻底删除与定期清理。
- 日记查看与编辑、日期切换、心情/天气/摘要、统一编辑器偏好。
- 表格合并/拆分、列宽与表格宽高持久化等编辑器能力。

### 安全与配置

- Markdown / HTML 安全净化与存量数据重净化迁移。
- Secret、数据库、主机、CSRF、缓存、LLM、Embedding 与 Qdrant 参数通过环境变量配置。
- 登录限流、统一失败提示、生产环境 Cookie / HSTS / Frame 等安全项。
- Agent 保持只读知识边界；轨迹不保存问题、正文、完整回答、JWT 或密钥。

### RAG 与 Knowledge Agent

- Markdown 结构解析、父/子分块、Embedding、Qdrant 写入与幂等初始化。
- 后台索引任务、失败重试、租约、删除任务、全量/局部重建和状态命令。
- 关键词 + Dense 混合检索、来源回链、资料不足拒答与真实评测集。
- Knowledge Agent API、查询重写、最近六轮上下文、滚动摘要和历史会话持久化。
- 运行轨迹 Cache + MySQL 回源持久化、独立链路诊断页和最近运行列表。
- LLM Token 用量按 `run_id` 幂等入账，并提供可筛选、分页及全量筛选汇总页面；运行轨迹列表单独限制为最近 100 次。

### 前端体验

- 首页真实统计、全局搜索、设置面板与统一工作区侧栏。
- 知识对话、历史会话、来源跳转、运行轨迹与 Token 用量页面。
- Agent 回答使用净化后的 Markdown，提供清晰标题、列表、浅色代码块和复制代码操作。
- 13 个业务页面及公共弹层已做响应式与浏览器缩放兜底。

## 4. 当前工作区状态

- 分支：`main`。
- 本次 Trellis 会话开始时共有 68 项未提交变化；这些变化属于用户现有工作，不在本任务中回滚或提交。
- 主要未提交范围：`backend/agent/`、`backend/rag/`、相关模型迁移与配置；知识对话/轨迹/Token 前端页面；Docker / Compose；前端视觉与响应式调整；Trellis 初始化。
- `CODE_LEARNINGS.md`、`SECURITY_AND_REVIEW.md`、`SECURITY_FIX_PLAN.md`、`TODO.md`、`UNSAFE_HTML_TAGS.md` 等旧文档已在当前索引中删除。本任务不恢复这些文件，只把仍然有效且有代码证据的规则迁入 Trellis。
- `00-bootstrap-guidelines` 的 `task.json` 状态为 `in_progress`。由于当前宿主没有可持久化的 `TRELLIS_CONTEXT_ID`，`task.py current` 不显示会话指针；本次仍以该任务为活动上下文。

## 5. 已知文档偏差

- 旧 `TODO.md` 把“AI 智能问答”列为未完成，但当前代码和开发记录已经实现 Knowledge Agent、RAG、会话记忆、轨迹和 Token 账本。
- 当前 `README.md` 的“当前页面”和“待继续完善方向”仍把部分已完成能力写成待办，例如智能问答、首页真实数据；后续应单独校正文档，不能把这些条目直接当作当前路线图。
- 当前 `README.md` 还把 Qdrant 写成绑定本机 `6333/6334` 端口，但 `compose.yaml` 未声明宿主机端口映射；Token 页面也并非固定汇总最近 100 条，而是默认每页 20 条、每页最多 100 条，并对筛选后的全部账本做汇总。这些属于范围外文档偏差，不应覆盖当前配置和 API 行为。
- 旧 `TODO.md` 仍有收藏、分类/文件夹、PDF 导出、批量导入、版本 diff、数学公式、Mermaid、多用户、分享、PWA、备份恢复等候选项，但尚未确认优先级，不能自动视为承诺范围。

## 6. 最近验证证据

以下来自 2026-07-16 的开发记录，不等同于本次会话重新运行：

- 后端全量测试：354 项通过。
- Django 系统检查通过，迁移一致性检查无额外变更，Python 依赖检查通过。
- 前端 Vite 生产构建通过，共转换 1747 个模块。
- RAG / Agent 专项测试在不同步骤中通过，最终验收与轨迹持久化均有独立记录。

本次 Trellis 初始化已另外验证规范索引、占位符、引用路径和必要的项目检查；结果见下方本次会话验证记录。

### 2026-08-16 本次会话验证

- 使用项目本地 `.venv` 运行 `python manage.py check`：通过，0 个问题。
- 运行 `python manage.py makemigrations --check --dry-run`：通过，无模型变更。
- 前一检查代理运行后端全量测试：396 项通过；本次文档复核没有重复运行该昂贵套件。
- 前一检查代理运行 `npm run build`：通过。
- 前一检查代理使用 Edge 运行 Playwright：6 项中 5 项通过，1 项失败。失败位于 `e2e/knowledge-source-navigation.spec.js` 的 `getByText('1,200')`：Token 汇总区和明细行各渲染一次 `1,200`，严格模式得到两个匹配。产品行为没有因此失败，但该测试定位器仍需在测试范围内改为区域/行内定位后复验。
- 本次规范检查确认：backend 6 份、frontend 7 份指南均被各自索引完整引用；95 个带目录的源码路径引用全部存在；未发现空标题、模板占位、失效 Markdown 链接或 UTF-8 replacement character。

## 7. 本任务完成条件

- 后端与前端 Trellis 规范均以当前源码、测试和项目文档为证据。
- 索引与文件集合一致，不保留模板占位或泛化框架建议。
- 规范覆盖当前配置、安全、数据、错误、状态、组件、测试和跨层契约。
- 本基线快照与开发日志能区分“已实现”“历史验证”“未确认候选项”。
