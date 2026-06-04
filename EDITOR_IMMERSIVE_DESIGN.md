# 编辑器暗色沉浸式设计方案

## 设计概览

将笔记编辑页面改造为专注写作的沉浸式体验，与列表页、详情页的亮色信息密集型风格形成鲜明对比。

## 核心特征

### 视觉风格
- **深色背景**：`#0f1419` → `#1a1d23` 渐变
- **编辑器容器**：`#23262e` 略浅卡片
- **文本颜色**：`#e4e6eb` 高对比度
- **强调色**：琥珀色 `#f59e0b` 用于交互元素
- **边框**：几乎不可见 `rgba(255,255,255,0.08)`

### 布局特点
1. **内容居中**：编辑器宽度限制在 820px
2. **垂直呼吸感**：上下留白 60px
3. **版本面板**：改为右侧抽屉，默认隐藏
4. **极简工具栏**：顶部固定，半透明背景

### 交互优化
1. **全屏模式**：一键进入沉浸式写作
2. **焦点模式**：淡化非当前段落（可选）
3. **版本抽屉**：点击按钮从右侧滑出
4. **状态栏**：底部固定显示字数、保存状态

## 实现清单

### Phase 1: 基础视觉改造
- [x] 深色背景渐变
- [x] 编辑器容器居中限宽
- [x] 调整文本颜色和对比度
- [x] 移除多余装饰（边框、阴影）
- [x] 更换强调色为琥珀色

### Phase 2: 版本面板抽屉化
- [ ] 版本面板改为固定定位
- [ ] 添加滑入/滑出动画
- [ ] 添加版本按钮到工具栏
- [ ] 添加遮罩层（点击关闭）

### Phase 3: 交互增强
- [ ] 全屏模式切换
- [ ] 焦点模式（可选）
- [ ] 底部状态栏
- [ ] 快捷键支持

## 设计Token

```css
/* 颜色系统 */
--editor-bg-dark: #0f1419;
--editor-bg-medium: #1a1d23;
--editor-surface: #23262e;
--editor-surface-raised: #2d3139;

--editor-text-primary: #e4e6eb;
--editor-text-secondary: #9ca3af;
--editor-text-muted: #6b7280;

--editor-accent: #f59e0b;
--editor-accent-hover: #fbbf24;

--editor-border: rgba(255, 255, 255, 0.08);
--editor-border-hover: rgba(255, 255, 255, 0.12);

/* 间距 */
--editor-container-width: 820px;
--editor-padding-y: 60px;
--editor-padding-x: 40px;

/* 字体 */
--editor-font-family: 'JetBrains Mono', 'Consolas', monospace;
--editor-font-size: 17px;
--editor-line-height: 1.8;
```

## 完成日期
2026年6月4日
