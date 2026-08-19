"""DeepSeek 官方 OpenAI 兼容 Chat Completions 客户端。"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlsplit

import httpx
from django.conf import settings

from .base import ChatCompletion, ChatModel, ChatModelError, ChatTokenUsage, ChatToolCall


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DeepSeekChatConfig:
    api_key: str
    base_url: str = 'https://api.deepseek.com'
    model: str = 'deepseek-v4-flash'
    timeout_seconds: float = 45.0
    max_output_tokens: int = 4096
    max_retries: int = 1
    retry_backoff_seconds: float = 0.5

    def __repr__(self) -> str:
        return (
            'DeepSeekChatConfig('
            f'api_key={"***" if self.api_key else ""!r}, '
            f'base_url={self.base_url!r}, model={self.model!r}, '
            f'timeout_seconds={self.timeout_seconds!r}, '
            f'max_output_tokens={self.max_output_tokens!r}, '
            f'max_retries={self.max_retries!r}, '
            f'retry_backoff_seconds={self.retry_backoff_seconds!r})'
        )

    def __post_init__(self):
        parsed = urlsplit(self.base_url)
        if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
            raise _config_error('DeepSeek base URL must be an absolute HTTP(S) URL.')
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise _config_error('DeepSeek base URL cannot contain credentials, query, or fragment.')
        if not self.api_key or not self.model:
            raise _config_error('DeepSeek API key and model are required.')
        if self.timeout_seconds <= 0 or self.max_output_tokens < 1:
            raise _config_error('DeepSeek timeout and max output tokens must be positive.')
        if self.max_retries < 0 or self.max_retries > 3 or self.retry_backoff_seconds < 0:
            raise _config_error('DeepSeek retry settings are invalid.')

    @classmethod
    def from_django_settings(cls) -> DeepSeekChatConfig:
        if settings.AGENT_LLM_PROVIDER != 'deepseek':
            raise _config_error('Only the confirmed DeepSeek provider is supported.')
        return cls(
            api_key=settings.AGENT_LLM_API_KEY,
            base_url=settings.AGENT_LLM_BASE_URL,
            model=settings.AGENT_LLM_MODEL,
            timeout_seconds=settings.AGENT_LLM_TIMEOUT_SECONDS,
            max_output_tokens=settings.AGENT_LLM_MAX_OUTPUT_TOKENS,
            max_retries=settings.AGENT_LLM_MAX_RETRIES,
            retry_backoff_seconds=settings.AGENT_LLM_RETRY_BACKOFF_SECONDS,
        )


class DeepSeekChatService(ChatModel):
    def __init__(
        self,
        config: DeepSeekChatConfig,
        *,
        client: httpx.Client | None = None,
        sleep=time.sleep,
    ):
        self.config = config
        self._client = client or httpx.Client(
            timeout=config.timeout_seconds,
            headers={
                'Authorization': f'Bearer {config.api_key}',
                'Content-Type': 'application/json',
            },
        )
        self._owns_client = client is None
        self._sleep = sleep

    @property
    def endpoint(self) -> str:
        return f'{self.config.base_url.rstrip("/")}/chat/completions'

    def close(self):
        if self._owns_client:
            self._client.close()

    def complete(
        self,
        messages: list[dict[str, object]],
        *,
        tools: tuple[dict[str, object], ...] = (),
    ) -> ChatCompletion:
        _validate_messages(messages)
        payload: dict[str, object] = {
            'model': self.config.model,
            'messages': messages,
            'stream': False,
            'max_tokens': self.config.max_output_tokens,
            # 知识问答与来源选择需要稳定复现，避免默认采样导致偶发拒答或错引。
            'temperature': 0,
        }
        if tools:
            payload['tools'] = list(tools)
            payload['tool_choice'] = 'auto'

        started = time.perf_counter()
        response = self._request(payload)
        completion = _parse_completion(response)
        usage = completion.usage
        logger.info(
            'DeepSeek chat completion succeeded.',
            extra={
                'provider': 'deepseek',
                'model': self.config.model,
                'message_count': len(messages),
                'tool_definition_count': len(tools),
                'returned_tool_call_count': len(completion.tool_calls),
                'duration_ms': round((time.perf_counter() - started) * 1000, 3),
                'finish_reason': completion.finish_reason,
                'usage_reported': usage is not None,
                'prompt_tokens': usage.prompt_tokens if usage else None,
                'completion_tokens': usage.completion_tokens if usage else None,
                'total_tokens': usage.total_tokens if usage else None,
            },
        )
        return completion

    def _request(self, payload: dict[str, object]) -> httpx.Response:
        for attempt in range(self.config.max_retries + 1):
            try:
                response = self._client.post(self.endpoint, json=payload)
            except (httpx.TimeoutException, httpx.TransportError):
                if attempt < self.config.max_retries:
                    self._sleep(self.config.retry_backoff_seconds * (2**attempt))
                    continue
                raise ChatModelError(
                    code='llm_transport_error',
                    message='DeepSeek request failed before receiving a response.',
                    retryable=True,
                ) from None

            if response.status_code < 400:
                return response
            retryable = response.status_code == 429 or response.status_code >= 500
            if retryable and attempt < self.config.max_retries:
                self._sleep(self.config.retry_backoff_seconds * (2**attempt))
                continue
            raise ChatModelError(
                code='llm_provider_unavailable' if retryable else 'llm_request_rejected',
                message='DeepSeek rejected the chat completion request.',
                retryable=retryable,
            )
        raise AssertionError('DeepSeek retry loop exited unexpectedly.')


def _validate_messages(messages: object):
    if not isinstance(messages, list) or not messages:
        raise _input_error('Chat messages must be a non-empty list.')
    allowed_roles = {'system', 'user', 'assistant', 'tool'}
    for message in messages:
        if not isinstance(message, dict) or message.get('role') not in allowed_roles:
            raise _input_error('Chat message role is invalid.')
        content = message.get('content')
        if content is not None and not isinstance(content, str):
            raise _input_error('Chat message content must be a string or null.')


def _parse_completion(
    response: httpx.Response,
) -> ChatCompletion:
    try:
        payload = response.json()
        choice = payload['choices'][0]
        message = choice['message']
        content = message.get('content') or ''
        finish_reason = choice.get('finish_reason') or ''
        raw_tool_calls = message.get('tool_calls') or []
        raw_usage = payload.get('usage')
    except (ValueError, KeyError, IndexError, TypeError):
        raise _response_error('DeepSeek returned a malformed chat completion.') from None
    if not isinstance(content, str) or not isinstance(raw_tool_calls, list):
        raise _response_error('DeepSeek returned invalid assistant content.')

    tool_calls = []
    for item in raw_tool_calls:
        try:
            call_id = item['id']
            function = item['function']
            name = function['name']
            arguments = function['arguments']
        except (KeyError, TypeError):
            raise _response_error('DeepSeek returned a malformed tool call.') from None
        if not all(isinstance(value, str) and value for value in (call_id, name, arguments)):
            raise _response_error('DeepSeek returned invalid tool call fields.')
        tool_calls.append(ChatToolCall(id=call_id, name=name, arguments=arguments))
    if not content.strip() and not tool_calls:
        raise _response_error('DeepSeek returned an empty completion.')
    return ChatCompletion(
        content=content,
        tool_calls=tuple(tool_calls),
        finish_reason=finish_reason,
        usage=_parse_usage(raw_usage),
    )


def _parse_usage(
    raw_usage: object,
) -> ChatTokenUsage | None:
    if not isinstance(raw_usage, dict):
        return None
    values = (
        raw_usage.get('prompt_tokens'),
        raw_usage.get('completion_tokens'),
        raw_usage.get('total_tokens'),
    )
    if any(
        not isinstance(value, int) or isinstance(value, bool) or value < 0
        for value in values
    ):
        return None
    prompt_tokens, completion_tokens, total_tokens = values
    try:
        return ChatTokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )
    except ValueError:
        return None


def _config_error(message: str) -> ChatModelError:
    return ChatModelError(code='llm_configuration_error', message=message, retryable=False)


def _input_error(message: str) -> ChatModelError:
    return ChatModelError(code='llm_input_error', message=message, retryable=False)


def _response_error(message: str) -> ChatModelError:
    return ChatModelError(code='llm_invalid_response', message=message, retryable=False)


@lru_cache(maxsize=1)
def get_chat_model() -> DeepSeekChatService:
    return DeepSeekChatService(DeepSeekChatConfig.from_django_settings())
