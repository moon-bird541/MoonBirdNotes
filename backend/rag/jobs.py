"""RAG 索引任务的防抖排队、租约领取、有限重试与 Worker。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache
from typing import Callable, Literal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from notes.models import Note

from .indexing import NoteIndexingError, NoteIndexingService, get_note_indexing_service
from .models import RagIndexDeletionJob, RagIndexJob, RagIndexState
from .qdrant import QdrantStoreError


JobOutcome = Literal['indexed', 'deleted', 'stale', 'retry', 'failed']


@dataclass(frozen=True, slots=True)
class JobProcessResult:
    """管理命令可以安全汇总的一次任务处理结果。"""

    job_id: str
    note_id: int
    outcome: JobOutcome
    attempts: int


def note_source_hash(markdown_content: str) -> str:
    """与第九步 source_hash 保持一致，只对完整 Markdown 计算 SHA-256。"""

    return hashlib.sha256(markdown_content.encode('utf-8')).hexdigest()


def enqueue_note_index(
    note_id: int,
    *,
    reason: str = 'note_saved',
    immediate: bool = False,
    now=None,
) -> RagIndexJob | None:
    """合并同一 Note 的 pending 任务，并把目标更新为最新原文哈希。"""

    _validate_note_id(note_id)
    normalized_reason = reason.strip() if isinstance(reason, str) else ''
    if not normalized_reason or len(normalized_reason) > 64:
        raise ValueError('reason must be a non-empty string up to 64 characters.')

    current_time = now or timezone.now()
    debounce_seconds = _non_negative_setting('RAG_INDEX_DEBOUNCE_SECONDS')
    available_at = current_time if immediate else current_time + timedelta(seconds=debounce_seconds)

    with transaction.atomic():
        # 锁定 Note 行，使多个请求不能同时为同一 Note 创建多个 pending 任务。
        note = (
            Note.objects.select_for_update()
            .only('id', 'markdown_content')
            .filter(pk=note_id)
            .first()
        )
        if note is None:
            return None

        pending_jobs = list(
            RagIndexJob.objects.select_for_update()
            .filter(note_id=note_id, status=RagIndexJob.Status.PENDING)
            .order_by('-created_at')
        )
        job = pending_jobs[0] if pending_jobs else None
        if len(pending_jobs) > 1:
            # 兼容旧数据或极端竞争留下的重复项，只保留最新 pending 任务。
            RagIndexJob.objects.filter(pk__in=[item.pk for item in pending_jobs[1:]]).update(
                status=RagIndexJob.Status.COMPLETED,
                completed_at=current_time,
                error_message='superseded_by_latest_pending_job',
            )

        target_hash = note_source_hash(note.markdown_content)
        if job is None:
            return RagIndexJob.objects.create(
                note=note,
                target_source_hash=target_hash,
                reason=normalized_reason,
                status=RagIndexJob.Status.PENDING,
                available_at=available_at,
            )

        job.target_source_hash = target_hash
        job.reason = normalized_reason
        job.available_at = available_at
        job.attempts = 0
        job.error_message = ''
        job.started_at = None
        job.completed_at = None
        job.save(
            update_fields=[
                'target_source_hash',
                'reason',
                'available_at',
                'attempts',
                'error_message',
                'started_at',
                'completed_at',
            ]
        )
        return job


def enqueue_note_index_on_commit(
    note_id: int,
    *,
    reason: str = 'note_saved',
    immediate: bool = False,
):
    """只在业务事务成功提交后创建任务，回滚时不留下幽灵任务。"""

    transaction.on_commit(
        lambda: enqueue_note_index(
            note_id,
            reason=reason,
            immediate=immediate,
        )
    )


def enqueue_note_ids_on_commit(note_ids, *, reason: str):
    """为 QuerySet.update 等不会触发 save signal 的批量操作补充排队。"""

    normalized_ids = tuple(sorted(set(note_ids)))
    if not normalized_ids:
        return

    def enqueue_all():
        for note_id in normalized_ids:
            enqueue_note_index(note_id, reason=reason)

    transaction.on_commit(enqueue_all)


def enqueue_note_deletion(note_id: int, *, now=None) -> RagIndexDeletionJob:
    """持久化不依赖 Note 外键的删除任务，供永久删除后继续清理 Qdrant。"""

    _validate_note_id(note_id)
    current_time = now or timezone.now()
    with transaction.atomic():
        job = (
            RagIndexDeletionJob.objects.select_for_update()
            .filter(note_id=note_id)
            .first()
        )
        if job is None:
            return RagIndexDeletionJob.objects.create(
                note_id=note_id,
                status=RagIndexDeletionJob.Status.PENDING,
                available_at=current_time,
            )
        if job.status == RagIndexDeletionJob.Status.INDEXING:
            return job
        job.status = RagIndexDeletionJob.Status.PENDING
        job.attempts = 0
        job.error_message = ''
        job.available_at = current_time
        job.started_at = None
        job.completed_at = None
        job.save(
            update_fields=[
                'status',
                'attempts',
                'error_message',
                'available_at',
                'started_at',
                'completed_at',
            ]
        )
        return job


class RagIndexWorker:
    """一次领取一个到期索引或删除任务；支持多进程行锁。"""

    def __init__(
        self,
        *,
        indexing_service: NoteIndexingService,
        max_attempts: int,
        retry_base_seconds: int,
        lease_seconds: int,
        now: Callable = timezone.now,
    ):
        if max_attempts < 1 or retry_base_seconds < 0 or lease_seconds < 1:
            raise ValueError('Worker attempts/lease must be positive and retry delay non-negative.')
        self.indexing_service = indexing_service
        self.max_attempts = max_attempts
        self.retry_base_seconds = retry_base_seconds
        self.lease_seconds = lease_seconds
        self._now = now

    def process_next(self) -> JobProcessResult | None:
        """处理一个已经到期的任务；没有可运行任务时返回 None。"""

        current_time = self._now()
        self._recover_expired_leases(current_time)
        deletion_job = self._claim_next_deletion(current_time)
        if deletion_job is not None:
            return self._process_deletion(deletion_job)
        job = self._claim_next(current_time)
        if job is None:
            return None

        note = Note.objects.filter(pk=job.note_id).only(
            'id',
            'markdown_content',
            'is_deleted',
            'ai_indexing_enabled',
        ).first()
        if note is None:
            return self._complete(job, outcome='stale', message='note_not_found')

        current_hash = note_source_hash(note.markdown_content)
        if current_hash != job.target_source_hash:
            result = self._complete(job, outcome='stale', message='stale_source_hash')
            enqueue_note_index(note.id, reason='stale_source_hash')
            return result

        try:
            if note.is_deleted or not note.ai_indexing_enabled:
                self.indexing_service.delete_note_index(note.id)
                return self._complete(job, outcome='deleted')
            self.indexing_service.index_note(note.id)
            return self._complete(job, outcome='indexed')
        except NoteIndexingError as exc:
            return self._handle_error(job, exc)
        except Exception:
            return self._handle_error(
                job,
                NoteIndexingError(
                    code='index_job_unexpected_error',
                    message='Background note indexing failed unexpectedly.',
                    retryable=False,
                ),
            )

    def _claim_next(self, current_time):
        with transaction.atomic():
            job = (
                RagIndexJob.objects.select_for_update(skip_locked=True)
                .filter(
                    status=RagIndexJob.Status.PENDING,
                    available_at__lte=current_time,
                )
                .order_by('available_at', 'created_at')
                .first()
            )
            if job is None:
                return None
            job.status = RagIndexJob.Status.INDEXING
            job.attempts += 1
            job.started_at = current_time
            job.completed_at = None
            job.save(update_fields=['status', 'attempts', 'started_at', 'completed_at'])
            return job

    def _claim_next_deletion(self, current_time):
        with transaction.atomic():
            job = (
                RagIndexDeletionJob.objects.select_for_update(skip_locked=True)
                .filter(
                    status=RagIndexDeletionJob.Status.PENDING,
                    available_at__lte=current_time,
                )
                .order_by('available_at', 'created_at')
                .first()
            )
            if job is None:
                return None
            job.status = RagIndexDeletionJob.Status.INDEXING
            job.attempts += 1
            job.started_at = current_time
            job.completed_at = None
            job.save(update_fields=['status', 'attempts', 'started_at', 'completed_at'])
            return job

    def _process_deletion(self, job: RagIndexDeletionJob) -> JobProcessResult:
        try:
            self.indexing_service.vector_store.delete_note(note_id=job.note_id)
        except QdrantStoreError as exc:
            return self._handle_deletion_error(job, code=exc.code, retryable=exc.retryable)
        except Exception:
            return self._handle_deletion_error(
                job,
                code='qdrant_deletion_unexpected_error',
                retryable=False,
            )

        RagIndexDeletionJob.objects.filter(
            note_id=job.note_id,
            status=RagIndexDeletionJob.Status.INDEXING,
        ).update(
            status=RagIndexDeletionJob.Status.COMPLETED,
            completed_at=self._now(),
            error_message='',
        )
        return JobProcessResult(
            f'delete:{job.note_id}',
            job.note_id,
            'deleted',
            job.attempts,
        )

    def _recover_expired_leases(self, current_time):
        expired_before = current_time - timedelta(seconds=self.lease_seconds)
        with transaction.atomic():
            expired_jobs = list(
                RagIndexJob.objects.select_for_update(skip_locked=True).filter(
                    status=RagIndexJob.Status.INDEXING,
                    started_at__lt=expired_before,
                )
            )
            if expired_jobs:
                expired_note_ids = [job.note_id for job in expired_jobs]
                # 与任务行在同一事务内释放状态，其他 Worker 只能在提交后重新领取。
                RagIndexState.objects.filter(
                    note_id__in=expired_note_ids,
                    status=RagIndexState.Status.INDEXING,
                ).update(
                    status=RagIndexState.Status.FAILED,
                    error_message='worker_lease_expired',
                )
                retry_ids = [job.pk for job in expired_jobs if job.attempts < self.max_attempts]
                failed_ids = [job.pk for job in expired_jobs if job.attempts >= self.max_attempts]
                RagIndexJob.objects.filter(pk__in=retry_ids).update(
                    status=RagIndexJob.Status.PENDING,
                    available_at=current_time,
                    started_at=None,
                    error_message='worker_lease_expired',
                )
                RagIndexJob.objects.filter(pk__in=failed_ids).update(
                    status=RagIndexJob.Status.FAILED,
                    completed_at=current_time,
                    error_message='worker_lease_expired_max_attempts',
                )

            expired_deletions = list(
                RagIndexDeletionJob.objects.select_for_update(skip_locked=True).filter(
                    status=RagIndexDeletionJob.Status.INDEXING,
                    started_at__lt=expired_before,
                )
            )
            # 删除 outbox 不因租约次数耗尽而放弃；重复删除同一 note_id 是幂等的。
            RagIndexDeletionJob.objects.filter(
                note_id__in=[job.note_id for job in expired_deletions]
            ).update(
                status=RagIndexDeletionJob.Status.PENDING,
                available_at=current_time,
                started_at=None,
                error_message='worker_lease_expired',
            )

    def _handle_deletion_error(
        self,
        job: RagIndexDeletionJob,
        *,
        code: str,
        retryable: bool,
    ) -> JobProcessResult:
        if retryable:
            exponent = min(job.attempts - 1, self.max_attempts - 1)
            delay = self.retry_base_seconds * (2**exponent)
            RagIndexDeletionJob.objects.filter(
                note_id=job.note_id,
                status=RagIndexDeletionJob.Status.INDEXING,
            ).update(
                status=RagIndexDeletionJob.Status.PENDING,
                available_at=self._now() + timedelta(seconds=delay),
                started_at=None,
                completed_at=None,
                error_message=code,
            )
            outcome: JobOutcome = 'retry'
        else:
            RagIndexDeletionJob.objects.filter(
                note_id=job.note_id,
                status=RagIndexDeletionJob.Status.INDEXING,
            ).update(
                status=RagIndexDeletionJob.Status.FAILED,
                completed_at=self._now(),
                error_message=code,
            )
            outcome = 'failed'
        return JobProcessResult(
            f'delete:{job.note_id}',
            job.note_id,
            outcome,
            job.attempts,
        )

    def _handle_error(self, job: RagIndexJob, error: NoteIndexingError) -> JobProcessResult:
        if error.code == 'note_changed_during_indexing':
            result = self._complete(job, outcome='stale', message=error.code)
            enqueue_note_index(job.note_id, reason='note_changed_during_indexing')
            return result

        if error.retryable and job.attempts < self.max_attempts:
            delay = self.retry_base_seconds * (2 ** (job.attempts - 1))
            available_at = self._now() + timedelta(seconds=delay)
            RagIndexJob.objects.filter(
                pk=job.pk,
                status=RagIndexJob.Status.INDEXING,
            ).update(
                status=RagIndexJob.Status.PENDING,
                available_at=available_at,
                started_at=None,
                completed_at=None,
                error_message=f'{error.code}: {error}',
            )
            return JobProcessResult(str(job.pk), job.note_id, 'retry', job.attempts)

        RagIndexJob.objects.filter(
            pk=job.pk,
            status=RagIndexJob.Status.INDEXING,
        ).update(
            status=RagIndexJob.Status.FAILED,
            completed_at=self._now(),
            error_message=f'{error.code}: {error}',
        )
        return JobProcessResult(str(job.pk), job.note_id, 'failed', job.attempts)

    def _complete(
        self,
        job: RagIndexJob,
        *,
        outcome: JobOutcome,
        message: str = '',
    ) -> JobProcessResult:
        RagIndexJob.objects.filter(
            pk=job.pk,
            status=RagIndexJob.Status.INDEXING,
        ).update(
            status=RagIndexJob.Status.COMPLETED,
            completed_at=self._now(),
            error_message=message,
        )
        return JobProcessResult(str(job.pk), job.note_id, outcome, job.attempts)


def _validate_note_id(note_id: int):
    if not isinstance(note_id, int) or isinstance(note_id, bool) or note_id < 1:
        raise ValueError('note_id must be a positive integer.')


def _non_negative_setting(name: str) -> int:
    value = getattr(settings, name)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f'{name} must be a non-negative integer.')
    return value


@lru_cache(maxsize=1)
def get_rag_index_worker() -> RagIndexWorker:
    """组装管理命令使用的进程级 Worker。"""

    return RagIndexWorker(
        indexing_service=get_note_indexing_service(),
        max_attempts=settings.RAG_INDEX_MAX_ATTEMPTS,
        retry_base_seconds=settings.RAG_INDEX_RETRY_BASE_SECONDS,
        lease_seconds=settings.RAG_INDEX_LEASE_SECONDS,
    )
