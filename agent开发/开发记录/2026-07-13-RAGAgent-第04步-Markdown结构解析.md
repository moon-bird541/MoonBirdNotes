# RAG Agent 第 04 步开发记录：实现 Markdown 结构解析

> 日期：2026-07-13  
> 状态：已完成  
> 对应文档：`agent开发/RAGAgent开发步骤.md`

## 本次完成的范围

本次完成 RAG Agent 实际执行顺序的第 4 步：把 Markdown 原文解析为稳定的顶层结构块，并保留块类型、原始 Markdown、标题层级和源码行号。

本次只负责结构识别，没有实现父片段合并、token 计数、子片段切分、Embedding 或向量索引。

## 做了什么

### 解析依赖

- 新增 `markdown-it-py==4.0.0`。
- 固定其依赖 `mdurl==0.1.2`，保持后端环境可重复安装。
- 保留现有 `Markdown==3.10.2` 和 bleach 渲染净化链路；新依赖只服务 RAG 结构解析。

### 数据契约

新增不可变的 `MarkdownBlock` 数据类，字段包括：

~~~text
block_type
content
heading_level
start_line
end_line
~~~

行号采用 1-based，`end_line` 为包含式。数据类会拒绝反向行号、非法标题层级，以及非标题块携带标题层级等解析器内部错误。

支持的块类型：

~~~text
heading
paragraph
list
blockquote
code_fence
table
image
horizontal_rule
~~~

### Markdown 解析器

- 使用 CommonMark 规则并显式启用表格 Token。
- 只输出 `level = 0` 的顶层 Token，避免列表、引用和表格内部段落被重复输出。
- `content` 从原始源码按 Token 行号截取，因此代码围栏、语言标记、表格分隔行、图片路径和链接地址不会被渲染结果替代。
- 独立图片或链接包裹的独立图片标记为 `image`；图片处于普通句子中时保留为 `paragraph`，避免拆散正文语义。
- 围栏未闭合时仍按 `code_fence` 保存，支持用户编辑过程中暂时不完整但可保存的 Markdown。
- HTML 等未单列类型以段落保留，不静默丢弃用户原文。
- 引用式链接定义通常不会生成普通块 Token，解析器会检测未被覆盖的有效源码行并作为段落补回，避免精确 URL 丢失。
- 空章节通过相邻标题块表达，不生成虚假的空正文块。
- 空 Markdown 返回空块列表；非字符串输入明确拒绝。

## 为什么这样做

- 后续父子分块必须理解 Markdown 结构，直接按固定字符数切分会破坏代码块、表格、列表和标题上下文。
- 现有 Python-Markdown 适合渲染 HTML，但没有为本场景提供稳定的源码 Token 行号映射；`markdown-it-py` 的块 Token 可以直接定位原文行范围。
- RAG 解析器保留原始 Markdown，而不是依赖渲染后的 HTML，确保 MySQL 中的 `Note.markdown_content` 始终是唯一真实来源。
- 只输出顶层块可以让第 5 步父片段分割基于单一、不重复的块序列工作。
- 行号只用于展示和辅助定位，后续写操作仍必须校验 `source_hash` 和 `section_hash`，不能把行号当成稳定主键。
- 对没有 Token 的有效行增加保底，是为了保证引用式链接和未知但可保存的 Markdown 不会在结构解析时被静默删除。

## 自动化测试

新增 15 个解析测试，覆盖：

- 一级至六级标题与标题层级。
- 围栏代码块、语言标记和未闭合围栏。
- 行内代码和 Markdown 链接。
- 有序列表与无序列表。
- 多行引用。
- 表格及表头分隔行。
- 独立图片、链接图片和正文内图片。
- 水平分割线。
- 空章节。
- 没有标题的笔记。
- 不完整的行内 Markdown。
- 引用式链接定义。
- 相同输入的确定性。
- 空 Markdown。

## 如何验证

- `python manage.py test rag.chunking.tests --noinput`：15 个解析测试全部通过。
- `python manage.py check`：通过，0 个问题。
- `python manage.py makemigrations --check --dry-run`：输出 `No changes detected`。
- `python -m pip check`：输出 `No broken requirements found`。
- `python manage.py test --noinput`：从干净测试数据库执行 116 个测试，全部通过，耗时约 33 秒。

## 文件变更

- 修改：`backend/requirements.txt`
- 修改：`backend/rag/chunking/__init__.py`
- 新增：`backend/rag/chunking/schemas.py`
- 新增：`backend/rag/chunking/parser.py`
- 新增：`backend/rag/chunking/tests.py`
- 更新：`agent开发/RAGAgent开发步骤.md`
- 新增：本开发记录

## 未完成事项与下一步

下一步是 `RAGAgent开发步骤.md` 的第 5 步：基于当前稳定块序列实现父片段分割、标题路径维护、短章节同级合并、超长章节二次切分、无标题文档回退和稳定 `section_hash`。

第 5 步必须使用最终选定 Embedding 模型的 tokenizer 计算 token，不能用字符数代替。
