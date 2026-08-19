# RAGAgent 第 14 步：Knowledge Agent 只读工具

日期：2026-07-14

## 本次完成的范围

本次完成 RAG Agent 实际执行顺序的第 14 步：实现 Knowledge Agent 可以调用的六个确定性只读工具，以及严格 Schema、当前管理员权限、文本预算、结构化错误和安全执行日志。

工具列表固定为：

```text
search_notes
get_parent_chunks
get_note
get_note_section
get_diary_by_date
list_tags
```

本步没有实现第 15 步的 Agent Prompt、LLM 工具循环或最多四步编排，也没有新增第 16 步 HTTP API。

## 分层设计

### RAG 公开只读服务

新增 `rag.knowledge`，集中读取并校验当前 MySQL 真实数据：

- `read_current_parent_chunks`
- `read_note`
- `read_note_section`
- `read_diary_by_date`
- `list_knowledge_tags`

这些函数从 `rag.services` 公开。ORM 与当前来源校验留在 RAG 领域层，`agent.tools` 不直接导入 Note Model、Qdrant Client 或任意数据库接口。

### Agent 工具层

新增 `agent.tools.knowledge`，只负责：

- 固定只读允许列表。
- JSON Schema。
- 当前 Django 用户权限。
- 参数到公开 RAG 服务的确定性映射。
- 文本预算。
- 结构化结果与安全日志。

工具层不存在任意 ORM、SQL、HTTP、Shell、Python、文件读写或环境变量入口。

## 严格 JSON Schema

每个工具发布标准函数定义：

```json
{
  "type": "function",
  "function": {
    "name": "...",
    "description": "...",
    "parameters": {
      "type": "object",
      "properties": {},
      "required": [],
      "additionalProperties": false
    },
    "strict": true
  }
}
```

运行时不会只依赖模型遵守 Schema，而是再次验证：

- 必填和额外字段。
- 字符串、整数、数组、布尔和 null 类型。
- 最小/最大长度与数量。
- enum。
- 数组去重。
- 日期、UUID 和 SHA-256 格式。
- Top K 数值范围。

任何额外参数都返回 `invalid_arguments`，不能透传到业务函数。

## 当前用户与能力权限

`execute_knowledge_tool` 要求：

- `user.is_authenticated=true`
- `user.is_active=true`
- `user.is_staff=true`

匿名用户返回 `authentication_required`，普通用户或停用管理员返回 `permission_denied`。未知工具返回 `tool_not_allowed`。

允许列表只有六个只读工具，`KNOWLEDGE_WRITE_TOOL_NAMES=()`。即使笔记正文包含“忽略之前指令”或“删除所有笔记”，正文仍只作为返回数据，不能注册工具或触发写行为。

## 六个工具的行为

### search_notes

调用第 13 步 `retrieve`，支持：

- 自然语言或精确关键词。
- `note/diary` 类型。
- 普通笔记标签。
- 日记日期范围。
- Dense、Keyword 和最终父片段 Top K。

最终 `top_k` 最大为 10，Dense/Keyword 候选最大为 100。搜索结果只返回来源、分数、行号和命中摘要，主动移除完整父片段 `content`；需要上下文时必须显式调用 `get_parent_chunks`。

### get_parent_chunks

- 一次最多读取 10 个 UUID 父片段。
- 保持调用方 ID 顺序。
- 只返回当前完成索引、当前 Embedding 版本、当前 `source_hash`、未删除且允许 AI 索引的父片段。
- 部分失效时返回 `missing_parent_ids`；全部失效时返回 `parent_chunks_not_found`。

### get_note

- 只读取当前普通笔记，不把日记底层 Note 当成普通笔记。
- 排除回收站和关闭 AI 索引的内容。
- 返回当前 Markdown、源文件名、标签、更新时间和 `source_hash`。
- 可传入搜索结果的 `source_hash`；不一致时返回 `source_hash_mismatch`。

### get_note_section

- 接收 Note ID 和完整标题路径。
- 从当前 Markdown 重新解析 ATX/Setext 与嵌套标题。
- 返回该标题直到下一个同级或更高级标题前的完整原文和行号。
- 区分章节不存在与重复标题路径导致的歧义。
- 支持当前 `source_hash` 前置校验。

### get_diary_by_date

- 按严格 `YYYY-MM-DD` 日期读取。
- 返回日记标题、摘要、心情、天气、当前 Markdown 和来源哈希。
- 排除回收站和关闭 AI 索引的日记。

### list_tags

- 最多返回 100 个标签。
- 支持名称包含过滤。
- 只统计未删除、允许 AI 索引的普通笔记。
- 历史脏数据中的日记标签、回收站标签和关闭 AI 索引内容的标签不会出现。

## 返回文本硬预算

每次工具成功结果的全部字符串值最多 12,000 个字符：

- 优先保留 Note ID、Parent ID、类型、标题路径、来源哈希和错误状态等结构字段。
- 正文、Markdown、摘要、心情、天气和命中摘要在剩余预算中分配。
- 多个父片段会公平分配可用正文预算，避免第一个长片段挤空全部后续片段。
- 截断结果设置 `meta.truncated=true`。
- `meta.text_characters` 和 `meta.max_text_characters` 供后续 Agent 循环二次检查。

## 结构化结果与错误

统一结果：

```json
{
  "ok": true,
  "tool_name": "get_note",
  "data": {},
  "error": null,
  "meta": {
    "duration_ms": 1.2,
    "result_count": 1,
    "text_characters": 100,
    "max_text_characters": 12000,
    "truncated": false,
    "read_only": true,
    "content_is_untrusted": true
  }
}
```

错误类别明确区分：

- `unauthorized`
- `forbidden`
- `invalid_request`
- `not_found`
- `stale_source`
- `conflict`
- `system`

未知内部异常统一返回 `tool_system_error`，不泄露数据库错误、路径、Provider 响应或密钥。

## 安全日志

每次执行记录：

- 工具名称。
- 当前用户 ID。
- 成功或失败状态。
- 安全错误码。
- 耗时。
- 结果数量。
- 是否截断。
- 参数键、查询长度、父片段数量、标题深度和 Top K 等摘要。

日志不记录完整查询、标题路径内容、笔记正文、日记正文、API Key 或内部异常文本。本步使用结构化应用日志；持久化 Agent Run/Tool Call 审计模型留到实际 Agent 运行与 API 阶段统一建立，避免在没有 `run_id` 前创建孤立审计记录。

## 为什么这样做

- Tool Calling Schema 不能代替后端校验，模型仍可能生成额外字段或错误类型。
- Agent 工具层不直接 ORM，能阻止模型通过工具参数拼接任意数据库查询。
- 搜索与读取拆开可以限制一次搜索返回的正文量，并让来源读取成为显式步骤。
- 所有最终内容都从 MySQL 当前来源读取或校验，旧 Qdrant Point 不能绕过来源哈希。
- 固定允许列表和空写工具列表能让提示词注入无法扩大权限。
- 统一文本预算防止单篇长笔记或多个父片段撑爆后续模型上下文。
- 按 `karpathy-guidelines` 保持本步边界，没有提前实现 LLM、API、写工具或任意执行能力。

## 代码注释

新增代码对严格参数拒绝、正文优先截断、搜索摘要边界、旧父片段过滤、章节范围、异常脱敏和日志摘要补充了中文注释。

## 自动化测试

第 14 步新增 19 个针对性测试，覆盖：

- 六个只读工具和空写工具列表。
- 每个函数定义的 `strict=true` 与 `additionalProperties=false`。
- 运行时类型、范围、日期、UUID、额外参数和 Top K 校验。
- 匿名、普通、停用管理员与当前管理员。
- 当前父片段顺序、部分丢失、旧来源过滤。
- 普通笔记/日记边界、回收站和 AI 索引授权。
- 当前完整笔记与来源哈希冲突。
- 嵌套章节、章节不存在与重复路径歧义。
- 日记日期读取。
- 普通笔记标签隔离与计数。
- 搜索参数映射和完整正文移除。
- 手动六工具完整读取流程。
- 找不到、来源过期和系统异常分类。
- 12,000字符总预算和多片段公平分配。
- 日志不包含完整查询或正文。
- 提示词注入正文不能扩大允许列表。
- Agent 工具模块不存在直接 ORM 或 Qdrant 访问。

针对性测试结果：19 个全部通过。

最终验证结果：

- `python manage.py test --noinput`：286 个测试全部通过。
- `python manage.py makemigrations --check --dry-run`：通过，无模型变更遗漏。
- `python manage.py check`：通过，无系统检查问题。
- `python -m pip check`：通过，无损坏依赖。
- Python 编译检查：`agent` 与 `rag` 全部通过。
- `git diff --check`：通过。
- 第 14 步文件与 Git diff 疑似密钥匹配数：0。
- 工具验证后真实数据保持不变：19 篇 Note、18 个完成状态、39 个父片段、151 个 Qdrant Point、0 个活动任务。

## 真实环境验证

使用当前管理员和不含私人内容的合成查询，手动依次执行六个工具。验证输出只打印布尔值和数量，不打印标题、标签、日期或正文。

结果：

- `search_notes`：成功。
- `get_parent_chunks`：成功。
- `get_note`：成功。
- `get_note_section`：成功。
- `get_diary_by_date`：成功。
- `list_tags`：成功。
- 六个结果均为 `read_only=true`。
- 六个结果均未超过 12,000 字符预算。

## 未完成事项与下一步

下一步是第 15 步：实现 Knowledge Agent 受控工具循环、系统指令、最多四步限制、超时和基于来源的固定回答结构。主对话模型的本地或云端方案仍需按第一步只读边界单独确认；在确认前不能把父片段或完整笔记正文发送给未经批准的第三方模型。
