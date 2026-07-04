# MoonBirdNotes 安全与完善建议

> 审计范围：`backend/`（settings、models、serializers、views、accounts 认证、throttle、signals、tests）与 `frontend/moonsbirdnotrs_vue/src`（api.js、路由守卫、v-html 渲染、依赖）。
> 定位：单用户（管理员本人）笔记 / 日记系统。下面的风险评级已结合“单用户”这一前提做过调整。
> 审计日期：2026-07-01

---

## 结论速览

整体架构清晰，认证用 JWT + `IsAdminUser`，Markdown 渲染在服务端用 bleach 做了 XSS 清洗，上传做了大小 / 扩展名 / magic bytes 三重校验，测试覆盖也不错。没有发现能被直接利用的高危漏洞。

高优先级问题已处理，登录限流缓存、搜索分页和统计聚合也已完成基础优化。后续重点关注的是一批**生产部署前必须处理的配置项**。

| 级别 | 数量 | 摘要 |
|------|------|------|
| 高 | 0 | H1 / H2 已修复 |
| 中 | 0 | M1 已修复 |
| 低 | 0 | L1-L6 已修复 |

---

## 高优先级

### H1. `.env` 没有被 `.gitignore` 忽略（已修复）

`backend/.env` 存放 `SECRET_KEY`、`DB_PASSWORD`、`ADMIN_PASSWORD`。修复前 `.gitignore` 只忽略了 `.env.local` / `.env.*.local`，**没有显式忽略 `backend/.env`**。

已在 `.gitignore` 中显式加入 `.env` 和 `backend/.env`。目前 `git check-ignore -v backend/.env` 命中忽略规则，`git ls-files` 里只应保留 `backend/.env.example`，真实密钥文件不会被普通 `git add .` 带入提交。

**后续建议**：如果怀疑真实 `.env` 曾经被提交过，需要轮换 `SECRET_KEY` / 数据库密码 / 管理员密码，并用 `git filter-repo` 清历史。

### H2. `purge_expired_trash_notes()` 挂在几乎每个读请求上（已修复）

修复前，`views.py` 里列表、详情、搜索、统计、导出、图片列表等**大量 GET 接口的第一行都调用了 `purge_expired_trash_notes()`**，而这个函数会查询过期笔记并执行 `delete()`（含文件删除）。

问题：
- **违反 HTTP 语义**：GET 请求本应是只读的，这里却可能产生删除写操作。
- **性能**：每次读都多一次 `filter + 循环删除`，笔记多时是额外负担。
- **并发**：多个 GET 同时命中同一批过期笔记时，会对同一文件 / 同一行重复删除，可能抛异常。

**已处理**：
- 已从 API 请求路径中移除所有 `purge_expired_trash_notes()` 调用，GET 请求不再触发永久删除。
- 已新增独立清理服务 `notes.services.trash.purge_expired_trash_notes()`。
- 已新增 management command：`python manage.py purge_trash`，可由 Windows 计划任务 / cron 每天执行一次。

**验证**：新增测试确认普通笔记列表 GET 不会清理过期回收站笔记，且 `purge_trash` 只会清理超过保留期的回收站笔记。

---

## 中优先级

### M1. 上传的媒体文件没有访问控制（已修复）

`MEDIA_ROOT` 下的笔记原始 `.md` 文件和图片，通过 `/media/...` 直接暴露。开发环境由 Django 提供，生产环境通常由 Nginx 直接托管。**任何知道 URL 的人都能读取**，路径又是 `note_images/YYYY/MM/DD/原文件名` 这种半可猜测结构。

对单用户系统这不是致命问题，但笔记内容（含图片、原始 md）本质上是私密数据，却以公开静态资源方式对外。

**已处理**：
- `/media/<path>` 已改为进入后端 `ProtectedMediaView`，使用现有 JWT Cookie / Authorization header 认证，并要求 `IsAdminUser`。
- 匿名访问媒体文件返回 401，普通已登录但非管理员用户返回 403。
- 已阻止 `../` 路径穿越读取 `MEDIA_ROOT` 外文件。
- JWT Cookie Path 已从 `/api/` 调整为 `/`，确保已登录用户在浏览器中加载 `/media/...` 图片时会携带 httpOnly access cookie。

**生产部署注意**：Nginx 不能再直接公开托管 `/media/`，否则会绕过 Django 鉴权。生产环境如果需要更高性能，可后续升级为“Django 鉴权 + `X-Accel-Redirect` 内部转发”的方式。

### M2. 登录限流用的是进程内缓存（已修复）

修复前，`settings.py` 里 `CACHES` 用 `LocMemCache`，而 `AdminLoginRateThrottle` 依赖它记录失败次数。

- LocMemCache 是**每个进程独立**的。生产用 gunicorn/uwsgi 多 worker 时，5 次/分钟的限流实际上变成“每 worker 5 次”，被稀释。
- 重启进程即清零。

**已处理**：
- 已新增 `CACHE_URL` 配置，配置后使用 Django 内置 Redis cache backend。
- `DEBUG=True` 且未配置 `CACHE_URL` 时仍允许本地开发使用 LocMemCache。
- `DEBUG=False` 且未配置 `CACHE_URL` 时直接抛出配置错误，避免生产环境静默退回进程内缓存。
- 已在 `requirements.txt` 增加 Redis 客户端依赖，并在 `.env.example` 补充 `CACHE_URL` 示例。

生产示例：
```
CACHE_URL=redis://127.0.0.1:6379/1
```

### M3. 搜索 / 统计在 Python 层做全表扫描（已修复）

修复前：
- `GlobalSearchView` 把所有匹配的普通笔记和日记全部取出，在 Python 里拼列表、排序、再分页；日记日期匹配还额外 `for entry in get_active_diary_entries()` 遍历全部日记。
- `NoteSummaryView` 对每篇笔记跑一遍正则统计字数，是一次全表 + 逐条计算。

**已处理**：
- 已在 `Note` 上新增 `word_count` 冗余字段，保存笔记 / 日记正文时自动更新，迁移会为历史数据回填。
- `NoteSummaryView` 改为数据库 `SUM(word_count)` 聚合，避免每次逐篇正则重算。
- `GlobalSearchView` 改为按数据库排序后只取当前页需要的候选结果，再做普通笔记 / 日记的页内合并，不再加载全部匹配结果。
- 日记日期匹配改为数据库 `Cast(diary_date)` 后过滤，不再 Python 遍历全部日记。

**后续可选**：`markdown_content__icontains` 仍是普通模糊匹配；如果笔记量增长到需要真正全文检索，可单独升级为 MySQL `FULLTEXT` + ngram 解析器。

### M4. 退出登录 / token 失效机制不完整（已修复）

前端 logout 只是清掉 localStorage，服务端没有让 token 失效。access token 30 分钟、refresh token 7 天，在过期前**始终有效**——如果 token 被泄露，登出并不能止损。

**已处理**：
- 已启用 `rest_framework_simplejwt.token_blacklist`。
- 已开启 `ROTATE_REFRESH_TOKENS` / `BLACKLIST_AFTER_ROTATION`，刷新 token 后旧 refresh token 会自动进入黑名单。
- 已新增 `/api/logout/`，退出登录时把当前 refresh token 拉黑；该接口不依赖 access token，避免 access 过期后无法正常失效 refresh token。
- 前端退出登录会先调用后端 logout，再清理本地 `access_token` / `refresh_token` / `current_user`；即使 token 已经失效，本地退出也会正常完成。

**验证**：新增测试覆盖 logout 拉黑 refresh token、refresh 轮换后旧 token 被拉黑、缺少 / 非法 refresh token 返回 400。

### M5. 前端浮动预览用了未清洗的 HTML（已修复）

服务端返回的 `rendered_html` 已经过 bleach 清洗，`v-html="version.rendered_html"` / `v-html="uploadedNote.rendered_html"` 是安全的。

此前 `FloatingPreview` 会直接把传入的 `bodyHtml` 交给 `v-html` 渲染。虽然当前主代码里标题和标签预览已经先做了 `escapeHtml`，但这个组件本身没有任何二次净化，一旦未来再次传入编辑器生成的 HTML，仍然会把风险重新打开。

**已处理**：
- 已引入 `DOMPurify`，`FloatingPreview` 在执行 `v-html` 前会先对 `bodyHtml` 做客户端净化。
- 标题 / 标签预览原有的 `escapeHtml` 仍然保留，客户端净化作为第二道防线。

**验证**：前端生产构建通过，浮动预览的渲染链路已改为 “输入 HTML -> DOMPurify -> `v-html`”。

### M6. JWT 存在 localStorage（XSS 会导致 token 被盗，已修复）

token 放在 `localStorage`，一旦发生 XSS，脚本可直接读取并外传 token。当前 XSS 面已被 bleach 收窄，但这与 M5 是叠加关系：清洗一旦被绕过，后果直接升级为账号劫持。

**已处理**：
- 登录 / 刷新 / 退出登录改为通过 `httpOnly`、`SameSite=Lax` 的 cookie 流转 JWT，前端不再把 `access_token` / `refresh_token` 写入 `localStorage`。
- 默认认证改为优先从 cookie 读取 access token，同时保留 `Authorization` header 兼容非浏览器客户端。
- 前端写请求会自动附带 `X-CSRFToken`，后端在“cookie 认证成功”的情况下强制执行 CSRF 校验。
- 新增 `/api/session/` 用于页面刷新后恢复登录态，并在恢复时同步下发 CSRF cookie。

**验证**：新增测试覆盖登录下发 httpOnly cookie、cookie 刷新 / 退出登录、session 恢复，以及 cookie 认证下缺少 CSRF 头时写请求会被拒绝。

---

## 低优先级 / 完善项

- **L1. TOC 锚点失效（已修复）**：`render_markdown_content` 已允许标题标签保留 `id` 属性，TOC 生成的目录锚点不再被 bleach 清掉；同时新增数据迁移重渲染历史 `rendered_html`，避免旧笔记和旧版本继续保留无锚点的 HTML。
- **L2. 图片列表接口无分页（已修复）**：`NoteImageListCreateView` 已接入后端分页，默认每页 24 张，支持 `page_size` 且最大 60；同时补充 `search` / `note_id` 查询参数，图片管理页的搜索和按内容筛选会在分页前完成，不再一次性拉取全部图片。
- **L3. 缺少“未授权访问被拒绝”的测试（已修复）**：已补充匿名访问笔记列表、详情、创建、预览、图片、日记、回收站等接口返回 401 的测试，并补充普通已登录用户访问同一批接口返回 403 的测试；同时新增真实 `/api/login/` 请求触发登录限流后返回 429 的测试。
- **L4. `a` 标签允许 `target` 但无 `rel`（已修复）**：Markdown 渲染清洗阶段已对 `target="_blank"` 的链接自动补充 `rel="noopener noreferrer"`，并保留已有 `rel` 值后合并必要属性；同时新增数据迁移重渲染历史 `Note` / `NoteVersion` 的 `rendered_html`，让旧链接也完成修复。
- **L5. 管理员密码更新语义（已修复）**：README 已新增“管理员账号与密码”说明，明确 `ADMIN_PASSWORD` 只用于首次创建默认管理员，已存在账号不会因修改 `.env` 自动重置密码；`.env.example` 也补充了改密提醒，后续改密码应使用 `python manage.py changepassword <ADMIN_USERNAME>` 或 Django admin 后台。
- **L6. 部分 N+1 / 循环建对象（已修复）**：已新增统一的 `get_or_create_tags()`，先批量查询已有标签，再批量创建缺失标签，并按调用方传入顺序返回标签对象；上传、创建、编辑保存、版本恢复和批量标签更新都已改为复用该 helper，不再在循环里逐个 `get_or_create`。

---

## 生产部署前检查清单

- [ ] `.env` 已加入 `.gitignore`，且 `DEBUG=False`（`settings.py` 默认 False，但 `.env.example` 是 `DEBUG=True`，别照抄到生产）。
- [ ] `ALLOWED_HOSTS` 配成真实域名。
- [ ] `SECRET_KEY` 为随机生成的强密钥，且从未进过 git 历史。
- [x] `CACHES` 换成 Redis 共享缓存（否则登录限流形同虚设，见 M2）。
- [x] 回收站清理改为定时任务（见 H2）。
- [x] logout 会拉黑 refresh token，且 refresh 轮换后旧 token 自动失效（见 M4）。
- [x] 媒体文件已通过 Django 鉴权访问；生产环境不要让 Nginx 直接公开托管 `/media/`（见 M1）。
- [ ] 若前后端跨域部署，需引入 `django-cors-headers` 并配置白名单（当前未安装，说明目前是同源 / 反代 `/api`，跨域部署会直接失败）。
- [ ] 若在反向代理后启用 HTTPS，设置 `SECURE_PROXY_SSL_HEADER`，避免 `SECURE_SSL_REDIRECT` 无限重定向。
- [ ] 用 gunicorn/uwsgi + Nginx，而非 `runserver`；确认 `runserver.*.log` 不会进仓库（`*.log` 已在 `.gitignore`，OK）。

---

## 做得好的地方（保留）

- Markdown 渲染服务端用 bleach 做了标签 / 属性 / 协议白名单清洗，`javascript:`、`onerror`、`<script>` 都能拦掉，并有对应测试。
- 图片上传做了扩展名 + `content_type` + magic bytes 三重校验，不只信任客户端声明的类型。
- 登录失败信息统一为“用户名或密码错误”，不泄露用户名是否存在；且校验了 `is_superuser` / `is_active`。
- 上传大小限制在 settings 和 serializer 两处都设了。
- 软删除 + 30 天回收站 + 彻底删除同步清文件，数据生命周期设计完整。
- 生产安全头（HSTS、SSL 重定向、Secure Cookie、nosniff、X-Frame-Options）在 `DEBUG=False` 时都开了。
