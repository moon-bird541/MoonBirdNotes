from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

# 待办与项目的分界时长：不超过 24 小时算待办，超过算项目。
# 判定只认时长不认自然日，这样 21:00 → 次日 01:00 仍然是待办。
TODO_SEGMENT_MAX_DURATION = timezone.timedelta(hours=24)

SEGMENT_TODO = 'todo'
SEGMENT_PROJECT = 'project'


class Task(models.Model):
    """任务：与笔记、日记并列的独立对象，不进入 RAG 索引。"""

    class Urgency(models.IntegerChoices):
        LOW = 1, '低'
        MEDIUM = 2, '中'
        HIGH = 3, '高'
        URGENT = 4, '紧急'

    # 标题：任务只有标题可搜，不写正文，所以长度收紧到 100。
    title = models.CharField(max_length=100)

    # 开始/结束时间：表单层必填，数据库允许为空以容纳历史脏数据。
    # 读取时为空的任务一律归入项目段并标记「时间未定」。
    start_at = models.DateTimeField(null=True, blank=True)
    end_at = models.DateTimeField(null=True, blank=True)

    # 紧急程度：四档整数枚举，不设默认值，必须由用户显式选择。
    urgency = models.PositiveSmallIntegerField(
        choices=Urgency.choices,
        validators=[MinValueValidator(1), MaxValueValidator(4)],
    )

    is_completed = models.BooleanField(default=False)

    # 完成时间：用于「已完成」视图按完成时间排序和统计。
    completed_at = models.DateTimeField(null=True, blank=True)

    # 总结：完成后的复盘，不是任务描述，因此允许为空。
    summary = models.TextField(blank=True, default='')

    # 关联笔记：可选，单向。笔记彻底删除时由外键置空，任务本体保留。
    linked_note = models.ForeignKey(
        'notes.Note',
        related_name='linked_tasks',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['is_completed', '-urgency', 'end_at', '-created_at']
        verbose_name = '任务'
        verbose_name_plural = '任务'

    def __str__(self):
        return self.title

    @property
    def segment(self):
        """实时计算所属分段，不落库。

        时间缺失时归入项目段，避免脏数据凭空消失。
        """
        if not self.start_at or not self.end_at:
            return SEGMENT_PROJECT

        if self.end_at - self.start_at <= TODO_SEGMENT_MAX_DURATION:
            return SEGMENT_TODO

        return SEGMENT_PROJECT

    @property
    def has_time(self):
        return bool(self.start_at and self.end_at)

    @property
    def is_overdue(self):
        """只有未完成且结束时间已过才算逾期，逾期任务仍留在原分段。"""
        if self.is_completed or not self.end_at:
            return False

        return self.end_at < timezone.now()

    def mark_completed(self, summary=None):
        self.is_completed = True
        self.completed_at = timezone.now()

        if summary is not None:
            self.summary = summary

    def mark_uncompleted(self):
        self.is_completed = False
        self.completed_at = None
