# RAG Agent 第 07 步开发记录：封装 SiliconFlowEmbeddingService

> 日期：2026-07-14  
> 状态：已完成  
> 对应文档：`agent开发/RAGAgent开发步骤.md`

## 本次完成的范围

本次完成 RAG Agent 实际执行顺序的第 7 步：建立业务无关的 `EmbeddingService` 接口，并实现硅基流动 `BAAI/bge-m3` 在线 Dense Embedding 服务，包括进程内 HTTP 连接复用、可配置批量请求、版本化统一输入、1024 维校验、数值校验、归一化、缓存、超时、有限重试、结构化异常和脱敏日志。

本步只实现 Embedding 服务能力，不提前实现 Qdrant、单篇索引任务或混合检索。查询失败后的关键词降级会在第 13 步真实检索流程接入，索引失败后的 `RagIndexJob` 状态更新会在第 9～10 步真实索引流程接入。

## 做了什么

### 统一服务边界

新增抽象接口：

~~~python
class EmbeddingService:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        ...

    def embed_query(self, query: str) -> list[float]:
        ...
~~~

后续索引和检索代码只依赖该接口，不直接拼接硅基流动 HTTP 请求。

新增进程级 `get_embedding_service()` 工厂。同一 Django 进程反复获取服务时返回同一个实例，从而复用同一个 `httpx.Client` 连接池。

### 后端配置

在已有 Provider、模型、维度和 Embedding 版本配置上补充：

~~~text
RAG_EMBEDDING_INPUT_TEMPLATE_VERSION
RAG_EMBEDDING_NORMALIZE
RAG_EMBEDDING_BATCH_SIZE
RAG_EMBEDDING_TIMEOUT_SECONDS
RAG_EMBEDDING_MAX_RETRIES
RAG_EMBEDDING_RETRY_BACKOFF_SECONDS
RAG_EMBEDDING_MAX_INPUT_CHARS
RAG_EMBEDDING_CACHE_TIMEOUT_SECONDS
~~~

API Key 仍只从 Git 忽略的 `backend/.env` 读取。`.env.example` 只保存占位值和非敏感默认配置。

项目依赖中显式加入 `httpx==0.28.1`，用于连接池、超时分类和可测试的 HTTP 传输边界。

### 批量请求与输入行为

- `embed_documents` 按 `RAG_EMBEDDING_BATCH_SIZE` 拆分请求，并按原始输入顺序组装结果。
- 空文档列表直接返回空列表，不产生网络请求。
- 空字符串、纯空白、非字符串和超过字符上限的输入在本地返回结构化输入错误。
- 第六步的子片段已有 500-token 硬上限；本步字符上限额外阻止异常查询或误把整篇正文直接传给服务。
- 文档和查询统一使用 BGE-M3 原文输入模板，不添加两套不一致的指令前缀；模板行为由 `bge-m3-unified-v1` 独立标识。
- 服务保留有效首尾空白，使 SHA-256 与第六步对完整 `vector_text` 计算的 `chunk_hash` 一致。

### 响应校验与归一化

每次 Provider 响应都会校验：

- `data` 数量必须和本批输入数量相同。
- `index` 必须为不重复且完整的 `0..n-1`，响应乱序时按 index 恢复。
- 每条向量必须严格等于配置维度，当前为 1024。
- 每个元素必须是非布尔数值且为有限值，拒绝 `NaN` 和无穷大。
- 开启归一化时拒绝零向量，并执行 L2 归一化。

第一版只读取硅基流动实际返回的 Dense `embedding`，没有假设云端会返回 BGE-M3 的 Sparse 或 ColBERT 数据。

### 超时、重试与结构化异常

新增统一异常类型：

~~~text
EmbeddingConfigurationError
EmbeddingInputError
EmbeddingTransportError
EmbeddingProviderError
EmbeddingResponseError
~~~

异常提供稳定的 `code`、`retryable`、`provider` 和可选 `status_code`，后续索引任务可以据此决定是否保留重试状态，检索流程可以据此决定是否降级。

重试规则固定为：

- 429、5xx、网络错误和超时允许有限重试。
- 退避时间按配置基数执行 `base * 2^attempt`。
- 普通 4xx、错误 JSON、错误数量、错误维度和无效数值不重试。
- 达到次数上限后返回结构化异常，不包含 Provider 响应正文、原始输入或 API Key。

### 缓存与日志

文档缓存内容哈希与第六步 `chunk_hash` 使用同一算法。缓存键包含：

~~~text
provider
document 或 query 命名空间
model
embedding_version
input_template_version
content_hash / chunk_hash
normalize
~~~

模型、输入模板或归一化行为变化后不会误用旧向量。缓存中的向量在使用前仍执行维度、数值和归一化校验；损坏缓存会被删除并重新请求。

日志只记录 Provider、模型、Embedding 版本、模板版本、批次数、请求哈希、耗时、尝试次数和状态，不记录完整子片段、完整查询、响应正文、向量或 API Key。

### 代码注释

新增代码包含必要中文模块说明、类说明、方法说明和关键分支注释，重点解释连接复用、缓存失效、哈希一致性、重试边界和日志脱敏原因。

## 为什么这样做

- 统一接口隔离具体 Provider，后续索引和检索不会散落带密钥的 HTTP 代码。
- 长生命周期 `httpx.Client` 可以复用 TCP/TLS 连接，批量索引时避免为每个子片段重新握手。
- 只重试 429、5xx 和传输类瞬时错误，能提高短暂故障恢复能力，同时避免对确定性的输入错误反复请求。
- 数量、index、维度和数值必须全部校验，否则错误向量可能静默写入 Qdrant，并在很久以后表现为难以定位的召回异常。
- 缓存键绑定模型和两类版本，确保模型或模板升级时自然失效；绑定完整文本哈希，确保正文或元数据变化时重新生成向量。
- 缓存是派生数据，使用前仍需校验，不能因为缓存命中而绕过向量契约。
- 服务只抛出不含正文和 Provider 响应体的结构化异常，后续可以安全写入任务错误字段或 API 响应。
- 查询降级和索引状态必须由拥有真实关键词通道或 `RagIndexJob` 的业务层实现；提前在 Provider 客户端中修改数据库或调用检索会破坏职责边界。

## 自动化测试

新增 19 个专项测试，覆盖：

- 配置错误和配置对象密钥脱敏。
- 空批次、空文本、非字符串和超长输入。
- 批次拆分、请求顺序和响应乱序恢复。
- 模型、float 编码和 Authorization 请求头。
- 文档与查询缓存命名空间。
- 缓存键版本字段、缓存命中和损坏缓存重取。
- 429 指数退避后成功。
- 5xx 重试耗尽。
- 普通 4xx 不重试。
- 超时重试、结构化错误及日志脱敏。
- 错误数量、维度、索引、非有限值、布尔值和零向量。
- 可配置关闭归一化。
- 进程级工厂复用服务与 HTTP Client。
- 未支持 Provider 的配置拒绝。

## 真实硅基流动验证

使用已配置的硅基流动在线 `BAAI/bge-m3`，发送两条不含私人笔记内容的固定连通性测试文本。

结果：

~~~text
请求输入数量：2
返回向量数量：2
每条向量维度：1024
所有数值有限：是
归一化后 L2 范数：1.0、1.0
~~~

验证过程没有输出向量内容或 API Key。

## 如何验证

- `python manage.py test rag.embeddings.tests --noinput`：19 个专项测试全部通过。
- `python manage.py test --noinput`：执行 173 个后端测试，全部通过，耗时约 31 秒。
- `python manage.py check`：通过，0 个问题。
- `python manage.py makemigrations --check --dry-run`：输出 `No changes detected`。
- `python -m pip check`：输出 `No broken requirements found`。
- Python 语法编译和 `git diff --check`：通过。
- 真实硅基流动批量请求：返回 2 条 1024 维有限向量。

## 文件变更

- 新增：`backend/rag/embeddings/base.py`
- 新增：`backend/rag/embeddings/siliconflow.py`
- 新增：`backend/rag/embeddings/tests.py`
- 修改：`backend/rag/embeddings/__init__.py`
- 修改：`backend/MoonBirdNotes/settings.py`
- 修改：`backend/.env.example`
- 修改：`backend/requirements.txt`
- 更新：`agent开发/RAGAgent开发步骤.md`
- 新增：本开发记录

## 未完成事项与下一步

- 第 8 步：部署独立 Qdrant 服务并建立 1024 维 Cosine Collection。
- 第 9～10 步：单篇索引和后台任务接入 `embed_documents`，并依据结构化异常保留可重试 `RagIndexJob`。
- 第 13 步：混合检索接入 `embed_query`，语义向量不可用时降级到关键词检索并明确标记。
- 首次全量索引前仍需完成逐篇 AI 索引开关、日记默认策略和疑似敏感内容提示/排除机制。
