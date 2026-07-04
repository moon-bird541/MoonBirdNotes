import json
from pathlib import Path

import bleach
import markdown
from django.db import transaction
from rest_framework import serializers
from bleach.html5lib_shim import Filter

from .models import DiaryEntry, Note, NoteImage, NoteVersion, Tag
from .text import count_markdown_words, markdown_to_plain_text


MAX_NOTE_VERSION_COUNT = 5
MAX_MARKDOWN_UPLOAD_SIZE = 10 * 1024 * 1024
MAX_IMAGE_UPLOAD_SIZE = 8 * 1024 * 1024
ALLOWED_IMAGE_EXTENSIONS = {
    '.gif': {'image/gif'},
    '.jpeg': {'image/jpeg'},
    '.jpg': {'image/jpeg'},
    '.png': {'image/png'},
    '.webp': {'image/webp'},
}
ALLOWED_MARKDOWN_TAGS = [
    'h1',
    'h2',
    'h3',
    'h4',
    'h5',
    'h6',
    'p',
    'br',
    'hr',
    'strong',
    'em',
    'u',
    's',
    'del',
    'ins',
    'a',
    'img',
    'ul',
    'ol',
    'li',
    'blockquote',
    'pre',
    'code',
    'table',
    'thead',
    'tbody',
    'tr',
    'th',
    'td',
    'div',
    'span',
]
ALLOWED_MARKDOWN_ATTRIBUTES = {
    'a': ['href', 'title', 'target', 'rel'],
    'img': ['src', 'alt', 'title', 'width', 'height'],
    'code': ['class'],
    'pre': ['class'],
    'div': ['class'],
    'span': ['class'],
    'h1': ['id'],
    'h2': ['id'],
    'h3': ['id'],
    'h4': ['id'],
    'h5': ['id'],
    'h6': ['id'],
}
ALLOWED_MARKDOWN_PROTOCOLS = ['http', 'https', 'mailto']


class AnchorRelFilter(Filter):
    def __iter__(self):
        for token in Filter.__iter__(self):
            if token.get('type') == 'StartTag' and token.get('name') == 'a':
                attributes = token.get('data', {})
                target = attributes.get((None, 'target'), '')

                if isinstance(target, str) and target.strip().lower() == '_blank':
                    rel_values = str(attributes.get((None, 'rel'), '')).split()
                    for required_rel in ('noopener', 'noreferrer'):
                        if required_rel not in rel_values:
                            rel_values.append(required_rel)
                    attributes[(None, 'rel')] = ' '.join(rel_values)

            yield token


def render_markdown_content(markdown_content):
    html = markdown.markdown(
        markdown_content,
        extensions=['extra', 'fenced_code', 'tables', 'toc'],
    )

    cleaner = bleach.Cleaner(
        tags=ALLOWED_MARKDOWN_TAGS,
        attributes=ALLOWED_MARKDOWN_ATTRIBUTES,
        protocols=ALLOWED_MARKDOWN_PROTOCOLS,
        strip=True,
        filters=[AnchorRelFilter],
    )
    return cleaner.clean(html)


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

    if len(normalized) > 4:
        raise serializers.ValidationError('每篇笔记最多只能选择四个标签。')

    return normalized


def get_or_create_tags(tag_names):
    tag_names = list(tag_names)
    if not tag_names:
        return []

    tag_by_name = {
        tag.name: tag
        for tag in Tag.objects.filter(name__in=tag_names)
    }
    missing_tag_names = [
        tag_name
        for tag_name in tag_names
        if tag_name not in tag_by_name
    ]

    if missing_tag_names:
        Tag.objects.bulk_create(
            [Tag(name=tag_name) for tag_name in missing_tag_names],
            ignore_conflicts=True,
        )
        tag_by_name = {
            tag.name: tag
            for tag in Tag.objects.filter(name__in=tag_names)
        }

    return [tag_by_name[tag_name] for tag_name in tag_names]


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


def build_default_diary_title(diary_date):
    return f'{diary_date.isoformat()} 日记'


def build_default_diary_markdown(diary_date):
    return (
        f'# {diary_date.isoformat()} 日记\n\n'
        '> 今天最值得留下的一句话：\n\n'
        '## 今日重点\n\n'
        '| 项目 | 记录 |\n'
        '| --- | --- |\n'
        '| 心情 |  |\n'
        '| 天气 |  |\n'
        '| 能量 |  |\n\n'
        '## 今天发生了什么\n\n'
        '- \n\n'
        '## 想法与感受\n\n'
        '- \n\n'
        '## 明天想推进\n\n'
        '- \n'
    )


def create_note_version_snapshot(note, note_text=''):
    version = NoteVersion.objects.create(
        note=note,
        title=note.title,
        markdown_content=note.markdown_content,
        rendered_html=note.rendered_html,
        tag_names=get_note_tag_names(note),
        note_text=note_text,
    )
    enforce_note_version_limit(note)
    return version


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['id', 'name']


class TagManagementSerializer(serializers.ModelSerializer):
    note_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Tag
        fields = ['id', 'name', 'note_count']


class NoteUploadSerializer(serializers.ModelSerializer):
    # 前端通过 file 字段上传原始 .md 文件。
    file = serializers.FileField(write_only=True)
    file_url = serializers.SerializerMethodField()
    # 标签必填，当前规则为每篇笔记最多四个标签。
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

        if value.size > MAX_MARKDOWN_UPLOAD_SIZE:
            size_mb = value.size / 1024 / 1024
            raise serializers.ValidationError(
                f'文件大小不能超过 10 MB，当前文件：{size_mb:.2f} MB。'
            )

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

        note.tags.set(get_or_create_tags(tag_names))
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
    tags = TagSerializer(many=True, read_only=True)

    class Meta:
        model = Note
        fields = [
            'id',
            'title',
            'excerpt',
            'word_count',
            'tags',
            'is_pinned',
            'pinned_at',
            'importance',
            'created_at',
            'updated_at',
        ]

    def get_excerpt(self, obj):
        plain_text = self._to_plain_text(obj.markdown_content)
        if not plain_text:
            return '这篇笔记暂时还没有可预览的正文内容。'
        return plain_text[:120] + ('...' if len(plain_text) > 120 else '')

    @staticmethod
    def _to_plain_text(markdown_content):
        return markdown_to_plain_text(markdown_content)


class NoteDetailSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
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
            'is_pinned',
            'pinned_at',
            'importance',
            'created_at',
            'updated_at',
        ]

    def get_file_url(self, obj):
        request = self.context.get('request')
        if not obj.markdown_file:
            return None
        url = obj.markdown_file.url
        return request.build_absolute_uri(url) if request else url

class NoteImageSerializer(serializers.ModelSerializer):
    note = serializers.SerializerMethodField()
    note_id = serializers.PrimaryKeyRelatedField(
        queryset=Note.objects.filter(is_deleted=False),
        source='note',
        write_only=True,
    )
    image = serializers.FileField(write_only=True)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = NoteImage
        fields = [
            'id',
            'note',
            'note_id',
            'image',
            'image_url',
            'original_filename',
            'alt_text',
            'file_size',
            'content_type',
            'created_at',
        ]
        read_only_fields = [
            'id',
            'note',
            'image_url',
            'original_filename',
            'file_size',
            'content_type',
            'created_at',
        ]

    def validate_image(self, value):
        suffix = Path(value.name).suffix.lower()
        content_type = getattr(value, 'content_type', '')

        if suffix not in ALLOWED_IMAGE_EXTENSIONS or content_type not in ALLOWED_IMAGE_EXTENSIONS[suffix]:
            raise serializers.ValidationError('只允许上传 PNG、JPEG、GIF 或 WebP 图片。')

        if value.size > MAX_IMAGE_UPLOAD_SIZE:
            size_mb = value.size / 1024 / 1024
            raise serializers.ValidationError(
                f'图片大小不能超过 8 MB，当前文件：{size_mb:.2f} MB。'
            )

        header = value.read(12)
        value.seek(0)
        if not self._has_valid_image_header(header, suffix):
            raise serializers.ValidationError('图片文件内容与格式不匹配。')

        return value

    def create(self, validated_data):
        uploaded_file = validated_data.pop('image')
        alt_text = validated_data.pop('alt_text', '')

        return NoteImage.objects.create(
            image=uploaded_file,
            original_filename=uploaded_file.name,
            alt_text=alt_text,
            file_size=uploaded_file.size,
            content_type=getattr(uploaded_file, 'content_type', ''),
            **validated_data,
        )

    def get_note(self, obj):
        diary_entry = getattr(obj.note, 'diary_entry', None)
        if diary_entry:
            return {
                'id': obj.note_id,
                'title': obj.note.title,
                'type': 'diary',
                'diary_date': diary_entry.diary_date.isoformat(),
            }

        return {
            'id': obj.note_id,
            'title': obj.note.title,
            'type': 'note',
        }

    def get_image_url(self, obj):
        request = self.context.get('request')
        if not obj.image:
            return None
        url = obj.image.url
        return request.build_absolute_uri(url) if request else url

    @staticmethod
    def _has_valid_image_header(header, suffix):
        if suffix == '.png':
            return header.startswith(b'\x89PNG\r\n\x1a\n')
        if suffix in {'.jpg', '.jpeg'}:
            return header.startswith(b'\xff\xd8\xff')
        if suffix == '.gif':
            return header.startswith((b'GIF87a', b'GIF89a'))
        if suffix == '.webp':
            return len(header) >= 12 and header[:4] == b'RIFF' and header[8:12] == b'WEBP'
        return False


class NoteEditSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    markdown_content = serializers.CharField(allow_blank=True)
    tag_names = serializers.ListField(
        child=serializers.CharField(max_length=50),
        required=True,
    )
    create_version = serializers.BooleanField(default=True)
    version_note = serializers.CharField(max_length=500, required=False, allow_blank=True)

    def validate_title(self, value):
        title = value.strip()
        if not title:
            raise serializers.ValidationError('请填写笔记标题。')
        return title

    def validate_tag_names(self, value):
        return normalize_tag_names(value)

    def update(self, instance, validated_data):
        create_version = validated_data.pop('create_version', True)
        version_note = validated_data.pop('version_note', '')

        self.no_changes = not note_has_changes(
            instance,
            validated_data['title'],
            validated_data['markdown_content'],
            validated_data['tag_names'],
        )

        # 自动保存时，如果无变化则直接返回，避免无意义的数据库写入
        # 手动创建版本时，即使无变化也要创建版本快照（用户想要里程碑）
        if self.no_changes and not create_version:
            return instance

        # 手动创建版本时才生成快照
        if create_version:
            create_note_version_snapshot(instance, version_note)

        # 只有真正有变化时才更新数据库
        if not self.no_changes:
            instance.title = validated_data['title']
            instance.markdown_content = validated_data['markdown_content']
            instance.rendered_html = render_markdown_content(validated_data['markdown_content'])
            instance.save(update_fields=['title', 'markdown_content', 'rendered_html', 'updated_at'])

            instance.tags.set(get_or_create_tags(validated_data['tag_names']))

        return instance

    def create(self, validated_data):
        raise NotImplementedError


class NoteCreateSerializer(serializers.ModelSerializer):
    tag_names = serializers.ListField(
        child=serializers.CharField(max_length=50),
        write_only=True,
        required=True,
    )
    tags = TagSerializer(many=True, read_only=True)
    file_url = serializers.SerializerMethodField()
    markdown_content = serializers.CharField(allow_blank=True, default='')

    class Meta:
        model = Note
        fields = [
            'id',
            'title',
            'source_filename',
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
            'source_filename',
            'file_url',
            'tags',
            'rendered_html',
            'created_at',
            'updated_at',
        ]

    def validate_title(self, value):
        title = value.strip()
        if not title:
            raise serializers.ValidationError('请填写笔记标题。')
        return title

    def validate_tag_names(self, value):
        return normalize_tag_names(value)

    def create(self, validated_data):
        tag_names = validated_data.pop('tag_names')
        title = validated_data.get('title', '未命名笔记')
        markdown_content = validated_data.get('markdown_content', '')

        # 渲染 Markdown 为 HTML
        rendered_html = render_markdown_content(markdown_content)

        note = Note.objects.create(
            title=title,
            source_filename='',  # 空白笔记没有原始文件
            markdown_file=None,
            markdown_content=markdown_content,
            rendered_html=rendered_html,
        )

        note.tags.set(get_or_create_tags(tag_names))
        return note

    def get_file_url(self, obj):
        request = self.context.get('request')
        if not obj.markdown_file:
            return None
        url = obj.markdown_file.url
        return request.build_absolute_uri(url) if request else url


class DiaryEntrySerializer(serializers.ModelSerializer):
    note = NoteDetailSerializer(read_only=True)
    note_id = serializers.SerializerMethodField()
    title = serializers.SerializerMethodField()
    markdown_content = serializers.SerializerMethodField()
    rendered_html = serializers.SerializerMethodField()
    word_count = serializers.SerializerMethodField()
    note_created_at = serializers.SerializerMethodField()
    note_updated_at = serializers.SerializerMethodField()

    class Meta:
        model = DiaryEntry
        fields = [
            'id',
            'diary_date',
            'mood',
            'weather',
            'summary',
            'note_id',
            'title',
            'markdown_content',
            'rendered_html',
            'word_count',
            'note',
            'note_created_at',
            'note_updated_at',
            'created_at',
            'updated_at',
        ]

    def get_note_id(self, obj):
        return obj.note_id

    def get_title(self, obj):
        return obj.note.title

    def get_markdown_content(self, obj):
        return obj.note.markdown_content

    def get_rendered_html(self, obj):
        return obj.note.rendered_html

    def get_word_count(self, obj):
        return obj.note.word_count

    def get_note_created_at(self, obj):
        return obj.note.created_at

    def get_note_updated_at(self, obj):
        return obj.note.updated_at


class DiaryEntryCreateSerializer(serializers.ModelSerializer):
    title = serializers.CharField(max_length=255, required=False, allow_blank=True)
    markdown_content = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = DiaryEntry
        fields = [
            'diary_date',
            'mood',
            'weather',
            'summary',
            'title',
            'markdown_content',
        ]
        extra_kwargs = {
            'diary_date': {'validators': []},
        }

    def create(self, validated_data):
        title = validated_data.pop('title', '').strip()
        markdown_content = validated_data.pop('markdown_content', '')
        diary_date = validated_data['diary_date']

        if not title:
            title = build_default_diary_title(diary_date)

        if markdown_content == '':
            markdown_content = build_default_diary_markdown(diary_date)

        with transaction.atomic():
            note = Note.objects.create(
                title=title,
                source_filename='',
                markdown_file=None,
                markdown_content=markdown_content,
                rendered_html=render_markdown_content(markdown_content),
            )
            return DiaryEntry.objects.create(note=note, **validated_data)


class DiaryEntryUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255, required=False)
    markdown_content = serializers.CharField(required=False, allow_blank=True)
    mood = serializers.CharField(max_length=30, required=False, allow_blank=True)
    weather = serializers.CharField(max_length=30, required=False, allow_blank=True)
    summary = serializers.CharField(max_length=200, required=False, allow_blank=True)
    create_version = serializers.BooleanField(default=False)
    version_note = serializers.CharField(max_length=500, required=False, allow_blank=True)

    def validate_title(self, value):
        title = value.strip()
        if not title:
            raise serializers.ValidationError('请填写日记标题。')
        return title

    def update(self, instance, validated_data):
        create_version = validated_data.pop('create_version', False)
        version_note = validated_data.pop('version_note', '')
        note = instance.note
        metadata_fields = ['mood', 'weather', 'summary']
        metadata_update_fields = []

        for field in metadata_fields:
            if field in validated_data and getattr(instance, field) != validated_data[field]:
                setattr(instance, field, validated_data[field])
                metadata_update_fields.append(field)

        title = validated_data.get('title', note.title)
        markdown_content = validated_data.get('markdown_content', note.markdown_content)
        note_fields_submitted = 'title' in validated_data or 'markdown_content' in validated_data
        tag_names = get_note_tag_names(note)
        note_changed = note_fields_submitted and note_has_changes(note, title, markdown_content, tag_names)

        with transaction.atomic():
            if create_version:
                create_note_version_snapshot(note, version_note)

            if note_changed:
                note.title = title
                note.markdown_content = markdown_content
                note.rendered_html = render_markdown_content(markdown_content)
                note.save(update_fields=['title', 'markdown_content', 'rendered_html', 'updated_at'])

            if metadata_update_fields or note_changed:
                instance.save(update_fields=[*metadata_update_fields, 'updated_at'])

        self.no_changes = not metadata_update_fields and not note_changed
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
            'rendered_html',
            'word_count',
            'tag_names',
            'note_text',
            'created_at',
        ]

    def get_word_count(self, obj):
        return count_markdown_words(obj.markdown_content)
