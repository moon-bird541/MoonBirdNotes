"""历史会话的创建、读取和问答记录服务。"""

from __future__ import annotations

from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from agent.agents.knowledge import KnowledgeAgentResult

from .models import KnowledgeConversation, KnowledgeConversationTurn
from .tracing import llm_usage_from_trace


MAX_CONVERSATION_HISTORY_TURNS = 6


def get_or_create_conversation(*, user, conversation_id: UUID | None, message: str):
    """使用所属用户解析会话；首轮请求自动创建并用问题生成短标题。"""

    if conversation_id:
        return get_object_or_404(
            KnowledgeConversation,
            pk=conversation_id,
            user=user,
        )
    conversation = KnowledgeConversation.objects.create(
        user=user,
        title=_conversation_title(message),
    )
    _prune_excess_conversations(user)
    return conversation


def build_persisted_history(conversation: KnowledgeConversation) -> list[dict[str, str]]:
    """保留最近六轮成功问答的完整上下文。"""

    turns = list(
        conversation.turns.filter(status=KnowledgeConversationTurn.Status.COMPLETED)
        .order_by('-created_at')[:MAX_CONVERSATION_HISTORY_TURNS]
    )
    history = []
    for turn in reversed(turns):
        history.append({'role': 'user', 'content': turn.question})
        history.append({'role': 'assistant', 'content': turn.answer})
    return history


def get_memory_summary(conversation: KnowledgeConversation) -> str:
    return conversation.memory_summary


@transaction.atomic
def record_completed_turn(
    *,
    conversation: KnowledgeConversation,
    run_id: str,
    question: str,
    result: KnowledgeAgentResult,
):
    KnowledgeConversationTurn.objects.create(
        conversation=conversation,
        run_id=run_id,
        question=question,
        answer=result.answer,
        sources=[source.as_dict() for source in result.sources],
        insufficient_context=result.insufficient_context,
        status=KnowledgeConversationTurn.Status.COMPLETED,
    )
    _touch_conversation(conversation)


@transaction.atomic
def record_failed_turn(
    *,
    conversation: KnowledgeConversation,
    run_id: str,
    question: str,
    error_code: str,
):
    KnowledgeConversationTurn.objects.create(
        conversation=conversation,
        run_id=run_id,
        question=question,
        status=KnowledgeConversationTurn.Status.FAILED,
        error_code=error_code[:64],
    )
    _touch_conversation(conversation)


def serialize_conversation_summary(conversation: KnowledgeConversation) -> dict[str, object]:
    return {
        'id': str(conversation.pk),
        'title': conversation.title,
        'created_at': conversation.created_at.isoformat(),
        'updated_at': conversation.updated_at.isoformat(),
        'turn_count': conversation.turns.count(),
    }


def serialize_conversation_detail(conversation: KnowledgeConversation) -> dict[str, object]:
    turns = []
    for turn in conversation.turns.all():
        llm_usage = llm_usage_from_trace(turn.run_trace)
        turns.append({
            'id': str(turn.pk),
            'run_id': str(turn.run_id),
            'question': turn.question,
            'answer': turn.answer,
            'sources': turn.sources,
            'insufficient_context': turn.insufficient_context,
            'status': turn.status,
            'error_code': turn.error_code,
            'llm_usage': llm_usage if llm_usage['total_tokens'] is not None else None,
            'created_at': turn.created_at.isoformat(),
        })
    return {
        **serialize_conversation_summary(conversation),
        'turns': turns,
    }

def _conversation_title(message: str) -> str:
    normalized = ' '.join(message.split())
    return normalized[:120]


def _touch_conversation(conversation: KnowledgeConversation):
    conversation.updated_at = timezone.now()
    conversation.save(update_fields=('updated_at',))


def _prune_excess_conversations(user):
    """创建新会话时删除当前用户超出上限的最旧会话。"""

    maximum = settings.AGENT_CONVERSATION_MAX_PER_USER
    if maximum < 1:
        return
    excess_ids = list(
        KnowledgeConversation.objects.filter(user=user)
        .order_by('-updated_at', '-created_at')
        .values_list('pk', flat=True)[maximum:]
    )
    if excess_ids:
        KnowledgeConversation.objects.filter(pk__in=excess_ids, user=user).delete()
