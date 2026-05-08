from datetime import timedelta

from django.utils import timezone
from rest_framework import generics, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from .models import Note
from .serializers import NoteListSerializer, NoteUploadSerializer


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


class NoteUploadView(generics.CreateAPIView):
    queryset = Note.objects.all()
    serializer_class = NoteUploadSerializer
    # 当前系统只允许管理员本人使用，因此上传接口仅开放给管理员。
    permission_classes = [IsAdminUser]


class NoteListView(generics.ListAPIView):
    serializer_class = NoteListSerializer
    permission_classes = [IsAdminUser]
    pagination_class = NoteListPagination

    def get_queryset(self):
        purge_expired_trash_notes()
        # 普通笔记列表按创建时间倒序展示，优先看到最新上传的笔记。
        return Note.objects.filter(is_deleted=False).order_by('-created_at')


class TrashNoteListView(generics.ListAPIView):
    serializer_class = NoteListSerializer
    permission_classes = [IsAdminUser]
    pagination_class = NoteListPagination

    def get_queryset(self):
        purge_expired_trash_notes()
        # 回收站只展示仍在保留期内的软删除笔记。
        return Note.objects.filter(is_deleted=True).order_by('-updated_at')


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
