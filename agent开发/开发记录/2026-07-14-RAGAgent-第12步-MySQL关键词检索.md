# RAGAgent 第 12 步：MySQL 关键词检索

日期：2026-07-14

## 本次完成的范围

本次完成 RAG Agent 实际执行顺序的第 12 步：在 `rag.retrieval` 中建立独立、确定性的 MySQL 关键词检索服务。

本步只实现关键词候选通道，没有提前实现第 13 步的 Qdrant Dense 查询、RRF 融合或父片段聚合，也没有新增 Agent API。

## 做了什么

### 统一检索入口

新增：

```python
search_keywords(query, types=None, limit=20)
```

参数行为：

- `types=None`：全局模式，同时检索普通笔记和日记。
- `types=('note',)`：只检索普通笔记，严格排除日记。
- `types=('diary',)`：只检索日记。
- `limit`：限制返回候选数量，允许 1～100。
- 空查询、超长查询、非法类型和非法数量返回带稳定 `code` 的 `KeywordSearchError`。

### MySQL 字段覆盖

普通笔记检索：

- `title`
- `markdown_content`
- `source_filename`
- `tags.name`

日记检索：

- `note.title`
- `note.markdown_content`
- `diary_date`
- `summary`
- `mood`
- `weather`

日期通过 MySQL `Cast` 转换为文本，因此既能匹配完整 `YYYY-MM-DD`，也能匹配 `YYYY-MM`。

### 严格范围边界

- 所有模式始终排除 `is_deleted=true` 的软删除 Note。
- 普通笔记通过 `diary_entry__isnull=true` 限定，不会混入日记底层 Note。
- 日记只搜索规范指定的日记字段，不使用底层 Note 的标签或源文件名。
- `ai_indexing_enabled` 只控制云端向量化；本地 MySQL 关键词检索不会调用硅基流动，因此不把关闭云端索引的有效 Note 排除在本地搜索之外。

### 结构化候选

新增不可变 `KeywordCandidate`，包含：

```text
note_id
parent_id
document_type
title
heading_path
source_hash
score
matched_excerpt
matched_fields
diary_date
```

`as_dict()` 会转换为规范中的 `type` 字段，并把标题路径、命中字段和日期转换为 JSON 友好结构，不直接拼接回答文本。

### 当前来源与父片段定位

- `source_hash` 每次直接根据 MySQL 当前 `Note.markdown_content` 计算，与索引层约定一致。
- 只读取 `RagIndexState.status=completed` 且索引版本、状态哈希一致的父片段。
- 候选优先绑定正文实际命中的当前父片段；元数据命中时回退到该 Note 的第一个当前父片段。
- 如果 Note 已修改而父片段仍是旧哈希，返回 Note 级候选，但 `parent_id=null`，禁止把旧父片段冒充当前来源。

### 排序与技术标识符

第一版使用简单、可解释的字段优先级：标题完整匹配最高，其次是源文件名、标签、日期和日记元数据，正文包含匹配作为基础分。相同分数按最近更新时间和 Note 主键稳定排序。

命中摘要从原字段值中截取，保留接口路径、类名、文件名和错误码原文，便于第 13 步与 Dense 结果融合。

### 对外服务边界

`KeywordCandidate`、`KeywordSearchError` 和 `search_keywords` 已从 `rag.services` 公开。后续 Agent App 应继续通过这一服务边界访问，不直接拼 ORM 查询。

## 为什么这样做

- 精确接口路径、文件名、类名和错误码不适合只依赖语义向量召回，MySQL 关键词通道必须独立可用。
- 第 12 步与现有产品搜索目标不同：产品搜索返回页面卡片，RAG 搜索返回可供融合与来源校验的内部候选，因此没有强行复用或修改现有 `GlobalSearchView`。
- 直接读取当前 Note 能让关键词检索在 Qdrant 或硅基流动不可用时仍然工作。
- 只在当前父片段安全可用时附加 `parent_id`，避免旧索引参与后续定位。
- 当前个人知识库规模下，先采用简单的 ORM `icontains` 和可解释排序；全文索引与性能优化留到第 19 步按实际指标决定。

## 代码注释

新增代码对日期 Cast、类型边界、稳定排序、当前父片段校验、来源哈希和摘要截取等关键规则补充了中文注释。

## 自动化测试

新增 9 个测试，覆盖：

- 普通笔记标题、Markdown、源文件名和标签。
- 日记标题、Markdown、完整/部分日期、摘要、心情和天气。
- 普通模式严格排除日记，全局模式包含两类内容。
- 默认排除软删除内容。
- 本地关键词检索不依赖云端向量授权。
- 接口路径、类名、文件名和错误码精确召回及摘要保留。
- 当前父片段、标题路径和 JSON 友好输出。
- 旧父片段不会作为当前来源返回。
- 标题完整匹配排序、Top K 限制及结构化参数错误。

针对性测试结果：9 个测试全部通过。

最终验证结果：

- `python manage.py test --noinput`：254 个测试全部通过。
- `python manage.py makemigrations --check --dry-run`：通过，无模型变更遗漏。
- `python manage.py check`：通过，无系统检查问题。
- `python -m pip check`：通过，无损坏依赖。
- 真实 MySQL 只读冒烟测试：成功返回目标 Note，类型、当前来源哈希和结构化字段均完整；测试未输出笔记正文。
- `git diff --check`：通过。
- 第 12 步文件与 Git diff 疑似密钥匹配数：0。

## 未完成事项与下一步

下一步是第 13 步：实现 Qdrant Dense 查询、MySQL 关键词候选融合、按父片段聚合、当前来源哈希过滤，以及 Embedding 查询失败时的关键词降级。本步没有调用硅基流动，也没有修改 Qdrant 或 Note 原文。
