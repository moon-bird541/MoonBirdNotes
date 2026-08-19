"""RAG 应用对外公开的服务边界。

其他 Django App 应从本包导入 RAG 能力，不能直接依赖数据模型、
向量存储或检索内部实现，避免 Agent 层绕过统一校验。
"""

from rag.indexing import (
    DeleteNoteIndexResult,
    IndexNoteResult,
    NoteIndexingError,
    delete_note_index,
    index_note,
)
from rag.jobs import (
    JobProcessResult,
    enqueue_note_deletion,
    enqueue_note_ids_on_commit,
    enqueue_note_index,
    enqueue_note_index_on_commit,
)
from rag.knowledge import (
    KnowledgeReadError,
    list_knowledge_tags,
    read_current_parent_chunks,
    read_diary_by_date,
    read_note,
    read_note_section,
)
from rag.retrieval import (
    HybridRetrievalCandidate,
    HybridRetrievalError,
    HybridRetrievalResult,
    KeywordCandidate,
    KeywordSearchError,
    retrieve,
    search_keywords,
)

__all__ = [
    'DeleteNoteIndexResult',
    'IndexNoteResult',
    'JobProcessResult',
    'HybridRetrievalCandidate',
    'HybridRetrievalError',
    'HybridRetrievalResult',
    'KeywordCandidate',
    'KeywordSearchError',
    'KnowledgeReadError',
    'NoteIndexingError',
    'delete_note_index',
    'enqueue_note_deletion',
    'enqueue_note_ids_on_commit',
    'enqueue_note_index',
    'enqueue_note_index_on_commit',
    'index_note',
    'list_knowledge_tags',
    'read_current_parent_chunks',
    'read_diary_by_date',
    'read_note',
    'read_note_section',
    'retrieve',
    'search_keywords',
]
