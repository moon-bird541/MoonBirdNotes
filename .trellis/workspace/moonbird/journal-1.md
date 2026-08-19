# Journal - moonbird (Part 1)

> AI development session journal
> Started: 2026-08-16

---



## Session 1: 初始化 MoonBirdNotes Trellis 规范与项目基线

**Date**: 2026-08-16
**Task**: 初始化 MoonBirdNotes Trellis 规范与项目基线
**Branch**: `main`

### Summary

从当前源码、测试、配置、设计文档和历史开发记录中提炼项目规范，并把当前能力、未提交状态、文档偏差和验证结果写入 Trellis。

### Main Changes

- 刷新 backend 规范：目录边界、数据库/事务、错误、日志、配置与安全、质量门。
- 刷新 frontend 规范：Vue 组件、状态、运行时契约、API/安全、设计系统与质量门；删除不适用的 React Hook 模板。
- 新增 2026-08-16 当前项目基线，纠正旧 TODO 中 AI 未完成和 README 中页面/统计/Qdrant 端口等过时描述。
- 独立复核 95 个源码路径、两层索引、Markdown 链接和占位符，并修正 E2E 守卫与 Token 统计口径。

### Git Commits

(No commits - planning session)

### Testing

- [OK] Django manage.py check 通过；makemigrations --check --dry-run 通过。
- [OK] Django 全量 396 项测试通过；前端 npm run build 通过。
- [WARN] Playwright 使用系统 Edge：5/6 通过；现有 getByText('1,200') 严格定位匹配两处导致 1 项失败。

### Status

[OK] **Completed**

### Next Steps

- 修复 Playwright 重复文本定位和现有 el-radio-* 解析警告后重跑 E2E。
- 单独校正 README 的已实现页面、后续方向、Qdrant 端口与 Token 统计描述。
- 审阅并分批提交当前 Trellis 初始化和既有产品改动，再归档 00-bootstrap-guidelines。
