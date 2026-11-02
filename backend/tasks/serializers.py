from rest_framework import serializers

from .models import Task


def _resolve_linked_note(note):
    """把关联 Note 折叠成前端能直接渲染的最小信息。

    日记底层也是 Note，用 diary_entry 判断类型，避免前端再去猜。
    """
    if note is None:
        return None

    diary_entry = getattr(note, 'diary_entry', None)

    return {
        'id': note.id,
        'title': note.title,
        'type': 'diary' if diary_entry else 'note',
        'diary_date': diary_entry.diary_date.isoformat() if diary_entry else None,
        # 软删除的笔记仍然保留关联，但前端必须显式展示「已删除」且不可跳转。
        'is_deleted': note.is_deleted,
    }


class TaskSerializer(serializers.ModelSerializer):
    segment = serializers.CharField(read_only=True)
    has_time = serializers.BooleanField(read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    urgency_display = serializers.CharField(source='get_urgency_display', read_only=True)
    linked_note = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = [
            'id',
            'title',
            'start_at',
            'end_at',
            'urgency',
            'urgency_display',
            'is_completed',
            'completed_at',
            'summary',
            'linked_note',
            'segment',
            'has_time',
            'is_overdue',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'urgency_display',
            'completed_at',
            'linked_note',
            'segment',
            'has_time',
            'is_overdue',
            'created_at',
            'updated_at',
        ]

    def get_linked_note(self, obj):
        return _resolve_linked_note(obj.linked_note)


class TaskWriteSerializer(serializers.ModelSerializer):
    title = serializers.CharField(max_length=100, allow_blank=False)
    start_at = serializers.DateTimeField(required=True, allow_null=False)
    end_at = serializers.DateTimeField(required=True, allow_null=False)
    linked_note_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = Task
        fields = [
            'id',
            'title',
            'start_at',
            'end_at',
            'urgency',
            'is_completed',
            'summary',
            'linked_note_id',
        ]

    def validate_title(self, value):
        title = value.strip()
        if not title:
            raise serializers.ValidationError('请填写任务标题。')
        return title

    def validate(self, attrs):
        # 部分更新时用实例上的旧值参与校验，避免只改一个时间就绕过区间检查。
        start_at = attrs.get('start_at', getattr(self.instance, 'start_at', None))
        end_at = attrs.get('end_at', getattr(self.instance, 'end_at', None))

        if start_at and end_at and end_at < start_at:
            raise serializers.ValidationError({'end_at': ['结束时间不能早于开始时间。']})

        return attrs

    def validate_linked_note_id(self, value):
        if value in (None, ''):
            return None

        # 延迟导入，避免 tasks 在 app 加载阶段就依赖 notes 的模型模块。
        from notes.models import Note

        if not Note.objects.filter(pk=value).exists():
            raise serializers.ValidationError('关联的笔记不存在。')

        return value

    def _pop_linked_note_id(self, validated_data):
        linked_note_id = validated_data.pop('linked_note_id', serializers.empty)

        if linked_note_id is serializers.empty:
            return

        if linked_note_id is None:
            validated_data['linked_note'] = None
            return

        from notes.models import Note

        validated_data['linked_note'] = Note.objects.get(pk=linked_note_id)

    def create(self, validated_data):
        self._pop_linked_note_id(validated_data)

        # 创建时如果直接带 is_completed，补齐完成时间，避免出现「已完成但没有完成时间」。
        if validated_data.get('is_completed'):
            from django.utils import timezone

            validated_data.setdefault('completed_at', timezone.now())

        return super().create(validated_data)

    def update(self, instance, validated_data):
        self._pop_linked_note_id(validated_data)

        is_completed = validated_data.get('is_completed')
        if is_completed is True and not instance.is_completed:
            from django.utils import timezone

            validated_data.setdefault('completed_at', timezone.now())
        elif is_completed is False and instance.is_completed:
            validated_data['completed_at'] = None

        return super().update(instance, validated_data)
