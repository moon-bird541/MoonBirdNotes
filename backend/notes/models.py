from django.db import models


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

    # 渲染后的 HTML 内容：后续展示时可以直接返回使用。
    rendered_html = models.TextField(blank=True, default='')

    # 标签：当前约束为每篇笔记最多两个标签，校验放在序列化器层处理。
    tags = models.ManyToManyField(Tag, related_name='notes', blank=True)

    # 软删除标记：进入回收站时置为 True，普通列表只展示 False 的数据。
    is_deleted = models.BooleanField(default=False)

    # 软删除时间：用于计算回收站保留时长，超过 30 天后自动清理。
    deleted_at = models.DateTimeField(null=True, blank=True)

    # 创建时间：第一次上传并保存这篇笔记的时间。
    created_at = models.DateTimeField(auto_now_add=True)

    # 更新时间：每次修改这篇笔记时自动更新。
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


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
