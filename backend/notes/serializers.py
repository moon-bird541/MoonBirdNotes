import re
from pathlib import Path

import markdown
from rest_framework import serializers

from .models import Note


class NoteUploadSerializer(serializers.ModelSerializer):
    # 前端通过 file 字段上传原始 .md 文件。
    file = serializers.FileField(write_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = Note
        fields = [
            'id',
            'title',
            'source_filename',
            'file',
            'file_url',
            'markdown_content',
            'rendered_html',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'title',
            'source_filename',
            'file_url',
            'markdown_content',
            'rendered_html',
            'created_at',
            'updated_at',
        ]

    def validate_file(self, value):
        suffix = Path(value.name).suffix.lower()
        if suffix != '.md':
            raise serializers.ValidationError('只允许上传 .md 文件。')
        return value

    def create(self, validated_data):
        uploaded_file = validated_data.pop('file')
        raw_bytes = uploaded_file.read()
        # 读取内容后需要重置指针，否则 Django 保存文件时会写入空内容。
        uploaded_file.seek(0)
        markdown_content = self._decode_markdown(raw_bytes)
        # 上传时统一渲染成 HTML，避免每次展示时重复转换。
        rendered_html = markdown.markdown(
            markdown_content,
            extensions=['extra', 'fenced_code', 'tables', 'toc'],
        )
        # 优先使用 Markdown 一级标题作为笔记标题，没有时回退到文件名。
        title = self._extract_title(markdown_content, uploaded_file.name)

        return Note.objects.create(
            title=title,
            source_filename=uploaded_file.name,
            markdown_file=uploaded_file,
            markdown_content=markdown_content,
            rendered_html=rendered_html,
        )

    def get_file_url(self, obj):
        request = self.context.get('request')
        if not obj.markdown_file:
            return None
        url = obj.markdown_file.url
        return request.build_absolute_uri(url) if request else url

    @staticmethod
    def _decode_markdown(raw_bytes):
        # 第一版先只接受 UTF-8 编码，避免不同本地编码导致内容错乱。
        for encoding in ('utf-8', 'utf-8-sig'):
            try:
                return raw_bytes.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise serializers.ValidationError('Markdown 文件编码不受支持，请使用 UTF-8。')

    @staticmethod
    def _extract_title(markdown_content, filename):
        for line in markdown_content.splitlines():
            stripped = line.strip()
            if stripped.startswith('# '):
                title = stripped[2:].strip()
                if title:
                    return title
        return Path(filename).stem


class NoteListSerializer(serializers.ModelSerializer):
    # 列表页使用摘要和字数增强信息流感，不再只展示纯标题。
    excerpt = serializers.SerializerMethodField()
    word_count = serializers.SerializerMethodField()

    class Meta:
        model = Note
        fields = [
            'id',
            'title',
            'excerpt',
            'word_count',
            'created_at',
            'updated_at',
        ]

    def get_excerpt(self, obj):
        plain_text = self._to_plain_text(obj.markdown_content)
        if not plain_text:
            return '这篇笔记暂时还没有可预览的正文内容。'
        return plain_text[:120] + ('...' if len(plain_text) > 120 else '')

    def get_word_count(self, obj):
        plain_text = self._to_plain_text(obj.markdown_content)
        # 这里展示的是“字数”，因此统计去掉空白后的可见文本长度，更符合中文阅读习惯。
        return len(re.sub(r'\s+', '', plain_text))

    @staticmethod
    def _to_plain_text(markdown_content):
        text = markdown_content or ''
        text = re.sub(r'```[\s\S]*?```', ' ', text)
        text = re.sub(r'`([^`]*)`', r'\1', text)
        text = re.sub(r'!\[[^\]]*\]\([^)]+\)', ' ', text)
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        text = re.sub(r'^\s{0,3}#{1,6}\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'[*_~>#-]+', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
