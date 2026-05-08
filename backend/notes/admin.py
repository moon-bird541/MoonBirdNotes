from django.contrib import admin

from .models import Note


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    # 管理后台先提供最常用的列表和搜索能力，便于排查上传结果。
    list_display = ('id', 'title', 'source_filename', 'created_at', 'updated_at')
    search_fields = ('title', 'source_filename')
    readonly_fields = ('created_at', 'updated_at')
