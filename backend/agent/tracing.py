"""按 run_id 收集不含正文的 Knowledge Agent 安全诊断轨迹。"""

from __future__ import annotations

import logging
import math
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from time import perf_counter

from django.conf import settings
from django.core.cache import cache


TRACE_CACHE_PREFIX = 'knowledge-agent-trace:'
logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RunTrace:
    run_id: str
    user_id: int | None
    started: float = field(default_factory=perf_counter)
    events: list[dict[str, object]] = field(default_factory=list)


_current_trace: ContextVar[RunTrace | None] = ContextVar(
    'knowledge_agent_run_trace',
    default=None,
)


def start_run_trace(run_id: str, *, user_id: int | None) -> Token:
    return _current_trace.set(RunTrace(run_id=run_id, user_id=user_id))


def trace_event(stage: str, **metadata):
    trace = _current_trace.get()
    if trace is None:
        return
    trace.events.append({
        'stage': stage,
        'offset_ms': round((perf_counter() - trace.started) * 1000, 3),
        'metadata': metadata,
    })


def bind_run_trace_user(user_id: int | None):
    """在 DRF 完成身份认证后，把轨迹绑定到实际请求用户。"""

    trace = _current_trace.get()
    if trace is not None:
        trace.user_id = user_id


def finish_run_trace(token: Token, *, http_status: int):
    trace = _current_trace.get()
    try:
        if trace is not None:
            payload = {
                'run_id': trace.run_id,
                'user_id': trace.user_id,
                'http_status': http_status,
                'duration_ms': round((perf_counter() - trace.started) * 1000, 3),
                'events': trace.events,
            }
            try:
                _persist_run_trace(payload)
            except Exception:
                logger.warning(
                    'Knowledge Agent run trace persistence failed.',
                    extra={'run_id': trace.run_id},
                )
            try:
                _persist_token_usage(payload)
            except Exception:
                logger.warning(
                    'Knowledge Agent token usage persistence failed.',
                    extra={'run_id': trace.run_id},
                )
            try:
                cache.set(
                    f'{TRACE_CACHE_PREFIX}{trace.run_id}',
                    payload,
                    timeout=settings.AGENT_RUN_TRACE_TTL_SECONDS,
                )
            except Exception:
                # 诊断缓存不可用不能影响已经完成的问答响应。
                pass
    finally:
        # 轨迹缓存失败也必须清理请求上下文，不能污染后续请求。
        _current_trace.reset(token)


def get_run_trace(run_id: str, *, user_id: int) -> dict[str, object] | None:
    try:
        payload = cache.get(f'{TRACE_CACHE_PREFIX}{run_id}')
    except Exception:
        payload = None
    if isinstance(payload, dict) and payload.get('user_id') == user_id:
        return payload

    # Cache 重启或过期后，从会话轮次回源，保证诊断页面与运行列表生命周期一致。
    from .models import KnowledgeConversationTurn

    stored = (
        KnowledgeConversationTurn.objects.filter(
            run_id=run_id,
            conversation__user_id=user_id,
        )
        .values_list('run_trace', flat=True)
        .first()
    )
    if not isinstance(stored, dict) or not stored:
        return None
    try:
        cache.set(
            f'{TRACE_CACHE_PREFIX}{run_id}',
            stored,
            timeout=settings.AGENT_RUN_TRACE_TTL_SECONDS,
        )
    except Exception:
        pass
    return stored


def llm_usage_from_trace(trace: object) -> dict[str, object]:
    """Extract only numeric token accounting from a sanitized run trace."""

    empty = {
        'request_count': 0,
        'usage_reported_request_count': 0,
        'usage_status': 'unavailable',
        'prompt_tokens': None,
        'completion_tokens': None,
        'total_tokens': None,
    }
    if not isinstance(trace, dict):
        return empty
    events = trace.get('events')
    if not isinstance(events, list):
        return empty
    for event in reversed(events):
        if not isinstance(event, dict) or event.get('stage') != 'agent.completed':
            continue
        metadata = event.get('metadata')
        if not isinstance(metadata, dict):
            return empty
        values = {
            'request_count': metadata.get('llm_request_count'),
            'usage_reported_request_count': metadata.get(
                'llm_usage_reported_request_count'
            ),
            'prompt_tokens': metadata.get('llm_prompt_tokens'),
            'completion_tokens': metadata.get('llm_completion_tokens'),
            'total_tokens': metadata.get('llm_total_tokens'),
        }
        for field in ('request_count', 'usage_reported_request_count'):
            value = values[field]
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                return empty
        if values['usage_reported_request_count'] > values['request_count']:
            return empty
        status = metadata.get('llm_usage_status')
        if status not in {'available', 'partial', 'unavailable'}:
            return empty
        if status == 'available':
            for field in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
                value = values[field]
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    return empty
            if values['total_tokens'] < (
                values['prompt_tokens'] + values['completion_tokens']
            ):
                return empty
        else:
            values['prompt_tokens'] = None
            values['completion_tokens'] = None
            values['total_tokens'] = None
        return {**values, 'usage_status': status}

    llm_events = [
        event.get('metadata')
        for event in events
        if isinstance(event, dict)
        and event.get('stage') == 'agent.llm.completed'
        and isinstance(event.get('metadata'), dict)
    ]
    if not llm_events:
        return empty
    reported = [metadata for metadata in llm_events if metadata.get('usage_reported') is True]
    token_fields = ('prompt_tokens', 'completion_tokens', 'total_tokens')
    if any(
        not isinstance(metadata.get(field), int)
        or isinstance(metadata.get(field), bool)
        or metadata[field] < 0
        for metadata in reported
        for field in token_fields
    ):
        return empty
    status = (
        'available'
        if reported and len(reported) == len(llm_events)
        else 'partial' if reported else 'unavailable'
    )
    return {
        'request_count': len(llm_events),
        'usage_reported_request_count': len(reported),
        'usage_status': status,
        'prompt_tokens': (
            sum(metadata['prompt_tokens'] for metadata in reported)
            if status == 'available'
            else None
        ),
        'completion_tokens': (
            sum(metadata['completion_tokens'] for metadata in reported)
            if status == 'available'
            else None
        ),
        'total_tokens': (
            sum(metadata['total_tokens'] for metadata in reported)
            if status == 'available'
            else None
        ),
    }


def _persist_run_trace(payload: dict[str, object]):
    """把已产生会话轮次的轨迹持久化；认证失败等无轮次请求仍只保留缓存。"""

    from .models import KnowledgeConversationTurn

    KnowledgeConversationTurn.objects.filter(
        run_id=payload['run_id'],
        conversation__user_id=payload['user_id'],
    ).update(run_trace=payload)


def _persist_token_usage(payload: dict[str, object]):
    from .models import AgentTokenUsage

    usage = llm_usage_from_trace(payload)
    user_id = payload.get('user_id')
    if user_id is None or usage['request_count'] < 1:
        return
    duration_ms = payload.get('duration_ms')
    if (
        not isinstance(duration_ms, (int, float))
        or isinstance(duration_ms, bool)
        or not math.isfinite(duration_ms)
        or duration_ms < 0
    ):
        duration_ms = None
    http_status = payload.get('http_status')
    if (
        not isinstance(http_status, int)
        or isinstance(http_status, bool)
        or not 100 <= http_status <= 599
    ):
        return
    AgentTokenUsage.objects.update_or_create(
        run_id=payload['run_id'],
        defaults={
            'user_id': user_id,
            'request_count': usage['request_count'],
            'usage_reported_request_count': usage['usage_reported_request_count'],
            'usage_status': usage['usage_status'],
            'prompt_tokens': usage['prompt_tokens'],
            'completion_tokens': usage['completion_tokens'],
            'total_tokens': usage['total_tokens'],
            'duration_ms': duration_ms,
            'http_status': http_status,
        },
    )
