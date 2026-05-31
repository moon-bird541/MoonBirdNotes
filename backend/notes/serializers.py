import json
import re
from pathlib import Path

import markdown
from rest_framework import serializers

from .models import Note, NoteVersion, Tag


MAX_NOTE_VERSION_COUNT = 5


def render_markdown_content(markdown_content):
    return markdown.markdown(
        markdown_content,
        extensions=['extra', 'fenced_code', 'tables', 'toc'],
    )


def normalize_tag_names(tag_names):
    normalized = []

    for tag_name in tag_names:
        stripped = tag_name.strip()
        if not stripped:
            continue
        if stripped not in normalized:
            normalized.append(stripped)

    if not normalized:
        raise serializers.ValidationError('请至少填写一个标签。')

    if len(normalized) > 2:
        raise serializers.ValidationError('每篇笔记最多只能选择两个标签。')

    return normalized


def enforce_note_version_limit(note):
    kept_ids = list(note.versions.order_by('-created_at', '-id').values_list('id', flat=True)[:MAX_NOTE_VERSION_COUNT])
    note.versions.exclude(id__in=kept_ids).delete()


def get_note_tag_names(note):
    return list(note.tags.order_by('name').values_list('name', flat=True))


def note_has_changes(note, title, markdown_content, tag_names):
    return (
        note.title.strip() != title.strip()
        or note.markdown_content != markdown_content
        or sorted(get_note_tag_names(note)) != sorted(tag_names)
    )


def create_note_version_snapshot(note):
    version = NoteVersion.objects.create(
        note=note,
        title=note.title,
        markdown_content=note.markdown_content,
        rendered_html=note.rendered_html,
        tag_names=get_note_tag_names(note),
    )
    enforce_note_version_limit(note)
    return version


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['id', 'name']


class NoteUploadSerializer(serializers.ModelSerializer):
    # 前端通过 file 字段上传原始 .md 文件。
    file = serializers.FileField(write_only=True)
    file_url = serializers.SerializerMethodField()
    # 标签必填，当前规则为每篇笔记最多两个标签。
    tag_names = serializers.ListField(
        child=serializers.CharField(max_length=50),
        write_only=True,
        required=True,
    )
    tags = TagSerializer(many=True, read_only=True)

    class Meta:
        model = Note
        fields = [
            'id',
            'title',
            'source_filename',
            'file',
            'file_url',
            'tag_names',
            'tags',
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
            'tags',
            'markdown_content',
            'rendered_html',
            'created_at',
            'updated_at',
        ]

    def to_internal_value(self, data):
        # multipart/form-data 下标签可能以重复字段或 JSON 字符串形式传入，这里统一整理成列表。
        normalized_data = data.copy()
        normalized_tag_names = self._extract_tag_names(data)

        if hasattr(normalized_data, 'setlist'):
            normalized_data.setlist('tag_names', normalized_tag_names)
        else:
            normalized_data['tag_names'] = normalized_tag_names

        return super().to_internal_value(normalized_data)

    def validate_file(self, value):
        suffix = Path(value.name).suffix.lower()
        if suffix != '.md':
            raise serializers.ValidationError('只允许上传 .md 文件。')
        return value

    def validate_tag_names(self, value):
        return normalize_tag_names(value)

    def create(self, validated_data):
        uploaded_file = validated_data.pop('file')
        tag_names = validated_data.pop('tag_names')
        raw_bytes = uploaded_file.read()
        # 读取内容后需要重置指针，否则 Django 保存文件时会写入空内容。
        uploaded_file.seek(0)
        markdown_content = self._decode_markdown(raw_bytes)
        # 上传时统一渲染成 HTML，避免每次展示时重复转换。
        rendered_html = render_markdown_content(markdown_content)
        # 优先使用 Markdown 一级标题作为笔记标题，没有时回退到文件名。
        title = self._extract_title(markdown_content, uploaded_file.name)

        note = Note.objects.create(
            title=title,
            source_filename=uploaded_file.name,
            markdown_file=uploaded_file,
            markdown_content=markdown_content,
            rendered_html=rendered_html,
        )

        tags = [Tag.objects.get_or_create(name=tag_name)[0] for tag_name in tag_names]
        note.tags.set(tags)
        return note

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

    @staticmethod
    def _extract_tag_names(data):
        if hasattr(data, 'getlist'):
            tag_names = data.getlist('tag_names')
            if tag_names:
                if len(tag_names) == 1 and isinstance(tag_names[0], str) and tag_names[0].strip().startswith('['):
                    try:
                        return json.loads(tag_names[0])
                    except json.JSONDecodeError:
                        return tag_names
                return tag_names

        raw_value = data.get('tag_names', [])

        if isinstance(raw_value, str):
            raw_value = raw_value.strip()
            if not raw_value:
                return []
            if raw_value.startswith('['):
                try:
                    return json.loads(raw_value)
                except json.JSONDecodeError:
                    return [raw_value]
            return [raw_value]

        if isinstance(raw_value, list):
            return raw_value

        return []


class NoteListSerializer(serializers.ModelSerializer):
    # 列表页使用摘要和字数增强信息流感，不再只展示纯标题。
    excerpt = serializers.SerializerMethodField()
    word_count = serializers.SerializerMethodField()
    tags = TagSerializer(many=True, read_only=True)

    class Meta:
        model = Note
        fields = [
            'id',
            'title',
            'excerpt',
            'word_count',
            'tags',
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


class NoteDetailSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    word_count = serializers.SerializerMethodField()
    tags = TagSerializer(many=True, read_only=True)

    class Meta:
        model = Note
        fields = [
            'id',
            'title',
            'source_filename',
            'file_url',
            'markdown_content',
            'rendered_html',
            'word_count',
            'tags',
            'created_at',
            'updated_at',
        ]

    def get_file_url(self, obj):
        request = self.context.get('request')
        if not obj.markdown_file:
            return None
        url = obj.markdown_file.url
        return request.build_absolute_uri(url) if request else url

    def get_word_count(self, obj):
        plain_text = NoteListSerializer._to_plain_text(obj.markdown_content)
        return len(re.sub(r'\s+', '', plain_text))


class NoteEditSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    markdown_content = serializers.CharField(allow_blank=True)
    tag_names = serializers.ListField(
        child=serializers.CharField(max_length=50),
        required=True,
    )

    def validate_title(self, value):
        title = value.strip()
        if not title:
            raise serializers.ValidationError('请填写笔记标题。')
        return title

    def validate_tag_names(self, value):
        return normalize_tag_names(value)

    def update(self, instance, validated_data):
        self.no_changes = not note_has_changes(
            instance,
            validated_data['title'],
            validated_data['markdown_content'],
            validated_data['tag_names'],
        )

        if self.no_changes:
            return instance

        create_note_version_snapshot(instance)

        instance.title = validated_data['title']
        instance.markdown_content = validated_data['markdown_content']
        instance.rendered_html = render_markdown_content(validated_data['markdown_content'])
        instance.save(update_fields=['title', 'markdown_content', 'rendered_html', 'updated_at'])

        tags = [Tag.objects.get_or_create(name=tag_name)[0] for tag_name in validated_data['tag_names']]
        instance.tags.set(tags)
        return instance

    def create(self, validated_data):
        raise NotImplementedError


class NoteVersionSerializer(serializers.ModelSerializer):
    word_count = serializers.SerializerMethodField()

    class Meta:
        model = NoteVersion
        fields = [
            'id',
            'title',
            'markdown_content',
            'word_count',
            'tag_names',
            'created_at',
        ]

    def get_word_count(self, obj):
        plain_text = NoteListSerializer._to_plain_text(obj.markdown_content)
        return len(re.sub(r'\s+', '', plain_text))
