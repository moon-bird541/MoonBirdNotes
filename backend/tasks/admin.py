from django.contrib import admin

from .models import Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'title',
        'start_at',
        'end_at',
        'urgency',
        'is_completed',
        'completed_at',
        'created_at',
    )
    search_fields = ('title',)
    list_filter = ('urgency', 'is_completed')
    readonly_fields = ('created_at', 'updated_at', 'completed_at')
