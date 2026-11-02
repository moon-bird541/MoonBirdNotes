from django.urls import path

from .views import TaskCompleteView, TaskDetailView, TaskListView, TaskSummaryView

urlpatterns = [
    path('', TaskListView.as_view(), name='task-list'),
    path('summary/', TaskSummaryView.as_view(), name='task-summary'),
    path('<int:pk>/', TaskDetailView.as_view(), name='task-detail'),
    path('<int:pk>/complete/', TaskCompleteView.as_view(), name='task-complete'),
]
