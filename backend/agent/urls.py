"""Agent HTTP API 路由。"""

from django.urls import path

from .views import (
    KnowledgeChatView,
    KnowledgeConversationDetailView,
    KnowledgeConversationListView,
    KnowledgeRunTraceView,
    KnowledgeRunListView,
    KnowledgeTokenUsageListView,
)


urlpatterns = [
    path('knowledge/chat/', KnowledgeChatView.as_view(), name='knowledge-agent-chat'),
    path(
        'knowledge/conversations/',
        KnowledgeConversationListView.as_view(),
        name='knowledge-conversation-list',
    ),
    path(
        'knowledge/conversations/<uuid:conversation_id>/',
        KnowledgeConversationDetailView.as_view(),
        name='knowledge-conversation-detail',
    ),
    path(
        'knowledge/runs/',
        KnowledgeRunListView.as_view(),
        name='knowledge-run-list',
    ),
    path(
        'knowledge/runs/<uuid:run_id>/trace/',
        KnowledgeRunTraceView.as_view(),
        name='knowledge-run-trace',
    ),
    path(
        'knowledge/token-usage/',
        KnowledgeTokenUsageListView.as_view(),
        name='knowledge-token-usage-list',
    ),
]
