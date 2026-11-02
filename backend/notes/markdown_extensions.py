"""Firefly 风格 Markdown 扩展语法（后端渲染）。

覆盖三类语法，产出与前端 `src/utils/markdownExtensions.js` 完全一致的 HTML 契约：

1. 提醒框（Callouts）
   - GitHub / Obsidian 风格：`> [!NOTE] 自定义标题`
   - Docusaurus / VitePress 容器：`:::tip[自定义标题] ... :::`
2. 代码块 info-string：```lang title="a.js" {1,3-5} ins={6} del={7}
   showLineNumbers startLineNumber=5 collapse={1-4} wrap=false frame=none
3. 代码组：`::: code-group labels=[a.js, b.py]` 包住多个代码块

前端只负责交互（折叠、标签切换）与样式，类名与 data 属性保持一一对应。
"""

from __future__ import annotations

import re
from html import escape

from markdown.extensions import Extension
from markdown.preprocessors import Preprocessor
from markdown.treeprocessors import Treeprocessor

# ── 提醒框类型表 ────────────────────────────────────────────────────────────
# canonical -> (family, 默认标题, 图标)
# family 只决定配色分组，canonical 决定默认文案；别名统一折叠到 canonical。
CALLOUT_TYPES = {
    'note': ('note', '注意', 'ℹ'),
    'abstract': ('note', '摘要', '📋'),
    'info': ('note', '信息', 'ℹ'),
    'todo': ('note', '待办', '☐'),
    'tip': ('tip', '提示', '✦'),
    'success': ('tip', '成功', '✔'),
    'question': ('tip', '问题', '❓'),
    'important': ('important', '重要', '❢'),
    'example': ('important', '示例', '🧪'),
    'warning': ('warning', '警告', '⚠'),
    'caution': ('danger', '小心', '⛔'),
    'danger': ('danger', '危险', '⛔'),
    'failure': ('danger', '失败', '✖'),
    'bug': ('danger', '缺陷', '🐞'),
    'quote': ('note', '引用', '❝'),
}

CALLOUT_ALIASES = {
    'summary': 'abstract',
    'tldr': 'abstract',
    'hint': 'tip',
    'check': 'success',
    'done': 'success',
    'help': 'question',
    'faq': 'question',
    'attention': 'caution',
    'error': 'danger',
    'fail': 'failure',
    'missing': 'failure',
    'cite': 'quote',
}


def resolve_callout_type(name):
    """把任意别名解析成 (canonical, family, label, icon)，未知类型返回 None。"""
    key = (name or '').strip().lower()
    key = CALLOUT_ALIASES.get(key, key)
    meta = CALLOUT_TYPES.get(key)
    if not meta:
        return None
    family, label, icon = meta
    return key, family, label, icon


# ── 代码块 info-string 解析 ─────────────────────────────────────────────────

TERMINAL_LANGUAGES = {
    'bash',
    'bat',
    'cmd',
    'console',
    'fish',
    'nu',
    'powershell',
    'ps',
    'ps1',
    'sh',
    'shell',
    'shellsession',
    'terminal',
    'zsh',
}

_QUOTES = ('"', "'")
_KNOWN_FLAGS = re.compile(
    r'^(showLineNumbers|wrap|preserveIndent|frame|title|startLineNumber|collapse|lang|mark|ins|del)(=|$)'
)
_RANGE_RE = re.compile(r'^(\d+)(?:\s*-\s*(\d+))?$')
_LABELLED_RE = re.compile(r'^(["\'])(.*?)\1\s*:\s*(.+)$')


def split_info_tokens(info):
    """按空白拆分 info-string，保留引号 / 花括号 / 正则内部的空白。"""
    source = str(info or '')
    tokens = []
    current = ''
    quote = ''
    brace_depth = 0
    in_regex = False

    for index, char in enumerate(source):
        previous = source[index - 1] if index else ''

        if quote:
            current += char
            if char == quote and previous != '\\':
                quote = ''
            continue

        if in_regex:
            current += char
            if char == '/' and previous != '\\':
                in_regex = False
            continue

        if char == '{':
            brace_depth += 1
            current += char
            continue

        if char == '}':
            brace_depth = max(0, brace_depth - 1)
            current += char
            continue

        if brace_depth == 0 and char in _QUOTES:
            quote = char
            current += char
            continue

        if brace_depth == 0 and char == '/' and not current:
            in_regex = True
            current += char
            continue

        if brace_depth == 0 and char.isspace():
            if current:
                tokens.append(current)
                current = ''
            continue

        current += char

    if current:
        tokens.append(current)

    return tokens


def parse_line_ranges(spec):
    """解析 `{1,3-5}` / `{"说明":7-8, 12}`。"""
    source = str(spec or '').strip()
    if source.startswith('{'):
        source = source[1:]
    if source.endswith('}'):
        source = source[:-1]

    ranges = []
    for chunk in source.split(','):
        piece = chunk.strip()
        if not piece:
            continue

        label = ''
        rest = piece
        labelled = _LABELLED_RE.match(piece)
        if labelled:
            label = labelled.group(2)
            rest = labelled.group(3)

        for part in rest.strip().split():
            match = _RANGE_RE.match(part)
            if not match:
                continue
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else start
            if start < 1:
                continue
            ranges.append({'start': start, 'end': max(start, end), 'label': label})

    return ranges


def _parse_mark_value(raw):
    value = str(raw or '').strip()
    if not value:
        return None

    if value.startswith('{'):
        ranges = parse_line_ranges(value)
        return {'kind': 'lines', 'ranges': ranges} if ranges else None

    if value.startswith('/') and value.endswith('/') and len(value) > 2:
        return {'kind': 'regex', 'regex': value[1:-1]}

    if value[0] in _QUOTES and value.endswith(value[0]) and len(value) > 1:
        text = value[1:-1]
        return {'kind': 'text', 'text': text} if text else None

    return None


def _parse_bool(value, fallback=True):
    if value is None:
        return fallback
    normalized = str(value).strip().lower()
    if normalized in ('false', 'no', '0', 'off'):
        return False
    if normalized in ('true', 'yes', '1', 'on'):
        return True
    return fallback


def _unquote(value=''):
    trimmed = str(value).strip()
    if len(trimmed) > 1 and trimmed[0] in _QUOTES and trimmed.endswith(trimmed[0]):
        return trimmed[1:-1]
    return trimmed


def parse_fence_info(info=''):
    """解析完整 fence info-string，规则与前端 `parseFenceInfo` 保持一致。"""
    tokens = split_info_tokens(info)
    result = {
        'lang': '',
        'title': '',
        'frame': 'auto',
        'wrap': True,
        'preserve_indent': True,
        'show_line_numbers': False,
        'start_line_number': 1,
        'collapse': [],
        'marks': [],
        'rest': '',
    }
    leftovers = []

    for index, token in enumerate(tokens):
        assignment = re.match(r'^([A-Za-z][\w-]*)=(.*)$', token)
        key = assignment.group(1) if assignment else ''
        value = assignment.group(2) if assignment else ''

        if not assignment and index == 0 and not _KNOWN_FLAGS.match(token) and not token.startswith('{'):
            mark_value = _parse_mark_value(token)
            if mark_value and mark_value['kind'] == 'lines':
                result['marks'].append({'type': 'mark', 'kind': 'lines', 'ranges': mark_value['ranges']})
                continue
            result['lang'] = token.lstrip('.')
            continue

        if not assignment:
            if token.startswith('{'):
                ranges = parse_line_ranges(token)
                if ranges:
                    result['marks'].append({'type': 'mark', 'kind': 'lines', 'ranges': ranges})
                    continue
            mark_value = _parse_mark_value(token)
            if mark_value:
                result['marks'].append({'type': 'mark', **mark_value})
                continue
            if token == 'showLineNumbers':
                result['show_line_numbers'] = True
                continue
            if token == 'wrap':
                result['wrap'] = True
                continue
            if token == 'preserveIndent':
                result['preserve_indent'] = True
                continue
            leftovers.append(token)
            continue

        if key == 'lang':
            result['lang'] = _unquote(value).lstrip('.')
        elif key == 'title':
            result['title'] = _unquote(value)
        elif key == 'frame':
            frame = _unquote(value)
            result['frame'] = frame if frame in ('code', 'terminal', 'none', 'auto') else 'auto'
        elif key == 'wrap':
            result['wrap'] = _parse_bool(value, True)
        elif key == 'preserveIndent':
            result['preserve_indent'] = _parse_bool(value, True)
        elif key == 'showLineNumbers':
            result['show_line_numbers'] = _parse_bool(value, True)
        elif key == 'startLineNumber':
            try:
                parsed = int(_unquote(value))
            except (TypeError, ValueError):
                parsed = 1
            result['start_line_number'] = parsed if parsed > 0 else 1
        elif key == 'collapse':
            result['collapse'] = parse_line_ranges(value)
        elif key in ('mark', 'ins', 'del'):
            mark_value = _parse_mark_value(value)
            if mark_value:
                result['marks'].append({'type': key, **mark_value})
        else:
            leftovers.append(token)

    result['rest'] = ' '.join(leftovers)
    return result


_MARK_WEIGHT = {'mark': 1, 'ins': 2, 'del': 3}


def build_line_mark_map(marks, lines):
    """把 marks 展开成 {行号: {'type': …, 'label': …}}，del > ins > mark。"""
    mark_map = {}

    def set_mark(line_number, mark_type, label=''):
        if line_number < 1:
            return
        existing = mark_map.get(line_number)
        if existing and _MARK_WEIGHT[mark_type] <= _MARK_WEIGHT[existing['type']]:
            return
        mark_map[line_number] = {'type': mark_type, 'label': label}

    for mark in marks:
        kind = mark.get('kind')
        if kind == 'lines':
            for line_range in mark.get('ranges', []):
                for line_number in range(line_range['start'], line_range['end'] + 1):
                    set_mark(line_number, mark['type'], line_range.get('label', ''))
            continue

        if kind == 'text' and mark.get('text'):
            for index, line in enumerate(lines):
                if mark['text'] in line:
                    set_mark(index + 1, mark['type'])
            continue

        if kind == 'regex' and mark.get('regex'):
            try:
                pattern = re.compile(mark['regex'])
            except re.error:
                continue
            for index, line in enumerate(lines):
                if pattern.search(line):
                    set_mark(index + 1, mark['type'])

    return mark_map


def _detect_frame(info):
    if info['frame'] != 'auto':
        return info['frame']
    return 'terminal' if info['lang'].lower() in TERMINAL_LANGUAGES else 'code'


def _diff_marks(lines):
    marks = []
    for index, line in enumerate(lines):
        if line.startswith('+') and not line.startswith('+++'):
            marks.append({'type': 'ins', 'kind': 'lines', 'ranges': [{'start': index + 1, 'end': index + 1, 'label': ''}]})
        elif line.startswith('-') and not line.startswith('---'):
            marks.append({'type': 'del', 'kind': 'lines', 'ranges': [{'start': index + 1, 'end': index + 1, 'label': ''}]})
    return marks


def _inline_markup(line, marks):
    """按 text / regex 标记做行内高亮，返回已转义的 HTML。"""
    for mark in marks:
        candidate = None
        if mark.get('kind') == 'text' and mark.get('text'):
            index = line.find(mark['text'])
            if index >= 0:
                candidate = (index, index + len(mark['text']))
        elif mark.get('kind') == 'regex' and mark.get('regex'):
            try:
                match = re.search(mark['regex'], line)
            except re.error:
                match = None
            if match:
                candidate = (match.start(), match.end())

        if candidate:
            start, end = candidate
            return (
                f'{escape(line[:start])}<span class="moonbird-code-mark">'
                f'{escape(line[start:end])}</span>{escape(line[end:])}'
            )

    return escape(line)


def _collapse_spec(collapse):
    return ','.join(f'{line_range["start"]}-{line_range["end"]}' for line_range in collapse)


def build_code_block_html(code, info=None):
    """生成规范化的代码块 HTML。

    没有任何扩展参数的普通代码块会退化成 `<pre><code class="language-x">`，
    保证既有笔记的排版与安全契约完全不变。
    """
    parsed = info or parse_fence_info('')
    code_text = str(code or '')
    if code_text.endswith('\n'):
        code_text = code_text[:-1]
    lines = code_text.split('\n')

    marks = list(parsed.get('marks') or [])
    lang = parsed.get('lang') or ''
    if lang.lower() == 'diff' and not any(mark['type'] != 'mark' for mark in marks):
        marks.extend(_diff_marks(lines))

    collapse = parsed.get('collapse') or []
    has_frame_override = parsed.get('frame') != 'auto'
    is_special = bool(
        parsed.get('title')
        or collapse
        or parsed.get('show_line_numbers')
        or parsed.get('start_line_number', 1) > 1
        or has_frame_override
        or parsed.get('rest')
        or marks
    )

    language_class = f' class="language-{escape(lang)}"' if lang else ''

    if not is_special:
        return f'<pre><code{language_class}>{escape(code_text)}</code></pre>'

    mark_map = build_line_mark_map(marks, lines)
    frame = _detect_frame(parsed)
    start = parsed.get('start_line_number') or 1

    classes = ['moonbird-code']
    if parsed.get('show_line_numbers'):
        classes.append('has-line-numbers')
    if frame != 'none':
        classes.append(f'is-frame-{frame}')
    if not parsed.get('wrap', True):
        classes.append('is-no-wrap')
    if collapse:
        classes.append('has-collapse')

    attrs = [f'class="{" ".join(classes)}"']
    if lang:
        attrs.append(f'data-mb-lang="{escape(lang)}"')
    if parsed.get('title'):
        attrs.append(f'data-mb-title="{escape(parsed["title"])}"')
    if collapse:
        attrs.append(f'data-mb-collapse="{escape(_collapse_spec(collapse))}"')
    if start > 1:
        attrs.append(f'data-mb-start="{start}"')

    parts = []
    if frame != 'none':
        dots = '<span class="moonbird-code-dots" aria-hidden="true"></span>' if frame == 'terminal' else ''
        title = (
            f'<span class="moonbird-code-title">{escape(parsed["title"])}</span>'
            if parsed.get('title')
            else ''
        )
        lang_label = escape(lang or 'text')
        parts.append(
            '<div class="moonbird-code-head">'
            f'{dots}<span class="moonbird-code-lang">{lang_label}</span>{title}'
            '</div>'
        )

    line_parts = []
    for index, line in enumerate(lines):
        line_number = index + 1
        mark = mark_map.get(line_number)
        line_classes = ['moonbird-code-line']
        if mark:
            line_classes.append(f'is-{mark["type"]}')
        if any(rng['start'] <= line_number <= rng['end'] for rng in collapse):
            line_classes.append('is-collapsed')
        number_html = (
            f'<span class="moonbird-code-lineno">{start + line_number - 1}</span>'
            if parsed.get('show_line_numbers')
            else ''
        )
        note_html = (
            f'<span class="moonbird-code-note">{escape(mark["label"])}</span>'
            if mark and mark.get('label')
            else ''
        )
        line_parts.append(
            f'<span class="{" ".join(line_classes)}">{number_html}'
            f'<span class="moonbird-code-text">{_inline_markup(line, marks)}</span>'
            f'{note_html}</span>'
        )

    pre_class = 'moonbird-code-pre has-line-numbers' if parsed.get('show_line_numbers') else 'moonbird-code-pre'
    parts.append(f'<pre class="{pre_class}"><code{language_class}>{"".join(line_parts)}</code></pre>')

    return f'<div {" ".join(attrs)}>{"".join(parts)}</div>'


# ── 代码组 ─────────────────────────────────────────────────────────────────

EMOJI_SHORTCODES = {
    'package': '📦',
    'yarn': '🧶',
    'npm': '📦',
    'pnpm': '📦',
    'rocket': '🚀',
    'fire': '🔥',
    'star': '⭐',
    'bulb': '💡',
    'warning': '⚠️',
    'gear': '⚙️',
    'hammer': '🔨',
    'book': '📖',
    'memo': '📝',
    'link': '🔗',
}

_LABELS_RE = re.compile(r'labels=\[(?P<labels>[^\]]*)\]')


def _replace_emoji(label):
    return re.sub(r':([a-z0-9_+-]+):', lambda match: EMOJI_SHORTCODES.get(match.group(1), match.group(0)), label)


def parse_code_group_labels(rest, count):
    match = _LABELS_RE.search(rest or '')
    labels = []
    if match:
        for chunk in match.group('labels').split(','):
            label = chunk.strip().strip('"').strip("'").strip()
            if label:
                labels.append(_replace_emoji(label))
    while len(labels) < count:
        labels.append(f'Tab {len(labels) + 1}')
    return labels[:count]


def build_code_group_html(panels):
    """panels: [{'label': str, 'html': str}]"""
    if not panels:
        return ''

    tab_parts = []
    panel_parts = []
    for index, panel in enumerate(panels):
        active = ' is-active' if index == 0 else ''
        selected = 'true' if index == 0 else 'false'
        tab_parts.append(
            f'<span class="moonbird-code-tab{active}" role="tab" tabindex="0" '
            f'aria-selected="{selected}">{escape(panel["label"])}</span>'
        )
        panel_parts.append(f'<div class="moonbird-code-panel{active}">{panel["html"]}</div>')

    return (
        '<div class="moonbird-code-group">'
        f'<div class="moonbird-code-tabs" role="tablist">{"".join(tab_parts)}</div>'
        f'<div class="moonbird-code-panels">{"".join(panel_parts)}</div>'
        '</div>'
    )


# ── markdown 扩展本体 ──────────────────────────────────────────────────────

FENCE_OPEN_RE = re.compile(r'^(?P<fence>`{3,}|~{3,})[ \t]*(?P<info>.*?)[ \t]*$')
DIRECTIVE_OPEN_RE = re.compile(r'^(?P<fence>:{3,})\s*(?P<name>[A-Za-z][\w-]*)\s*(?P<rest>.*)$')
CALLOUT_MARKER_RE = re.compile(r'^\[!(?P<name>[A-Za-z][\w-]*)\]\s*(?P<title>.*)$')

_INNER_EXTENSIONS = None


def _fence_closer(fence):
    return re.compile(r'^' + re.escape(fence[0]) + '{' + str(len(fence)) + r',}[ \t]*$')


def _split_fence_blocks(lines):
    """把一段行拆成 [{'kind': 'code'|'text', …}]，只识别顶层围栏。"""
    segments = []
    buffer = []
    index = 0
    total = len(lines)

    while index < total:
        line = lines[index]
        match = FENCE_OPEN_RE.match(line)
        if not match:
            buffer.append(line)
            index += 1
            continue

        fence = match.group('fence')
        closer = _fence_closer(fence)
        cursor = index + 1
        code_lines = []
        closed = False
        while cursor < total:
            if closer.match(lines[cursor]):
                closed = True
                break
            code_lines.append(lines[cursor])
            cursor += 1

        if not closed:
            buffer.append(line)
            index += 1
            continue

        if buffer:
            segments.append({'kind': 'text', 'lines': buffer})
            buffer = []

        segments.append({'kind': 'code', 'info': match.group('info'), 'code': '\n'.join(code_lines)})
        index = cursor + 1

    if buffer:
        segments.append({'kind': 'text', 'lines': buffer})

    return segments


def get_inner_extensions():
    """容器内部内容复用同一套扩展，保证嵌套语法一致。"""
    global _INNER_EXTENSIONS
    if _INNER_EXTENSIONS is None:
        _INNER_EXTENSIONS = ['extra', 'fenced_code', 'tables', MoonBirdMarkdownExtension()]
    return _INNER_EXTENSIONS


def render_inner_markdown(text):
    import markdown as markdown_module

    return markdown_module.markdown(text, extensions=get_inner_extensions())


class MoonBirdDirectivePreprocessor(Preprocessor):
    """把 `:::` 容器归一化：提醒框转 blockquote，代码组直接渲染成 HTML。"""

    def run(self, lines):
        if not any(':::' in line for line in lines):
            return lines

        output = []
        index = 0
        total = len(lines)

        while index < total:
            line = lines[index]
            match = DIRECTIVE_OPEN_RE.match(line)
            name = (match.group('name') or '').lower() if match else ''
            callout = resolve_callout_type(name) if match else None
            is_code_group = bool(match) and name == 'code-group'

            if not match or (not callout and not is_code_group):
                output.append(line)
                index += 1
                continue

            fence = match.group('fence')
            rest = match.group('rest').strip()
            close_re = re.compile(r'^' + re.escape(fence) + r'[ \t]*$')
            cursor = index + 1
            inner = []
            while cursor < total and not close_re.match(lines[cursor]):
                inner.append(lines[cursor])
                cursor += 1

            if cursor >= total:
                # 没有闭合结构，按普通文本处理，避免吞掉后文
                output.append(line)
                index += 1
                continue

            if is_code_group:
                output.extend(self._render_code_group(inner, rest))
            else:
                output.extend(self._render_callout(inner, callout, rest))

            index = cursor + 1

        return output

    def _render_callout(self, inner, callout, rest):
        """容器写法直接产出 HTML，容器内部可以继续嵌套代码块等块级语法。"""
        canonical, family, label, icon = callout
        title = rest.strip()
        if title.startswith('[') and title.endswith(']'):
            title = title[1:-1].strip()
        else:
            title = title.strip('"').strip("'").strip()

        body_html = render_inner_markdown('\n'.join(inner))
        title_text = title or label
        classes = ['moonbird-callout', f'moonbird-callout-{family}']
        if canonical != family:
            classes.append(f'moonbird-callout-{canonical}')
        html = (
            f'<blockquote class="{" ".join(classes)}">'
            f'<p class="moonbird-callout-title">{icon} {escape(title_text)}</p>'
            f'{body_html}</blockquote>'
        )
        return [self.md.htmlStash.store(html), '']

    def _render_code_group(self, inner, rest):
        segments = _split_fence_blocks(inner)
        segments = [
            segment
            for segment in segments
            if not (segment['kind'] == 'text' and not ''.join(segment['lines']).strip())
        ]
        if not segments:
            return []

        panels = []
        for segment in segments:
            if segment['kind'] == 'code':
                html = build_code_block_html(segment['code'], parse_fence_info(segment['info']))
            else:
                html = render_inner_markdown('\n'.join(segment['lines']))
            panels.append({'label': '', 'html': html})

        for panel, label in zip(panels, parse_code_group_labels(rest, len(panels))):
            panel['label'] = label

        return [self.md.htmlStash.store(build_code_group_html(panels)), '']


class MoonBirdFencePreprocessor(Preprocessor):
    """接管围栏代码块。

    python-markdown 内置的 fenced_code 只保留 info-string 的第一个词，
    `title=` / 行标记 / 行号 / 折叠信息会全部丢失，因此这里自行解析并 stash。
    """

    def run(self, lines):
        output = []
        index = 0
        total = len(lines)

        while index < total:
            match = FENCE_OPEN_RE.match(lines[index])
            if not match:
                output.append(lines[index])
                index += 1
                continue

            closer = _fence_closer(match.group('fence'))
            cursor = index + 1
            code_lines = []
            closed = False
            while cursor < total:
                if closer.match(lines[cursor]):
                    closed = True
                    break
                code_lines.append(lines[cursor])
                cursor += 1

            if not closed:
                output.append(lines[index])
                index += 1
                continue

            info = parse_fence_info(match.group('info'))
            html = build_code_block_html('\n'.join(code_lines), info)
            output.append(self.md.htmlStash.store(html))
            index = cursor + 1

        return output


class MoonBirdCalloutTreeprocessor(Treeprocessor):
    """把 `> [!TYPE] 标题` 形式的引用块改写成提示框结构。"""

    def run(self, root):
        for parent in list(root.iter()):
            for quote in list(parent.findall('blockquote')):
                self._convert(quote)
        return root

    def _convert(self, quote):
        first = next(iter(quote), None)
        if first is None or first.tag != 'p':
            return

        text = first.text or ''
        newline = text.find('\n')
        marker_line = (text if newline == -1 else text[:newline]).strip()

        match = CALLOUT_MARKER_RE.match(marker_line)
        if not match:
            return

        callout = resolve_callout_type(match.group('name'))
        if not callout:
            return

        canonical, family, label, icon = callout
        custom_title = match.group('title').strip()
        title_text = custom_title or label

        remaining = text[newline + 1:] if newline != -1 else ''
        if remaining:
            first.text = remaining
        else:
            quote.remove(first)

        title = quote.makeelement('p', {'class': 'moonbird-callout-title'})
        title.text = f'{icon} {title_text}'
        quote.insert(0, title)

        classes = quote.get('class', '').split()
        classes.extend(
            ['moonbird-callout', f'moonbird-callout-{family}', f'moonbird-callout-{canonical}']
        )
        quote.set('class', ' '.join(dict.fromkeys(classes)))


class MoonBirdMarkdownExtension(Extension):
    def extendMarkdown(self, md):
        md.registerExtension(self)
        # 必须低于 normalize_whitespace(30)：该预处理器会删除 htmlStash 用的
        # STX/ETX 哨兵字符，若在此之前 stash，占位符将无法还原成 HTML。
        md.preprocessors.register(MoonBirdDirectivePreprocessor(md), 'moonbird_directive', 28)
        # 必须晚于 normalize_whitespace(30)（否则哨兵字符被清掉），
        # 又必须早于 fenced_code(25)（否则围栏已被内置扩展吞并）。
        md.preprocessors.register(MoonBirdFencePreprocessor(md), 'moonbird_fence', 26)
        md.treeprocessors.register(MoonBirdCalloutTreeprocessor(md), 'moonbird_callout', 16)
