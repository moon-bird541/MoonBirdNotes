"""Dense 与关键词候选融合、父片段聚合和当前来源校验。"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from time import perf_counter
from typing import Callable, Iterable, Literal
from uuid import UUID

from django.conf import settings
from django.db.models import F

from agent.tracing import trace_event
from notes.models import Note
from rag.embeddings import EmbeddingService, EmbeddingServiceError, get_embedding_service
from rag.models import RagParentChunk
from rag.qdrant import (
    QdrantPointFilter,
    QdrantScoredPoint,
    QdrantStoreError,
    QdrantVectorStore,
    get_qdrant_store,
)

from .keyword import KeywordCandidate, KeywordSearchError, search_keywords


DocumentType = Literal['note', 'diary']
KeywordSearch = Callable[..., tuple[KeywordCandidate, ...]]
ALLOWED_DOCUMENT_TYPES = frozenset({'note', 'diary'})
RRF_K = 60
MAX_DENSE_TOP_K = 100
MAX_FINAL_PARENT_TOP_K = 20
EXCERPT_LENGTH = 240
logger = logging.getLogger(__name__)


class HybridRetrievalError(ValueError):
    """混合检索参数错误；外部服务故障会降级而不是转换为此异常。"""

    def __init__(self, *, code: str, message: str):
        super().__init__(message)
        self.code = code

    def as_dict(self) -> dict[str, str]:
        return {'code': self.code, 'message': str(self)}


@dataclass(frozen=True, slots=True)
class HybridRetrievalCandidate:
    """已由 MySQL 当前来源验证的持久化或临时章节结果。"""

    note_id: int
    parent_id: str | None
    document_type: DocumentType
    title: str
    heading_path: tuple[str, ...]
    source_hash: str
    score: float
    matched_child_excerpt: str
    content: str
    start_line: int
    end_line: int
    diary_date: date | None

    def as_dict(self) -> dict[str, object]:
        return {
            'note_id': self.note_id,
            'parent_id': self.parent_id,
            'type': self.document_type,
            'title': self.title,
            'heading_path': list(self.heading_path),
            'source_hash': self.source_hash,
            'score': self.score,
            'matched_child_excerpt': self.matched_child_excerpt,
            'content': self.content,
            'start_line': self.start_line,
            'end_line': self.end_line,
            'diary_date': self.diary_date.isoformat() if self.diary_date else None,
        }


@dataclass(frozen=True, slots=True)
class HybridRetrievalResult:
    results: tuple[HybridRetrievalCandidate, ...]
    semantic_available: bool
    degradation_code: str | None
    dense_candidate_count: int
    keyword_candidate_count: int

    @property
    def degraded(self) -> bool:
        return not self.semantic_available

    def as_dict(self) -> dict[str, object]:
        return {
            'results': [item.as_dict() for item in self.results],
            'semantic_available': self.semantic_available,
            'degraded': self.degraded,
            'degradation_code': self.degradation_code,
            'dense_candidate_count': self.dense_candidate_count,
            'keyword_candidate_count': self.keyword_candidate_count,
        }


@dataclass(frozen=True, slots=True)
class _DenseHit:
    rank: int
    note_id: int
    parent_id: str
    document_type: DocumentType
    source_hash: str
    index_version: int
    embedding_version: str
    excerpt: str


class HybridRetrievalService:
    """编排查询向量化、Dense 查询、关键词召回和父片段级融合。"""

    def __init__(
        self,
        *,
        embedding_service: EmbeddingService,
        vector_store: QdrantVectorStore,
        embedding_version: str,
        dense_score_threshold: float,
        keyword_search: KeywordSearch = search_keywords,
        clock=perf_counter,
        retrieval_logger=logger,
    ):
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.embedding_version = embedding_version
        if not 0 <= dense_score_threshold <= 1:
            raise ValueError('Dense score threshold must be between 0 and 1.')
        self.dense_score_threshold = dense_score_threshold
        self.keyword_search = keyword_search
        self.clock = clock
        self.logger = retrieval_logger

    def retrieve(
        self,
        query: str,
        *,
        types: Iterable[DocumentType] | None = None,
        tags: Iterable[str] | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        dense_top_k: int = 20,
        keyword_top_k: int = 20,
        final_parent_top_k: int = 5,
    ) -> HybridRetrievalResult:
        started = self.clock()
        selected_types = _validate_types(types)
        normalized_tags = _validate_tags(tags)
        _validate_date_range(date_from, date_to)
        _validate_limit(dense_top_k, 'dense_top_k', MAX_DENSE_TOP_K)
        _validate_limit(final_parent_top_k, 'final_parent_top_k', MAX_FINAL_PARENT_TOP_K)

        try:
            keyword_candidates = self.keyword_search(
                query,
                types=selected_types,
                tags=normalized_tags,
                date_from=date_from,
                date_to=date_to,
                limit=keyword_top_k,
            )
        except KeywordSearchError as exc:
            raise HybridRetrievalError(code=exc.code, message=str(exc)) from None

        semantic_available = True
        degradation_code = None
        dense_points: tuple[QdrantScoredPoint, ...] = ()
        try:
            query_vector = tuple(self.embedding_service.embed_query(query.strip()))
            dense_points = self.vector_store.search_points(
                query_vector,
                point_filter=QdrantPointFilter(
                    document_type=_single_type(selected_types),
                    tags=normalized_tags,
                    diary_date_from=date_from,
                    diary_date_to=date_to,
                    embedding_version=self.embedding_version,
                ),
                limit=dense_top_k,
                score_threshold=self.dense_score_threshold,
            )
        except (EmbeddingServiceError, QdrantStoreError) as exc:
            # 语义通道故障不能阻断 MySQL 精确关键词检索。
            semantic_available = False
            degradation_code = exc.code

        results = self._fuse(
            dense_points,
            keyword_candidates,
            selected_types=selected_types,
            tags=normalized_tags,
            date_from=date_from,
            date_to=date_to,
            limit=final_parent_top_k,
        )
        result = HybridRetrievalResult(
            results=results,
            semantic_available=semantic_available,
            degradation_code=degradation_code,
            dense_candidate_count=len(dense_points),
            keyword_candidate_count=len(keyword_candidates),
        )
        self.logger.info(
            'Hybrid retrieval completed.',
            extra={
                'retrieval_duration_ms': round((self.clock() - started) * 1000, 3),
                'result_count': len(results),
                'semantic_available': semantic_available,
                'degradation_code': degradation_code or '',
                'dense_candidate_count': len(dense_points),
                'keyword_candidate_count': len(keyword_candidates),
                'embedding_version': self.embedding_version,
                'dense_score_threshold': self.dense_score_threshold,
                'final_parent_top_k': final_parent_top_k,
                'type_filter_count': len(selected_types),
                'tag_filter_count': len(normalized_tags),
                'date_filter_applied': bool(date_from or date_to),
            },
        )
        # 诊断轨迹仅保留候选定位和分数，不保存查询、摘要或正文。
        trace_event(
            'retrieval.completed',
            semantic_available=semantic_available,
            degradation_code=degradation_code,
            dense_candidate_count=len(dense_points),
            keyword_candidate_count=len(keyword_candidates),
            dense_score_threshold=self.dense_score_threshold,
            candidates=[
                {
                    'note_id': item.note_id,
                    'heading_path': list(item.heading_path),
                    'score': item.score,
                    'type': item.document_type,
                    'diary_date': item.diary_date.isoformat() if item.diary_date else None,
                }
                for item in results
            ],
        )
        return result

    def _fuse(
        self,
        dense_points: tuple[QdrantScoredPoint, ...],
        keyword_candidates: tuple[KeywordCandidate, ...],
        *,
        selected_types: frozenset[str],
        tags: tuple[str, ...],
        date_from: date | None,
        date_to: date | None,
        limit: int,
    ) -> tuple[HybridRetrievalCandidate, ...]:
        dense_by_parent = _group_dense_hits(dense_points)
        keyword_by_parent = _group_keyword_hits(keyword_candidates)
        inline_keyword_hits = _inline_keyword_hits(keyword_candidates)
        parent_ids = set(dense_by_parent) | set(keyword_by_parent)
        parents = self._load_current_parents(
            parent_ids,
            selected_types=selected_types,
            tags=tags,
            date_from=date_from,
            date_to=date_to,
        )

        ranked_results = []
        for parent in parents:
            parent_id = str(parent.pk)
            document_type, diary_date = _current_document_type(parent)
            dense_hits = tuple(
                hit
                for hit in dense_by_parent.get(parent_id, ())
                if _dense_hit_matches_parent(hit, parent, document_type, self.embedding_version)
            )
            keyword_hit = keyword_by_parent.get(parent_id)
            if keyword_hit and not _keyword_hit_matches_parent(
                keyword_hit[1], parent, document_type
            ):
                keyword_hit = None
            if not dense_hits and not keyword_hit:
                continue

            score = _fused_score(dense_hits, keyword_hit)
            excerpt = (
                keyword_hit[1].matched_excerpt
                if keyword_hit
                else dense_hits[0].excerpt
            )
            candidate = HybridRetrievalCandidate(
                note_id=parent.note_id,
                parent_id=parent_id,
                document_type=document_type,
                title=parent.note.title,
                heading_path=tuple(parent.heading_path),
                source_hash=parent.source_hash,
                score=score,
                matched_child_excerpt=_shorten(excerpt),
                content=parent.content,
                start_line=parent.start_line,
                end_line=parent.end_line,
                diary_date=diary_date,
            )
            ranked_results.append(
                (candidate, parent.note.updated_at, parent.chunk_index)
            )

        ranked_results.extend(
            self._load_inline_keyword_results(
                inline_keyword_hits,
                selected_types=selected_types,
                tags=tags,
                date_from=date_from,
                date_to=date_to,
            )
        )

        ranked_results.sort(
            key=lambda item: (item[0].score, item[1], -item[2]),
            reverse=True,
        )
        return tuple(item[0] for item in ranked_results[:limit])

    def _load_inline_keyword_results(
        self,
        keyword_hits: tuple[tuple[int, KeywordCandidate], ...],
        *,
        selected_types: frozenset[str],
        tags: tuple[str, ...],
        date_from: date | None,
        date_to: date | None,
    ) -> list[tuple[HybridRetrievalCandidate, object, int]]:
        """复验并返回尚无活动父片段的当前 Note 临时章节。"""

        if not keyword_hits:
            return []
        note_ids = {candidate.note_id for _, candidate in keyword_hits}
        queryset = (
            Note.objects.select_related('diary_entry')
            .prefetch_related('tags')
            .filter(
                pk__in=note_ids,
                is_deleted=False,
                ai_indexing_enabled=True,
            )
        )
        if selected_types == {'note'}:
            queryset = queryset.filter(diary_entry__isnull=True)
        elif selected_types == {'diary'}:
            queryset = queryset.filter(diary_entry__isnull=False)
        for tag in tags:
            queryset = queryset.filter(tags__name=tag)
        if date_from:
            queryset = queryset.filter(diary_entry__diary_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(diary_entry__diary_date__lte=date_to)
        notes_by_id = {note.pk: note for note in queryset.distinct()}

        results = []
        for rank, keyword_hit in keyword_hits:
            note = notes_by_id.get(keyword_hit.note_id)
            if note is None or keyword_hit.source_hash != _source_hash(note.markdown_content):
                continue
            document_type, diary_date = _note_document_type(note)
            if keyword_hit.document_type != document_type:
                continue
            content = _content_for_line_range(
                note.markdown_content,
                keyword_hit.start_line,
                keyword_hit.end_line,
            )
            if not content:
                continue
            candidate = HybridRetrievalCandidate(
                note_id=note.pk,
                parent_id=None,
                document_type=document_type,
                title=note.title,
                heading_path=keyword_hit.heading_path,
                source_hash=keyword_hit.source_hash,
                score=_fused_score((), (rank, keyword_hit)),
                matched_child_excerpt=_shorten(keyword_hit.matched_excerpt),
                content=content,
                start_line=keyword_hit.start_line,
                end_line=keyword_hit.end_line,
                diary_date=diary_date,
            )
            results.append((candidate, note.updated_at, keyword_hit.start_line))
        return results

    def _load_current_parents(
        self,
        parent_ids: set[str],
        *,
        selected_types: frozenset[str],
        tags: tuple[str, ...],
        date_from: date | None,
        date_to: date | None,
    ) -> tuple[RagParentChunk, ...]:
        if not parent_ids:
            return ()
        queryset = (
            RagParentChunk.objects.select_related(
                'note',
                'note__rag_index_state',
                'note__diary_entry',
            )
            .filter(
                pk__in=parent_ids,
                note__is_deleted=False,
                note__ai_indexing_enabled=True,
                note__rag_index_state__embedding_version=self.embedding_version,
                # source_hash is populated only after a version is successfully activated.
                # The latest attempt may be indexing or failed while this active version
                # remains valid and should continue serving reads.
                note__rag_index_state__source_hash__gt='',
                index_version=F('note__rag_index_state__index_version'),
                source_hash=F('note__rag_index_state__source_hash'),
            )
        )
        if selected_types == {'note'}:
            queryset = queryset.filter(note__diary_entry__isnull=True)
        elif selected_types == {'diary'}:
            queryset = queryset.filter(note__diary_entry__isnull=False)
        for tag in tags:
            queryset = queryset.filter(note__tags__name=tag)
        if date_from:
            queryset = queryset.filter(note__diary_entry__diary_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(note__diary_entry__diary_date__lte=date_to)

        # 数据库约束验证版本，Python 再验证 Note 当前正文哈希，阻断保存后的短暂旧索引窗口。
        return tuple(
            parent
            for parent in queryset.distinct()
            if parent.source_hash == _source_hash(parent.note.markdown_content)
        )


def _group_dense_hits(
    points: tuple[QdrantScoredPoint, ...],
) -> dict[str, tuple[_DenseHit, ...]]:
    grouped: dict[str, list[_DenseHit]] = {}
    for rank, point in enumerate(points, start=1):
        hit = _parse_dense_hit(point, rank)
        if hit:
            grouped.setdefault(hit.parent_id, []).append(hit)
    return {parent_id: tuple(hits) for parent_id, hits in grouped.items()}


def _parse_dense_hit(point: QdrantScoredPoint, rank: int) -> _DenseHit | None:
    payload = point.payload
    try:
        parent_id = str(UUID(str(payload['parent_id'])))
        note_id = payload['note_id']
        document_type = payload['type']
        source_hash = payload['source_hash']
        index_version = payload['index_version']
        embedding_version = payload['embedding_version']
        excerpt = payload['content']
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    if (
        not isinstance(note_id, int)
        or isinstance(note_id, bool)
        or note_id < 1
        or document_type not in ALLOWED_DOCUMENT_TYPES
        or not _is_sha256(source_hash)
        or not isinstance(index_version, int)
        or isinstance(index_version, bool)
        or index_version < 1
        or not isinstance(embedding_version, str)
        or not isinstance(excerpt, str)
        or not excerpt.strip()
    ):
        return None
    return _DenseHit(
        rank=rank,
        note_id=note_id,
        parent_id=parent_id,
        document_type=document_type,
        source_hash=source_hash,
        index_version=index_version,
        embedding_version=embedding_version,
        excerpt=excerpt,
    )


def _group_keyword_hits(
    candidates: tuple[KeywordCandidate, ...],
) -> dict[str, tuple[int, KeywordCandidate]]:
    grouped = {}
    for rank, candidate in enumerate(candidates, start=1):
        if not candidate.parent_id:
            continue
        try:
            parent_id = str(UUID(candidate.parent_id))
        except (ValueError, TypeError, AttributeError):
            continue
        grouped.setdefault(parent_id, (rank, candidate))
    return grouped


def _inline_keyword_hits(
    candidates: tuple[KeywordCandidate, ...],
) -> tuple[tuple[int, KeywordCandidate], ...]:
    return tuple(
        (rank, candidate)
        for rank, candidate in enumerate(candidates, start=1)
        if candidate.parent_id is None
    )


def _dense_hit_matches_parent(
    hit: _DenseHit,
    parent: RagParentChunk,
    document_type: DocumentType,
    embedding_version: str,
) -> bool:
    return (
        hit.note_id == parent.note_id
        and hit.document_type == document_type
        and hit.source_hash == parent.source_hash
        and hit.index_version == parent.index_version
        and hit.embedding_version == embedding_version
    )


def _keyword_hit_matches_parent(
    candidate: KeywordCandidate,
    parent: RagParentChunk,
    document_type: DocumentType,
) -> bool:
    return (
        candidate.note_id == parent.note_id
        and candidate.document_type == document_type
        and candidate.source_hash == parent.source_hash
    )


def _fused_score(
    dense_hits: tuple[_DenseHit, ...],
    keyword_hit: tuple[int, KeywordCandidate] | None,
) -> float:
    score = 0.0
    if dense_hits:
        score += 1 / (RRF_K + dense_hits[0].rank)
        # 同一父片段的额外子命中只作弱加分，避免长章节凭子片段数量占满结果。
        score += sum(0.1 / (RRF_K + hit.rank) for hit in dense_hits[1:])
    if keyword_hit:
        score += 1 / (RRF_K + keyword_hit[0])
    return round(score, 8)


def _current_document_type(parent: RagParentChunk) -> tuple[DocumentType, date | None]:
    diary = getattr(parent.note, 'diary_entry', None)
    return ('diary', diary.diary_date) if diary else ('note', None)


def _note_document_type(note: Note) -> tuple[DocumentType, date | None]:
    diary = getattr(note, 'diary_entry', None)
    return ('diary', diary.diary_date) if diary else ('note', None)


def _content_for_line_range(markdown_content: str, start_line: int, end_line: int) -> str:
    lines = markdown_content.splitlines(keepends=True)
    if not lines or start_line < 1 or end_line < start_line or end_line > len(lines):
        return ''
    return ''.join(lines[start_line - 1:end_line]).strip('\r\n')


def _source_hash(content: str) -> str:
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in '0123456789abcdef' for character in value)
    )


def _shorten(value: str) -> str:
    flattened = ' '.join(value.split())
    return flattened[:EXCERPT_LENGTH] + ('…' if len(flattened) > EXCERPT_LENGTH else '')


def _single_type(selected_types: frozenset[str]) -> DocumentType | None:
    return next(iter(selected_types)) if len(selected_types) == 1 else None


def _validate_types(types: Iterable[DocumentType] | None) -> frozenset[str]:
    if types is None:
        return ALLOWED_DOCUMENT_TYPES
    try:
        selected = {types} if isinstance(types, str) else set(types)
    except TypeError:
        selected = set()
    if not selected or not selected.issubset(ALLOWED_DOCUMENT_TYPES):
        raise HybridRetrievalError(
            code='retrieval_types_invalid',
            message='Retrieval types must contain note, diary, or both.',
        )
    return frozenset(selected)


def _validate_tags(tags: Iterable[str] | None) -> tuple[str, ...]:
    if tags is None:
        return ()
    try:
        values = (tags,) if isinstance(tags, str) else tuple(tags)
        normalized = tuple(dict.fromkeys(tag.strip() for tag in values))
    except (TypeError, AttributeError):
        normalized = ()
        values = (None,)
    if not values:
        return ()
    if not normalized or any(not tag for tag in normalized) or len(normalized) > 20:
        raise HybridRetrievalError(
            code='retrieval_tags_invalid',
            message='Retrieval tags must contain at most 20 non-empty names.',
        )
    return normalized


def _validate_date_range(date_from: date | None, date_to: date | None):
    if (date_from is not None and not isinstance(date_from, date)) or (
        date_to is not None and not isinstance(date_to, date)
    ):
        raise HybridRetrievalError(
            code='retrieval_date_invalid',
            message='Retrieval date filters must be date values.',
        )
    if date_from and date_to and date_from > date_to:
        raise HybridRetrievalError(
            code='retrieval_date_range_reversed',
            message='Retrieval date range must not be reversed.',
        )


def _validate_limit(value: int, field_name: str, maximum: int):
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not 1 <= value <= maximum
    ):
        raise HybridRetrievalError(
            code=f'retrieval_{field_name}_invalid',
            message=f'{field_name} must be between 1 and {maximum}.',
        )


@lru_cache(maxsize=1)
def get_hybrid_retrieval_service() -> HybridRetrievalService:
    """组装进程级检索依赖，复用 Embedding 和 Qdrant 连接。"""

    return HybridRetrievalService(
        embedding_service=get_embedding_service(),
        vector_store=get_qdrant_store(),
        embedding_version=settings.RAG_EMBEDDING_VERSION,
        dense_score_threshold=settings.RAG_DENSE_SCORE_THRESHOLD,
    )


def retrieve(
    query: str,
    *,
    types: Iterable[DocumentType] | None = None,
    tags: Iterable[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    dense_top_k: int = 20,
    keyword_top_k: int = 20,
    final_parent_top_k: int = 5,
) -> HybridRetrievalResult:
    """公开的混合检索入口。"""

    return get_hybrid_retrieval_service().retrieve(
        query,
        types=types,
        tags=tags,
        date_from=date_from,
        date_to=date_to,
        dense_top_k=dense_top_k,
        keyword_top_k=keyword_top_k,
        final_parent_top_k=final_parent_top_k,
    )
