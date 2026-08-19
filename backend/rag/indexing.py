"""单篇 Note 的父子分块、Embedding、Qdrant 写入与版本切换流程。"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from time import perf_counter
from uuid import NAMESPACE_URL, UUID, uuid5

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from notes.models import DiaryEntry, Note

from .chunking import (
    BgeM3TokenCounter,
    ChildChunk,
    ChildChunkConfig,
    ChildChunkingError,
    ParentChunk,
    ParentChunkConfig,
    RagDocumentMetadata,
    TokenCounter,
    split_child_chunks,
    split_parent_chunks,
)
from .chunking.tokenizer import TokenizerLoadError
from .embeddings import EmbeddingService, EmbeddingServiceError, get_embedding_service
from .models import RagIndexState, RagParentChunk
from .qdrant import (
    QdrantChunkPayload,
    QdrantChunkPoint,
    QdrantStoreError,
    QdrantVectorStore,
    get_qdrant_store,
)


PARENT_ID_NAMESPACE = uuid5(NAMESPACE_URL, 'moonbirdnotes:rag-parent:v1')
POINT_ID_NAMESPACE = uuid5(NAMESPACE_URL, 'moonbirdnotes:rag-child-point:v1')
logger = logging.getLogger(__name__)


class NoteIndexingError(RuntimeError):
    """单篇索引流程统一、可安全写入状态表的结构化异常。"""

    def __init__(self, *, code: str, message: str, retryable: bool):
        super().__init__(message)
        self.code = code
        self.retryable = retryable

    def as_dict(self) -> dict[str, str | bool]:
        return {
            'code': self.code,
            'message': str(self),
            'retryable': self.retryable,
        }


@dataclass(frozen=True, slots=True)
class NoteSnapshot:
    """一次索引尝试绑定的 Note、标签和日记元数据快照。"""

    note_id: int
    title: str
    markdown_content: str
    is_deleted: bool
    ai_indexing_enabled: bool
    tags: tuple[str, ...]
    diary_date: date | None
    mood: str
    weather: str
    summary: str

    @property
    def source_hash(self) -> str:
        """规范中的 source_hash 只标识完整 Markdown 原文。"""

        return hashlib.sha256(self.markdown_content.encode('utf-8')).hexdigest()

    @property
    def snapshot_hash(self) -> str:
        """额外覆盖会影响向量文本的标题、标签和日记字段，用于并发校验。"""

        payload = {
            'note_id': self.note_id,
            'title': self.title,
            'markdown_content': self.markdown_content,
            'is_deleted': self.is_deleted,
            'ai_indexing_enabled': self.ai_indexing_enabled,
            'tags': self.tags,
            'diary_date': self.diary_date.isoformat() if self.diary_date else None,
            'mood': self.mood,
            'weather': self.weather,
            'summary': self.summary,
        }
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(serialized.encode('utf-8')).hexdigest()

    def document_metadata(self) -> RagDocumentMetadata:
        if self.diary_date is None:
            return RagDocumentMetadata(
                document_type='note',
                title=self.title,
                tags=self.tags,
            )
        return RagDocumentMetadata(
            document_type='diary',
            title=self.title,
            diary_date=self.diary_date,
            mood=self.mood,
            weather=self.weather,
            summary=self.summary,
        )


@dataclass(frozen=True, slots=True)
class PreparedChild:
    """绑定确定性父片段 UUID 的子片段。"""

    parent_id: UUID
    child: ChildChunk


@dataclass(frozen=True, slots=True)
class PreparedIndex:
    """发起外部写入前已完全确定的父子片段计划。"""

    parent_models: tuple[RagParentChunk, ...]
    children: tuple[PreparedChild, ...]


@dataclass(frozen=True, slots=True)
class IndexNoteResult:
    note_id: int
    source_hash: str
    index_version: int
    parent_count: int
    child_count: int
    cleanup_complete: bool


@dataclass(frozen=True, slots=True)
class DeleteNoteIndexResult:
    note_id: int
    deleted_parent_count: int
    deleted_state_count: int


class NoteIndexingService:
    """同步执行单篇索引；后台排队与防抖由第十步负责。"""

    def __init__(
        self,
        *,
        token_counter: TokenCounter,
        embedding_service: EmbeddingService,
        vector_store: QdrantVectorStore,
        embedding_model: str,
        embedding_version: str,
        parent_config: ParentChunkConfig | None = None,
        child_config: ChildChunkConfig | None = None,
    ):
        self.token_counter = token_counter
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.embedding_model = embedding_model
        self.embedding_version = embedding_version
        self.parent_config = parent_config or ParentChunkConfig()
        self.child_config = child_config or ChildChunkConfig()

    def index_note(self, note_id: int) -> IndexNoteResult:
        """完整重建一篇 Note；新版本可用前不删除旧版本。"""

        started = perf_counter()
        _validate_note_id(note_id)
        snapshot = self._load_snapshot(note_id)
        self._validate_snapshot_can_index(snapshot)
        target_version = self._begin_attempt(note_id)

        try:
            prepared = self._prepare_index(snapshot, target_version)
            vectors = self.embedding_service.embed_documents(
                [item.child.vector_text for item in prepared.children]
            )
            if len(vectors) != len(prepared.children):
                raise NoteIndexingError(
                    code='indexing_vector_count_mismatch',
                    message='Embedding result count does not match prepared child chunks.',
                    retryable=False,
                )

            self._save_parent_version(snapshot, target_version, prepared.parent_models)
            # Worker 已在调用前校验 target_source_hash；此处在 Qdrant 写入前再验完整快照。
            self._assert_snapshot_current(snapshot)
            # 重试同一目标版本时，先清理上一次未激活的部分 Point。
            self.vector_store.delete_note_version(
                note_id=note_id,
                index_version=target_version,
            )
            points = self._build_qdrant_points(snapshot, target_version, prepared.children, vectors)
            if points:
                self.vector_store.upsert_points(points)
            self._activate_version(snapshot, target_version)
        except Exception as exc:
            error = _normalize_indexing_error(exc)
            self._cleanup_failed_version(note_id, target_version)
            self._mark_attempt_failed(note_id, target_version, error)
            logger.error(
                'RAG note indexing failed.',
                extra={
                    'note_id': note_id,
                    'index_version': target_version,
                    'embedding_model': self.embedding_model,
                    'embedding_version': self.embedding_version,
                    'indexing_duration_ms': round((perf_counter() - started) * 1000, 3),
                    'error_code': error.code,
                    'retryable': error.retryable,
                },
            )
            raise error from None

        cleanup_complete = self._cleanup_old_versions(note_id, target_version)
        result = IndexNoteResult(
            note_id=note_id,
            source_hash=snapshot.source_hash,
            index_version=target_version,
            parent_count=len(prepared.parent_models),
            child_count=len(prepared.children),
            cleanup_complete=cleanup_complete,
        )
        logger.info(
            'RAG note indexing completed.',
            extra={
                'note_id': note_id,
                'index_version': target_version,
                'embedding_model': self.embedding_model,
                'embedding_version': self.embedding_version,
                'parent_count': result.parent_count,
                'child_count': result.child_count,
                'cleanup_complete': cleanup_complete,
                'indexing_duration_ms': round((perf_counter() - started) * 1000, 3),
            },
        )
        return result

    def delete_note_index(self, note_id: int) -> DeleteNoteIndexResult:
        """删除一篇 Note 的全部派生索引，不修改 Note 真实内容。"""

        _validate_note_id(note_id)
        state = RagIndexState.objects.filter(note_id=note_id).only('status').first()
        if state and state.status == RagIndexState.Status.INDEXING:
            raise NoteIndexingError(
                code='indexing_in_progress',
                message='Cannot delete note index while indexing is in progress.',
                retryable=True,
            )

        # 先删除外部派生数据；Qdrant 不可用时保留 MySQL 状态以便安全重试。
        try:
            self.vector_store.delete_note(note_id=note_id)
        except Exception as exc:
            raise _normalize_indexing_error(exc) from None

        with transaction.atomic():
            deleted_parent_count, _ = RagParentChunk.objects.filter(note_id=note_id).delete()
            deleted_state_count, _ = RagIndexState.objects.filter(note_id=note_id).delete()
        return DeleteNoteIndexResult(
            note_id=note_id,
            deleted_parent_count=deleted_parent_count,
            deleted_state_count=deleted_state_count,
        )

    def _load_snapshot(self, note_id: int, *, lock: bool = False) -> NoteSnapshot:
        queryset = Note.objects.select_related('diary_entry').prefetch_related('tags')
        if lock:
            queryset = queryset.select_for_update()
        try:
            note = queryset.get(pk=note_id)
        except Note.DoesNotExist:
            raise NoteIndexingError(
                code='note_not_found',
                message='Note does not exist.',
                retryable=False,
            ) from None

        try:
            diary = note.diary_entry
        except DiaryEntry.DoesNotExist:
            diary = None
        tags = tuple(sorted(tag.name for tag in note.tags.all()))
        return NoteSnapshot(
            note_id=note.id,
            title=note.title,
            markdown_content=note.markdown_content,
            is_deleted=note.is_deleted,
            ai_indexing_enabled=note.ai_indexing_enabled,
            # 日记不消费 Note.tags，即使历史脏数据意外携带标签也不会进入向量文本。
            tags=() if diary else tags,
            diary_date=diary.diary_date if diary else None,
            mood=diary.mood if diary else '',
            weather=diary.weather if diary else '',
            summary=diary.summary if diary else '',
        )

    def _validate_snapshot_can_index(self, snapshot: NoteSnapshot):
        if snapshot.is_deleted:
            raise NoteIndexingError(
                code='note_deleted',
                message='Deleted notes cannot be indexed.',
                retryable=False,
            )
        if not snapshot.ai_indexing_enabled:
            raise NoteIndexingError(
                code='ai_indexing_disabled',
                message='AI indexing is not enabled for this note.',
                retryable=False,
            )

    def _begin_attempt(self, note_id: int) -> int:
        with transaction.atomic():
            state, _ = RagIndexState.objects.select_for_update().get_or_create(note_id=note_id)
            if state.status == RagIndexState.Status.INDEXING:
                raise NoteIndexingError(
                    code='indexing_in_progress',
                    message='This note is already being indexed.',
                    retryable=True,
                )
            active_version = state.index_version if state.source_hash else 0
            target_version = max(active_version, state.latest_attempt_version) + 1
            # 激活字段继续指向旧版本，只标记本次尝试正在运行。
            state.latest_attempt_version = target_version
            state.status = RagIndexState.Status.INDEXING
            state.error_message = ''
            state.save(update_fields=['latest_attempt_version', 'status', 'error_message'])
            return target_version

    def _prepare_index(self, snapshot: NoteSnapshot, index_version: int) -> PreparedIndex:
        parent_chunks = split_parent_chunks(
            snapshot.markdown_content,
            token_counter=self.token_counter,
            config=self.parent_config,
        )
        metadata = snapshot.document_metadata()
        parent_models: list[RagParentChunk] = []
        children: list[PreparedChild] = []

        for parent in parent_chunks:
            parent_id = _parent_id(snapshot.note_id, index_version, parent)
            parent_models.append(
                RagParentChunk(
                    id=parent_id,
                    note_id=snapshot.note_id,
                    chunk_index=parent.chunk_index,
                    heading_path=list(parent.heading_path),
                    content=parent.content,
                    start_line=parent.start_line,
                    end_line=parent.end_line,
                    source_hash=snapshot.source_hash,
                    section_hash=parent.section_hash,
                    index_version=index_version,
                )
            )
            children.extend(
                PreparedChild(parent_id=parent_id, child=child)
                for child in split_child_chunks(
                    parent,
                    parent_id=parent_id,
                    metadata=metadata,
                    token_counter=self.token_counter,
                    config=self.child_config,
                )
            )
        return PreparedIndex(tuple(parent_models), tuple(children))

    def _save_parent_version(
        self,
        snapshot: NoteSnapshot,
        index_version: int,
        parent_models: tuple[RagParentChunk, ...],
    ):
        with transaction.atomic():
            self._assert_snapshot_current(snapshot, lock=True)
            RagParentChunk.objects.filter(
                note_id=snapshot.note_id,
                index_version=index_version,
            ).delete()
            RagParentChunk.objects.bulk_create(parent_models)

    def _build_qdrant_points(
        self,
        snapshot: NoteSnapshot,
        index_version: int,
        children: tuple[PreparedChild, ...],
        vectors: list[list[float]],
    ) -> list[QdrantChunkPoint]:
        points = []
        for item, vector in zip(children, vectors, strict=True):
            child = item.child
            points.append(
                QdrantChunkPoint(
                    point_id=_point_id(item.parent_id, child),
                    vector=tuple(vector),
                    payload=QdrantChunkPayload(
                        note_id=snapshot.note_id,
                        parent_id=str(item.parent_id),
                        document_type='diary' if snapshot.diary_date else 'note',
                        title=snapshot.title,
                        heading_path=child.heading_path,
                        tags=() if snapshot.diary_date else snapshot.tags,
                        diary_date=snapshot.diary_date,
                        chunk_index=child.chunk_index,
                        content=child.content,
                        chunk_hash=child.chunk_hash,
                        source_hash=snapshot.source_hash,
                        index_version=index_version,
                        embedding_version=self.embedding_version,
                    ),
                )
            )
        return points

    def _activate_version(self, snapshot: NoteSnapshot, index_version: int):
        with transaction.atomic():
            self._assert_snapshot_current(snapshot, lock=True)
            state = RagIndexState.objects.select_for_update().get(note_id=snapshot.note_id)
            if (
                state.status != RagIndexState.Status.INDEXING
                or state.latest_attempt_version != index_version
            ):
                raise NoteIndexingError(
                    code='indexing_state_conflict',
                    message='RAG index state changed during indexing.',
                    retryable=True,
                )
            state.source_hash = snapshot.source_hash
            state.embedding_model = self.embedding_model
            state.embedding_version = self.embedding_version
            state.index_version = index_version
            state.status = RagIndexState.Status.COMPLETED
            state.indexed_at = timezone.now()
            state.error_message = ''
            state.save(
                update_fields=[
                    'source_hash',
                    'embedding_model',
                    'embedding_version',
                    'index_version',
                    'status',
                    'indexed_at',
                    'error_message',
                ]
            )

    def _assert_snapshot_current(self, expected: NoteSnapshot, *, lock: bool = False):
        try:
            current = self._load_snapshot(expected.note_id, lock=lock)
        except NoteIndexingError as exc:
            if exc.code == 'note_not_found':
                raise NoteIndexingError(
                    code='note_changed_during_indexing',
                    message='Note changed or was removed during indexing.',
                    retryable=True,
                ) from None
            raise
        if current.snapshot_hash != expected.snapshot_hash:
            raise NoteIndexingError(
                code='note_changed_during_indexing',
                message='Note changed during indexing; stale output was discarded.',
                retryable=True,
            )

    def _cleanup_failed_version(self, note_id: int, index_version: int):
        # 外部清理失败时保留不可激活的孤立 Point，后续同版本重试会再次清理。
        try:
            self.vector_store.delete_note_version(
                note_id=note_id,
                index_version=index_version,
            )
        except Exception:
            pass
        try:
            RagParentChunk.objects.filter(
                note_id=note_id,
                index_version=index_version,
            ).delete()
        except Exception:
            pass

    def _mark_attempt_failed(
        self,
        note_id: int,
        index_version: int,
        error: NoteIndexingError,
    ):
        with transaction.atomic():
            state = RagIndexState.objects.select_for_update().filter(note_id=note_id).first()
            if (
                state is None
                or state.status != RagIndexState.Status.INDEXING
                or state.latest_attempt_version != index_version
            ):
                return
            state.status = RagIndexState.Status.FAILED
            state.error_message = f'{error.code}: {error}'
            state.save(update_fields=['status', 'error_message'])

    def _cleanup_old_versions(self, note_id: int, active_version: int) -> bool:
        old_versions = list(
            RagParentChunk.objects.filter(note_id=note_id)
            .exclude(index_version=active_version)
            .values_list('index_version', flat=True)
            .distinct()
        )
        failed_versions = []
        for old_version in old_versions:
            try:
                self.vector_store.delete_note_version(
                    note_id=note_id,
                    index_version=old_version,
                )
                RagParentChunk.objects.filter(
                    note_id=note_id,
                    index_version=old_version,
                ).delete()
            except Exception:
                # 新版本已经激活，旧版本即使暂时残留也不会被当前状态采用。
                failed_versions.append(old_version)

        if failed_versions:
            message = 'cleanup_pending: old index versions require cleanup: ' + ','.join(
                str(version) for version in sorted(failed_versions)
            )
            RagIndexState.objects.filter(
                note_id=note_id,
                index_version=active_version,
                status=RagIndexState.Status.COMPLETED,
            ).update(error_message=message)
            return False
        return True


def _parent_id(note_id: int, index_version: int, parent: ParentChunk) -> UUID:
    identity = f'{note_id}:{index_version}:{parent.chunk_index}:{parent.section_hash}'
    return uuid5(PARENT_ID_NAMESPACE, identity)


def _point_id(parent_id: UUID, child: ChildChunk) -> str:
    identity = f'{parent_id}:{child.chunk_index}:{child.chunk_hash}'
    return str(uuid5(POINT_ID_NAMESPACE, identity))


def _validate_note_id(note_id: int):
    if not isinstance(note_id, int) or isinstance(note_id, bool) or note_id < 1:
        raise NoteIndexingError(
            code='invalid_note_id',
            message='note_id must be a positive integer.',
            retryable=False,
        )


def _normalize_indexing_error(exc: Exception) -> NoteIndexingError:
    if isinstance(exc, NoteIndexingError):
        return exc
    if isinstance(exc, (EmbeddingServiceError, QdrantStoreError)):
        return NoteIndexingError(
            code=exc.code,
            message=str(exc),
            retryable=exc.retryable,
        )
    if isinstance(exc, TokenizerLoadError):
        return NoteIndexingError(
            code='indexing_tokenizer_unavailable',
            message='Embedding tokenizer is unavailable.',
            retryable=True,
        )
    if isinstance(exc, ChildChunkingError):
        return NoteIndexingError(
            code='indexing_chunking_error',
            message='Note contains a structure that cannot be chunked safely.',
            retryable=False,
        )
    return NoteIndexingError(
        code='indexing_unexpected_error',
        message='Note indexing failed unexpectedly.',
        retryable=False,
    )


@lru_cache(maxsize=1)
def get_note_indexing_service() -> NoteIndexingService:
    """组装进程级依赖，复用 Embedding 与 Qdrant HTTP 连接池。"""

    return NoteIndexingService(
        token_counter=BgeM3TokenCounter(
            model_name=settings.RAG_EMBEDDING_MODEL,
            tokenizer_file=settings.RAG_TOKENIZER_FILE or None,
        ),
        embedding_service=get_embedding_service(),
        vector_store=get_qdrant_store(),
        embedding_model=settings.RAG_EMBEDDING_MODEL,
        embedding_version=settings.RAG_EMBEDDING_VERSION,
    )


def index_note(note_id: int) -> IndexNoteResult:
    """公开的单篇索引接口。"""

    return get_note_indexing_service().index_note(note_id)


def delete_note_index(note_id: int) -> DeleteNoteIndexResult:
    """公开的单篇索引删除接口。"""

    return get_note_indexing_service().delete_note_index(note_id)
