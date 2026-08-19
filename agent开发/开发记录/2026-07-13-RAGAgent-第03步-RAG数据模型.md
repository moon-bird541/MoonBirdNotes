# RAG Agent 第 03 步开发记录：建立 RAG 数据模型

> 日期：2026-07-13  
> 状态：已完成  
> 对应文档：`agent开发/RAGAgent开发步骤.md`

## 本次完成的范围

本次完成 RAG Agent 实际执行顺序的第 3 步：建立 `RagParentChunk`、`RagIndexState` 和 `RagIndexJob`，定义约束与查询索引，创建并执行初始迁移，并为关键数据规则增加自动化测试。

本次没有实现 Markdown 解析、父子分块、任务 Worker、Embedding 或 Qdrant 操作。

## 做了什么

### RagParentChunk

- 使用 UUID 主键，便于后续把稳定的 `parent_id` 写入 Qdrant Payload。
- 通过外键关联 `Note`，反向名称为 `rag_parent_chunks`，硬删除 Note 时级联清理。
- 保存片段顺序、标题路径、正文、起止行、完整原文哈希、章节哈希、索引版本和创建时间。
- 约束同一 Note、同一索引版本下的 `chunk_index` 唯一。
- 约束 `start_line >= 1`、`end_line >= start_line`、`index_version >= 1`。
- 为 `note + index_version` 和 `source_hash` 建立查询索引。

### RagIndexState

- 使用 `OneToOneField` 保证每个 Note 只有一个当前索引状态。
- 保存已索引原文哈希、Embedding 模型与版本、索引版本、状态、完成时间和错误信息。
- 状态统一为 `pending / indexing / completed / failed`。
- 在数据库层约束状态取值和正数索引版本，并为状态建立索引。

### RagIndexJob

- 使用 UUID 主键并通过外键关联 Note，硬删除 Note 时级联清理。
- 保存目标原文哈希、任务原因、状态、尝试次数、错误信息以及创建、开始、完成时间。
- 在数据库层约束合法状态。
- 为 `status + created_at` 和 `note + created_at` 建立索引，支持 Worker 获取待处理任务和查询单篇笔记任务历史。
- 允许同一 Note、同一 `target_source_hash` 因不同原因再次创建任务，以支持更换 Embedding 模型、分块规则或索引版本后的全量重建。后续的短时间重复任务合并由任务服务处理，不使用永久唯一约束阻断合法重建。

### 迁移与测试

- 新增并执行 `rag/migrations/0001_initial.py`。
- 新增测试覆盖：
  - Note 硬删除后，三个 RAG 模型记录全部级联清理。
  - 同一 Note 不能创建两个 `RagIndexState`。
  - 同一 Note 和索引版本不能出现重复父片段序号。
  - 父片段不能保存反向行号范围。
  - 索引状态不能保存未知状态。
  - 相同正文可以因不同索引原因再次排队。

## 为什么这样做

- 三个模型保存的都是可从 `Note.markdown_content` 重建的派生数据，因此使用 `CASCADE`；MySQL 中的 Note 原文仍是唯一真实来源。
- 哈希字段固定为 64 字符，对应后续统一使用的 SHA-256 十六进制摘要。
- 父片段 UUID 可以同时作为 MySQL 定位键和 Qdrant 子片段的 `parent_id`，避免依赖标题或易变化行号。
- 数据库唯一约束负责阻止真正不合法的数据，例如一篇 Note 存在两个当前状态、同一版本出现重复片段顺序。
- 没有把索引任务永久限制为 `note + source_hash` 唯一，因为正文不变时仍可能因模型、向量维度或分块规则变化需要重新索引。任务防抖和去重应基于当时的任务状态与索引版本，由后续任务服务确定。
- 状态采用专项开发步骤中定义的 `completed`，而不是总规范早期示例中的 `ready`，保证索引状态和索引任务使用同一套名称。

## 实现过程中的修正

最初曾考虑给 `RagIndexJob` 增加 `note + target_source_hash` 唯一约束。审查后发现该约束会阻止相同正文在更换 Embedding 模型或分块规则后重建索引。

在确认三张新表均为空后，回退了本次尚未投入使用的初始迁移，移除该约束并重新应用迁移。整个过程只操作新建且为空的 RAG 派生表，没有修改 Note、日记或其他现有业务数据。

## 如何验证

- `python manage.py check`：通过，0 个问题。
- `python manage.py makemigrations --check --dry-run`：输出 `No changes detected`。
- `python manage.py migrate --plan`：只包含 `rag.0001_initial` 的三张新表。
- `python manage.py migrate`：`rag.0001_initial` 应用成功。
- `python manage.py test --noinput`：从干净测试数据库执行 101 个测试，全部通过，耗时约 30 秒。
- 测试结束后 Django 自动删除测试数据库；开发数据库中的 RAG 迁移保持已应用状态。

## 文件变更

- 修改：`backend/rag/models.py`
- 修改：`backend/rag/tests.py`
- 新增：`backend/rag/migrations/0001_initial.py`
- 更新：`agent开发/RAGAgent开发步骤.md`
- 新增：本开发记录

## 未完成事项与下一步

下一步是 `RAGAgent开发步骤.md` 的第 4 步：实现 Markdown 结构解析，把 Markdown 稳定解析为带块类型和行号的结构化序列，并覆盖标题、代码块、列表、引用、表格、图片、链接及不完整 Markdown 等边界测试。
