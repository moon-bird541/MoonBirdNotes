"""按 Markdown 章节和 BGE-M3 token 数生成父片段。"""

import hashlib
import re
from collections import deque
from dataclasses import dataclass

from markdown_it import MarkdownIt

from .parser import parse_markdown
from .schemas import BlockType, MarkdownBlock, ParentChunk, ParentChunkConfig
from .tokenizer import TokenCounter


_INLINE_PARSER = MarkdownIt('commonmark')
_ATX_PREFIX = re.compile(r'^ {0,3}#{1,6}(?:[ \t]+|$)')
_ATX_SUFFIX = re.compile(r'[ \t]+#+[ \t]*$')
_SETEXT_UNDERLINE = re.compile(r'^ {0,3}(?:=+|-+)[ \t]*$')
_HTML_TAG = re.compile(r'<[^>]+>')
_PREFERRED_SPLIT_MARKERS = ('\n', ' ', '\t', '。', '！', '？', '；', '.', '!', '?', ';')


@dataclass(frozen=True, slots=True)
class _ChunkPart:
    """携带当时标题路径的块或超长块片段。"""

    content: str
    start_line: int
    end_line: int
    heading_path: tuple[str, ...]
    block_type: BlockType
    heading_level: int | None
    # 只有原块已经超过 max_tokens 时，才允许继续切前缀填充当前父片段。
    is_oversized_fragment: bool = False


@dataclass(slots=True)
class _SectionDraft:
    """按一级至三级标题优先形成、尚未执行 token 限制的章节。"""

    parts: list[_ChunkPart]
    heading_path: tuple[str, ...]
    boundary_level: int | None


@dataclass(slots=True)
class _ParentDraft:
    """已满足 token 上限、但尚未生成最终顺序和哈希的父片段。"""

    parts: list[_ChunkPart]
    heading_path: tuple[str, ...]
    token_count: int
    merge_key: tuple[str, ...]
    merge_allowed: bool


def _inline_plain_text(markdown: str) -> str:
    """提取标题的可见文字，去除强调和链接语法但保留代码及图片 alt。"""

    tokens = _INLINE_PARSER.parseInline(markdown)
    children = tokens[0].children if tokens else None
    if not children:
        return markdown.strip()

    text_parts: list[str] = []
    for token in children:
        if token.type in {'text', 'code_inline', 'image'}:
            text_parts.append(token.content)
        elif token.type in {'softbreak', 'hardbreak'}:
            text_parts.append(' ')
        elif token.type == 'html_inline':
            text_parts.append(_HTML_TAG.sub('', token.content))
    return ''.join(text_parts).strip()


def extract_heading_title(block: MarkdownBlock) -> str:
    """兼容 ATX 与 Setext 标题，并为无文字标题提供稳定回退名称。"""

    lines = block.content.splitlines()
    if len(lines) > 1 and _SETEXT_UNDERLINE.fullmatch(lines[-1]):
        raw_title = ' '.join(lines[:-1])
    else:
        raw_title = _ATX_PREFIX.sub('', lines[0] if lines else '')
        raw_title = _ATX_SUFFIX.sub('', raw_title)

    return _inline_plain_text(raw_title) or '未命名章节'


def _common_heading_path(paths: list[tuple[str, ...]]) -> tuple[str, ...]:
    """合并同级短章节时返回它们共有的上级标题路径。"""

    if not paths:
        return ()

    common = list(paths[0])
    for path in paths[1:]:
        common_length = 0
        for left, right in zip(common, path):
            if left != right:
                break
            common_length += 1
        common = common[:common_length]
        if not common:
            break
    return tuple(common)


def _boundary_levels(blocks: list[MarkdownBlock]) -> set[int]:
    """优先以 H2/H3 建节；文档没有 H2/H3 时回退到现有标题层级。"""

    levels = {
        block.heading_level
        for block in blocks
        if block.block_type == 'heading' and block.heading_level is not None
    }
    if levels.intersection({2, 3}):
        # H1 同时作为文档级边界，防止一篇笔记中的多个 H1 被错误合并。
        return {1, 2, 3}
    return levels


def _has_body(section: _SectionDraft) -> bool:
    return any(part.block_type != 'heading' for part in section.parts)


def _last_heading_level(section: _SectionDraft) -> int | None:
    for part in reversed(section.parts):
        if part.block_type == 'heading':
            return part.heading_level
    return None


def _build_sections(blocks: list[MarkdownBlock]) -> list[_SectionDraft]:
    """维护完整标题栈，并构建只包含当前文档内容的原始章节。"""

    boundaries = _boundary_levels(blocks)
    heading_stack: list[tuple[int, str]] = []
    sections: list[_SectionDraft] = []
    current: _SectionDraft | None = None

    for block in blocks:
        if block.block_type == 'heading':
            level = block.heading_level
            assert level is not None

            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, extract_heading_title(block)))
            current_path = tuple(title for _, title in heading_stack)

            if level in boundaries:
                if current and current.parts:
                    last_level = _last_heading_level(current)
                    # 连续的父子标题可以留在同一空章节；同级标题必须各自建节。
                    should_flush = _has_body(current) or (
                        last_level is not None and last_level >= level
                    )
                    if should_flush:
                        sections.append(current)
                        current = None

                if current is None:
                    current = _SectionDraft([], current_path, level)
                else:
                    current.heading_path = current_path
                    current.boundary_level = level
            elif current is None:
                current = _SectionDraft([], current_path, None)

            current.parts.append(
                _ChunkPart(
                    content=block.content,
                    start_line=block.start_line,
                    end_line=block.end_line,
                    heading_path=current_path,
                    block_type=block.block_type,
                    heading_level=level,
                )
            )
            continue

        current_path = tuple(title for _, title in heading_stack)
        if current is None:
            current = _SectionDraft([], current_path, None)
        current.parts.append(
            _ChunkPart(
                content=block.content,
                start_line=block.start_line,
                end_line=block.end_line,
                heading_path=current_path,
                block_type=block.block_type,
                heading_level=None,
            )
        )

    if current and current.parts:
        sections.append(current)
    return sections


def _parts_content(parts: list[_ChunkPart]) -> str:
    return '\n\n'.join(part.content for part in parts)


def _split_text_to_token_limit(
    text: str,
    token_counter: TokenCounter,
    max_tokens: int,
) -> list[str]:
    """对超长单行执行 tokenizer 校验的最大前缀切分。

    这是自然行仍超过上限时的最后回退。字符位置只用于保留原文切点，
    每个输出片段是否合格始终由模型 tokenizer 重新计数决定。
    """

    fragments: list[str] = []
    remaining = text

    while remaining:
        if token_counter.count_tokens(remaining) <= max_tokens:
            fragments.append(remaining)
            break

        low, high = 1, len(remaining)
        best = 0
        while low <= high:
            middle = (low + high) // 2
            if token_counter.count_tokens(remaining[:middle]) <= max_tokens:
                best = middle
                low = middle + 1
            else:
                high = middle - 1

        if best == 0:
            raise ValueError('max_tokens is too small for a single tokenizer unit.')

        # 在不超过已验证前缀的范围内优先选择自然标点或空白边界。
        preferred = max(remaining.rfind(marker, 0, best) + len(marker) for marker in _PREFERRED_SPLIT_MARKERS)
        if preferred >= max(1, best // 2):
            best = preferred

        fragments.append(remaining[:best])
        remaining = remaining[best:]

    return fragments


def _split_oversized_part(
    part: _ChunkPart,
    token_counter: TokenCounter,
    max_tokens: int,
) -> list[_ChunkPart]:
    """先按自然行合并，单行仍过长时再使用 tokenizer 校验前缀。"""

    if token_counter.count_tokens(part.content) <= max_tokens:
        return [part]

    result: list[_ChunkPart] = []
    buffered_lines: list[str] = []
    buffer_start_line = part.start_line

    def flush_buffer(end_line: int):
        if not buffered_lines:
            return
        content = ''.join(buffered_lines).rstrip('\r\n')
        if content:
            result.append(
                _ChunkPart(
                    content=content,
                    start_line=buffer_start_line,
                    end_line=end_line,
                    heading_path=part.heading_path,
                    block_type=part.block_type,
                    heading_level=part.heading_level,
                    is_oversized_fragment=True,
                )
            )
        buffered_lines.clear()

    for offset, line in enumerate(part.content.splitlines(keepends=True)):
        line_number = min(part.start_line + offset, part.end_line)
        line_content = line.rstrip('\r\n')
        candidate = ''.join([*buffered_lines, line]).rstrip('\r\n')

        if buffered_lines and token_counter.count_tokens(candidate) > max_tokens:
            flush_buffer(line_number - 1)
            buffer_start_line = line_number

        if token_counter.count_tokens(line_content) > max_tokens:
            flush_buffer(line_number - 1)
            for fragment in _split_text_to_token_limit(line_content, token_counter, max_tokens):
                result.append(
                    _ChunkPart(
                        content=fragment,
                        start_line=line_number,
                        end_line=line_number,
                        heading_path=part.heading_path,
                        block_type=part.block_type,
                        heading_level=part.heading_level,
                        is_oversized_fragment=True,
                    )
                )
            buffer_start_line = line_number + 1
        else:
            if not buffered_lines:
                buffer_start_line = line_number
            buffered_lines.append(line)

    flush_buffer(part.end_line)
    return result


def _fragment_with_content(
    part: _ChunkPart,
    content: str,
    start_line: int,
    end_line: int,
) -> _ChunkPart:
    return _ChunkPart(
        content=content,
        start_line=start_line,
        end_line=end_line,
        heading_path=part.heading_path,
        block_type=part.block_type,
        heading_level=part.heading_level,
        is_oversized_fragment=True,
    )


def _split_fragment_to_fill_current(
    current: list[_ChunkPart],
    part: _ChunkPart,
    token_counter: TokenCounter,
    max_tokens: int,
) -> tuple[_ChunkPart | None, _ChunkPart]:
    """从已过长片段切出能与当前内容共同放入上限的最大前缀。"""

    low, high = 1, len(part.content)
    best = 0
    while low <= high:
        middle = (low + high) // 2
        prefix = _fragment_with_content(
            part,
            part.content[:middle],
            part.start_line,
            part.end_line,
        )
        if token_counter.count_tokens(_parts_content([*current, prefix])) <= max_tokens:
            best = middle
            low = middle + 1
        else:
            high = middle - 1

    if best == 0:
        return None, part

    preferred = max(
        part.content.rfind(marker, 0, best) + len(marker)
        for marker in _PREFERRED_SPLIT_MARKERS
    )
    if preferred >= max(1, best // 2):
        best = preferred

    prefix_content = part.content[:best]
    remainder_content = part.content[best:]
    newline_count = prefix_content.count('\n')
    prefix_end_line = part.start_line + newline_count
    if prefix_content.endswith('\n'):
        prefix_end_line -= 1
    prefix_end_line = max(part.start_line, min(prefix_end_line, part.end_line))
    remainder_start_line = min(part.start_line + newline_count, part.end_line)

    return (
        _fragment_with_content(
            part,
            prefix_content,
            part.start_line,
            prefix_end_line,
        ),
        _fragment_with_content(
            part,
            remainder_content,
            remainder_start_line,
            part.end_line,
        ),
    )


def _make_parent_draft(
    parts: list[_ChunkPart],
    token_counter: TokenCounter,
    *,
    merge_allowed: bool,
    heading_path: tuple[str, ...] | None = None,
    merge_key: tuple[str, ...] | None = None,
) -> _ParentDraft:
    content = _parts_content(parts)
    resolved_path = heading_path
    if resolved_path is None:
        resolved_path = _common_heading_path([part.heading_path for part in parts])
    return _ParentDraft(
        parts=parts,
        heading_path=resolved_path,
        token_count=token_counter.count_tokens(content),
        merge_key=merge_key if merge_key is not None else resolved_path[:-1],
        merge_allowed=merge_allowed,
    )


def _split_section(
    section: _SectionDraft,
    token_counter: TokenCounter,
    config: ParentChunkConfig,
) -> list[_ParentDraft]:
    """超长章节优先在内部标题处切开，再按顶层块贪心装箱。"""

    whole = _make_parent_draft(
        section.parts,
        token_counter,
        merge_allowed=True,
        heading_path=section.heading_path,
    )
    if whole.token_count <= config.max_tokens:
        return [whole]

    expanded_parts: list[_ChunkPart] = []
    for part in section.parts:
        expanded_parts.extend(
            _split_oversized_part(part, token_counter, config.max_tokens)
        )

    groups: list[list[_ChunkPart]] = []
    current: list[_ChunkPart] = []

    pending = deque(expanded_parts)
    while pending:
        part = pending.popleft()
        is_internal_heading = (
            part.block_type == 'heading'
            and section.boundary_level is not None
            and part.heading_level is not None
            and part.heading_level > section.boundary_level
        )
        if current and is_internal_heading:
            groups.append(current)
            current = []

        candidate = [*current, part]
        if current and token_counter.count_tokens(_parts_content(candidate)) > config.max_tokens:
            if part.is_oversized_fragment:
                prefix, remainder = _split_fragment_to_fill_current(
                    current,
                    part,
                    token_counter,
                    config.max_tokens,
                )
                if prefix is not None:
                    current.append(prefix)
                    groups.append(current)
                    current = []
                    if remainder.content:
                        pending.appendleft(remainder)
                    continue
            groups.append(current)
            current = [part]
        else:
            current = candidate

    if current:
        groups.append(current)

    return [
        _make_parent_draft(group, token_counter, merge_allowed=False)
        for group in groups
    ]


def _merge_short_sibling_sections(
    drafts: list[_ParentDraft],
    token_counter: TokenCounter,
    config: ParentChunkConfig,
) -> list[_ParentDraft]:
    """只合并同一上级标题内相邻且都未达到目标大小的完整章节。"""

    merged: list[_ParentDraft] = []
    for draft in drafts:
        if not merged:
            merged.append(draft)
            continue

        previous = merged[-1]
        can_merge = (
            previous.merge_allowed
            and draft.merge_allowed
            and previous.merge_key == draft.merge_key
            and previous.token_count < config.target_tokens
            and draft.token_count < config.target_tokens
        )
        if can_merge:
            combined_parts = [*previous.parts, *draft.parts]
            combined_count = token_counter.count_tokens(_parts_content(combined_parts))
        else:
            combined_parts = []
            combined_count = config.max_tokens + 1

        if combined_count <= config.max_tokens:
            merged[-1] = _make_parent_draft(
                combined_parts,
                token_counter,
                merge_allowed=True,
                heading_path=_common_heading_path(
                    [previous.heading_path, draft.heading_path]
                ),
                # 合并后仍使用原共同上级作为同级分组键，允许继续合并第三节。
                merge_key=previous.merge_key,
            )
        else:
            merged.append(draft)
    return merged


def split_parent_chunks(
    markdown: str,
    *,
    token_counter: TokenCounter,
    config: ParentChunkConfig | None = None,
) -> list[ParentChunk]:
    """对单篇 Note 原文生成稳定父片段。

    函数一次只接收一篇 Note 的 Markdown，因此不同笔记和不同日期的日记
    不可能在本层被合并；数据库关联由后续索引服务负责。
    """

    # 强制调用方显式提供与当前 Embedding 模型匹配的 tokenizer，禁止隐式字符估算。
    counter = token_counter
    resolved_config = config or ParentChunkConfig()
    blocks = parse_markdown(markdown)
    if not blocks:
        return []

    drafts: list[_ParentDraft] = []
    for section in _build_sections(blocks):
        drafts.extend(_split_section(section, counter, resolved_config))
    drafts = _merge_short_sibling_sections(drafts, counter, resolved_config)

    chunks: list[ParentChunk] = []
    for chunk_index, draft in enumerate(drafts):
        content = _parts_content(draft.parts)
        token_count = counter.count_tokens(content)
        if token_count > resolved_config.max_tokens:
            raise AssertionError('Parent chunk exceeds max_tokens after splitting.')
        chunks.append(
            ParentChunk(
                chunk_index=chunk_index,
                heading_path=draft.heading_path,
                content=content,
                start_line=draft.parts[0].start_line,
                end_line=draft.parts[-1].end_line,
                token_count=token_count,
                section_hash=hashlib.sha256(content.encode('utf-8')).hexdigest(),
            )
        )
    return chunks
