# MoonBirdNotes 前端

Vue 3 + Vite 前端应用。

## 本地开发

```bash
npm install
npm run dev
```

## Playwright 前端验收

首次运行先安装 Chromium：

```bash
npx playwright install chromium
```

若环境已安装 Chrome，也可以不下载 Playwright 浏览器，直接指定系统浏览器：

```powershell
$env:PLAYWRIGHT_CHANNEL = 'chrome'
npm run test:e2e
```

执行无头验收测试：

```bash
npm run test:e2e
```

打开交互式调试界面：

```bash
npm run test:e2e:ui
```

查看最近一次 HTML 报告：

```bash
npm run test:e2e:report
```

默认情况下，Playwright 会在 `127.0.0.1:4173` 自动启动 Vite，并 mock `/api` 请求，因此不需要启动后端或数据库。若要验收一个已经运行的环境，可传入完整站点地址：

```powershell
$env:PLAYWRIGHT_BASE_URL = 'http://127.0.0.1:5173'
npm run test:e2e
```

当前核心验收覆盖：

- 未登录访问工作台会跳转到登录页，并进行必填校验。
- 管理员登录请求与首页摘要渲染正常。
- 已登录用户可进入笔记列表并退出登录。

失败时会在 `test-results/` 保存截图或 trace，HTML 报告输出到 `playwright-report/`。
