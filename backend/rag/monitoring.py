"""RAG 索引积压、失败率和当前索引状态的只读运行快照。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from django.db.models import Count, Min
from django.utils import timezone

from .models import RagIndexDeletionJob, RagIndexJob, RagIndexState


@dataclass(frozen=True, slots=True)
class RagRuntimeSnapshot:
    generated_at: datetime
    job_counts: dict[str, int]
    deletion_job_counts: dict[str, int]
    state_counts: dict[str, int]
    backlog_count: int
    deletion_backlog_count: int
    failed_job_rate: float
    oldest_pending_age_seconds: float | None

    def as_dict(self) -> dict[str, object]:
        return {
            'generated_at': self.generated_at.isoformat(),
            'job_counts': self.job_counts,
            'deletion_job_counts': self.deletion_job_counts,
            'state_counts': self.state_counts,
            'backlog_count': self.backlog_count,
            'deletion_backlog_count': self.deletion_backlog_count,
            'failed_job_rate': self.failed_job_rate,
            'oldest_pending_age_seconds': self.oldest_pending_age_seconds,
        }


def get_rag_runtime_snapshot(*, now=None) -> RagRuntimeSnapshot:
    """用固定数量聚合查询生成监控快照，不读取笔记正文或错误详情。"""

    current_time = now or timezone.now()
    job_counts = _status_counts(RagIndexJob, RagIndexJob.Status.values)
    deletion_job_counts = _status_counts(
        RagIndexDeletionJob,
        RagIndexDeletionJob.Status.values,
    )
    state_counts = _status_counts(RagIndexState, RagIndexState.Status.values)
    index_backlog_count = (
        job_counts[RagIndexJob.Status.PENDING]
        + job_counts[RagIndexJob.Status.INDEXING]
    )
    deletion_backlog_count = (
        deletion_job_counts[RagIndexDeletionJob.Status.PENDING]
        + deletion_job_counts[RagIndexDeletionJob.Status.INDEXING]
    )
    backlog_count = index_backlog_count + deletion_backlog_count
    finished_jobs = (
        job_counts[RagIndexJob.Status.COMPLETED]
        + job_counts[RagIndexJob.Status.FAILED]
    )
    failed_job_rate = (
        round(job_counts[RagIndexJob.Status.FAILED] / finished_jobs, 6)
        if finished_jobs
        else 0.0
    )
    oldest_pending = RagIndexJob.objects.filter(
        status=RagIndexJob.Status.PENDING
    ).aggregate(oldest=Min('created_at'))['oldest']
    oldest_pending_age_seconds = (
        round(max(0.0, (current_time - oldest_pending).total_seconds()), 3)
        if oldest_pending
        else None
    )
    return RagRuntimeSnapshot(
        generated_at=current_time,
        job_counts=job_counts,
        deletion_job_counts=deletion_job_counts,
        state_counts=state_counts,
        backlog_count=backlog_count,
        deletion_backlog_count=deletion_backlog_count,
        failed_job_rate=failed_job_rate,
        oldest_pending_age_seconds=oldest_pending_age_seconds,
    )


def _status_counts(model, statuses) -> dict[str, int]:
    counts = {status: 0 for status in statuses}
    rows = model.objects.values('status').annotate(total=Count('pk'))
    for row in rows:
        counts[row['status']] = row['total']
    return counts
