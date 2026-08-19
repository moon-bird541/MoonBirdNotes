"""使用 markdown-it-py Token 将 Markdown 解析为稳定的顶层结构块。"""

from collections.abc import Sequence

from markdown_it import MarkdownIt
from markdown_it.token import Token

from .schemas import BlockType, MarkdownBlock


# 解析器只负责结构识别；现有 Python-Markdown 与 bleach 继续负责 HTML 渲染和净化。
_MARKDOWN_PARSER = MarkdownIt('commonmark').enable('table')

_TOKEN_BLOCK_TYPES: dict[str, BlockType] = {
    'heading_open': 'heading',
    'paragraph_open': 'paragraph',
    'bullet_list_open': 'list',
    'ordered_list_open': 'list',
    'blockquote_open': 'blockquote',
    'fence': 'code_fence',
    'code_block': 'code_fence',
    'table_open': 'table',
    'hr': 'horizontal_rule',
}


def _is_standalone_image_paragraph(tokens: Sequence[Token], token_index: int) -> bool:
    """判断段落是否只包含图片或包裹图片的链接。

    图片夹在普通文字中时仍属于 paragraph，避免后续分块把同一句话拆开。
    """

    if token_index + 1 >= len(tokens):
        return False

    inline_token = tokens[token_index + 1]
    if inline_token.type != 'inline':
        return False

    has_image = False
    for child in inline_token.children or []:
        if child.type == 'image':
            has_image = True
            continue
        if child.type in {'link_open', 'link_close'}:
            continue
        if child.type in {'text', 'softbreak', 'hardbreak'} and not child.content.strip():
            continue
        return False

    return has_image


def _raw_block_content(source_lines: Sequence[str], start: int, end: int) -> str:
    """按 Token 行号截取原始 Markdown，同时去除块末尾的行分隔符。"""

    return ''.join(source_lines[start:end]).rstrip('\r\n')


def _fallback_blocks(source_lines: Sequence[str], covered_lines: set[int]) -> list[MarkdownBlock]:
    """保留解析器不生成 Token 的有效源码，例如引用式链接定义。

    markdown-it-py 会把 ``[ref]: URL`` 放入解析环境而不输出块 Token。
    若直接忽略这些行，精确 URL 会从 RAG 结构中丢失，因此将连续的未覆盖
    非空行作为普通段落保留。
    """

    blocks: list[MarkdownBlock] = []
    line_index = 0

    while line_index < len(source_lines):
        if line_index in covered_lines or not source_lines[line_index].strip():
            line_index += 1
            continue

        start = line_index
        while (
            line_index < len(source_lines)
            and line_index not in covered_lines
            and source_lines[line_index].strip()
        ):
            line_index += 1

        blocks.append(
            MarkdownBlock(
                block_type='paragraph',
                content=_raw_block_content(source_lines, start, line_index),
                heading_level=None,
                start_line=start + 1,
                end_line=line_index,
            )
        )

    return blocks


def parse_markdown(markdown: str) -> list[MarkdownBlock]:
    """把 Markdown 原文解析为不重复的顶层块，并保留 1-based 行号。

    列表、引用和表格的内部 Token 不会再次输出，避免同一段正文同时作为
    容器块和段落块重复进入后续父子分块。
    """

    if not isinstance(markdown, str):
        raise TypeError('markdown must be a string.')
    if not markdown:
        return []

    source_lines = markdown.splitlines(keepends=True)
    tokens = _MARKDOWN_PARSER.parse(markdown)
    blocks: list[MarkdownBlock] = []
    covered_lines: set[int] = set()

    for token_index, token in enumerate(tokens):
        # 只消费 level=0 的 Token；嵌套 Token 已包含在外层列表、引用或表格中。
        if token.level != 0 or token.map is None:
            continue

        block_type = _TOKEN_BLOCK_TYPES.get(token.type)
        if block_type is None:
            # HTML 块等未单列类型仍以段落保留，不能静默丢失用户正文。
            block_type = 'paragraph'

        if token.type == 'paragraph_open' and _is_standalone_image_paragraph(tokens, token_index):
            block_type = 'image'

        start, end = token.map
        if end <= start:
            continue

        heading_level = int(token.tag[1:]) if block_type == 'heading' else None
        blocks.append(
            MarkdownBlock(
                block_type=block_type,
                content=_raw_block_content(source_lines, start, end),
                heading_level=heading_level,
                start_line=start + 1,
                end_line=end,
            )
        )
        covered_lines.update(range(start, end))

    # 引用式链接定义等没有 Token 的有效行需要按原文位置补回。
    blocks.extend(_fallback_blocks(source_lines, covered_lines))
    blocks.sort(key=lambda block: (block.start_line, block.end_line))
    return blocks
