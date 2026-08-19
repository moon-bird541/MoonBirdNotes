"""Markdown 结构解析阶段使用的数据契约。"""

from dataclasses import dataclass
from datetime import date
from typing import Literal


BlockType = Literal[
    'heading',
    'paragraph',
    'list',
    'blockquote',
    'code_fence',
    'table',
    'image',
    'horizontal_rule',
]

DocumentType = Literal['note', 'diary']


@dataclass(frozen=True, slots=True)
class MarkdownBlock:
    """一个保留原始 Markdown 和源码位置的顶层结构块。

    行号采用 1-based 且 end_line 为包含式。行号只服务展示和辅助定位，
    后续修改仍必须结合原文哈希与章节哈希验证。
    """

    block_type: BlockType
    content: str
    heading_level: int | None
    start_line: int
    end_line: int

    def __post_init__(self):
        """尽早拒绝解析器内部产生的不合法位置或标题层级。"""

        if self.start_line < 1 or self.end_line < self.start_line:
            raise ValueError('Markdown block line range is invalid.')

        if self.block_type == 'heading':
            if self.heading_level not in range(1, 7):
                raise ValueError('Heading blocks require a level from 1 to 6.')
        elif self.heading_level is not None:
            raise ValueError('Only heading blocks can define heading_level.')


@dataclass(frozen=True, slots=True)
class ParentChunkConfig:
    """父片段软目标和不可突破的 token 上限。"""

    target_tokens: int = 1200
    max_tokens: int = 1800

    def __post_init__(self):
        if self.target_tokens < 1:
            raise ValueError('target_tokens must be positive.')
        if self.max_tokens < self.target_tokens:
            raise ValueError('max_tokens must be greater than or equal to target_tokens.')


@dataclass(frozen=True, slots=True)
class ParentChunk:
    """父片段分割结果；写入数据库前仍需绑定具体 Note 和索引版本。"""

    chunk_index: int
    heading_path: tuple[str, ...]
    content: str
    start_line: int
    end_line: int
    token_count: int
    section_hash: str

    def __post_init__(self):
        if self.chunk_index < 0:
            raise ValueError('chunk_index cannot be negative.')
        if self.start_line < 1 or self.end_line < self.start_line:
            raise ValueError('Parent chunk line range is invalid.')
        if self.token_count < 1:
            raise ValueError('Parent chunk token_count must be positive.')
        if len(self.section_hash) != 64:
            raise ValueError('section_hash must be a SHA-256 hexadecimal digest.')


@dataclass(frozen=True, slots=True)
class ChildChunkConfig:
    """子片段目标、硬上限和同章节重叠 token 数。"""

    target_tokens: int = 350
    max_tokens: int = 500
    overlap_tokens: int = 50

    def __post_init__(self):
        if self.target_tokens < 1:
            raise ValueError('target_tokens must be positive.')
        if self.max_tokens < self.target_tokens:
            raise ValueError('max_tokens must be greater than or equal to target_tokens.')
        if self.overlap_tokens < 0 or self.overlap_tokens >= self.target_tokens:
            raise ValueError('overlap_tokens must be non-negative and below target_tokens.')


@dataclass(frozen=True, slots=True)
class RagDocumentMetadata:
    """构建子片段向量文本所需的最少业务元数据。"""

    document_type: DocumentType
    title: str
    tags: tuple[str, ...] = ()
    diary_date: date | None = None
    mood: str = ''
    weather: str = ''
    summary: str = ''

    def __post_init__(self):
        if self.document_type not in {'note', 'diary'}:
            raise ValueError('document_type must be note or diary.')
        if not self.title.strip():
            raise ValueError('Document title cannot be empty.')

        if self.document_type == 'note':
            if self.diary_date or self.mood or self.weather or self.summary:
                raise ValueError('Note metadata cannot contain diary-only fields.')
        else:
            if self.diary_date is None:
                raise ValueError('Diary metadata requires diary_date.')
            if self.tags:
                raise ValueError('Diary metadata cannot contain note tags.')


@dataclass(frozen=True, slots=True)
class ChildChunk:
    """写入 Qdrant 前的子片段、完整向量文本和稳定哈希。"""

    parent_id: str
    chunk_index: int
    heading_path: tuple[str, ...]
    content: str
    vector_text: str
    token_count: int
    overlap_token_count: int
    chunk_hash: str

    def __post_init__(self):
        if not self.parent_id:
            raise ValueError('parent_id cannot be empty.')
        if self.chunk_index < 0:
            raise ValueError('chunk_index cannot be negative.')
        if not self.content or not self.vector_text:
            raise ValueError('Child chunk content and vector_text cannot be empty.')
        if self.token_count < 1:
            raise ValueError('Child chunk token_count must be positive.')
        if self.overlap_token_count < 0:
            raise ValueError('overlap_token_count cannot be negative.')
        if len(self.chunk_hash) != 64:
            raise ValueError('chunk_hash must be a SHA-256 hexadecimal digest.')
