import re
from decimal import Decimal, InvalidOperation
from html import escape
from datetime import datetime, timedelta
from io import BytesIO
from urllib.parse import quote
from zipfile import ZIP_DEFLATED, ZipFile

from django.http import HttpResponse
from django.db import transaction
from django.db.models import CharField, Count, Max, Q, Sum
from django.db.models.functions import Cast
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.negotiation import DefaultContentNegotiation
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAdminUser
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.views import APIView

from rag.services import enqueue_note_ids_on_commit

from .models import DiaryEntry, Note, NoteImage, NoteVersion, Tag
from .serializers import (
    DiaryEntryCreateSerializer,
    DiaryEntrySerializer,
    DiaryEntryUpdateSerializer,
    NoteCreateSerializer,
    NoteDetailSerializer,
    NoteEditSerializer,
    NoteImageSerializer,
    NoteListSerializer,
    NoteUploadSerializer,
    NoteVersionSerializer,
    TagManagementSerializer,
    create_note_version_snapshot,
    enforce_note_version_limit,
    get_or_create_tags,
    note_has_changes,
    normalize_tag_names,
    render_markdown_content,
)
from .services.trash import delete_note_files


def get_active_diary_entries():
    return (
        DiaryEntry.objects
        .select_related('note')
        .prefetch_related('note__tags')
        .filter(note__is_deleted=False)
    )


def get_regular_note_queryset():
    return Note.objects.filter(diary_entry__isnull=True)


def get_active_regular_notes():
    return get_regular_note_queryset().filter(is_deleted=False)


def get_deleted_regular_notes():
    return get_regular_note_queryset().filter(is_deleted=True)


REGULAR_TAG_NOTE_COUNT_FILTER = Q(notes__is_deleted=False, notes__diary_entry__isnull=True)
REGULAR_TAG_TOTAL_COUNT_FILTER = Q(notes__diary_entry__isnull=True)
DIARY_TAG_TOTAL_COUNT_FILTER = Q(notes__diary_entry__isnull=False)


def parse_diary_date_param(value):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        raise DRFValidationError({'diary_date': ['日期格式应为 YYYY-MM-DD。']})


def parse_diary_month_param(value):
    try:
        return datetime.strptime(value, '%Y-%m').date().replace(day=1)
    except (TypeError, ValueError):
        raise DRFValidationError({'month': ['月份格式应为 YYYY-MM。']})


class NoteListPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 50


class NoteImagePagination(PageNumberPagination):
    page_size = 24
    page_size_query_param = 'page_size'
    max_page_size = 60


def get_active_note_image_queryset():
    return NoteImage.objects.select_related('note', 'note__diary_entry').filter(note__is_deleted=False)


def filter_note_images_queryset(queryset, query_params):
    note_id = query_params.get('note_id', '').strip()
    search = query_params.get('search', '').strip()
    scope = query_params.get('scope', 'all').strip()

    if note_id:
        if not note_id.isdigit():
            return queryset.none()
        queryset = queryset.filter(note_id=int(note_id))

    if scope == 'note':
        queryset = queryset.filter(note__diary_entry__isnull=True)
    elif scope == 'diary':
        queryset = queryset.filter(note__diary_entry__isnull=False)

    if search:
        queryset = queryset.filter(
            Q(original_filename__icontains=search)
            | Q(alt_text__icontains=search)
            | Q(note__title__icontains=search)
        )

    return queryset


def note_image_file_exists(image):
    if not image.image:
        return False

    try:
        return image.image.storage.exists(image.image.name)
    except (OSError, ValueError):
        return False


def build_note_image_reference_candidates(image, request=None):
    if not image.image:
        return set()

    image_name = image.image.name.replace('\\', '/')
    image_url = image.image.url.replace('\\', '/')
    candidates = {
        image_name,
        quote(image_name, safe='/'),
        image_url,
        quote(image_url, safe='/:'),
    }

    if image_url.startswith('/'):
        candidates.add(image_url.lstrip('/'))

    if request:
        absolute_url = request.build_absolute_uri(image_url)
        candidates.add(absolute_url)
        candidates.add(quote(absolute_url, safe=':/'))

    return {candidate for candidate in candidates if candidate}


def note_image_is_referenced(image, request=None):
    note = image.note
    content = f'{note.markdown_content or ""}\n{note.rendered_html or ""}'
    return any(
        candidate in content
        for candidate in build_note_image_reference_candidates(image, request)
    )


def note_image_is_orphan(image, request=None):
    return note_image_file_exists(image) and not note_image_is_referenced(image, request)


NOTE_LIST_SORT_OPTIONS = {
    'pinned_created': ['-is_pinned', '-pinned_at', '-created_at', '-id'],
    'pinned_updated': ['-is_pinned', '-pinned_at', '-updated_at', '-id'],
    'importance': ['-importance', '-updated_at', '-id'],
    'title': ['title', 'id'],
}
DEFAULT_NOTE_LIST_SORT = 'pinned_created'


class TagListView(generics.ListAPIView):
    serializer_class = TagManagementSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        return (
            Tag.objects
            .annotate(note_count=Count('notes', filter=REGULAR_TAG_NOTE_COUNT_FILTER, distinct=True))
            .annotate(regular_note_count=Count('notes', filter=REGULAR_TAG_TOTAL_COUNT_FILTER, distinct=True))
            .annotate(diary_note_count=Count('notes', filter=DIARY_TAG_TOTAL_COUNT_FILTER, distinct=True))
            .filter(Q(diary_note_count=0) | Q(regular_note_count__gt=0))
            .order_by('name')
        )


class TagDetailView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        tag = get_object_or_404(Tag, pk=pk)
        raw_name = request.data.get('name', '')
        name = raw_name.strip() if isinstance(raw_name, str) else ''

        if not name:
            return Response({'name': ['请填写标签名称。']}, status=status.HTTP_400_BAD_REQUEST)

        if Tag.objects.filter(name__iexact=name).exclude(pk=tag.pk).exists():
            return Response({'name': ['该标签名称已存在。']}, status=status.HTTP_400_BAD_REQUEST)

        tag.name = name
        tag.save(update_fields=['name'])
        payload = TagManagementSerializer(
            Tag.objects.annotate(note_count=Count('notes', filter=REGULAR_TAG_NOTE_COUNT_FILTER, distinct=True)).get(pk=tag.pk)
        ).data
        return Response(payload, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        tag = get_object_or_404(Tag, pk=pk)
        tag.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TagMergeView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        source_tag = get_object_or_404(Tag, pk=pk)
        target_tag_id = request.data.get('target_tag_id')

        if not target_tag_id:
            return Response({'target_tag_id': ['请选择要合并到的标签。']}, status=status.HTTP_400_BAD_REQUEST)

        if not str(target_tag_id).isdigit():
            return Response({'target_tag_id': ['请选择有效的目标标签。']}, status=status.HTTP_400_BAD_REQUEST)

        target_tag = get_object_or_404(Tag, pk=int(target_tag_id))

        if source_tag.pk == target_tag.pk:
            return Response({'target_tag_id': ['不能合并到当前标签。']}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            for note in source_tag.notes.all():
                note.tags.add(target_tag)
            source_tag.delete()

        payload = TagManagementSerializer(
            Tag.objects.annotate(note_count=Count('notes', filter=REGULAR_TAG_NOTE_COUNT_FILTER, distinct=True)).get(pk=target_tag.pk)
        ).data
        return Response(payload, status=status.HTTP_200_OK)


class DiaryEntryListCreateView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        queryset = get_active_diary_entries()
        month = request.query_params.get('month', '').strip()

        if month:
            month_start = parse_diary_month_param(month)
            next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
            queryset = queryset.filter(diary_date__gte=month_start, diary_date__lt=next_month)
        else:
            queryset = queryset.order_by('-diary_date')[:90]

        payload = DiaryEntrySerializer(queryset, many=True, context={'request': request}).data
        return Response(payload, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = DiaryEntryCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        diary_date = serializer.validated_data['diary_date']

        existing_entry = (
            DiaryEntry.objects
            .select_related('note')
            .prefetch_related('note__tags')
            .filter(diary_date=diary_date)
            .first()
        )

        if existing_entry:
            if existing_entry.note.is_deleted:
                return Response(
                    {'detail': '这一天的日记已在回收站中，请先恢复后再继续编写。'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            payload = DiaryEntrySerializer(existing_entry, context={'request': request}).data
            return Response(payload, status=status.HTTP_200_OK)

        diary_entry = serializer.save()
        diary_entry = get_active_diary_entries().get(pk=diary_entry.pk)
        payload = DiaryEntrySerializer(diary_entry, context={'request': request}).data
        return Response(payload, status=status.HTTP_201_CREATED)


class DiaryEntryTodayView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        diary_entry = get_object_or_404(get_active_diary_entries(), diary_date=timezone.localdate())
        payload = DiaryEntrySerializer(diary_entry, context={'request': request}).data
        return Response(payload, status=status.HTTP_200_OK)


class DiaryEntryByDateView(APIView):
    permission_classes = [IsAdminUser]

    def get_entry(self, diary_date):
        return get_object_or_404(get_active_diary_entries(), diary_date=parse_diary_date_param(diary_date))

    def get(self, request, diary_date):
        payload = DiaryEntrySerializer(self.get_entry(diary_date), context={'request': request}).data
        return Response(payload, status=status.HTTP_200_OK)

    def patch(self, request, diary_date):
        diary_entry = self.get_entry(diary_date)
        serializer = DiaryEntryUpdateSerializer(diary_entry, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        diary_entry = serializer.save()
        diary_entry = get_active_diary_entries().get(pk=diary_entry.pk)
        payload = DiaryEntrySerializer(diary_entry, context={'request': request}).data
        payload['no_changes'] = getattr(serializer, 'no_changes', False)
        return Response(payload, status=status.HTTP_200_OK)


class DiaryEntryDetailView(APIView):
    permission_classes = [IsAdminUser]

    def get_entry(self, pk):
        return get_object_or_404(get_active_diary_entries(), pk=pk)

    def get(self, request, pk):
        payload = DiaryEntrySerializer(self.get_entry(pk), context={'request': request}).data
        return Response(payload, status=status.HTTP_200_OK)

    def patch(self, request, pk):
        diary_entry = self.get_entry(pk)
        serializer = DiaryEntryUpdateSerializer(diary_entry, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        diary_entry = serializer.save()
        diary_entry = get_active_diary_entries().get(pk=diary_entry.pk)
        payload = DiaryEntrySerializer(diary_entry, context={'request': request}).data
        payload['no_changes'] = getattr(serializer, 'no_changes', False)
        return Response(payload, status=status.HTTP_200_OK)


class NoteUploadView(generics.CreateAPIView):
    queryset = Note.objects.all()
    serializer_class = NoteUploadSerializer
    # 当前系统只允许管理员本人使用，因此上传接口仅开放给管理员。
    permission_classes = [IsAdminUser]


class NoteCreateView(generics.CreateAPIView):
    queryset = Note.objects.all()
    serializer_class = NoteCreateSerializer
    # 当前系统只允许管理员本人使用，因此创建接口仅开放给管理员。
    permission_classes = [IsAdminUser]


class NoteListView(generics.ListAPIView):
    serializer_class = NoteListSerializer
    permission_classes = [IsAdminUser]
    pagination_class = NoteListPagination

    def get_queryset(self):
        # 普通笔记列表支持按当前浏览意图切换排序，默认仍优先展示置顶笔记。
        queryset = get_active_regular_notes().prefetch_related('tags')
        search = self.request.query_params.get('search', '').strip()
        tag_id = self.request.query_params.get('tag', '').strip()
        sort_key = self.request.query_params.get('sort', DEFAULT_NOTE_LIST_SORT).strip()

        if tag_id:
            if not tag_id.isdigit():
                return queryset.none()
            queryset = queryset.filter(tags__id=int(tag_id))

        if search:
            queryset = queryset.filter(
                Q(title__icontains=search)
                | Q(markdown_content__icontains=search)
                | Q(source_filename__icontains=search)
                | Q(tags__name__icontains=search)
            ).distinct()

        ordering = NOTE_LIST_SORT_OPTIONS.get(sort_key, NOTE_LIST_SORT_OPTIONS[DEFAULT_NOTE_LIST_SORT])
        return queryset.order_by(*ordering)


class GlobalSearchView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        search = request.query_params.get('search', '').strip()
        page_size = self._parse_int(request.query_params.get('page_size'), default=8, minimum=1, maximum=50)
        page = self._parse_int(request.query_params.get('page'), default=1, minimum=1, maximum=100000)

        notes = get_active_regular_notes().prefetch_related('tags').order_by('-updated_at', '-id')
        diaries = (
            get_active_diary_entries()
            .annotate(diary_date_text=Cast('diary_date', output_field=CharField()))
            .order_by('-note__updated_at', '-id')
        )

        if search:
            notes = notes.filter(
                Q(title__icontains=search)
                | Q(markdown_content__icontains=search)
                | Q(source_filename__icontains=search)
                | Q(tags__name__icontains=search)
            ).distinct()

            diaries = diaries.filter(
                Q(note__title__icontains=search)
                | Q(note__markdown_content__icontains=search)
                | Q(summary__icontains=search)
                | Q(mood__icontains=search)
                | Q(weather__icontains=search)
                | Q(diary_date_text__icontains=search)
            ).distinct()

        total_count = notes.count() + diaries.count()
        start = (page - 1) * page_size
        end = start + page_size
        combined = [
            (note.updated_at, note.id, self._build_note_result(note, request))
            for note in notes[:end]
        ] + [
            (entry.note.updated_at, entry.note_id, self._build_diary_result(entry))
            for entry in diaries[:end]
        ]
        combined.sort(key=lambda item: (item[0], item[1]), reverse=True)

        return Response(
            {
                'count': total_count,
                'results': [payload for _, _, payload in combined[start:end]],
            },
            status=status.HTTP_200_OK,
        )

    @staticmethod
    def _parse_int(value, default, minimum, maximum):
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default

        return min(max(parsed, minimum), maximum)

    @staticmethod
    def _build_note_result(note, request):
        payload = NoteListSerializer(note, context={'request': request}).data
        payload['type'] = 'note'
        return payload

    @staticmethod
    def _build_diary_result(entry):
        plain_text = NoteListSerializer._to_plain_text(entry.note.markdown_content)
        if not plain_text:
            plain_text = entry.summary

        return {
            'type': 'diary',
            'id': entry.id,
            'note_id': entry.note_id,
            'diary_date': entry.diary_date.isoformat(),
            'title': entry.note.title,
            'excerpt': plain_text[:120] + ('...' if len(plain_text) > 120 else ''),
            'tags': [],
            'updated_at': entry.note.updated_at,
        }


class NoteSummaryView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        try:
            recent_limit = int(request.query_params.get('recent_limit', 5))
        except (TypeError, ValueError):
            recent_limit = 5

        recent_limit = min(max(recent_limit, 1), 10)
        notes = get_active_regular_notes().order_by('-created_at')
        total_notes = notes.count()
        total_word_count = notes.aggregate(total=Sum('word_count'))['total'] or 0
        activity_start = timezone.localdate() - timedelta(days=31)
        activity_counts = {}
        for created_at in notes.filter(created_at__date__gte=activity_start).values_list('created_at', flat=True):
            date_key = timezone.localtime(created_at).date().isoformat()
            activity_counts[date_key] = activity_counts.get(date_key, 0) + 1

        tags = (
            Tag.objects.filter(notes__is_deleted=False, notes__diary_entry__isnull=True)
            .annotate(note_count=Count('notes', filter=REGULAR_TAG_NOTE_COUNT_FILTER, distinct=True))
            .filter(note_count__gt=0)
            .order_by('-note_count', 'name')
        )
        tag_distribution = [
            {
                'id': tag.id,
                'name': tag.name,
                'count': tag.note_count,
                'percentage': round((tag.note_count / total_notes) * 100, 1) if total_notes else 0,
            }
            for tag in tags
        ]
        recent_notes = NoteListSerializer(
            notes.prefetch_related('tags')[:recent_limit],
            many=True,
            context={'request': request},
        ).data

        return Response(
            {
                'stats': {
                    'note_count': total_notes,
                    'word_count': total_word_count,
                    'tag_count': len(tag_distribution),
                },
                'tag_distribution': tag_distribution,
                'recent_notes': recent_notes,
                'upload_activity': [
                    {'date': date_key, 'count': count}
                    for date_key, count in sorted(activity_counts.items())
                ],
            },
            status=status.HTTP_200_OK,
        )

class NoteDetailView(generics.RetrieveAPIView):
    serializer_class = NoteDetailSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        return get_active_regular_notes().prefetch_related('tags')


class NotePinView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        note = get_object_or_404(get_active_regular_notes().prefetch_related('tags'), pk=pk)

        target_state = request.data.get('is_pinned', None)
        if target_state is None:
            target_state = not note.is_pinned

        if not isinstance(target_state, bool):
            return Response({'is_pinned': ['is_pinned 必须是布尔值。']}, status=status.HTTP_400_BAD_REQUEST)

        if note.is_pinned != target_state:
            note.is_pinned = target_state
            note.pinned_at = timezone.now() if target_state else None
            note.save(update_fields=['is_pinned', 'pinned_at', 'updated_at'])

        payload = NoteListSerializer(note, context={'request': request}).data
        return Response(payload, status=status.HTTP_200_OK)


class NoteImportanceView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        note = get_object_or_404(get_active_regular_notes().prefetch_related('tags'), pk=pk)

        raw_importance = request.data.get('importance', None)
        if raw_importance is None:
            return Response({'importance': ['请填写笔记重要程度。']}, status=status.HTTP_400_BAD_REQUEST)

        try:
            importance = Decimal(str(raw_importance))
        except (InvalidOperation, TypeError, ValueError):
            return Response({'importance': ['笔记重要程度必须是 0 到 5 之间的数字。']}, status=status.HTTP_400_BAD_REQUEST)

        if importance < 0 or importance > 5:
            return Response({'importance': ['笔记重要程度必须在 0 到 5 星之间。']}, status=status.HTTP_400_BAD_REQUEST)

        doubled = importance * Decimal('2')
        if doubled != doubled.to_integral_value():
            return Response({'importance': ['笔记重要程度只能按 0.5 星调整。']}, status=status.HTTP_400_BAD_REQUEST)

        importance = importance.quantize(Decimal('0.0'))
        if note.importance != importance:
            note.importance = importance
            note.save(update_fields=['importance', 'updated_at'])

        payload = NoteListSerializer(note, context={'request': request}).data
        return Response(payload, status=status.HTTP_200_OK)


def build_export_filename(note, extension):
    cleaned = re.sub(r'[\\/:*?"<>|\r\n]+', '_', note.title).strip(' ._')
    filename = cleaned or f'note-{note.id}'
    return f'{filename}.{extension}'


def build_unique_export_filename(note, extension, used_filenames):
    filename = build_export_filename(note, extension)
    if filename not in used_filenames:
        used_filenames.add(filename)
        return filename

    stem = filename[:-(len(extension) + 1)]
    index = 2
    while True:
        next_filename = f'{stem}-{index}.{extension}'
        if next_filename not in used_filenames:
            used_filenames.add(next_filename)
            return next_filename
        index += 1


def build_content_disposition(filename):
    ascii_filename = re.sub(r'[^\x20-\x7E]+', '_', filename)
    escaped_filename = ascii_filename.replace('\\', '\\\\').replace('"', r'\"')
    from urllib.parse import quote

    return f'attachment; filename="{escaped_filename}"; filename*=UTF-8\'\'{quote(filename)}'


def build_export_html(note):
    tag_names = list(note.tags.order_by('name').values_list('name', flat=True))
    tags = ' / '.join(escape(tag_name) for tag_name in tag_names) or '无标签'
    updated_at = timezone.localtime(note.updated_at).strftime('%Y-%m-%d %H:%M')

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(note.title)}</title>
  <style>
    body {{
      margin: 0;
      background: #f6f8fc;
      color: #0f172a;
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      line-height: 1.85;
    }}
    main {{
      max-width: 860px;
      margin: 0 auto;
      padding: 48px 24px 72px;
    }}
    header {{
      margin-bottom: 32px;
      padding-bottom: 20px;
      border-bottom: 1px solid #dbe3ef;
    }}
    h1 {{
      margin: 0 0 12px;
      font-size: 2.4rem;
      line-height: 1.1;
      letter-spacing: 0;
    }}
    .meta {{
      color: #64748b;
      font-size: 0.95rem;
    }}
    img {{
      max-width: 100%;
      height: auto;
    }}
    pre {{
      overflow-x: auto;
      padding: 16px;
      border-radius: 12px;
      background: #0f172a;
      color: #e5edf8;
    }}
    code {{
      font-family: "Cascadia Code", Consolas, monospace;
    }}
    :not(pre) > code {{
      padding: 0.15em 0.4em;
      border-radius: 6px;
      background: rgba(34, 81, 209, 0.1);
      color: #173fa3;
    }}
    blockquote {{
      margin-left: 0;
      padding-left: 16px;
      border-left: 4px solid #2251d1;
      color: #475569;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
    }}
    th,
    td {{
      padding: 10px 12px;
      border: 1px solid #cbd5e1;
      vertical-align: top;
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>{escape(note.title)}</h1>
      <div class="meta">标签：{tags} · 更新时间：{escape(updated_at)}</div>
    </header>
    <article>
{note.rendered_html}
    </article>
  </main>
</body>
</html>
"""


class NoteExportContentNegotiation(DefaultContentNegotiation):
    def select_renderer(self, request, renderers, format_suffix=None):
        renderer = renderers[0]
        return renderer, renderer.media_type


class NoteExportView(APIView):
    permission_classes = [IsAdminUser]
    renderer_classes = [JSONRenderer]
    content_negotiation_class = NoteExportContentNegotiation

    def get(self, request, pk):
        note = get_active_regular_notes().filter(pk=pk).prefetch_related('tags').first()
        if note is None:
            return Response({'detail': '未找到。'}, status=status.HTTP_404_NOT_FOUND)

        query_params = getattr(request, 'query_params', request.GET)
        export_format = query_params.get('format', 'markdown').strip().lower()

        if export_format in {'markdown', 'md'}:
            filename = build_export_filename(note, 'md')
            response = HttpResponse(note.markdown_content, content_type='text/markdown; charset=utf-8')
        elif export_format == 'html':
            filename = build_export_filename(note, 'html')
            response = HttpResponse(build_export_html(note), content_type='text/html; charset=utf-8')
        else:
            return Response({'detail': '导出格式仅支持 markdown 或 html。'}, status=status.HTTP_400_BAD_REQUEST)

        response['Content-Disposition'] = build_content_disposition(filename)
        return response


class NoteBatchExportView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        note_ids = request.data.get('note_ids')
        export_format = request.data.get('format', 'markdown')

        if not isinstance(note_ids, list) or not note_ids:
            return Response({'note_ids': ['请选择要导出的笔记。']}, status=status.HTTP_400_BAD_REQUEST)

        normalized_ids = []
        seen_ids = set()
        for note_id in note_ids:
            if not isinstance(note_id, int) or isinstance(note_id, bool):
                return Response({'note_ids': ['笔记 ID 必须是整数。']}, status=status.HTTP_400_BAD_REQUEST)
            if note_id not in seen_ids:
                normalized_ids.append(note_id)
                seen_ids.add(note_id)

        if not isinstance(export_format, str):
            return Response({'detail': '导出格式仅支持 markdown 或 html。'}, status=status.HTTP_400_BAD_REQUEST)

        export_format = export_format.strip().lower()
        if export_format in {'markdown', 'md'}:
            extension = 'md'
            content_type_label = 'markdown'
        elif export_format == 'html':
            extension = 'html'
            content_type_label = 'html'
        else:
            return Response({'detail': '导出格式仅支持 markdown 或 html。'}, status=status.HTTP_400_BAD_REQUEST)

        notes = get_active_regular_notes().filter(id__in=normalized_ids).prefetch_related('tags')
        notes_by_id = {note.id: note for note in notes}
        ordered_notes = [notes_by_id[note_id] for note_id in normalized_ids if note_id in notes_by_id]

        if not ordered_notes:
            return Response({'detail': '没有可导出的笔记。'}, status=status.HTTP_404_NOT_FOUND)

        used_filenames = set()
        archive_buffer = BytesIO()
        with ZipFile(archive_buffer, 'w', ZIP_DEFLATED) as archive:
            for note in ordered_notes:
                filename = build_unique_export_filename(note, extension, used_filenames)
                content = note.markdown_content if extension == 'md' else build_export_html(note)
                archive.writestr(filename, content)

        zip_filename = f"moonbird-notes-{timezone.localtime().strftime('%Y%m%d-%H%M%S')}-{content_type_label}.zip"
        response = HttpResponse(archive_buffer.getvalue(), content_type='application/zip')
        response['Content-Disposition'] = build_content_disposition(zip_filename)
        return response


class NoteEditView(generics.UpdateAPIView):
    serializer_class = NoteEditSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        return get_active_regular_notes().prefetch_related('tags')

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        note = serializer.save()
        payload = NoteDetailSerializer(note, context=self.get_serializer_context()).data
        payload['no_changes'] = getattr(serializer, 'no_changes', False)
        return Response(payload)


class NoteMarkdownPreviewView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        markdown_content = request.data.get('markdown_content', '')
        if not isinstance(markdown_content, str):
            return Response({'detail': 'markdown_content 必须是字符串。'}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'rendered_html': render_markdown_content(markdown_content)}, status=status.HTTP_200_OK)


class NoteImageListCreateView(generics.ListCreateAPIView):
    serializer_class = NoteImageSerializer
    permission_classes = [IsAdminUser]
    pagination_class = NoteImagePagination

    def list(self, request, *args, **kwargs):
        images = self.apply_usage_filter(self.filter_queryset(self.get_queryset()))
        stats = self.build_stats(images)
        groups = self.build_groups(images)
        page = self.paginate_queryset(images)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            response.data['stats'] = {
                'image_count': stats['image_count'] or 0,
                'content_count': stats['content_count'] or 0,
                'total_size': stats['total_size'] or 0,
            }
            response.data['groups'] = groups
            return response

        serializer = self.get_serializer(images, many=True)
        return Response({
            'count': stats['image_count'] or 0,
            'next': None,
            'previous': None,
            'results': serializer.data,
            'stats': {
                'image_count': stats['image_count'] or 0,
                'content_count': stats['content_count'] or 0,
                'total_size': stats['total_size'] or 0,
            },
            'groups': groups,
        })

    def get_queryset(self):
        return filter_note_images_queryset(get_active_note_image_queryset(), self.request.query_params)

    def apply_usage_filter(self, images):
        usage = self.request.query_params.get('usage', 'all').strip()
        if usage != 'orphan':
            return images

        return [
            image
            for image in images
            if note_image_is_orphan(image, self.request)
        ]

    @staticmethod
    def build_stats(images):
        if hasattr(images, 'aggregate'):
            stats = images.aggregate(
                image_count=Count('id'),
                content_count=Count('note_id', distinct=True),
                total_size=Sum('file_size'),
            )
            return {
                'image_count': stats['image_count'] or 0,
                'content_count': stats['content_count'] or 0,
                'total_size': stats['total_size'] or 0,
            }

        note_ids = {image.note_id for image in images}
        return {
            'image_count': len(images),
            'content_count': len(note_ids),
            'total_size': sum(image.file_size or 0 for image in images),
        }

    def build_groups(self, images):
        group_by = self.request.query_params.get('group_by', 'content').strip()
        if not hasattr(images, 'values'):
            return self.build_groups_from_images(images, group_by)

        if group_by == 'diary_date':
            return self.build_diary_date_groups(images)

        return self.build_content_groups(images)

    def build_groups_from_images(self, images, group_by):
        groups = {}

        for image in images:
            diary_entry = getattr(image.note, 'diary_entry', None)
            if group_by == 'diary_date' and diary_entry:
                key = f'diary:{diary_entry.diary_date.isoformat()}'
                group_type = 'diary_date'
                title = f'{diary_entry.diary_date.isoformat()} 日记'
                diary_date = diary_entry.diary_date.isoformat()
            else:
                key = f'content:{image.note_id}'
                group_type = 'diary' if diary_entry else 'note'
                title = image.note.title
                diary_date = diary_entry.diary_date.isoformat() if diary_entry else None

            group = groups.setdefault(key, {
                'key': key,
                'type': group_type,
                'note_id': image.note_id,
                'title': title,
                'diary_date': diary_date,
                'image_count': 0,
                'total_size': 0,
                'latest_at': None,
            })
            group['image_count'] += 1
            group['total_size'] += image.file_size or 0
            if group['latest_at'] is None or image.created_at > group['latest_at']:
                group['latest_at'] = image.created_at

        serialized_groups = []
        for group in groups.values():
            serialized_groups.append({
                **group,
                'latest_at': group['latest_at'].isoformat() if group['latest_at'] else None,
            })

        serialized_groups.sort(key=lambda group: (group['latest_at'] or '', group['title']), reverse=True)
        return serialized_groups

    def build_content_groups(self, queryset):
        rows = (
            queryset
            .values('note_id', 'note__title', 'note__diary_entry__diary_date')
            .annotate(
                image_count=Count('id'),
                total_size=Sum('file_size'),
                latest_at=Max('created_at'),
            )
            .order_by('-latest_at', 'note__title')
        )

        return [self.serialize_content_group(row) for row in rows]

    def build_diary_date_groups(self, queryset):
        diary_rows = (
            queryset
            .filter(note__diary_entry__isnull=False)
            .values('note_id', 'note__title', 'note__diary_entry__diary_date')
            .annotate(
                image_count=Count('id'),
                total_size=Sum('file_size'),
                latest_at=Max('created_at'),
            )
        )
        note_rows = (
            queryset
            .filter(note__diary_entry__isnull=True)
            .values('note_id', 'note__title', 'note__diary_entry__diary_date')
            .annotate(
                image_count=Count('id'),
                total_size=Sum('file_size'),
                latest_at=Max('created_at'),
            )
        )

        groups = [
            self.serialize_diary_date_group(row)
            for row in diary_rows
        ] + [
            self.serialize_content_group(row)
            for row in note_rows
        ]
        groups.sort(key=lambda group: (group['latest_at'] or '', group['title']), reverse=True)
        return groups

    @staticmethod
    def serialize_content_group(row):
        diary_date = row['note__diary_entry__diary_date']
        content_type = 'diary' if diary_date else 'note'
        return {
            'key': f'content:{row["note_id"]}',
            'type': content_type,
            'note_id': row['note_id'],
            'title': row['note__title'],
            'diary_date': diary_date.isoformat() if diary_date else None,
            'image_count': row['image_count'] or 0,
            'total_size': row['total_size'] or 0,
            'latest_at': row['latest_at'].isoformat() if row['latest_at'] else None,
        }

    @staticmethod
    def serialize_diary_date_group(row):
        diary_date = row['note__diary_entry__diary_date']
        diary_date_value = diary_date.isoformat() if diary_date else 'unknown'
        return {
            'key': f'diary:{diary_date_value}',
            'type': 'diary_date',
            'note_id': row['note_id'],
            'title': f'{diary_date_value} 日记',
            'diary_date': diary_date_value,
            'image_count': row['image_count'] or 0,
            'total_size': row['total_size'] or 0,
            'latest_at': row['latest_at'].isoformat() if row['latest_at'] else None,
        }


class NoteImageDestroyView(generics.DestroyAPIView):
    serializer_class = NoteImageSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        return get_active_note_image_queryset()

    def perform_destroy(self, instance):
        if instance.image:
            instance.image.delete(save=False)
        instance.delete()


class NoteImageOrphanCleanupView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        queryset = filter_note_images_queryset(get_active_note_image_queryset(), request.query_params)
        orphan_images = [
            image
            for image in queryset
            if note_image_is_orphan(image, request)
        ]
        cleaned_count = len(orphan_images)
        released_size = sum(image.file_size or 0 for image in orphan_images)

        for image in orphan_images:
            if image.image:
                image.image.delete(save=False)
            image.delete()

        return Response(
            {
                'detail': f'已清理 {cleaned_count} 张孤儿图片。',
                'cleaned_count': cleaned_count,
                'released_size': released_size,
            },
            status=status.HTTP_200_OK,
        )


class NoteVersionListView(generics.ListAPIView):
    serializer_class = NoteVersionSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        note = get_object_or_404(get_active_regular_notes(), pk=self.kwargs['pk'])
        return note.versions.all()


class NoteVersionRestoreView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk, version_pk):
        version = get_object_or_404(
            NoteVersion.objects.select_related('note').filter(
                note__is_deleted=False,
                note__diary_entry__isnull=True,
                note_id=pk,
            ),
            pk=version_pk,
        )

        note = get_object_or_404(get_active_regular_notes().prefetch_related('tags'), pk=version.note_id)

        # 检查是否需要保存当前内容
        save_current = request.data.get('save_current', False)
        version_note = request.data.get('version_note', '')

        if not note_has_changes(note, version.title, version.markdown_content, version.tag_names):
            payload = NoteDetailSerializer(note, context={'request': request}).data
            payload['no_changes'] = True
            return Response(payload, status=status.HTTP_200_OK)

        with transaction.atomic():
            note = Note.objects.select_for_update().get(pk=version.note_id)

            # 如果用户选择保存当前内容，先创建版本
            if save_current:
                create_note_version_snapshot(note, version_note)

            note.title = version.title
            note.markdown_content = version.markdown_content
            note.rendered_html = version.rendered_html
            note.save(update_fields=['title', 'markdown_content', 'rendered_html', 'updated_at'])

            note.tags.set(get_or_create_tags(version.tag_names))
            enforce_note_version_limit(note)

        note = Note.objects.prefetch_related('tags').get(pk=note.pk)
        payload = NoteDetailSerializer(note, context={'request': request}).data
        payload['no_changes'] = False
        return Response(payload, status=status.HTTP_200_OK)


class TrashNoteListView(generics.ListAPIView):
    serializer_class = NoteListSerializer
    permission_classes = [IsAdminUser]
    pagination_class = NoteListPagination

    def get_queryset(self):
        # 过期清理由 purge_trash 定时任务处理，列表接口保持只读。
        return get_deleted_regular_notes().prefetch_related('tags').order_by('-updated_at')


class NoteDeleteView(generics.DestroyAPIView):
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        # 删除入口只处理仍在正常列表中的笔记，避免重复删除。
        return get_active_regular_notes()

    def perform_destroy(self, instance):
        # 当前阶段采用软删除，先将笔记移入回收站并记录删除时间。
        instance.is_deleted = True
        instance.deleted_at = timezone.now()
        instance.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])

    def delete(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response({'detail': '笔记已移入回收站，30 天后将自动删除。'}, status=status.HTTP_200_OK)


class NoteBatchDeleteView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        note_ids = request.data.get('note_ids')

        if not isinstance(note_ids, list) or not note_ids:
            return Response({'note_ids': ['请选择要删除的笔记。']}, status=status.HTTP_400_BAD_REQUEST)

        normalized_ids = []
        for note_id in note_ids:
            if not isinstance(note_id, int) or isinstance(note_id, bool):
                return Response({'note_ids': ['笔记 ID 必须是整数。']}, status=status.HTTP_400_BAD_REQUEST)
            normalized_ids.append(note_id)

        deleted_at = timezone.now()
        queryset = get_active_regular_notes().filter(id__in=normalized_ids)
        affected_ids = list(queryset.values_list('id', flat=True))
        deleted_count = queryset.update(
            is_deleted=True,
            deleted_at=deleted_at,
            updated_at=deleted_at,
        )
        # QuerySet.update 不触发 save signal，需要显式在提交后排队清理索引。
        enqueue_note_ids_on_commit(affected_ids, reason='notes_batch_deleted')

        return Response(
            {
                'detail': f'{deleted_count} 篇笔记已移入回收站。',
                'deleted_count': deleted_count,
            },
            status=status.HTTP_200_OK,
        )


class NoteBatchTagsView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        note_ids = request.data.get('note_ids')
        action = request.data.get('action', 'add')

        if not isinstance(note_ids, list) or not note_ids:
            return Response({'note_ids': ['请选择要修改标签的笔记。']}, status=status.HTTP_400_BAD_REQUEST)

        normalized_ids = []
        seen_ids = set()
        for note_id in note_ids:
            if not isinstance(note_id, int) or isinstance(note_id, bool):
                return Response({'note_ids': ['笔记 ID 必须是整数。']}, status=status.HTTP_400_BAD_REQUEST)
            if note_id not in seen_ids:
                normalized_ids.append(note_id)
                seen_ids.add(note_id)

        if action not in {'add', 'remove', 'replace'}:
            return Response({'action': ['批量标签操作仅支持添加、移除或替换。']}, status=status.HTTP_400_BAD_REQUEST)

        try:
            tag_names = normalize_tag_names(request.data.get('tag_names', []))
        except DRFValidationError as exc:
            return Response({'tag_names': exc.detail}, status=status.HTTP_400_BAD_REQUEST)

        notes = list(get_active_regular_notes().filter(id__in=normalized_ids).prefetch_related('tags'))
        notes_by_id = {note.id: note for note in notes}
        ordered_notes = [notes_by_id[note_id] for note_id in normalized_ids if note_id in notes_by_id]

        if not ordered_notes:
            return Response({'detail': '没有可修改标签的笔记。'}, status=status.HTTP_404_NOT_FOUND)

        next_tag_names_by_note_id = {}
        for note in ordered_notes:
            current_tag_names = list(note.tags.order_by('name').values_list('name', flat=True))

            if action == 'add':
                next_tag_names = current_tag_names[:]
                for tag_name in tag_names:
                    if tag_name not in next_tag_names:
                        next_tag_names.append(tag_name)
            elif action == 'remove':
                next_tag_names = [tag_name for tag_name in current_tag_names if tag_name not in tag_names]
            else:
                next_tag_names = tag_names[:]

            if not next_tag_names:
                return Response(
                    {'detail': f'《{note.title}》至少需要保留一个标签。'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if len(next_tag_names) > 4:
                return Response(
                    {'detail': f'《{note.title}》修改后会超过 4 个标签。'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            next_tag_names_by_note_id[note.id] = next_tag_names

        with transaction.atomic():
            tag_cache = {
                tag.name: tag
                for tag in get_or_create_tags({
                    tag_name
                    for tag_names_for_note in next_tag_names_by_note_id.values()
                    for tag_name in tag_names_for_note
                })
            }

            for note in ordered_notes:
                note.tags.set([tag_cache[tag_name] for tag_name in next_tag_names_by_note_id[note.id]])
                note.updated_at = timezone.now()
                note.save(update_fields=['updated_at'])

        return Response(
            {
                'detail': f'{len(ordered_notes)} 篇笔记的标签已更新。',
                'updated_count': len(ordered_notes),
            },
            status=status.HTTP_200_OK,
        )


class TrashNoteRestoreView(generics.UpdateAPIView):
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        # 只有回收站中的笔记才允许恢复。
        return get_deleted_regular_notes()

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_deleted = False
        instance.deleted_at = None
        instance.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])
        return Response({'detail': '笔记已从回收站恢复。'}, status=status.HTTP_200_OK)


class TrashNoteBatchRestoreView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        note_ids = request.data.get('note_ids')

        if not isinstance(note_ids, list) or not note_ids:
            return Response({'note_ids': ['请选择要恢复的笔记。']}, status=status.HTTP_400_BAD_REQUEST)

        normalized_ids = []
        for note_id in note_ids:
            if not isinstance(note_id, int) or isinstance(note_id, bool):
                return Response({'note_ids': ['笔记 ID 必须是整数。']}, status=status.HTTP_400_BAD_REQUEST)
            normalized_ids.append(note_id)

        restored_at = timezone.now()
        queryset = get_deleted_regular_notes().filter(id__in=normalized_ids)
        affected_ids = list(queryset.values_list('id', flat=True))
        restored_count = queryset.update(
            is_deleted=False,
            deleted_at=None,
            updated_at=restored_at,
        )
        # 恢复后仅由 Worker 判断是重新索引还是保持未授权状态。
        enqueue_note_ids_on_commit(affected_ids, reason='notes_batch_restored')

        return Response(
            {
                'detail': f'{restored_count} 篇笔记已恢复到正常列表。',
                'restored_count': restored_count,
            },
            status=status.HTTP_200_OK,
        )


class TrashNoteBatchDestroyView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        note_ids = request.data.get('note_ids')

        if not isinstance(note_ids, list) or not note_ids:
            return Response({'note_ids': ['请选择要彻底删除的笔记。']}, status=status.HTTP_400_BAD_REQUEST)

        normalized_ids = []
        for note_id in note_ids:
            if not isinstance(note_id, int) or isinstance(note_id, bool):
                return Response({'note_ids': ['笔记 ID 必须是整数。']}, status=status.HTTP_400_BAD_REQUEST)
            normalized_ids.append(note_id)

        notes = list(get_deleted_regular_notes().filter(id__in=normalized_ids).prefetch_related('images'))
        destroyed_count = len(notes)

        for note in notes:
            delete_note_files(note)
            note.delete()

        return Response(
            {
                'detail': f'{destroyed_count} 篇笔记已彻底删除。',
                'destroyed_count': destroyed_count,
            },
            status=status.HTTP_200_OK,
        )


class TrashNoteDestroyView(generics.DestroyAPIView):
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        # 彻底删除只处理已经进入回收站的笔记。
        return get_deleted_regular_notes()

    def perform_destroy(self, instance):
        # 彻底删除时同步清理原始 Markdown 文件，避免遗留孤立文件。
        delete_note_files(instance)
        instance.delete()

    def delete(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response({'detail': '笔记已彻底删除。'}, status=status.HTTP_200_OK)
