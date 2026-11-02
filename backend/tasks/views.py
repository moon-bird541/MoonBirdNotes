from datetime import timedelta

from django.db.models import F, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import SEGMENT_PROJECT, SEGMENT_TODO, TODO_SEGMENT_MAX_DURATION, Task
from .serializers import TaskSerializer, TaskWriteSerializer

# 三档排序：紧急程度、截止时间、创建时间。分段由前端按 segment 字段渲染，
# 排序只在同一分段内部生效，所以这里不把 segment 混进 order_by。
TASK_SORT_OPTIONS = {
    'urgency': ('-urgency', 'end_at', '-created_at'),
    'due': ('end_at', '-urgency', '-created_at'),
    'created': ('-created_at', '-urgency'),
}
DEFAULT_TASK_SORT = 'urgency'

# 已完成任务按「最近完成的优先」排序，符合「刚做完」的查看习惯。
COMPLETED_TASK_ORDERING = ('-completed_at', '-updated_at')

# 分段判定在 SQL 层的等价表达：时间齐全且时长不超过 24 小时。
TODO_SEGMENT_FILTER = Q(start_at__isnull=False, end_at__isnull=False) & Q(
    end_at__lte=F('start_at') + TODO_SEGMENT_MAX_DURATION,
)


class TaskPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class TaskListView(generics.ListCreateAPIView):
    permission_classes = [IsAdminUser]
    pagination_class = TaskPagination

    def get_serializer_class(self):
        return TaskWriteSerializer if self.request.method == 'POST' else TaskSerializer

    def get_queryset(self):
        queryset = Task.objects.select_related('linked_note', 'linked_note__diary_entry')
        scope = self.request.query_params.get('scope', 'active').strip()

        if scope == 'completed':
            queryset = queryset.filter(is_completed=True).order_by(*COMPLETED_TASK_ORDERING)
        elif scope == 'all':
            queryset = queryset.order_by(*TASK_SORT_OPTIONS[DEFAULT_TASK_SORT])
        else:
            sort_key = self.request.query_params.get('sort', DEFAULT_TASK_SORT).strip()
            ordering = TASK_SORT_OPTIONS.get(sort_key, TASK_SORT_OPTIONS[DEFAULT_TASK_SORT])
            queryset = queryset.filter(is_completed=False).order_by(*ordering)

        segment = self.request.query_params.get('segment', '').strip()
        if segment == SEGMENT_TODO:
            queryset = queryset.filter(TODO_SEGMENT_FILTER)
        elif segment == SEGMENT_PROJECT:
            queryset = queryset.exclude(TODO_SEGMENT_FILTER)

        search = self.request.query_params.get('search', '').strip()
        if search:
            # 任务只搜标题，不搜总结：总结是完成后的复盘，语义上不属于检索入口。
            queryset = queryset.filter(title__icontains=search)

        return queryset

    def create(self, request, *args, **kwargs):
        serializer = TaskWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = serializer.save()

        return Response(TaskSerializer(task).data, status=status.HTTP_201_CREATED)


class TaskDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminUser]
    queryset = Task.objects.select_related('linked_note', 'linked_note__diary_entry')

    def get_serializer_class(self):
        return TaskWriteSerializer if self.request.method in ('PUT', 'PATCH') else TaskSerializer

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = TaskWriteSerializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        task = serializer.save()

        return Response(TaskSerializer(task).data, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        # 任务硬删除，不进回收站。
        self.get_object().delete()

        return Response(status=status.HTTP_204_NO_CONTENT)


class TaskCompleteView(APIView):
    """完成 / 取消完成单独成接口，避免前端为了勾一个勾就构造整个 PUT 载荷。"""

    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        task = get_object_or_404(Task.objects.select_related('linked_note'), pk=pk)
        summary = request.data.get('summary')

        if summary is not None and not isinstance(summary, str):
            return Response({'summary': ['总结必须是文本。']}, status=status.HTTP_400_BAD_REQUEST)

        if task.is_completed:
            task.mark_uncompleted()
        else:
            task.mark_completed(summary=summary)

        task.save()

        return Response(TaskSerializer(task).data, status=status.HTTP_200_OK)


class TaskSummaryView(APIView):
    """首页任务面板需要的聚合：待办段未完成任务 + 计数。"""

    permission_classes = [IsAdminUser]

    def get(self, request):
        # 用本地日的起止时刻做区间过滤，而不是 completed_at__date：
        # MySQL 的 __date 会按数据库时区（UTC）截断，和 Asia/Shanghai 的「今天」对不上。
        today_start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        active = (
            Task.objects
            .select_related('linked_note', 'linked_note__diary_entry')
            .filter(is_completed=False)
        )
        todo_tasks = active.filter(TODO_SEGMENT_FILTER).order_by('-urgency', 'end_at')
        project_count = active.exclude(TODO_SEGMENT_FILTER).count()

        return Response(
            {
                'todo_tasks': TaskSerializer(todo_tasks[:5], many=True).data,
                'stats': {
                    'todo_count': todo_tasks.count(),
                    'project_count': project_count,
                    'overdue_count': active.filter(
                        end_at__isnull=False,
                        end_at__lt=timezone.now(),
                    ).count(),
                    'completed_today': Task.objects.filter(
                        is_completed=True,
                        completed_at__gte=today_start,
                        completed_at__lt=today_end,
                    ).count(),
                },
            },
            status=status.HTTP_200_OK,
        )
