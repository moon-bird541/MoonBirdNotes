# 参与开发

这个项目目前是个人自用的私密知识库，代码按「先把边界做稳，再堆功能」的顺序推进。
在动手改代码前，先读这两份文档，它们比代码更权威：

- `PRODUCT_RULES.md` —— 产品边界。笔记 / 日记 / 标签 / 图片 / 搜索的规则写在这里，代码与它冲突时以它为准。
- `.trellis/spec/` —— 按层划分的编码约定（后端 Django、前端 Vue）。

## 环境准备

后端：

```bash
cd backend
cp .env.example .env          # 然后填 SECRET_KEY / 数据库 / 管理员账号
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

RAG 相关功能需要 Qdrant 与 SiliconFlow（或兼容的 Embedding 服务）：

```bash
docker compose up -d qdrant
cd backend && python manage.py initialize_qdrant
```

前端：

```bash
cd frontend/moonsbirdnotrs_vue
npm install
npm run dev
```

## 提交前必须跑通的检查

| 改动范围 | 至少跑 |
| --- | --- |
| `backend/accounts`、`backend/notes` | `cd backend && python manage.py test accounts notes` |
| `backend/agent`、`backend/rag` | `cd backend && python manage.py test agent rag` |
| 模型 / 迁移 | `python manage.py makemigrations --check --dry-run` |
| 前端任意改动 | `cd frontend/moonsbirdnotrs_vue && npm run test:unit && npm run build` |
| 编辑器 / 交互改动 | 额外跑 `npm run test:e2e`（需要后端在跑） |

完整的后端测试是 `python manage.py test`（约 400 项），CI 会跑这一档。

## 前端单元测试的边界

`src/**/__tests__/**/*.test.js` 只放**不依赖真实浏览器和真实后端**的逻辑：
info-string 解析、表格布局换算、Markdown 净化、纯函数式的选区计算。

需要真实编辑器（toast-ui / ProseMirror）或真实接口的用例，写进 `e2e/*.spec.js`，
不要为了「能测」把业务代码改写成另一套实现。

## 代码风格

- 后端：Django 6，函数式视图与 DRF 混用；新代码用 `from __future__ import annotations` 与类型标注，不为老代码做无关重构。
- 前端：Vue 3 `<script setup>`，逻辑优先抽到 `src/utils/` 并配单测；组件只负责编排与渲染。
- 注释写「为什么」，不写「做了什么」。中文注释与现有文件保持一致。

## 提交信息

沿用现有风格：`type(scope): 说明`，例如 `fix(editor): 空笔记输入时编辑区塌陷不可见`。
类型常用 `feat` / `fix` / `refactor` / `test` / `chore` / `docs`。

## 分支

`main` 用于发布基线，日常改动在 `codex/develop` 上进行。
