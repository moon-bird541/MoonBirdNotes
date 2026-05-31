from django.contrib import admin

from .models import Note, Tag


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    # 后台提供标签检索，便于后续整理已有标签。
    list_display = ('id', 'name', 'created_at')
    search_fields = ('name',)
    readonly_fields = ('created_at',)


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    # 管理后台先提供最常用的列表和搜索能力，便于排查上传结果。
    list_display = ('id', 'title', 'source_filename', 'is_deleted', 'created_at', 'updated_at')
    search_fields = ('title', 'source_filename', 'tags__name')
    list_filter = ('is_deleted', 'tags')
    filter_horizontal = ('tags',)
    readonly_fields = ('created_at', 'updated_at', 'deleted_at')
