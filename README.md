# MoonBirdNotes

## 项目简介

MoonBirdNotes 是一个面向个人使用的在线 Markdown 知识库系统。
它主要用于统一管理个人文章、学习笔记和日记内容，帮助用户完成笔记的上传、整理、查看、编辑、删除与长期保存。

当前系统以前后端分离方式实现，前期仅支持管理员本人登录使用，不开放用户注册，所有内容默认私密保存。
后续可以继续扩展智能问答、导出备份以及多用户能力。

## 技术栈

- 后端：Django
- 接口：Django REST Framework
- 认证：JWT
- 数据库：MySQL
- 向量数据库：Qdrant
- 前端：Vue 3
- UI 组件：Element Plus
- 构建工具：Vite

## 当前已实现功能

- 管理员登录
- 上传 Markdown 笔记
- 自动保存原始 Markdown 文件
- 自动渲染 Markdown 为 HTML
- 标签必填，且每篇笔记最多四个标签
- 支持选择已有标签或创建新标签
- 笔记列表分页展示
- 列表展示标题、摘要、字数、标签、时间信息
- 笔记列表支持按置顶/创建时间、更新时间、重要程度或标题排序
- 支持置顶重要笔记，列表优先展示置顶内容
- 支持为笔记设置 0 到 5 星重要程度，支持半星
- 全局搜索支持在任意工作台页面检索标题、正文、标签或文件名
- 笔记详情页展示完整内容
- 单篇笔记支持导出为 Markdown 或 HTML 文件
- 笔记列表支持批量选择、批量修改标签、批量导出和移入回收站
- 在线编辑笔记标题、正文和标签
- 编辑器支持图片上传和粘贴，并生成 Markdown 图片引用
- 图片管理页支持按笔记整理、上传、复制引用和删除图片
- 偏好设置支持主题模式、自动保存开关/间隔和正文字号
- 编辑历史版本记录与版本回退
- 无实际修改时不生成新的历史版本
- 笔记软删除
- 回收站恢复笔记
- 回收站支持批量恢复笔记
- 回收站彻底删除笔记
- 回收站支持批量彻底删除笔记
- 回收站 30 天自动清理
- 左侧功能栏收起与展开
- Token 用量页汇总最近 100 次 Knowledge Agent 运行，并可跳转查看对应 RAG 轨迹

## 历史版本规则

在线编辑笔记时，系统会在真正发生修改之前自动保存修改前的内容为历史版本。
每篇笔记最多保留最近 5 个历史版本。
如果用户保存时标题、正文和标签都没有变化，则不会生成新的历史版本，也不会刷新更新时间。

## 管理员账号与密码

系统会在数据库迁移完成后自动检查默认管理员账号。
如果 `ADMIN_USERNAME` 对应的账号不存在，会使用 `.env` 中的 `ADMIN_PASSWORD` 创建初始管理员。

如果该管理员账号已经存在，后续修改 `.env` 里的 `ADMIN_PASSWORD` 不会同步重置数据库中的登录密码。
这是为了避免每次执行 `migrate` 或重启服务时意外覆盖你已经修改过的密码。

需要修改管理员密码时，请使用 Django 的正式改密入口：

```bash
python manage.py changepassword <ADMIN_USERNAME>
```

也可以登录 Django admin 后台，在用户管理里修改密码。

## Qdrant 向量服务

RAG 使用独立 Qdrant 服务，容器只绑定本机 `6333/6334` 端口，索引数据保存在 Docker 命名卷中。

启动并初始化：

```bash
docker compose up -d qdrant
cd backend
python manage.py initialize_qdrant
```

初始化命令会幂等创建或校验 `moonbird_note_chunks_bge_m3_v1`，不会删除已有 Point。停止容器可执行：

```bash
docker compose stop qdrant
```

Dense 检索默认使用 `RAG_DENSE_SCORE_THRESHOLD=0.50` 过滤弱相关候选。该数值通过仓库内置真实评测集针对当前 BGE-M3 Embedding 版本校准；更换模型、Embedding 输入模板或版本后，必须重新运行 `evaluate_rag` 校准，不能直接沿用。

最终验收使用 `python manage.py evaluate_rag --with-agent --acceptance --admin-username <管理员账号>`。安全门禁要求来源准确率 100%、无依据回答率 0%、无资料拒答率 100%，且不允许检索、Agent 或语义通道失败；生成质量门禁按当前 39 条可回答样本校准为成功率、联合成功率和关键词覆盖率至少 90%，误拒答率最多 10%。这允许最多 3 条非确定性表达波动，但 4 条失败仍会阻断验收。

## Agent Token 追踪

DeepSeek 响应中的 `usage` 会随 Knowledge Agent 的查询改写、工具循环、最终 JSON 修复和拒答复核一并聚合到 API 响应的 `llm_usage` 字段，以及运行轨迹和后端完成日志中。仅记录模型请求数、输入 token、输出 token 和总 token，不记录价格、货币、问题、回答、笔记正文、Provider 原始响应或密钥。如果 Provider 没有为全部请求返回有效 usage，`usage_status` 会是 `partial` 或 `unavailable`，聚合 token 为 `null`，不会伪造为零。`evaluate_rag --with-agent` 的回答报告还会输出 `p95_answer_ms` 和对应的 `llm_*` token 汇总指标。

每次 Agent 请求收尾时会按 `run_id` 幂等写入独立的 `AgentTokenUsage` 账本。该记录只关联当前用户，不依赖会话或运行轨迹的生命周期，因此删除和定期清理历史会话不会删除 Token 用量；页面默认汇总最近 100 条账本记录。

所有普通笔记和日记默认允许云端 AI 索引，现有 Note 在迁移后也会统一设置为 `ai_indexing_enabled=true`。迁移本身只修改授权状态，不上传正文；新建或后续修改的 Note 会排队等待 Worker 处理，现有 Note 可通过下方重建命令统一向量化。若某篇内容不应发送到硅基流动，可在 Django Admin 中逐篇关闭该字段。

保存已授权 Note 后只会在 MySQL 中排队，不会在 HTTP 请求内等待 Embedding。处理已到期后台任务：

```bash
cd backend
python manage.py process_rag_jobs --max-jobs 100
```

第一版命令处理完当前已经到期的任务后退出；部署时应由计划任务或进程管理器周期调用。

从 MySQL 重建 RAG 派生索引：

```bash
# 全部范围；未授权和软删除内容只清理残留索引，不上传
python manage.py rebuild_rag_index

# 只处理普通笔记或日记
python manage.py rebuild_rag_index --scope note
python manage.py rebuild_rag_index --scope diary

# 只处理指定 Note
python manage.py rebuild_rag_index --note-id 15

# 显式删除并重建当前 Collection 后恢复全部已授权内容
python manage.py rebuild_rag_index --recreate-collection
```

`--recreate-collection` 只允许全范围重建。执行前应停止其他索引 Worker，避免同时写入 Collection。

## 当前页面

系统当前已经提供以下页面：

- 登录页
- 首页
- 笔记列表页
- 笔记上传页
- 笔记详情页
- 笔记编辑页
- 图片管理页
- 回收站页

## 项目目录结构

```text
MoonBirdNotes/
├─ backend/     Django 后端
├─ frontend/    Vue 前端
├─ compose.yaml Qdrant 独立服务
├─ Function.md  功能说明
├─ TODO.md      开发进度记录
└─ README.md    项目说明
```

## 当前待继续完善的方向

- Markdown 渲染样式继续优化
- 搜索排序与高级筛选
- 首页接入真实笔记数据
- 智能问答功能
- 多用户能力预留
