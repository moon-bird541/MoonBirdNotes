"""导出 HTML 用的自包含样式与交互脚本。

导出文件是离线单文件，读不到站内的 CSS 变量与 Vue 增强器，因此这里内联一份
最小实现，覆盖 Firefly 风格扩展语法（提示框、代码块标题/行号/行标记/折叠、
Tab 代码组）。类名与 `frontend/.../styles/blog-prose.css` 保持一致。
"""

EXPORT_STYLES = """
    .moonbird-callout {
      margin: 1.5em 0;
      padding: 1rem 1.15rem;
      border: 1px solid rgba(148, 163, 184, 0.35);
      border-radius: 12px;
      background: #f8fafc;
      color: #1f2937;
      font-style: normal;
    }
    .moonbird-callout-title {
      margin: 0 0 0.5em;
      color: #475569;
      font-size: 0.9rem;
      font-weight: 700;
      letter-spacing: 0.01em;
    }
    .moonbird-callout > p { margin: 0.5em 0; }
    .moonbird-callout > :last-child { margin-bottom: 0; }
    .moonbird-callout-note { border-color: #c7d2fe; background: #eef2ff; }
    .moonbird-callout-note .moonbird-callout-title { color: #3730a3; }
    .moonbird-callout-tip { border-color: #bbf7d0; background: #f0fdf4; }
    .moonbird-callout-tip .moonbird-callout-title { color: #166534; }
    .moonbird-callout-important { border-color: #fde68a; background: #fffbeb; }
    .moonbird-callout-important .moonbird-callout-title { color: #92400e; }
    .moonbird-callout-warning { border-color: #fed7aa; background: #fff7ed; }
    .moonbird-callout-warning .moonbird-callout-title { color: #9a3412; }
    .moonbird-callout-danger { border-color: #fecaca; background: #fef2f2; }
    .moonbird-callout-danger .moonbird-callout-title { color: #991b1b; }

    .moonbird-code {
      margin: 1.5em 0;
      border: 1px solid #1f2937;
      border-radius: 12px;
      background: #0f172a;
      overflow: hidden;
    }
    .moonbird-code-head {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.55rem 0.9rem;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      background: rgba(255, 255, 255, 0.04);
      color: #94a3b8;
      font-family: "Cascadia Code", Consolas, monospace;
      font-size: 0.78rem;
      line-height: 1.4;
    }
    .moonbird-code-dots {
      width: 0.55rem;
      height: 0.55rem;
      margin-right: 1.8rem;
      border-radius: 999px;
      background: #f2777a;
      box-shadow: 0.9rem 0 0 #f2c14e, 1.8rem 0 0 #7ec46f;
      flex: none;
    }
    .moonbird-code-lang { text-transform: uppercase; letter-spacing: 0.06em; opacity: 0.72; }
    .moonbird-code-title { margin-left: auto; color: #e2e8f0; font-weight: 600; }
    .moonbird-code > pre {
      margin: 0;
      padding: 0.9rem 1rem;
      border: none;
      border-radius: 0;
      background: transparent;
      color: #e5edf8;
      font-size: 0.875em;
      line-height: 1.7143;
      overflow-x: auto;
    }
    .moonbird-code.is-no-wrap > pre { white-space: pre; }
    .moonbird-code-line {
      display: block;
      min-height: 1.2em;
      padding: 0 0.25rem;
      margin: 0 -0.25rem;
      border-radius: 4px;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }
    .moonbird-code.is-no-wrap .moonbird-code-line { white-space: pre; overflow-wrap: normal; }
    .moonbird-code-lineno {
      display: inline-block;
      width: 2.4em;
      margin-right: 0.9em;
      color: rgba(255, 255, 255, 0.34);
      text-align: right;
      user-select: none;
    }
    .moonbird-code-line.is-mark { background: rgba(179, 132, 50, 0.18); box-shadow: inset 2px 0 0 #b38432; }
    .moonbird-code-line.is-ins { background: rgba(126, 196, 111, 0.16); box-shadow: inset 2px 0 0 #7ec46f; }
    .moonbird-code-line.is-del { background: rgba(242, 119, 122, 0.16); box-shadow: inset 2px 0 0 #f2777a; }
    .moonbird-code-mark { padding: 0.05em 0.15em; border-radius: 3px; background: rgba(179, 132, 50, 0.32); }
    .moonbird-code-note { margin-left: 0.75em; color: rgba(255, 255, 255, 0.52); font-size: 0.82em; font-style: italic; }
    .moonbird-code.has-collapse-ready:not(.is-expanded) .moonbird-code-line.is-collapsed { display: none; }
    .moonbird-code-toggle {
      display: block;
      width: 100%;
      padding: 0.5rem 1rem;
      border: none;
      border-top: 1px dashed rgba(255, 255, 255, 0.14);
      background: rgba(255, 255, 255, 0.03);
      color: #cbd5e1;
      font-size: 0.78rem;
      text-align: center;
      cursor: pointer;
    }
    .moonbird-code-toggle:hover { background: rgba(255, 255, 255, 0.07); color: #f8fafc; }

    .moonbird-code-group {
      margin: 1.5em 0;
      border: 1px solid #1f2937;
      border-radius: 12px;
      background: #0f172a;
      overflow: hidden;
    }
    .moonbird-code-tabs {
      display: flex;
      flex-wrap: wrap;
      gap: 0.25rem;
      padding: 0.4rem 0.5rem 0;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      background: rgba(255, 255, 255, 0.03);
    }
    .moonbird-code-tab {
      padding: 0.45rem 0.85rem;
      border-radius: 0.5rem 0.5rem 0 0;
      color: #94a3b8;
      font-family: "Cascadia Code", Consolas, monospace;
      font-size: 0.8rem;
      cursor: pointer;
    }
    .moonbird-code-tab:hover { color: #f8fafc; background: rgba(255, 255, 255, 0.06); }
    .moonbird-code-tab.is-active { background: rgba(255, 255, 255, 0.1); color: #f8fafc; }
    .moonbird-code-panel { display: none; }
    .moonbird-code-panel.is-active { display: block; }
    .moonbird-code-panel > .moonbird-code,
    .moonbird-code-panel > pre { margin: 0; border: none; border-radius: 0; }
"""

EXPORT_SCRIPT = """
(function () {
  function activate(group, index) {
    var tabs = group.querySelectorAll('.moonbird-code-tab');
    var panels = group.querySelectorAll('.moonbird-code-panel');
    tabs.forEach(function (tab, i) {
      tab.classList.toggle('is-active', i === index);
      tab.setAttribute('aria-selected', i === index ? 'true' : 'false');
    });
    panels.forEach(function (panel, i) {
      panel.classList.toggle('is-active', i === index);
    });
  }

  document.querySelectorAll('.moonbird-code-group').forEach(function (group) {
    var tabs = Array.prototype.slice.call(group.querySelectorAll('.moonbird-code-tab'));
    tabs.forEach(function (tab, index) {
      tab.addEventListener('click', function () { activate(group, index); });
      tab.addEventListener('keydown', function (event) {
        var next = null;
        if (event.key === 'ArrowRight') next = index + 1 >= tabs.length ? 0 : index + 1;
        if (event.key === 'ArrowLeft') next = index === 0 ? tabs.length - 1 : index - 1;
        if (event.key === 'Home') next = 0;
        if (event.key === 'End') next = tabs.length - 1;
        if (next === null) return;
        event.preventDefault();
        activate(group, next);
        tabs[next].focus();
      });
    });
    activate(group, 0);
  });

  document.querySelectorAll('.moonbird-code.has-collapse').forEach(function (block) {
    var collapsed = block.querySelectorAll('.moonbird-code-line.is-collapsed');
    if (!collapsed.length) return;
    var toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'moonbird-code-toggle';
    block.appendChild(toggle);
    block.classList.add('has-collapse-ready');
    var sync = function () {
      var expanded = block.classList.contains('is-expanded');
      toggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
      toggle.textContent = expanded ? '收起折叠代码' : '展开折叠的 ' + collapsed.length + ' 行';
    };
    toggle.addEventListener('click', function () {
      block.classList.toggle('is-expanded');
      sync();
    });
    sync();
  });
})();
"""
