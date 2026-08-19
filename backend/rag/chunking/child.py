"""在单个父片段内部生成用于向量召回的结构安全子片段。"""

import hashlib
import re
from dataclasses import dataclass, field
from uuid import UUID

from markdown_it import MarkdownIt
from markdown_it.token import Token

from .parent import extract_heading_title
from .parser import parse_markdown
from .schemas import (
    ChildChunk,
    ChildChunkConfig,
    MarkdownBlock,
    ParentChunk,
    RagDocumentMetadata,
)
from .tokenizer import TokenCounter


_MARKDOWN_PARSER = MarkdownIt('commonmark').enable('table')
_HTML_TAG = re.compile(r'<[^>]+>')
_FENCE_OPEN = re.compile(r'^ {0,3}(`{3,}|~{3,})')
_NATURAL_BOUNDARY = re.compile(r'[。！？；]+|[.!?;]+(?:\s+|$)|\n+')
_PREFERRED_SPLIT_MARKERS = ('\n', ' ', '\t', '。', '！', '？', '；', '.', '!', '?', ';')


class ChildChunkingError(ValueError):
    """单个结构原子无法在不破坏规则的情况下放入 token 上限。"""


@dataclass(frozen=True, slots=True)
class _LocatedBlock:
    block: MarkdownBlock
    heading_path: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ChildUnit:
    """可安全组合的最小结构单元，例如段落句子、列表项或完整代码块。"""

    content: str
    heading_path: tuple[str, ...]
    separator_before: str = '\n\n'
    overlap_eligible: bool = True
    force_boundary: bool = False


@dataclass(slots=True)
class _ChildDraft:
    """尚未添加重叠和生成向量文本的子片段草稿。"""

    primary_units: list[_ChildUnit]
    heading_path: tuple[str, ...]
    overlap_allowed: bool = True
    overlap_units: list[_ChildUnit] = field(default_factory=list)


def _visible_inline_text(tokens: list[Token]) -> str:
    """保留可见文字和图片 alt，忽略链接地址及 Markdown 容器标记。"""

    parts: list[str] = []
    for token in tokens:
        if token.type in {'text', 'code_inline', 'image'}:
            parts.append(token.content)
        elif token.type in {'softbreak', 'hardbreak'}:
            parts.append('\n')
        elif token.type == 'html_inline':
            parts.append(_HTML_TAG.sub('', token.content))
        elif token.children:
            parts.append(_visible_inline_text(token.children))
    return ''.join(parts)


def markdown_to_embedding_text(markdown: str) -> str:
    """把 Markdown 转为向量正文，保留语义但移除图片路径和链接 URL。"""

    semantic_parts: list[str] = []
    for token in _MARKDOWN_PARSER.parse(markdown):
        if token.type in {'fence', 'code_block'}:
            language = token.info.strip()
            code = token.content.rstrip('\r\n')
            semantic_parts.append('\n'.join(part for part in (language, code) if part))
        elif token.type == 'inline':
            visible = _visible_inline_text(token.children or []).strip()
            if visible:
                semantic_parts.append(visible)
        elif token.type == 'html_block':
            visible = _HTML_TAG.sub('', token.content).strip()
            if visible:
                semantic_parts.append(visible)

    return '\n'.join(part for part in semantic_parts if part).strip()


def build_vector_text(
    metadata: RagDocumentMetadata,
    heading_path: tuple[str, ...],
    body: str,
) -> str:
    """按普通笔记和日记边界生成稳定、可版本化的 Embedding 输入。"""

    if metadata.document_type == 'note':
        lines = [
            '类型：普通笔记',
            f'标题：{metadata.title}',
            f'标签：{"、".join(metadata.tags) if metadata.tags else "无"}',
        ]
    else:
        lines = [
            '类型：日记',
            f'日期：{metadata.diary_date.isoformat()}',
            f'标题：{metadata.title}',
        ]
        if metadata.mood:
            lines.append(f'心情：{metadata.mood}')
        if metadata.weather:
            lines.append(f'天气：{metadata.weather}')
        if metadata.summary:
            lines.append(f'摘要：{metadata.summary}')

    lines.append(f'章节：{" > ".join(heading_path) if heading_path else "未分节"}')
    semantic_body = body.strip() or '（无可索引正文）'
    return f'{"\n".join(lines)}\n\n正文：\n{semantic_body}'


def _annotate_heading_paths(parent: ParentChunk) -> list[_LocatedBlock]:
    """从父片段共同路径继续维护子片段所需的具体标题路径。"""

    blocks = parse_markdown(parent.content)
    base_path = parent.heading_path
    local_stack: list[tuple[int, str]] = []
    current_path = parent.heading_path
    first_heading = True
    located: list[_LocatedBlock] = []

    for block in blocks:
        if block.block_type == 'heading':
            level = block.heading_level
            assert level is not None
            title = extract_heading_title(block)

            if first_heading:
                if level == 1:
                    base_path = ()
                elif parent.heading_path and title == parent.heading_path[-1]:
                    base_path = parent.heading_path[:-1]
                first_heading = False

            while local_stack and local_stack[-1][0] >= level:
                local_stack.pop()
            local_stack.append((level, title))
            current_path = (*base_path, *(name for _, name in local_stack))

        located.append(_LocatedBlock(block=block, heading_path=current_path))
    return located


def _join_units(units: list[_ChildUnit]) -> str:
    if not units:
        return ''
    content = units[0].content
    for unit in units[1:]:
        content += f'{unit.separator_before}{unit.content}'
    return content


def _vector_text_for_units(
    units: list[_ChildUnit],
    metadata: RagDocumentMetadata,
    heading_path: tuple[str, ...],
) -> str:
    body = markdown_to_embedding_text(_join_units(units))
    return build_vector_text(metadata, heading_path, body)


def _fits(
    units: list[_ChildUnit],
    metadata: RagDocumentMetadata,
    heading_path: tuple[str, ...],
    token_counter: TokenCounter,
    max_tokens: int,
) -> bool:
    return token_counter.count_tokens(
        _vector_text_for_units(units, metadata, heading_path)
    ) <= max_tokens


def _split_list_block(
    block: MarkdownBlock,
    heading_path: tuple[str, ...],
    metadata: RagDocumentMetadata,
    token_counter: TokenCounter,
    max_tokens: int,
) -> list[_ChildUnit]:
    """列表过长时只在顶层列表项之间切分，不截断单个列表项。"""

    whole = _ChildUnit(block.content, heading_path)
    if _fits([whole], metadata, heading_path, token_counter, max_tokens):
        return [whole]

    source_lines = block.content.splitlines(keepends=True)
    items: list[str] = []
    for token in _MARKDOWN_PARSER.parse(block.content):
        if token.type == 'list_item_open' and token.level == 1 and token.map:
            start, end = token.map
            items.append(''.join(source_lines[start:end]).rstrip('\r\n'))

    if not items:
        raise ChildChunkingError('列表无法识别顶层列表项，不能安全切分。')

    units: list[_ChildUnit] = []
    for index, item in enumerate(items):
        unit = _ChildUnit(
            item,
            heading_path,
            separator_before='\n' if index else '\n\n',
        )
        if not _fits([unit], metadata, heading_path, token_counter, max_tokens):
            raise ChildChunkingError('单个列表项超过子片段 token 上限。')
        units.append(unit)
    return units


def _table_content(header: list[str], rows: list[str]) -> str:
    return '\n'.join([*header, *rows])


def _split_table_block(
    block: MarkdownBlock,
    heading_path: tuple[str, ...],
    metadata: RagDocumentMetadata,
    token_counter: TokenCounter,
    max_tokens: int,
) -> list[_ChildUnit]:
    """长表格按数据行切分，每个输出片段重复表头和分隔行。"""

    whole = _ChildUnit(block.content, heading_path, overlap_eligible=False)
    if _fits([whole], metadata, heading_path, token_counter, max_tokens):
        return [whole]

    lines = block.content.splitlines()
    if len(lines) < 3:
        raise ChildChunkingError('表格缺少可安全重复的表头或数据行。')

    header = lines[:2]
    rows = lines[2:]
    groups: list[list[str]] = []
    current_rows: list[str] = []

    for row in rows:
        candidate_rows = [*current_rows, row]
        candidate = _ChildUnit(
            _table_content(header, candidate_rows),
            heading_path,
            overlap_eligible=False,
            force_boundary=True,
        )
        if current_rows and not _fits(
            [candidate], metadata, heading_path, token_counter, max_tokens
        ):
            groups.append(current_rows)
            current_rows = [row]
        else:
            current_rows = candidate_rows

        single_row = _ChildUnit(
            _table_content(header, [row]),
            heading_path,
            overlap_eligible=False,
            force_boundary=True,
        )
        if not _fits([single_row], metadata, heading_path, token_counter, max_tokens):
            raise ChildChunkingError('单个表格行连同表头超过子片段 token 上限。')

    if current_rows:
        groups.append(current_rows)

    return [
        _ChildUnit(
            _table_content(header, group),
            heading_path,
            overlap_eligible=False,
            force_boundary=True,
        )
        for group in groups
    ]


def _split_code_block(
    block: MarkdownBlock,
    heading_path: tuple[str, ...],
    metadata: RagDocumentMetadata,
    token_counter: TokenCounter,
    max_tokens: int,
) -> list[_ChildUnit]:
    """代码块能放下时保持原子；超长时按完整代码行分组并补齐围栏。"""

    whole = _ChildUnit(block.content, heading_path, overlap_eligible=False)
    if _fits([whole], metadata, heading_path, token_counter, max_tokens):
        return [whole]

    lines = block.content.splitlines()
    opening_match = _FENCE_OPEN.match(lines[0]) if lines else None
    if opening_match:
        opening = lines[0]
        fence = opening_match.group(1)
        has_closing = len(lines) > 1 and lines[-1].strip().startswith(fence)
        closing = lines[-1] if has_closing else fence
        body_lines = lines[1:-1] if has_closing else lines[1:]
    else:
        opening = ''
        closing = ''
        body_lines = lines

    def wrap(rows: list[str]) -> str:
        return '\n'.join(part for part in (opening, *rows, closing) if part != '')

    groups: list[list[str]] = []
    current_lines: list[str] = []
    for line in body_lines:
        candidate_lines = [*current_lines, line]
        candidate = _ChildUnit(
            wrap(candidate_lines),
            heading_path,
            overlap_eligible=False,
            force_boundary=True,
        )
        if current_lines and not _fits(
            [candidate], metadata, heading_path, token_counter, max_tokens
        ):
            groups.append(current_lines)
            current_lines = [line]
        else:
            current_lines = candidate_lines

        single_line = _ChildUnit(
            wrap([line]),
            heading_path,
            overlap_eligible=False,
            force_boundary=True,
        )
        if not _fits([single_line], metadata, heading_path, token_counter, max_tokens):
            raise ChildChunkingError('单个代码行连同围栏超过子片段 token 上限。')

    if current_lines:
        groups.append(current_lines)
    if not groups:
        raise ChildChunkingError('代码块没有可安全切分的代码行。')

    return [
        _ChildUnit(
            wrap(group),
            heading_path,
            overlap_eligible=False,
            force_boundary=True,
        )
        for group in groups
    ]


def _natural_segments(text: str) -> list[str]:
    """保留原始字符的自然句子和换行边界。"""

    segments: list[str] = []
    start = 0
    for match in _NATURAL_BOUNDARY.finditer(text):
        end = match.end()
        if end > start:
            segments.append(text[start:end])
        start = end
    if start < len(text):
        segments.append(text[start:])
    return [segment for segment in segments if segment]


def _split_text_to_fit_vector(
    text: str,
    heading_path: tuple[str, ...],
    metadata: RagDocumentMetadata,
    token_counter: TokenCounter,
    max_tokens: int,
) -> list[str]:
    """自然句仍超限时，用完整向量文本校验最大原文前缀。"""

    fragments: list[str] = []
    remaining = text
    while remaining:
        unit = _ChildUnit(remaining, heading_path)
        if _fits([unit], metadata, heading_path, token_counter, max_tokens):
            fragments.append(remaining)
            break

        low, high = 1, len(remaining)
        best = 0
        while low <= high:
            middle = (low + high) // 2
            prefix = _ChildUnit(remaining[:middle], heading_path)
            if _fits([prefix], metadata, heading_path, token_counter, max_tokens):
                best = middle
                low = middle + 1
            else:
                high = middle - 1

        if best == 0:
            raise ChildChunkingError('向量元数据已占满 token 上限，正文无法放入。')

        preferred = max(
            remaining.rfind(marker, 0, best) + len(marker)
            for marker in _PREFERRED_SPLIT_MARKERS
        )
        if preferred >= max(1, best // 2):
            best = preferred

        fragments.append(remaining[:best])
        remaining = remaining[best:]
    return fragments


def _split_regular_block(
    block: MarkdownBlock,
    heading_path: tuple[str, ...],
    metadata: RagDocumentMetadata,
    token_counter: TokenCounter,
    max_tokens: int,
) -> list[_ChildUnit]:
    overlap_eligible = block.block_type in {'paragraph', 'blockquote', 'image'}
    whole = _ChildUnit(
        block.content,
        heading_path,
        overlap_eligible=overlap_eligible,
    )
    if _fits([whole], metadata, heading_path, token_counter, max_tokens):
        return [whole]

    if block.block_type in {'heading', 'horizontal_rule'}:
        raise ChildChunkingError(f'{block.block_type} 超过子片段 token 上限。')

    units: list[_ChildUnit] = []
    for segment in _natural_segments(block.content):
        fragments = _split_text_to_fit_vector(
            segment,
            heading_path,
            metadata,
            token_counter,
            max_tokens,
        )
        for fragment in fragments:
            units.append(
                _ChildUnit(
                    fragment,
                    heading_path,
                    separator_before='' if units else '\n\n',
                    overlap_eligible=overlap_eligible,
                )
            )
    return units


def _units_for_block(
    located: _LocatedBlock,
    metadata: RagDocumentMetadata,
    token_counter: TokenCounter,
    max_tokens: int,
) -> list[_ChildUnit]:
    block = located.block
    if block.block_type == 'list':
        return _split_list_block(
            block, located.heading_path, metadata, token_counter, max_tokens
        )
    if block.block_type == 'table':
        return _split_table_block(
            block, located.heading_path, metadata, token_counter, max_tokens
        )
    if block.block_type == 'code_fence':
        return _split_code_block(
            block, located.heading_path, metadata, token_counter, max_tokens
        )
    return _split_regular_block(
        block, located.heading_path, metadata, token_counter, max_tokens
    )


def _group_units(
    units: list[_ChildUnit],
    metadata: RagDocumentMetadata,
    token_counter: TokenCounter,
    config: ChildChunkConfig,
) -> list[_ChildDraft]:
    """同一标题路径内按 target 软目标和 max 硬上限组合原子单元。"""

    drafts: list[_ChildDraft] = []
    current: list[_ChildUnit] = []
    current_path: tuple[str, ...] | None = None

    def flush_current():
        nonlocal current, current_path
        if current and current_path is not None:
            drafts.append(_ChildDraft(current, current_path))
        current = []
        current_path = None

    for unit in units:
        if current and unit.heading_path != current_path:
            flush_current()

        if unit.force_boundary:
            flush_current()
            drafts.append(
                _ChildDraft([unit], unit.heading_path, overlap_allowed=False)
            )
            continue

        if not current:
            current = [unit]
            current_path = unit.heading_path
            continue

        current_vector = _vector_text_for_units(current, metadata, current_path)
        current_count = token_counter.count_tokens(current_vector)
        candidate = [*current, unit]
        candidate_fits = _fits(
            candidate,
            metadata,
            current_path,
            token_counter,
            config.max_tokens,
        )

        if current_count >= config.target_tokens or not candidate_fits:
            flush_current()
            current = [unit]
            current_path = unit.heading_path
        else:
            current = candidate

    flush_current()
    return drafts


def _semantic_token_count(units: list[_ChildUnit], token_counter: TokenCounter) -> int:
    semantic = markdown_to_embedding_text(_join_units(units))
    return token_counter.count_tokens(semantic) if semantic else 0


def _apply_overlap(
    drafts: list[_ChildDraft],
    metadata: RagDocumentMetadata,
    token_counter: TokenCounter,
    config: ChildChunkConfig,
):
    """只从同标题路径的前一片段复制完整尾部单元，不跨章节添加重叠。"""

    if config.overlap_tokens == 0:
        return

    for index in range(1, len(drafts)):
        previous = drafts[index - 1]
        current = drafts[index]
        if (
            previous.heading_path != current.heading_path
            or not current.overlap_allowed
        ):
            continue

        selected: list[_ChildUnit] = []
        for unit in reversed(previous.primary_units):
            # 重叠必须是连续尾部；遇到代码或表格等非重叠原子就停止。
            if not unit.overlap_eligible:
                break
            proposed = [unit, *selected]
            proposed_overlap = _semantic_token_count(proposed, token_counter)
            if selected and proposed_overlap >= config.overlap_tokens:
                current_overlap = _semantic_token_count(selected, token_counter)
                # 原子单元不能截断时，在目标值两侧选择更接近的一组。
                if abs(current_overlap - config.overlap_tokens) <= abs(
                    proposed_overlap - config.overlap_tokens
                ):
                    break
            candidate = [*proposed, *current.primary_units]
            if not _fits(
                candidate,
                metadata,
                current.heading_path,
                token_counter,
                config.max_tokens,
            ):
                break
            selected = proposed
            if proposed_overlap >= config.overlap_tokens:
                break

        current.overlap_units = selected


def split_child_chunks(
    parent: ParentChunk,
    *,
    parent_id: str | UUID,
    metadata: RagDocumentMetadata,
    token_counter: TokenCounter,
    config: ChildChunkConfig | None = None,
) -> list[ChildChunk]:
    """只在指定父片段内部生成可直接发送给 Embedding API 的子片段。"""

    resolved_parent_id = str(parent_id).strip()
    if not resolved_parent_id:
        raise ValueError('parent_id cannot be empty.')
    resolved_config = config or ChildChunkConfig()

    units: list[_ChildUnit] = []
    for located in _annotate_heading_paths(parent):
        units.extend(
            _units_for_block(
                located,
                metadata,
                token_counter,
                resolved_config.max_tokens,
            )
        )
    if not units:
        return []

    drafts = _group_units(units, metadata, token_counter, resolved_config)
    _apply_overlap(drafts, metadata, token_counter, resolved_config)

    chunks: list[ChildChunk] = []
    for chunk_index, draft in enumerate(drafts):
        combined_units = [*draft.overlap_units, *draft.primary_units]
        content = _join_units(combined_units)
        vector_text = _vector_text_for_units(
            combined_units,
            metadata,
            draft.heading_path,
        )
        token_count = token_counter.count_tokens(vector_text)
        if token_count > resolved_config.max_tokens:
            raise AssertionError('Child chunk exceeds max_tokens after overlap.')

        chunks.append(
            ChildChunk(
                parent_id=resolved_parent_id,
                chunk_index=chunk_index,
                heading_path=draft.heading_path,
                content=content,
                vector_text=vector_text,
                token_count=token_count,
                overlap_token_count=_semantic_token_count(
                    draft.overlap_units, token_counter
                ),
                # 向量输入的任何元数据变化都应产生新 hash 并重新向量化。
                chunk_hash=hashlib.sha256(vector_text.encode('utf-8')).hexdigest(),
            )
        )
    return chunks
