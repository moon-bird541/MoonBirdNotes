"""从 MySQL Note 全量或按范围重建可派生的 RAG 索引。"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from django.db import transaction

from notes.models import Note

from .indexing import NoteIndexingError, NoteIndexingService, get_note_indexing_service
from .models import RagIndexJob, RagIndexState, RagParentChunk
from .qdrant import QdrantStoreError, QdrantVectorStore, get_qdrant_store


RebuildScope = Literal['all', 'note', 'diary']


class RagRebuildError(RuntimeError):
    """全量重建启动条件或基础设施失败的结构化异常。"""

    def __init__(self, *, code: str, message: str, retryable: bool):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class RebuildFailure:
    note_id: int
    code: str
    retryable: bool


@dataclass(frozen=True, slots=True)
class RebuildRagResult:
    scope: RebuildScope
    total: int
    succeeded: int
    failed: int
    skipped: int
    recreated_collection: bool
    cleared_parent_count: int
    cleared_state_count: int
    failures: tuple[RebuildFailure, ...]


class RagIndexRebuildService:
    """逐篇复用单篇索引，确保一个失败不会中断后续 Note。"""

    def __init__(
        self,
        *,
        indexing_service: NoteIndexingService,
        vector_store: QdrantVectorStore,
    ):
        self.indexing_service = indexing_service
        self.vector_store = vector_store

    def rebuild(
        self,
        *,
        scope: RebuildScope = 'all',
        note_id: int | None = None,
        recreate_collection: bool = False,
    ) -> RebuildRagResult:
        self._validate_options(scope, note_id, recreate_collection)
        self._ensure_no_active_indexing()
        notes = list(self._candidate_queryset(scope, note_id))
        if note_id is not None and not notes:
            raise RagRebuildError(
                code='rebuild_note_not_found',
                message='Specified Note does not exist.',
                retryable=False,
            )

        cleared_parent_count = 0
        cleared_state_count = 0
        if recreate_collection:
            try:
                self.vector_store.recreate_collection()
            except QdrantStoreError as exc:
                raise RagRebuildError(
                    code=exc.code,
                    message=str(exc),
                    retryable=exc.retryable,
                ) from None
            # Collection 已清空，MySQL 中所有激活状态也必须清空，避免指向不存在的 Point。
            with transaction.atomic():
                cleared_parent_count, _ = RagParentChunk.objects.all().delete()
                cleared_state_count, _ = RagIndexState.objects.all().delete()

        succeeded = 0
        skipped = 0
        failures: list[RebuildFailure] = []
        for note in notes:
            if note.is_deleted or not note.ai_indexing_enabled:
                if recreate_collection:
                    skipped += 1
                    continue
                # 未重建 Collection 时也清理可能残留的未授权或已删除索引。
                try:
                    self.indexing_service.delete_note_index(note.id)
                    skipped += 1
                except NoteIndexingError as exc:
                    failures.append(RebuildFailure(note.id, exc.code, exc.retryable))
                except Exception:
                    failures.append(
                        RebuildFailure(note.id, 'rebuild_unexpected_error', False)
                    )
                continue

            try:
                self.indexing_service.index_note(note.id)
                succeeded += 1
            except NoteIndexingError as exc:
                failures.append(RebuildFailure(note.id, exc.code, exc.retryable))
            except Exception:
                # 命令输出只包含固定错误码，禁止泄漏正文或 Provider 响应。
                failures.append(RebuildFailure(note.id, 'rebuild_unexpected_error', False))

        return RebuildRagResult(
            scope=scope,
            total=len(notes),
            succeeded=succeeded,
            failed=len(failures),
            skipped=skipped,
            recreated_collection=recreate_collection,
            cleared_parent_count=cleared_parent_count,
            cleared_state_count=cleared_state_count,
            failures=tuple(failures),
        )

    def _candidate_queryset(self, scope: RebuildScope, note_id: int | None):
        queryset = Note.objects.select_related('diary_entry').order_by('id')
        if note_id is not None:
            return queryset.filter(pk=note_id)
        if scope == 'note':
            return queryset.filter(diary_entry__isnull=True)
        if scope == 'diary':
            return queryset.filter(diary_entry__isnull=False)
        return queryset

    def _validate_options(
        self,
        scope: RebuildScope,
        note_id: int | None,
        recreate_collection: bool,
    ):
        if scope not in {'all', 'note', 'diary'}:
            raise RagRebuildError(
                code='rebuild_invalid_scope',
                message='Rebuild scope must be all, note, or diary.',
                retryable=False,
            )
        if note_id is not None and (
            not isinstance(note_id, int) or isinstance(note_id, bool) or note_id < 1
        ):
            raise RagRebuildError(
                code='rebuild_invalid_note_id',
                message='note_id must be a positive integer.',
                retryable=False,
            )
        if note_id is not None and scope != 'all':
            raise RagRebuildError(
                code='rebuild_conflicting_options',
                message='Cannot combine note_id with a type scope.',
                retryable=False,
            )
        if recreate_collection and (note_id is not None or scope != 'all'):
            raise RagRebuildError(
                code='rebuild_partial_collection_recreation',
                message='Collection recreation requires a full all-notes rebuild.',
                retryable=False,
            )

    def _ensure_no_active_indexing(self):
        if RagIndexJob.objects.filter(status=RagIndexJob.Status.INDEXING).exists() or (
            RagIndexState.objects.filter(status=RagIndexState.Status.INDEXING).exists()
        ):
            raise RagRebuildError(
                code='rebuild_indexing_in_progress',
                message='Stop active index workers before starting a rebuild.',
                retryable=True,
            )


@lru_cache(maxsize=1)
def get_rag_index_rebuild_service() -> RagIndexRebuildService:
    """组装管理命令使用的全量重建服务。"""

    indexing_service = get_note_indexing_service()
    return RagIndexRebuildService(
        indexing_service=indexing_service,
        vector_store=get_qdrant_store(),
    )
