# RAGAgent 第 17 步：RAG 评测集

日期：2026-07-14

## 本次完成的范围

本次完成 RAG Agent 实际执行顺序的第 17 步：从当前真实知识库建立 43 个标注问题，实现评测集格式校验、当前来源校验、真实混合检索评测和可选 Knowledge Agent 回答评测，并记录第一版真实基线。

本步只增加评测数据和只读评测工具，没有修改检索排序、Agent Prompt、Embedding、Qdrant 索引、笔记内容或 API 行为。这样可以先固定可重复的质量基线，再根据失败 case 定向改进，避免一边改算法一边改变验收标准。

## 真实评测集

评测集文件：

```text
backend/rag/evaluation_dataset.json
```

总计 43 个问题：

```text
可回答：39
不可回答：4
中文语义：30
中英混合技术词：21
接口路径、文件名、类名等精确标识：15
普通笔记：38
日记：3
日期、心情和天气：3
相似标题：2
跨章节：8
不可回答：4
```

评测问题来自当前 19 篇真实笔记，主要覆盖：

- SaaS 三步积分校验流程、接口路径、请求字段、代理文件、错误响应、Prompt Merging 和 `postMessage`。
- Skill Manager 的定位、目标用户、技术栈、导入/安装/启停/备份、页面、数据库表、适配器、MVP 和打包命令。
- 两篇标题相同、正文相同的“功能说明”，要求同时召回两个 Note ID。
- 2026-07-01 日记模板的章节。
- 日记中实际为空的心情和天气字段，标记为不可回答，用于检测模型是否编造。
- 知识库完全不存在的 OAuth 错误码和工资表问题。

当前日记只有日期和空模板，没有真实心情、天气或正文内容。因此本步没有虚构日记标注，而是把心情和天气问题标记为 `answerable=false`，要求 Agent 明确资料不足。

## 每题标注

每个评测项严格包含：

```text
id
question
categories
filters
expected_note_ids
expected_heading_paths
answerable
expected_keywords
```

其中：

- `expected_note_ids` 用于 Recall@5 和目标笔记命中率。
- `expected_heading_paths` 使用当前 `RagParentChunk.heading_path` 的精确值。
- `answerable` 区分应回答和应拒答的问题。
- `expected_keywords` 只用于可回答问题的答案覆盖检查。
- `filters` 复用真实 API 支持的 `types`、`tags`、`date_from` 和 `date_to`。

为什么这样做：Note ID 和标题路径是当前系统最稳定、可自动验证的来源标识；只写自然语言“预期答案”容易产生主观评分，而来源与关键词可以先提供确定性基线。

## 严格数据集校验

新增 `rag.evaluation.load_evaluation_cases`，校验：

- 默认数据集必须包含 30～50 题。
- case ID 唯一。
- 字段集合必须完全匹配，额外字段不能被静默忽略。
- 问题、类别、过滤条件、Note ID、标题路径和关键词类型正确。
- 可回答问题必须同时有 Note ID、标题路径和关键词标注。
- 日期必须是 ISO 日期。
- 覆盖类别不能缺少中文语义、中英混合、精确标识、普通笔记、日记、日期/心情/天气、相似标题、跨章节和不可回答问题。

新增 `validate_evaluation_sources`，在执行评测前使用当前 MySQL 数据确认：

- 标注 Note 仍存在、未删除并允许 AI 索引。
- 标注标题路径仍存在于对应 Note 的父片段中。

来源失效时命令直接失败，避免数据库内容变化后继续用过期标注计算虚假低分。

## 评测管理命令

新增命令：

```powershell
python manage.py evaluate_rag --validate-only
python manage.py evaluate_rag
python manage.py evaluate_rag --with-agent --admin-username <管理员用户名>
```

三种模式：

1. `--validate-only`：只校验 JSON、覆盖类别和当前来源，不调用外部服务。
2. 默认模式：执行 43 题真实混合检索，调用在线 BGE-M3 和 Qdrant，但不调用 DeepSeek。
3. `--with-agent`：在检索指标之外执行真实 Knowledge Agent，计算回答和来源指标。

默认不自动调用 DeepSeek，是为了让日常数据集校验和检索回归不会意外产生大量模型费用。回答评测必须由开发者显式指定管理员和 `--with-agent`。

命令只输出聚合指标和失败 case ID，不输出问题、笔记正文、标题、模型答案、JWT 或 API Key。运行结束后显式关闭 DeepSeek、Embedding 和 Qdrant 连接池。

## 检索指标

实现并输出：

```text
Recall@K
目标笔记命中率
目标章节命中率
普通笔记/日记/日期范围越界率
不可回答问题空召回率
语义通道降级率
平均检索耗时
失败 case ID
笔记、章节和范围不合格 case ID
```

Recall@5 按每题期望 Note ID 集合计算；相似标题问题同时标注 Note 2 和 Note 3，因此必须同时召回才能获得完整 Recall。

不可回答问题不要求检索层完全无结果。Dense 语义检索通常会返回“最接近”的候选，因此另外记录 `unanswerable_nonempty_case_ids`，最终是否安全由 Agent 的来源验证和拒答指标判断。

## 回答指标

显式 `--with-agent` 模式实现并输出：

```text
来源正确率
无依据回答率
不可回答拒答率
预期关键词命中率
平均回答耗时
Provider 失败 case ID
错误来源 case ID
无依据回答 case ID
关键词缺失 case ID
未拒答 case ID
```

来源正确必须同时匹配预期 Note ID 和标题路径。不可回答问题只有在 `insufficient_context=true` 且来源为空时才算正确拒答。

为什么这样做：第 15 步的来源白名单只能保证来源确实来自本轮工具，不能保证模型选中了评测题的正确章节；评测层必须再与人工标注的目标来源比较。

## 第一版真实基线

### 混合检索

43 题真实检索结果：

```text
Recall@5：100%
目标笔记命中率：100%
目标章节命中率：100%
范围越界率：0%
语义通道降级率：0%
平均检索耗时：约 151ms
执行失败：0
```

4 个不可回答问题均召回了语义候选，空召回率为 0%。这不是越界，因为候选仍受 Note/日记/日期过滤约束；它证明最终 Agent 必须判断候选是否足以支持回答。

### Knowledge Agent

43 题真实 DeepSeek `deepseek-v4-flash` 回答评测：

```text
完成题数：43/43
Provider 失败：0
来源正确率：87.5%
无依据回答率：约 6.98%
不可回答拒答率：100%
预期关键词命中率：约 57.76%
平均回答耗时：约 7.68 秒
```

结论：

- 检索层已经超过目标笔记 Recall@5 约 90% 的建议门槛。
- 普通笔记、日记和日期过滤没有越界。
- 4 个不可回答问题全部安全拒答。
- 来源正确率未达到 100%。
- 仍有约 6.98% 的运行被评测为无依据回答。
- 关键词覆盖偏低，部分回答不够完整或发生安全回退。

因此第 17 步的“评测集与执行工具”已经完成，但当前 Knowledge Agent 回答质量尚未达到进入下一能力扩展阶段的建议门槛。后续应先依据 case ID 定向分析来源选择和回答完整性，不能把检索 100% 误写成端到端回答已经达标。

## 中文注释

新增代码对默认覆盖类别、旧来源阻断、外部异常脱敏、范围越界统计、不可回答候选、来源正确性、无依据回答定义和连接池释放添加了必要中文注释。

## 自动化测试

新增 `rag.test_evaluation`，覆盖：

- 默认数据集题数、唯一 ID、必需类别和标注完整性。
- 可回答与不可回答数量统计。
- Recall@5、笔记/章节命中、范围越界、空召回、降级率和耗时计算。
- 来源正确率、拒答率、无依据回答、关键词命中和回答耗时计算。
- 质量失败报告只包含 case ID，不包含问题或回答。

验证结果：

- `python manage.py test rag.test_evaluation --noinput`：5 项全部通过。
- `python manage.py evaluate_rag --validate-only`：43 题格式和当前来源全部通过。
- `python manage.py evaluate_rag`：43 题真实检索完成，无失败、无降级。
- `python manage.py evaluate_rag --with-agent ...`：43 题真实 Agent 评测完成，无 Provider 失败。
- `python manage.py test --noinput`：320 项全部通过。
- `python manage.py makemigrations --check --dry-run`：通过，无模型变更。
- `python manage.py check`：通过。
- `python -m pip check`：通过。

## 数据与密钥边界

评测命令只读取笔记、父片段、Qdrant 和现有管理员身份，不修改业务数据。评测前后保持：

```text
Note：19
RagParentChunk：39
RagIndexState：18
Qdrant Point：151
活动索引任务：0
```

真实 Key 仍只存在于 Git 忽略的 `backend/.env`。数据集、代码、测试、命令输出和本开发记录均未写入 API Key、JWT、完整模型回答或 Provider 响应正文。

## 主要文件

- `backend/rag/evaluation_dataset.json`：43 题真实评测集。
- `backend/rag/evaluation.py`：加载、校验和指标计算。
- `backend/rag/management/commands/evaluate_rag.py`：评测管理命令。
- `backend/rag/test_evaluation.py`：数据集与指标测试。

## 下一步建议

第 18 步按文档将进入安全和异常测试。与此同时，任何提高 Knowledge Agent 回答质量的改动都应重新运行第 17 步评测，并优先消除错误来源 case 和无依据回答 case；在来源正确率达到 100% 前，不建议增加 SSE、长期记忆或写工具。
