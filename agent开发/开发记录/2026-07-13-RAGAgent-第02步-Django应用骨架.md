# RAG Agent 第 02 步开发记录：创建 Django 应用与目录

> 日期：2026-07-13  
> 状态：已完成  
> 对应文档：`agent开发/RAGAgent开发步骤.md`

## 本次完成的范围

本次完成 RAG Agent 实际执行顺序的第 2 步：创建 `rag` 与 `agent` Django App、注册应用、建立最小包边界，并验证现有后端检查和测试继续通过。

本次没有提前实现第 3 步的数据模型，也没有增加 Agent API、URL 路由、Embedding、Qdrant 或 LLM 依赖。

## 做了什么

1. 在 `backend/MoonBirdNotes/settings.py` 的 `INSTALLED_APPS` 中注册：
   - `rag.apps.RagConfig`
   - `agent.apps.AgentConfig`
2. 创建 `rag` Django App 的最小结构：
   - `apps.py`、`models.py`、`migrations/` 和注册测试。
   - `chunking/`、`embeddings/`、`retrieval/`、`services/`。
   - `management/commands/`，为后续索引管理命令保留符合 Django 约定的入口。
3. 创建 `agent` Django App 的最小结构：
   - `apps.py`、`models.py`、`migrations/` 和注册测试。
   - `agents/` 与 `tools/`，分别承载后续 Agent 实现和受控工具。
4. 将 `rag.services` 定义为 RAG 对其他 Django App 的公开服务边界。后续 `agent` 应通过该入口使用 RAG，不直接依赖 RAG 模型、向量存储或检索内部实现。
5. 新增两个 `SimpleTestCase`，验证 Django 能通过预期名称加载 `rag` 和 `agent` AppConfig。

## 为什么这样做

- RAG 数据处理和 Agent 推理的依赖不同。拆成两个 Django App，可以让 Markdown 分块、索引和检索在没有 LLM 的情况下独立运行。
- `rag.services` 作为公开入口可以防止 Agent 层直接耦合 Qdrant、Django ORM 或分块实现，后续更换存储或 Embedding 实现时不需要改 Agent 代码。
- 当前只创建包入口，不创建占位业务类和空 API，避免在需求尚未进入对应步骤时形成无用抽象。
- `models.py` 暂时不包含字段，因此本步不生成空迁移；第 3 步会一次性定义 `RagParentChunk`、`RagIndexState` 和 `RagIndexJob` 后再创建实际迁移。
- 不把 `agent.urls` 接入项目路由，是因为 Knowledge Agent API 属于第 16 步，当前没有可公开的接口。

## 如何验证

### 基线

- 修改前执行 `python manage.py check`：通过，0 个问题。
- 修改前检查 Python 模块：虚拟环境中不存在同名 `rag` 或 `agent` 包，不会产生包名冲突。

### 修改后

- `python manage.py check`：通过，0 个问题。
- `python manage.py makemigrations --check --dry-run`：输出 `No changes detected`，确认没有遗漏迁移或意外模型变化。
- `python manage.py test --keepdb`：发现并执行 95 个测试，全部通过，耗时约 30 秒。

第一次直接执行 `python manage.py test` 时，发现已有 MySQL 测试库 `test_moonsbirdnotrs_db`。Django 在非交互环境中无法询问是否删除旧测试库，因此未进入测试执行。随后使用 `--keepdb` 安全复用该测试库并完成全部测试，没有删除或重建用户已有的测试数据库。

## 文件变更

- 修改：`backend/MoonBirdNotes/settings.py`
- 新增：`backend/rag/`
- 新增：`backend/agent/`
- 更新：`agent开发/RAGAgent开发步骤.md`
- 新增：本开发记录

## 未完成事项与下一步

下一步是 `RAGAgent开发步骤.md` 的第 3 步：设计并实现 `RagParentChunk`、`RagIndexState` 和 `RagIndexJob`，定义数据库约束与索引，创建迁移，并补充删除关联和唯一性测试。
