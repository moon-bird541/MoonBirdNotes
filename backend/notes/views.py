from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Note, NoteVersion, Tag
from .serializers import (
    NoteCreateSerializer,
    NoteDetailSerializer,
    NoteEditSerializer,
    NoteListSerializer,
    NoteUploadSerializer,
    NoteVersionSerializer,
    TagSerializer,
    create_note_version_snapshot,
    enforce_note_version_limit,
    note_has_changes,
    render_markdown_content,
)


def purge_expired_trash_notes():
    # 回收站仅保留 30 天，超过保留期的笔记会被自动彻底清理。
    expired_before = timezone.now() - timedelta(days=30)
    expired_notes = Note.objects.filter(
        is_deleted=True,
        deleted_at__isnull=False,
        deleted_at__lt=expired_before,
    )

    for note in expired_notes:
        if note.markdown_file:
            note.markdown_file.delete(save=False)
        note.delete()


class NoteListPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 50


class TagListView(generics.ListAPIView):
    queryset = Tag.objects.all().order_by('name')
    serializer_class = TagSerializer
    permission_classes = [IsAdminUser]


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
        purge_expired_trash_notes()
        # 普通笔记列表按创建时间倒序展示，优先看到最新上传的笔记。
        queryset = Note.objects.filter(is_deleted=False).prefetch_related('tags')
        search = self.request.query_params.get('search', '').strip()

        if search:
            queryset = queryset.filter(
                Q(title__icontains=search)
                | Q(markdown_content__icontains=search)
                | Q(source_filename__icontains=search)
                | Q(tags__name__icontains=search)
            ).distinct()

        return queryset.order_by('-created_at')


class NoteDetailView(generics.RetrieveAPIView):
    serializer_class = NoteDetailSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        purge_expired_trash_notes()
        return Note.objects.filter(is_deleted=False).prefetch_related('tags')


class NoteEditView(generics.UpdateAPIView):
    serializer_class = NoteEditSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        purge_expired_trash_notes()
        return Note.objects.filter(is_deleted=False).prefetch_related('tags')

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


class NoteVersionListView(generics.ListAPIView):
    serializer_class = NoteVersionSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        purge_expired_trash_notes()
        note = get_object_or_404(Note.objects.filter(is_deleted=False), pk=self.kwargs['pk'])
        return note.versions.all()


class NoteVersionRestoreView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk, version_pk):
        purge_expired_trash_notes()
        version = get_object_or_404(
            NoteVersion.objects.select_related('note').filter(note__is_deleted=False, note_id=pk),
            pk=version_pk,
        )

        note = get_object_or_404(Note.objects.filter(is_deleted=False).prefetch_related('tags'), pk=version.note_id)

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

            tags = [Tag.objects.get_or_create(name=tag_name)[0] for tag_name in version.tag_names]
            note.tags.set(tags)
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
        purge_expired_trash_notes()
        # 回收站只展示仍在保留期内的软删除笔记。
        return Note.objects.filter(is_deleted=True).prefetch_related('tags').order_by('-updated_at')


class NoteDeleteView(generics.DestroyAPIView):
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        purge_expired_trash_notes()
        # 删除入口只处理仍在正常列表中的笔记，避免重复删除。
        return Note.objects.filter(is_deleted=False)

    def perform_destroy(self, instance):
        # 当前阶段采用软删除，先将笔记移入回收站并记录删除时间。
        instance.is_deleted = True
        instance.deleted_at = timezone.now()
        instance.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])

    def delete(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response({'detail': '笔记已移入回收站，30 天后将自动删除。'}, status=status.HTTP_200_OK)


class TrashNoteRestoreView(generics.UpdateAPIView):
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        purge_expired_trash_notes()
        # 只有回收站中的笔记才允许恢复。
        return Note.objects.filter(is_deleted=True)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_deleted = False
        instance.deleted_at = None
        instance.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])
        return Response({'detail': '笔记已从回收站恢复。'}, status=status.HTTP_200_OK)


class TrashNoteDestroyView(generics.DestroyAPIView):
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        purge_expired_trash_notes()
        # 彻底删除只处理已经进入回收站的笔记。
        return Note.objects.filter(is_deleted=True)

    def perform_destroy(self, instance):
        # 彻底删除时同步清理原始 Markdown 文件，避免遗留孤立文件。
        if instance.markdown_file:
            instance.markdown_file.delete(save=False)
        instance.delete()

    def delete(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response({'detail': '笔记已彻底删除。'}, status=status.HTTP_200_OK)
