"""保存可从笔记原文重建的 RAG 父片段、索引状态和索引任务。"""

import uuid

from django.db import models
from django.utils import timezone

from notes.models import Note


class RagParentChunk(models.Model):
    """保存在 MySQL 中的父片段，用于向量召回后的完整上下文回查。"""

    # UUID 会作为 Qdrant 子片段 Payload 中稳定的 parent_id。
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Note.markdown_content 是真实来源；Note 硬删除后派生片段随之清理。
    note = models.ForeignKey(
        Note,
        related_name='rag_parent_chunks',
        on_delete=models.CASCADE,
    )

    # chunk_index 只表示同一 Note、同一索引版本内的原文顺序。
    chunk_index = models.PositiveIntegerField()

    # 从顶层到当前章节的完整标题路径，例如 ["接口详情", "校验接口"]。
    heading_path = models.JSONField(default=list)

    # 父片段保留完整章节上下文，但它仍是可重建数据，不是笔记真实原文。
    content = models.TextField()

    # 行号只用于展示和辅助定位，后续写操作不能只依赖行号。
    start_line = models.PositiveIntegerField()
    end_line = models.PositiveIntegerField()

    # source_hash 校验完整原文版本，section_hash 校验当前父片段内容。
    source_hash = models.CharField(max_length=64)
    section_hash = models.CharField(max_length=64)

    # 分块规则或 Embedding 配置变化时递增版本，避免混用旧索引。
    index_version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['note_id', 'index_version', 'chunk_index']
        constraints = [
            # 一个索引版本中，同一顺序只能对应一个父片段。
            models.UniqueConstraint(
                fields=['note', 'index_version', 'chunk_index'],
                name='rag_parent_note_ver_chunk_uniq',
            ),
            # 防止保存无法对应原文位置的反向或零行号范围。
            models.CheckConstraint(
                condition=models.Q(start_line__gte=1, end_line__gte=models.F('start_line')),
                name='rag_parent_lines_valid',
            ),
            models.CheckConstraint(
                condition=models.Q(index_version__gte=1),
                name='rag_parent_version_valid',
            ),
        ]
        indexes = [
            # 单篇索引切换和父片段批量读取都按 Note 与版本查询。
            models.Index(
                fields=['note', 'index_version'],
                name='rag_parent_note_ver_idx',
            ),
            # 检索结果回查时按原文哈希快速过滤过期片段。
            models.Index(fields=['source_hash'], name='rag_parent_source_idx'),
        ]


class RagIndexState(models.Model):
    """记录每篇 Note 当前可用的 RAG 索引版本和执行状态。"""

    class Status(models.TextChoices):
        # 索引状态和任务状态使用同一组值，便于后续统一监控。
        PENDING = 'pending', 'Pending'
        INDEXING = 'indexing', 'Indexing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'

    # 一篇 Note 只能有一个当前状态，历史执行过程由 RagIndexJob 保存。
    note = models.OneToOneField(
        Note,
        related_name='rag_index_state',
        on_delete=models.CASCADE,
    )

    # 首次进入 pending、尚无成功索引时允许这些版本信息为空。
    source_hash = models.CharField(max_length=64, blank=True, default='')
    embedding_model = models.CharField(max_length=255, blank=True, default='')
    embedding_version = models.CharField(max_length=100, blank=True, default='')
    index_version = models.PositiveIntegerField(default=1)
    # 每次索引尝试先预留一个永不复用的版本，作为并发 Worker 的 fencing token。
    latest_attempt_version = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )

    # 只有成功完成索引后才填写 indexed_at；失败详情单独保存以便重试。
    indexed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default='')

    class Meta:
        constraints = [
            # choices 负责应用层校验，数据库约束防止绕过 ORM 写入非法状态。
            models.CheckConstraint(
                condition=models.Q(status__in=['pending', 'indexing', 'completed', 'failed']),
                name='rag_state_status_valid',
            ),
            models.CheckConstraint(
                condition=models.Q(index_version__gte=1),
                name='rag_state_version_valid',
            ),
        ]
        indexes = [
            models.Index(fields=['status'], name='rag_state_status_idx'),
        ]


class RagIndexJob(models.Model):
    """记录最终一致性索引流程中的一次可重试后台任务。"""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        INDEXING = 'indexing', 'Indexing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'

    # UUID 便于日志、Worker 和未来 Agent 运行记录安全引用同一任务。
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Note 是真实数据源；彻底删除 Note 后保留索引任务没有业务意义。
    note = models.ForeignKey(
        Note,
        related_name='rag_index_jobs',
        on_delete=models.CASCADE,
    )

    # Worker 执行前再次比较 target_source_hash，过期任务应停止而不是写旧索引。
    target_source_hash = models.CharField(max_length=64)

    # reason 区分保存触发、手动重建、模型变化等排队原因。
    reason = models.CharField(max_length=64)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )

    # 重试更新同一任务的 attempts，不依赖新增重复任务表示尝试次数。
    attempts = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    # 防抖和重试都通过 available_at 调度，不在保存请求中等待或 sleep。
    available_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']
        constraints = [
            # 不对 note + source_hash 永久去重，以允许模型或分块规则变化后重建。
            models.CheckConstraint(
                condition=models.Q(status__in=['pending', 'indexing', 'completed', 'failed']),
                name='rag_job_status_valid',
            ),
        ]
        indexes = [
            # Worker 按状态领取最早创建的任务。
            models.Index(
                fields=['status', 'created_at'],
                name='rag_job_status_created_idx',
            ),
            # Worker 只领取已经到期的 pending 任务。
            models.Index(
                fields=['status', 'available_at'],
                name='rag_job_status_avail_idx',
            ),
            # 支持查询单篇 Note 的索引任务历史。
            models.Index(
                fields=['note', 'created_at'],
                name='rag_job_note_created_idx',
            ),
        ]


class RagIndexDeletionJob(models.Model):
    """Note 删除后仍可重试的 Qdrant 全版本清理 outbox。"""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        INDEXING = 'indexing', 'Indexing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'

    # 不能使用 Note 外键，否则永久删除 Note 时任务会被级联删除。
    note_id = models.PositiveIntegerField(primary_key=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )
    attempts = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    available_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=['pending', 'indexing', 'completed', 'failed']),
                name='rag_delete_job_status_valid',
            ),
        ]
        indexes = [
            models.Index(
                fields=['status', 'available_at'],
                name='rag_delete_status_avail_idx',
            ),
        ]
