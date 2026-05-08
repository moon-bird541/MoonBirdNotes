from django.db import models


class Note(models.Model):
    # 笔记标题：优先取 Markdown 一级标题，没有时回退到文件名。
    title = models.CharField(max_length=255)

    # 原始上传文件名：保留用户本地文件名，便于识别来源。
    source_filename = models.CharField(max_length=255)

    # 原始 Markdown 文件：保存到 media/notes/日期目录下。
    markdown_file = models.FileField(upload_to='notes/%Y/%m/%d/')

    # Markdown 原文内容：后续可用于编辑、搜索和重新渲染。
    markdown_content = models.TextField()

    # 渲染后的 HTML 内容：后续展示时可以直接返回使用。
    rendered_html = models.TextField()

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
