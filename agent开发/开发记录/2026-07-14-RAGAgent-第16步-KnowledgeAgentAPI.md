# RAGAgent 第 16 步：Knowledge Agent API

日期：2026-07-14

## 本次完成的范围

本次完成 RAG Agent 实际执行顺序的第 16 步，对外提供第一版受保护接口：

```text
POST /api/agent/knowledge/chat/
```

接口复用第 15 步的只读 Knowledge Agent，新增 HTTP 请求校验、管理员鉴权、频率限制、安全错误契约、运行标识和结构化指标日志。本步没有加入 SSE、长期对话记忆、会话持久化、Agent 运行数据库表或任何写工具。

## 请求与响应契约

请求支持：

```json
{
  "message": "积分校验接口怎么工作？",
  "filters": {
    "types": ["note", "diary"],
    "tags": ["后端"],
    "date_from": "2026-01-01",
    "date_to": "2026-07-14"
  },
  "session_id": "可选 UUID"
}
```

成功响应只包含：

```json
{
  "answer": "……",
  "sources": [],
  "insufficient_context": false,
  "run_id": "每次请求唯一的 UUID"
}
```

`tool_steps`、内部异常、模型配置和调试字段不会返回客户端。`session_id` 第一版只校验 UUID 并记录是否提供，不读取历史消息、不保存会话，也不会传给 Knowledge Agent。

## 严格输入校验

新增 `KnowledgeChatRequestSerializer` 和嵌套过滤器序列化器：

- `message` 必填、去除首尾空白，并复用 `AGENT_KNOWLEDGE_MAX_INPUT_CHARS` 字符上限。
- `message` 和标签必须是 JSON 字符串，拒绝 DRF 把数字隐式转换为字符串。
- `filters` 只能包含 `types`、`tags`、`date_from`、`date_to`。
- `types` 只能使用 `note`、`diary`，并限制数量和重复值。
- 标签限制单项长度、总数量和重复值。
- 日期必须是 ISO 日期，且结束日期不能早于开始日期。
- 顶层、过滤器中的任何额外字段都会被拒绝，不能被静默忽略。
- `session_id` 必须是合法 UUID。

为什么这样做：HTTP 边界先拒绝无效类型和未知字段，可以避免参数在进入 Agent 后发生歧义；同时 Agent 内部仍保留第二层校验，形成纵深防护。

## JWT、管理员权限与 CSRF

视图继续使用项目全局的 `CookieJWTAuthentication`，并设置 DRF `IsAdminUser`：

- 未登录请求返回 `401 authentication_required`。
- 已登录普通用户返回 `403 permission_denied`。
- Cookie JWT 的 POST 请求继续要求正确 CSRF Token。
- 管理员也可以沿用现有 Bearer JWT 兼容入口。
- View 将当前 `request.user` 原样传给 Knowledge Agent，Agent 和工具层仍会再次校验权限。

为什么这样做：复用现有认证链可以保持登录、刷新、Cookie 和 CSRF 策略一致，避免为 Agent 建立第二套身份体系。

## 按用户频率限制

新增 `KnowledgeChatRateThrottle`，默认配置：

```env
AGENT_KNOWLEDGE_CHAT_RATE=10/minute
```

限流缓存键使用管理员用户 ID，不同管理员额度相互独立。匿名请求先被权限类拒绝，不占用已登录用户的调用额度。生产环境继续依赖项目现有共享缓存配置，避免多进程分别计数。

为什么这样做：Knowledge Agent 会调用 DeepSeek、Embedding 和 Qdrant，单次成本明显高于普通 CRUD；按账号限流比按 IP 更符合管理员接口的身份边界，也不会让共享出口 IP 下的管理员互相影响。

## run_id、session_id 与运行日志

每次 HTTP 请求在权限检查前生成新的 UUID `run_id`，因此成功、校验失败、未认证、无权限、限流和内部错误都有可关联标识。本步直接使用 `uuid4()`，没有新增 `AgentRun` 数据库模型和迁移。

每次请求只记录以下结构化指标：

```text
run_id
user_id
session_id_provided
request_status
http_status
duration_ms
tool_steps
source_count
insufficient_context
error_code
```

日志不记录用户问题、过滤器内容、会话 UUID、模型答案、来源正文、Provider 响应或 API Key。`KnowledgeAgentError` 增加了向后兼容的 `tool_steps` 元数据，使模型在已经执行工具后失败或超时时，API 仍能记录已完成的工具调用数量。

为什么这样做：当前尚未确定 Agent 审计数据的保留期限和清理策略，用结构化应用日志即可满足第 16 步观测要求，避免提前创建没有生命周期策略的数据库记录。

## 安全错误契约

错误响应统一为：

```json
{
  "error": {
    "code": "agent_timeout",
    "message": "Knowledge Agent request timed out.",
    "retryable": true
  },
  "run_id": "UUID"
}
```

主要状态映射：

| 场景 | HTTP 状态 | 稳定错误码 |
| --- | ---: | --- |
| 请求或过滤条件错误 | 400 | `invalid_request` 或受控 Agent 校验码 |
| 未认证 | 401 | `authentication_required` |
| 非管理员或 CSRF 拒绝 | 403 | `permission_denied` |
| DeepSeek 拒绝或响应畸形 | 502 | `llm_request_rejected` / `llm_invalid_response` |
| Provider、网络或配置暂不可用 | 503 | 对应受控错误码 |
| Agent 总期限超时 | 504 | `agent_timeout` |
| 未知内部错误 | 500 | `internal_error` |
| 超过频率限制 | 429 | `rate_limited` |

客户端永远不会收到原始异常字符串。即使异常文本包含本地路径、Provider 响应或疑似 Key，响应和 API 日志也只使用固定安全消息。

## 普通 JSON 与只读边界

- View 仅使用 `JSONParser` 和 `JSONRenderer`。
- `Accept: text/event-stream` 返回可处理的 `406 not_acceptable`，第一版没有 SSE。
- API 只调用 `run_knowledge_agent`，不直接访问或修改 Note、父片段、索引任务和 Qdrant。
- 成功响应不暴露工具调用次数等内部调试字段。
- 第 14、15 步的工具允许列表、来源白名单和四步限制保持不变。

为什么这样做：普通 JSON 的请求生命周期和错误语义更容易先稳定；流式输出需要额外设计中断、部分响应、心跳、代理超时和审计边界，不应混入第一版。

## 代码注释

本步新增代码对未知字段拒绝、严格字符串类型、日期字符串保留、`session_id` 无记忆、匿名限流顺序、错误脱敏、运行日志边界和失败工具次数补充了中文注释。后续 Agent 开发继续遵循“新增必要代码同时添加中文注释”的要求。

## 自动化测试

新增 `agent.test_api`，覆盖：

- 管理员完成一轮带有效来源的普通 JSON 问答。
- 当前 `request.user` 和服务器过滤条件正确传入 Agent。
- 每次请求 `run_id` 是 UUID 且互不相同。
- `session_id` 不触发历史记忆，也不会出现在响应中。
- 空消息、超长消息、错误 JSON 类型、未知字段、非法过滤器、非法日期和非法 UUID 返回 400。
- 匿名请求返回 401，普通用户返回 403。
- 真实 Cookie JWT 缺少 CSRF 时拒绝，携带 CSRF 时允许管理员调用。
- 逐用户限流返回 429，不同管理员额度独立，匿名请求不先消耗限流。
- DeepSeek 4xx、Provider 不可用、配置错误、超时和未知异常映射到稳定状态。
- 响应和日志不泄露测试中的疑似 Key、Provider 正文或本地路径。
- 只提供 JSON，不提供 SSE。
- API 响应不包含 `tool_steps` 等内部字段。
- API 层不修改 Note、父片段或 Qdrant。
- Agent 在执行工具后失败时，错误携带正确的已完成工具次数。

最终验证结果：

- `python manage.py test agent.test_api --noinput`：12 个 API 测试方法全部通过，包含多组子用例。
- `python manage.py test agent.agents.test_knowledge agent.test_api --noinput`：22 项全部通过。
- `python manage.py test --noinput`：315 项全部通过。
- `python manage.py makemigrations --check --dry-run`：通过，无模型变更遗漏。
- `python manage.py check`：通过，无系统检查问题。
- `python -m pip check`：通过，无损坏依赖。
- `backend/agent` 与 `backend/rag` Python 编译检查通过。
- `git diff --check`：通过。
- 排除 Git 忽略的 `backend/.env` 后，源码和配置文本疑似密钥匹配数为 0；`backend/.env` 未被 Git 跟踪。

## 真实环境冒烟

使用当前管理员、真实 Cookie JWT 和 CSRF Token 调用新增 API，只输出结构性检查，不输出 JWT、问题正文、回答、标题、来源正文或 Key。

结果：

```text
HTTP 状态：200
Content-Type：application/json
响应字段：answer、sources、insufficient_context、run_id
run_id：合法 UUID
answer：非空
```

本次真实模型运行没有形成可验证来源，API 返回 `sources=[]`、`insufficient_context=true`。这属于第 15 步已记录的模型工具规划波动；服务器按来源白名单执行了安全回退，没有生成无依据的带来源回答。自动化 API 测试已使用确定性 Agent 结果验证带来源成功响应。

真实 API 冒烟前后数据保持一致：

```text
Note：19 → 19
RagParentChunk：39 → 39
RagIndexState：18 → 18
Qdrant Point：151 → 151
活动索引任务：0 → 0
```

## 主要文件

- `backend/agent/serializers.py`：严格请求与过滤器校验。
- `backend/agent/throttles.py`：按管理员账号限流。
- `backend/agent/views.py`：权限、调用、错误契约、`run_id` 和指标日志。
- `backend/agent/urls.py`：Knowledge Agent API 路由。
- `backend/agent/test_api.py`：API 边界与安全测试。
- `backend/agent/agents/knowledge.py`：失败时携带已完成工具次数。
- `backend/MoonBirdNotes/urls.py`：挂载 `/api/agent/`。
- `backend/MoonBirdNotes/settings.py`：读取接口限流配置。
- `backend/.env.example`：记录非敏感限流配置示例。

## 下一步

第 17 步将建立 30～50 个真实问题的 RAG 评测集，量化 Recall@5、目标笔记/章节命中率、来源正确率和无依据回答率。开始第 17 步前不在本接口中追加长期记忆、SSE、写工具或其他未评测能力。
