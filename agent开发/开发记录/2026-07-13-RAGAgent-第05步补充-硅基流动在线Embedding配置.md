# RAG Agent 第 05 步补充记录：配置硅基流动在线 Embedding

> 日期：2026-07-13  
> 状态：已完成  
> 范围：在线模型环境配置与连通性验证

## 本次完成的范围

本次为后端配置硅基流动在线 Embeddings API，并验证 `BAAI/bge-m3` 能正常返回 1024 维向量。

本次没有实现第 7 步的 `SiliconFlowEmbeddingService`、重试、批处理、缓存或结构化异常；这些仍按原开发顺序完成。

## 做了什么

- 将真实 API Key 只写入 Git 已忽略的 `backend/.env`。
- 配置硅基流动 API 地址 `https://api.siliconflow.cn/v1`。
- 配置 Embedding Provider 为 `siliconflow`。
- 配置模型为 `BAAI/bge-m3`。
- 配置向量维度为 `1024`。
- 配置 Embedding 版本为 `siliconflow-bge-m3-input-v1`。
- 在 `backend/.env.example` 增加相同变量的安全占位符，没有写入真实密钥。
- 在 Django settings 中读取这些变量，并添加中文安全注释。

## 为什么这样做

- API Key 必须只存在后端环境文件，不能进入 Vue、Git、日志、错误响应或开发记录。
- Provider、模型、维度和版本分别配置，便于后续创建 Qdrant Collection、校验响应维度和触发索引版本重建。
- Django settings 现在可以统一向后续 `SiliconFlowEmbeddingService` 提供配置，业务代码不需要自行读取环境文件。
- 当前先验证配置和连通性，可以在实现批量、重试和缓存之前排除密钥或模型名称错误。

## 在线验证

使用不包含私人笔记内容的固定英文测试文本调用：

~~~text
POST https://api.siliconflow.cn/v1/embeddings
model: BAAI/bge-m3
~~~

返回结果：

~~~text
请求成功：是
模型：BAAI/bge-m3
向量数量：1
向量维度：1024
Prompt tokens：13
Total tokens：13
~~~

验证过程只输出模型、数量、维度和 token 用量，没有输出 API Key 或向量内容。

## 安全验证

- `backend/.env` 命中 `.gitignore` 规则。
- Git 跟踪文件中的真实 API Key 匹配数量为 0。
- `backend/.env.example` 只包含占位符。
- Django 安全摘要只输出 `api_key_configured = true`，不输出密钥内容或前缀。
- 本开发记录不保存密钥。

## 其他验证

- `python manage.py check`：通过，0 个问题。
- `python manage.py makemigrations --check --dry-run`：输出 `No changes detected`。
- `python manage.py test --noinput`：执行 134 个后端测试，全部通过。

## 文件变更

- 本地安全配置：`backend/.env`，已被 Git 忽略。
- 修改：`backend/.env.example`
- 修改：`backend/MoonBirdNotes/settings.py`
- 新增：本开发记录

## 下一步

下一开发步骤仍是第 6 步子片段分割。第 7 步实现 `SiliconFlowEmbeddingService` 时，将复用本次配置并补齐连接复用、批量请求、超时、429/5xx 有限重试、响应数量与维度校验、日志脱敏和关键词检索降级。
