from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from .text import count_markdown_words


def note_image_upload_to(instance, filename):
    diary_entry = getattr(instance.note, 'diary_entry', None)

    if diary_entry:
        return f'diary_images/{diary_entry.diary_date.isoformat()}/{filename}'

    today = timezone.localdate()
    return f'note_images/{today:%Y/%m/%d}/{filename}'


class Tag(models.Model):
    # 标签名称：例如“教程”“Django”，在系统内全局复用。
    name = models.CharField(max_length=50, unique=True)

    # 创建时间：便于后续做标签管理和统计。
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Note(models.Model):
    # 笔记标题：优先取 Markdown 一级标题，没有时回退到文件名。
    title = models.CharField(max_length=255)

    # 原始上传文件名：保留用户本地文件名，便于识别来源。空白笔记时为空。
    source_filename = models.CharField(max_length=255, blank=True, default='')

    # 原始 Markdown 文件：保存到 media/notes/日期目录下。空白笔记时为空。
    markdown_file = models.FileField(upload_to='notes/%Y/%m/%d/', blank=True, null=True)

    # Markdown 原文内容：后续可用于编辑、搜索和重新渲染。空白笔记时为空字符串。
    markdown_content = models.TextField(blank=True, default='')

    # 可见文本字数：保存时冗余，统计接口直接聚合，避免每次全表逐篇正则计算。
    word_count = models.PositiveIntegerField(default=0)

    # 渲染后的 HTML 内容：后续展示时可以直接返回使用。
    rendered_html = models.TextField(blank=True, default='')

    # 标签：当前约束为每篇笔记最多四个标签，校验放在序列化器层处理。
    tags = models.ManyToManyField(Tag, related_name='notes', blank=True)

    # 软删除标记：进入回收站时置为 True，普通列表只展示 False 的数据。
    is_deleted = models.BooleanField(default=False)

    # 置顶标记：普通列表优先展示置顶笔记，回收站保留原状态以便恢复后继续生效。
    is_pinned = models.BooleanField(default=False)

    # 置顶时间：用于多个置顶笔记之间按最近置顶优先排序。
    pinned_at = models.DateTimeField(null=True, blank=True)

    # 重要程度：0 到 5 星，支持 0.5 星步进。
    importance = models.DecimalField(
        max_digits=2,
        decimal_places=1,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
    )

    # 软删除时间：用于计算回收站保留时长，超过 30 天后自动清理。
    deleted_at = models.DateTimeField(null=True, blank=True)

    # 创建时间：第一次上传并保存这篇笔记的时间。
    created_at = models.DateTimeField(auto_now_add=True)

    # 更新时间：每次修改这篇笔记时自动更新。
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_pinned', '-pinned_at', '-created_at']

    def save(self, *args, **kwargs):
        update_fields = kwargs.get('update_fields')
        should_refresh_word_count = update_fields is None or 'markdown_content' in update_fields

        if should_refresh_word_count:
            self.word_count = count_markdown_words(self.markdown_content)
            if update_fields is not None:
                kwargs['update_fields'] = [*dict.fromkeys([*update_fields, 'word_count'])]

        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class DiaryEntry(models.Model):
    # 日记正文复用现有笔记能力，包括 Markdown、图片、版本、标签和回收站。
    note = models.OneToOneField(Note, related_name='diary_entry', on_delete=models.CASCADE)

    # 日记日期独立于创建时间，便于补写或修改过去某一天的记录。
    diary_date = models.DateField(unique=True)

    mood = models.CharField(max_length=30, blank=True, default='')
    weather = models.CharField(max_length=30, blank=True, default='')
    summary = models.CharField(max_length=200, blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-diary_date']

    def __str__(self):
        return f'{self.diary_date} - {self.note.title}'


class NoteImage(models.Model):
    note = models.ForeignKey(Note, related_name='images', on_delete=models.CASCADE)
    image = models.FileField(upload_to=note_image_upload_to)
    original_filename = models.CharField(max_length=255)
    alt_text = models.CharField(max_length=255, blank=True, default='')
    file_size = models.PositiveIntegerField(default=0)
    content_type = models.CharField(max_length=100, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return self.original_filename


class NoteVersion(models.Model):
    note = models.ForeignKey(Note, related_name='versions', on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    markdown_content = models.TextField()
    rendered_html = models.TextField()
    tag_names = models.JSONField(default=list)
    note_text = models.CharField(max_length=500, blank=True, default='')  # 版本备注
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f'{self.note_id} - {self.title}'
