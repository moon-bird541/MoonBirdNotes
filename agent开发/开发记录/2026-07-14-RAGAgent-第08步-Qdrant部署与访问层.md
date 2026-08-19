# RAG Agent 第 08 步开发记录：Qdrant 部署与访问层

> 日期：2026-07-14  
> 状态：已完成  
> 对应文档：`agent开发/RAGAgent开发步骤.md`

## 本次完成的范围

本次完成 RAG Agent 实际执行顺序的第 8 步：部署独立 Qdrant 服务，配置并幂等初始化 `moonbird_note_chunks_bge_m3_v1` Collection，实现健康检查、Collection 契约校验、Payload Index、子片段 Point 批量写入、受控 Payload Filter 查询、同 ID 更新和按笔记版本删除。

本步只提供向量数据库基础设施和访问边界，没有提前实现第 9 步的单篇笔记索引编排，也没有把任何真实笔记发送到 Qdrant。

## 做了什么

### 独立 Qdrant 服务

新增根目录 `compose.yaml`，固定使用：

~~~yaml
image: qdrant/qdrant:v1.18.2
rest_port: 127.0.0.1:6333
grpc_port: 127.0.0.1:6334
storage: qdrant_storage
~~~

- 使用独立容器，不使用 Django 进程内嵌入式文件模式。
- 开发环境端口只绑定 `127.0.0.1`，避免无认证服务暴露到外部网络。
- 使用 Docker 命名卷持久化索引，容器重启不会丢失现有 Point。
- Qdrant 只保存可从 MySQL 和分块规则重建的派生索引，不成为业务真实数据源。

后端显式加入 `qdrant-client==1.18.0`，与 Qdrant 1.18 系列服务配套。

### 后端连接配置

新增以下环境配置：

~~~text
QDRANT_URL=http://127.0.0.1:6333
QDRANT_API_KEY=
QDRANT_COLLECTION=moonbird_note_chunks_bge_m3_v1
QDRANT_VECTOR_NAME=dense
QDRANT_VECTOR_SIZE=1024
QDRANT_TIMEOUT_SECONDS=10
~~~

- 本地只通过 HTTP URL 连接独立服务，不允许传入嵌入式文件路径。
- API Key 为可选后端配置，配置对象的 `repr` 会隐藏密钥。
- URL 禁止包含用户名、密码、查询参数或 fragment。
- Qdrant 向量维度必须与 `RAG_EMBEDDING_DIMENSION` 一致，否则在初始化客户端前返回配置错误。

### Collection 契约

新增 `QdrantVectorStore.ensure_collection()`，按以下契约幂等创建或校验 Collection：

~~~text
collection: moonbird_note_chunks_bge_m3_v1
vector_name: dense
dimension: 1024
distance: Cosine
~~~

只允许当前已验证的单个命名 Dense 向量。现有 Collection 如果使用匿名向量、错误名称、错误维度、错误距离或额外的未验证向量，会返回 `QdrantCollectionError`，不会静默重建或删除数据。

### Payload 与索引

新增强类型 `QdrantChunkPayload`，每个 Point 必须包含：

~~~text
note_id
parent_id
type
title
heading_path
tags
diary_date
chunk_index
source_hash
index_version
embedding_version
~~~

这些字段都来自 MySQL、父子分块结果和当前索引配置，可以完全重建。普通笔记与日记继续保持边界：普通笔记不能携带 `diary_date`，日记必须有日期且不能携带普通笔记标签。

幂等创建并校验 8 个 Payload Index：

| 字段 | Qdrant 类型 |
| --- | --- |
| `note_id` | integer |
| `parent_id` | keyword |
| `type` | keyword |
| `tags` | keyword |
| `diary_date` | datetime |
| `source_hash` | keyword |
| `index_version` | integer |
| `embedding_version` | keyword |

已有同名索引类型不一致时明确失败，不删除或覆盖现有索引。

### Point 基础操作

`QdrantVectorStore` 提供：

~~~text
health_check()
ensure_collection()
upsert_points(points)
scroll_points(point_filter, ...)
delete_note_version(note_id, index_version)
~~~

- `upsert_points` 一次提交一组 Point，使用 `wait=True` 等待服务确认。
- 每条向量必须严格等于 1024 维，且所有元素为有限数值。
- 批次内重复 Point ID 会被拒绝，避免同一请求中发生隐式覆盖。
- 相同 Point ID 再次 upsert 用于确定性更新。
- 删除操作同时绑定 `note_id` 和 `index_version`，不会误删其他版本。
- Filter 只开放已经建立索引的字段，不接收任意 Qdrant 表达式。
- 多标签生成多个 `must` 条件，表示结果必须同时包含全部标签。
- 日记日期支持 `date_from/date_to` 范围过滤。
- 查询结果转换为本地数据类，不让后续业务层依赖 qdrant-client 内部模型。

### 结构化异常

新增：

~~~text
QdrantConfigurationError
QdrantCollectionError
QdrantInputError
QdrantOperationError
~~~

异常包含稳定 `code`、`retryable`、`provider` 和可选 `status_code`。连接失败、429 和 5xx 标记为可重试；确定性配置、输入或普通 4xx 错误不可重试。错误消息不包含 Qdrant 响应正文、Payload、向量或 API Key。

### 初始化命令

新增：

~~~text
python manage.py initialize_qdrant
~~~

命令执行真实健康检查，随后创建或校验 Collection 和 Payload Index。重复执行不会重建 Collection。命令只输出 Collection 名、向量名、维度、距离和索引数量，并在退出前显式关闭 HTTP 连接池。

### 代码注释

新增代码包含必要中文模块说明、数据契约说明和关键分支注释，重点解释独立服务边界、可重建 Payload、版本删除、全标签过滤、配置漂移拒绝和连接释放原因。

## 为什么这样做

- Qdrant 作为独立服务可以支持 Django 多进程和并发访问，避免嵌入式文件模式的锁与进程一致性问题。
- Collection 名包含模型版本，命名向量固定为 `dense`，为以后评估 Sparse 或其他向量保留明确扩展边界，但当前不创建未验证字段。
- 严格校验已存在 Collection 比自动删除重建安全；维度或距离漂移应由明确的新版本和全量重建处理。
- Payload Index 与后续按用户可见范围、笔记、类型、标签、日期、原文哈希和索引版本过滤直接对应，避免全量扫描。
- Qdrant 中只保存派生数据，确保删除 Collection 后仍可从 MySQL 恢复，不会产生第二份不可重建的业务事实。
- 删除同时绑定笔记和版本，可以让后续索引流程安全清理旧版本而不影响当前版本。
- 访问层负责把底层客户端异常转换为结构化错误，后续任务可以安全决定重试，API 也不会泄漏服务响应内容。
- 按最小职责范围原则，本步没有提前调用 Embedding、读取 Note ORM 或编排单篇索引，这些属于第 9 步。

## 自动化测试

新增 19 个专项测试，覆盖：

- Qdrant API Key 的配置对象脱敏。
- 拒绝嵌入式路径、带凭据 URL 和 Embedding 维度漂移。
- 普通笔记与日记 Payload 互斥规则。
- UUID、SHA-256、索引版本和运行时类型校验。
- 健康检查和服务不可用结构化异常。
- Collection 首次创建与 8 个 Payload Index。
- 重复初始化不重建 Collection 或索引。
- 错误向量名称、维度、距离和额外向量拒绝。
- 错误或缺失 Payload Index 拒绝。
- 多 Point 命名向量批量 upsert。
- 空批次、重复 ID、错误维度和无效数值。
- `note_id + index_version` 删除过滤器。
- 类型、标签、日期、哈希和版本组合过滤。
- 分页结果与下一页游标转换。
- 非法 Filter、limit 和 offset。
- 初始化命令健康检查、初始化、输出与连接关闭。

## 真实 Qdrant 验证

Docker Compose 已启动 `qdrant/qdrant:v1.18.2`，`/readyz` 返回 HTTP 200 和 `all shards are ready`。

真实验证结果：

~~~text
连续初始化次数：2
Collection：moonbird_note_chunks_bge_m3_v1
向量：dense / 1024 / Cosine
Payload Index：8
创建测试 Point：成功，过滤命中 1
同 ID 更新：成功，标题和命名向量已更新
按 note_id + index_version 删除：成功，剩余 0
普通笔记双标签过滤：命中 1
日记日期范围过滤：命中 1
未监听端口健康检查：qdrant_unavailable，retryable=true
~~~

所有集成测试 Point 都已在 `finally` 中删除，Collection 内没有遗留测试数据。

## 如何验证

- `python manage.py test rag.test_qdrant --noinput`：19 个专项测试全部通过。
- `python manage.py test --noinput`：执行 192 个后端测试，全部通过，耗时约 32 秒。
- `python manage.py check`：通过，0 个问题。
- `python manage.py makemigrations --check --dry-run`：输出 `No changes detected`。
- `python -m pip check`：输出 `No broken requirements found`。
- `docker compose config --quiet`：通过。
- `docker compose ps qdrant`：容器处于运行状态，端口只绑定本机。
- Qdrant `/readyz`：HTTP 200。
- `python manage.py initialize_qdrant` 连续执行两次：均输出相同合法配置。
- Python 语法编译与 `git diff --check`：通过。

## 文件变更

- 新增：`compose.yaml`
- 新增：`backend/rag/qdrant.py`
- 新增：`backend/rag/test_qdrant.py`
- 新增：`backend/rag/management/commands/initialize_qdrant.py`
- 修改：`backend/MoonBirdNotes/settings.py`
- 修改：`backend/.env.example`
- 修改：`backend/requirements.txt`
- 修改：`README.md`
- 更新：`agent开发/RAGAgent开发步骤.md`
- 新增：本开发记录

## 未完成事项与下一步

下一步是第 9 步：实现单篇笔记索引。该步骤会从 MySQL 读取当前 Note，生成父子片段，调用第 7 步批量 Embedding，再通过本步访问层写入 Qdrant，并在提交前后校验 `source_hash`，保证旧内容不会覆盖新内容。
