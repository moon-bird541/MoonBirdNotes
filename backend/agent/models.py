"""Knowledge Agent 历史会话和问答记录模型。"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class KnowledgeConversation(models.Model):
    """属于单个管理员的持久化知识对话。"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='knowledge_conversations',
    )
    title = models.CharField(max_length=120)
    # 六轮之前的成功问答压缩为滚动摘要，原始 turn 记录仍完整保留。
    memory_summary = models.TextField(blank=True, default='')
    summarized_turn_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-updated_at', '-created_at')
        indexes = [models.Index(fields=('user', '-updated_at'))]


class KnowledgeConversationTurn(models.Model):
    """记录一次用户问题及其回答或结构化失败状态。"""

    class Status(models.TextChoices):
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        KnowledgeConversation,
        on_delete=models.CASCADE,
        related_name='turns',
    )
    run_id = models.UUIDField(unique=True)
    question = models.TextField()
    answer = models.TextField(blank=True, default='')
    sources = models.JSONField(default=list)
    insufficient_context = models.BooleanField(default=False)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.COMPLETED,
    )
    error_code = models.CharField(max_length=64, blank=True, default='')
    # 只保存脱敏诊断元数据，不保存问题、笔记正文或模型完整回答。
    run_trace = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('created_at',)
        indexes = [models.Index(fields=('conversation', 'created_at'))]


class AgentTokenUsage(models.Model):
    """与会话生命周期解耦的脱敏模型 Token 用量账本。"""

    class UsageStatus(models.TextChoices):
        AVAILABLE = 'available', 'Available'
        PARTIAL = 'partial', 'Partial'
        UNAVAILABLE = 'unavailable', 'Unavailable'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='agent_token_usages',
    )
    run_id = models.UUIDField(unique=True)
    request_count = models.PositiveIntegerField()
    usage_reported_request_count = models.PositiveIntegerField()
    usage_status = models.CharField(max_length=16, choices=UsageStatus.choices)
    prompt_tokens = models.PositiveBigIntegerField(null=True, blank=True)
    completion_tokens = models.PositiveBigIntegerField(null=True, blank=True)
    total_tokens = models.PositiveBigIntegerField(null=True, blank=True)
    duration_ms = models.FloatField(null=True, blank=True)
    http_status = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ('-created_at', '-pk')
        indexes = [models.Index(fields=('user', '-created_at'))]
        constraints = [
            models.CheckConstraint(
                condition=Q(usage_reported_request_count__lte=F('request_count')),
                name='agent_usage_reported_lte_requests',
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        usage_status='available',
                        prompt_tokens__isnull=False,
                        completion_tokens__isnull=False,
                        total_tokens__isnull=False,
                    )
                    | Q(
                        usage_status__in=('partial', 'unavailable'),
                        prompt_tokens__isnull=True,
                        completion_tokens__isnull=True,
                        total_tokens__isnull=True,
                    )
                ),
                name='agent_usage_tokens_match_status',
            ),
        ]
