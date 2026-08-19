"""Knowledge Agent 的管理员只读 HTTP API。"""

from __future__ import annotations

import logging
from datetime import datetime, time
from time import perf_counter
from uuid import uuid4

from django.db.models import Count, Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAdminUser
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from agent.agents.knowledge import KnowledgeAgentError, run_knowledge_agent
from agent.llm import ChatModelError

from .conversation_memory import refresh_conversation_memory
from .conversation_store import (
    build_persisted_history,
    get_memory_summary,
    get_or_create_conversation,
    record_completed_turn,
    record_failed_turn,
    serialize_conversation_detail,
    serialize_conversation_summary,
)
from .models import AgentTokenUsage, KnowledgeConversation, KnowledgeConversationTurn
from .serializers import KnowledgeChatRequestSerializer, KnowledgeTokenUsageQuerySerializer
from .throttles import KnowledgeChatRateThrottle
from .tracing import (
    bind_run_trace_user,
    finish_run_trace,
    get_run_trace,
    start_run_trace,
    trace_event,
)


logger = logging.getLogger(__name__)

# 只暴露稳定的前端错误契约；Provider 原文、配置值和内部路径一律留在边界内。
AGENT_ERROR_RESPONSES = {
    'agent_message_empty': (status.HTTP_400_BAD_REQUEST, 'Message must not be empty.', False),
    'agent_message_too_long': (status.HTTP_400_BAD_REQUEST, 'Message is too long.', False),
    'agent_filters_invalid': (status.HTTP_400_BAD_REQUEST, 'Filters are invalid.', False),
    'agent_history_invalid': (status.HTTP_400_BAD_REQUEST, 'Conversation history is invalid.', False),
    'authentication_required': (
        status.HTTP_401_UNAUTHORIZED,
        'Authentication is required.',
        False,
    ),
    'permission_denied': (status.HTTP_403_FORBIDDEN, 'Administrator access is required.', False),
    'llm_request_rejected': (
        status.HTTP_502_BAD_GATEWAY,
        'The language model rejected the request.',
        False,
    ),
    'llm_invalid_response': (
        status.HTTP_502_BAD_GATEWAY,
        'The language model returned an invalid response.',
        False,
    ),
    'llm_input_error': (
        status.HTTP_502_BAD_GATEWAY,
        'The language model request could not be processed.',
        False,
    ),
    'llm_transport_error': (
        status.HTTP_503_SERVICE_UNAVAILABLE,
        'The language model is temporarily unavailable.',
        True,
    ),
    'llm_provider_unavailable': (
        status.HTTP_503_SERVICE_UNAVAILABLE,
        'The language model is temporarily unavailable.',
        True,
    ),
    'llm_configuration_error': (
        status.HTTP_503_SERVICE_UNAVAILABLE,
        'Knowledge Agent is not configured.',
        False,
    ),
    'agent_configuration_error': (
        status.HTTP_503_SERVICE_UNAVAILABLE,
        'Knowledge Agent is not configured.',
        False,
    ),
    'agent_timeout': (
        status.HTTP_504_GATEWAY_TIMEOUT,
        'Knowledge Agent request timed out.',
        True,
    ),
}

HTTP_ERROR_RESPONSES = {
    status.HTTP_400_BAD_REQUEST: ('invalid_request', 'The request is invalid.', False),
    status.HTTP_401_UNAUTHORIZED: (
        'authentication_required',
        'Authentication is required.',
        False,
    ),
    status.HTTP_403_FORBIDDEN: (
        'permission_denied',
        'Administrator access is required.',
        False,
    ),
    status.HTTP_404_NOT_FOUND: ('not_found', 'The requested endpoint was not found.', False),
    status.HTTP_405_METHOD_NOT_ALLOWED: (
        'method_not_allowed',
        'The HTTP method is not allowed.',
        False,
    ),
    status.HTTP_406_NOT_ACCEPTABLE: (
        'not_acceptable',
        'Only JSON responses are supported.',
        False,
    ),
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: (
        'unsupported_media_type',
        'Only JSON requests are supported.',
        False,
    ),
    status.HTTP_429_TOO_MANY_REQUESTS: (
        'rate_limited',
        'Too many Knowledge Agent requests.',
        True,
    ),
}


class KnowledgeChatView(APIView):
    """执行问答并把每次结果记录到当前用户的持久化会话。"""

    permission_classes = [IsAdminUser]
    throttle_classes = [KnowledgeChatRateThrottle]
    parser_classes = [JSONParser]
    renderer_classes = [JSONRenderer]

    def dispatch(self, request, *args, **kwargs):
        self.run_id = str(uuid4())
        self.request_started = perf_counter()
        self.tool_steps = 0
        self.source_count = 0
        self.insufficient_context = None
        self.llm_usage = None
        self.session_id_provided = False
        self.conversation_id = None
        self.error_code = None
        self.memory_compressed = False
        trace_token = start_run_trace(
            self.run_id,
            user_id=getattr(request.user, 'pk', None),
        )
        trace_event('api.request.received', method=request.method)
        try:
            response = super().dispatch(request, *args, **kwargs)
            self._log_response(response.status_code)
            trace_event('api.response.ready', http_status=response.status_code)
            return response
        finally:
            authenticated_user = getattr(getattr(self, 'request', None), 'user', None)
            bind_run_trace_user(getattr(authenticated_user, 'pk', None))
            finish_run_trace(
                trace_token,
                http_status=getattr(locals().get('response'), 'status_code', 500),
            )

    def post(self, request):
        serializer = KnowledgeChatRequestSerializer(data=request.data)
        self.session_id_provided = (
            isinstance(request.data, dict) and 'session_id' in request.data
        )
        if not serializer.is_valid():
            trace_event('api.request.invalid')
            return self._error_response(
                'invalid_request',
                'The request is invalid.',
                retryable=False,
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        validated_data = serializer.validated_data
        trace_event(
            'api.request.validated',
            has_conversation_id=bool(validated_data.get('conversation_id')),
            has_client_history='history' in validated_data,
            message_length=len(validated_data['message']),
        )
        conversation = get_or_create_conversation(
            user=request.user,
            conversation_id=validated_data.get('conversation_id'),
            message=validated_data['message'],
        )
        self.conversation_id = str(conversation.pk)
        trace_event('conversation.resolved', conversation_id=self.conversation_id)
        try:
            agent_kwargs = {
                'user': request.user,
                'filters': validated_data.get('filters'),
            }
            if validated_data.get('conversation_id'):
                agent_kwargs['history'] = build_persisted_history(conversation)
                memory_summary = get_memory_summary(conversation)
                if memory_summary:
                    agent_kwargs['memory_summary'] = memory_summary
            elif 'history' in validated_data:
                agent_kwargs['history'] = validated_data['history']
            result = run_knowledge_agent(
                validated_data['message'],
                **agent_kwargs,
            )
        except (KnowledgeAgentError, ChatModelError) as exc:
            self.tool_steps = getattr(exc, 'tool_steps', 0)
            record_failed_turn(
                conversation=conversation,
                run_id=self.run_id,
                question=validated_data['message'],
                error_code=exc.code,
            )
            trace_event('conversation.turn.failed', error_code=exc.code)
            return self._agent_error_response(exc)
        except Exception:
            # 异常内容可能包含 Provider 响应、Key 或本地路径，禁止写入日志和响应。
            record_failed_turn(
                conversation=conversation,
                run_id=self.run_id,
                question=validated_data['message'],
                error_code='internal_error',
            )
            trace_event('conversation.turn.failed', error_code='internal_error')
            return self._error_response(
                'internal_error',
                'Knowledge Agent request failed.',
                retryable=False,
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        self.tool_steps = result.tool_steps
        self.source_count = len(result.sources)
        self.insufficient_context = result.insufficient_context
        self.llm_usage = result.llm_usage
        payload = result.as_dict()
        payload['run_id'] = self.run_id
        payload['conversation_id'] = self.conversation_id
        record_completed_turn(
            conversation=conversation,
            run_id=self.run_id,
            question=validated_data['message'],
            result=result,
        )
        trace_event(
            'conversation.turn.recorded',
            source_count=len(result.sources),
            insufficient_context=result.insufficient_context,
        )
        try:
            self.memory_compressed = refresh_conversation_memory(conversation)
            trace_event(
                'conversation.memory.checked',
                compressed=self.memory_compressed,
            )
        except Exception:
            # 压缩失败不能影响已完成回答，也不能把历史正文写入日志。
            logger.warning(
                'Knowledge conversation memory compression failed.',
                extra={'conversation_id': self.conversation_id, 'run_id': self.run_id},
            )
        return Response(payload, status=status.HTTP_200_OK)

    def handle_exception(self, exc):
        if not isinstance(exc, (APIException, Http404)):
            # 认证、解析或调度层的意外异常同样不能把原始异常文本返回给客户端。
            return self._error_response(
                'internal_error',
                'Knowledge Agent request failed.',
                retryable=False,
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response = super().handle_exception(exc)
        error_code, message, retryable = HTTP_ERROR_RESPONSES.get(
            response.status_code,
            ('api_error', 'Knowledge Agent request failed.', False),
        )
        self.error_code = error_code
        response.data = self._error_payload(error_code, message, retryable)
        return response

    def _agent_error_response(self, exc):
        definition = AGENT_ERROR_RESPONSES.get(exc.code)
        if definition is None:
            return self._error_response(
                'internal_error',
                'Knowledge Agent request failed.',
                retryable=False,
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        http_status, message, retryable = definition
        return self._error_response(
            exc.code,
            message,
            retryable=retryable,
            http_status=http_status,
        )

    def _error_response(self, code, message, *, retryable, http_status):
        self.error_code = code
        return Response(
            self._error_payload(code, message, retryable),
            status=http_status,
        )

    def _error_payload(self, code, message, retryable):
        payload = {
            'error': {
                'code': code,
                'message': message,
                'retryable': retryable,
            },
            'run_id': self.run_id,
        }
        if self.conversation_id:
            payload['conversation_id'] = self.conversation_id
        return payload

    def _log_response(self, http_status):
        user = getattr(getattr(self, 'request', None), 'user', None)
        log_method = logger.error if http_status >= 500 else logger.info
        log_method(
            'Knowledge Agent API request completed.',
            extra={
                'run_id': self.run_id,
                'user_id': getattr(user, 'pk', None),
                'session_id_provided': self.session_id_provided,
                'request_status': 'success' if http_status < 400 else 'error',
                'http_status': http_status,
                'duration_ms': round((perf_counter() - self.request_started) * 1000, 3),
                'tool_steps': self.tool_steps,
                'source_count': self.source_count,
                'insufficient_context': self.insufficient_context,
                'error_code': self.error_code,
                'memory_compressed': self.memory_compressed,
                'llm_request_count': (
                    self.llm_usage.request_count if self.llm_usage else 0
                ),
                'llm_usage_reported_request_count': (
                    self.llm_usage.usage_reported_request_count if self.llm_usage else 0
                ),
                'llm_usage_status': (
                    self.llm_usage.usage_status if self.llm_usage else 'unavailable'
                ),
                'llm_prompt_tokens': (
                    self.llm_usage.prompt_tokens if self.llm_usage else None
                ),
                'llm_completion_tokens': (
                    self.llm_usage.completion_tokens if self.llm_usage else None
                ),
                'llm_total_tokens': (
                    self.llm_usage.total_tokens if self.llm_usage else None
                ),
            },
        )


class KnowledgeConversationListView(APIView):
    """列出当前管理员的历史会话。"""

    permission_classes = [IsAdminUser]
    renderer_classes = [JSONRenderer]

    def get(self, request):
        conversations = (
            KnowledgeConversation.objects.filter(user=request.user)
            .prefetch_related('turns')[:100]
        )
        return Response({
            'results': [
                serialize_conversation_summary(item) for item in conversations
            ]
        })


class KnowledgeConversationDetailView(APIView):
    """读取或删除当前管理员自己的单个历史会话。"""

    permission_classes = [IsAdminUser]
    renderer_classes = [JSONRenderer]

    def get_object(self, request, conversation_id):
        return get_object_or_404(
            KnowledgeConversation.objects.prefetch_related('turns'),
            pk=conversation_id,
            user=request.user,
        )

    def get(self, request, conversation_id):
        return Response(serialize_conversation_detail(self.get_object(request, conversation_id)))

    def delete(self, request, conversation_id):
        self.get_object(request, conversation_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class KnowledgeRunTraceView(APIView):
    """按 run_id 返回当前管理员自己的脱敏执行轨迹。"""

    permission_classes = [IsAdminUser]
    renderer_classes = [JSONRenderer]

    def get(self, request, run_id):
        payload = get_run_trace(str(run_id), user_id=request.user.pk)
        if payload is None:
            return Response(
                {'error': {'code': 'trace_not_found', 'message': 'Run trace was not found.'}},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(payload)


class KnowledgeRunListView(APIView):
    """列出当前管理员最近的运行标识，不暴露问题、标题或回答正文。"""

    permission_classes = [IsAdminUser]
    renderer_classes = [JSONRenderer]

    def get(self, request):
        turns = (
            KnowledgeConversationTurn.objects.filter(conversation__user=request.user)
            .exclude(run_trace={})
            .select_related('conversation')
            .order_by('-created_at')[:100]
        )
        return Response({
            'results': [
                {
                    'run_id': str(turn.run_id),
                    'conversation_id': str(turn.conversation_id),
                    'status': turn.status,
                    'error_code': turn.error_code,
                    'created_at': turn.created_at.isoformat(),
                }
                for turn in turns
            ]
        })


class KnowledgeTokenUsageListView(APIView):
    """分页返回当前管理员的脱敏 Token 用量账本和全量筛选汇总。"""

    permission_classes = [IsAdminUser]
    renderer_classes = [JSONRenderer]

    def get(self, request):
        serializer = KnowledgeTokenUsageQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        params = serializer.validated_data

        records_query = AgentTokenUsage.objects.filter(user=request.user)
        local_tz = timezone.get_current_timezone()
        if params.get('date_from'):
            records_query = records_query.filter(
                created_at__gte=timezone.make_aware(
                    datetime.combine(params['date_from'], time.min),
                    local_tz,
                )
            )
        if params.get('date_to'):
            records_query = records_query.filter(
                created_at__lte=timezone.make_aware(
                    datetime.combine(params['date_to'], time.max),
                    local_tz,
                )
            )

        available_filter = Q(usage_status=AgentTokenUsage.UsageStatus.AVAILABLE)
        aggregate = records_query.aggregate(
            run_count=Count('pk'),
            token_reported_run_count=Count('pk', filter=available_filter),
            llm_request_count=Sum('request_count'),
            prompt_tokens=Sum('prompt_tokens', filter=available_filter),
            completion_tokens=Sum('completion_tokens', filter=available_filter),
            total_tokens=Sum('total_tokens', filter=available_filter),
        )

        page = params['page']
        page_size = params['page_size']
        total_count = aggregate['run_count']
        total_pages = (total_count + page_size - 1) // page_size
        offset = (page - 1) * page_size
        records = list(
            records_query.order_by('-created_at', '-pk')[offset:offset + page_size]
        )
        turn_by_run_id = {
            turn['run_id']: turn
            for turn in KnowledgeConversationTurn.objects.filter(
                conversation__user=request.user,
                run_id__in=[record.run_id for record in records],
            ).values('run_id', 'conversation_id', 'error_code', 'run_trace')
        }
        results = []
        for record in records:
            turn = turn_by_run_id.get(record.run_id)
            results.append({
                'run_id': str(record.run_id),
                'conversation_id': (
                    str(turn['conversation_id']) if turn is not None else None
                ),
                'status': 'completed' if record.http_status < 400 else 'failed',
                'error_code': turn['error_code'] if turn is not None else '',
                'created_at': record.created_at.isoformat(),
                'duration_ms': record.duration_ms,
                'trace_available': bool(turn and turn['run_trace']),
                'llm_usage': {
                    'request_count': record.request_count,
                    'usage_reported_request_count': (
                        record.usage_reported_request_count
                    ),
                    'usage_status': record.usage_status,
                    'prompt_tokens': record.prompt_tokens,
                    'completion_tokens': record.completion_tokens,
                    'total_tokens': record.total_tokens,
                },
            })
        return Response({
            'summary': {
                key: value or 0
                for key, value in aggregate.items()
            },
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_count': total_count,
                'total_pages': total_pages,
                'has_previous': page > 1,
                'has_next': page < total_pages,
            },
            'results': results,
        })
