"""通过可复用 HTTP Client 调用硅基流动 Dense Embeddings API。"""

from __future__ import annotations

import hashlib
import logging
import math
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, Sequence
from urllib.parse import urlsplit

import httpx
from django.conf import settings
from django.core.cache import cache

from .base import (
    EmbeddingConfigurationError,
    EmbeddingInputError,
    EmbeddingProviderError,
    EmbeddingResponseError,
    EmbeddingService,
    EmbeddingTransportError,
)


PROVIDER_NAME = 'siliconflow'
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SiliconFlowEmbeddingConfig:
    """硅基流动调用参数；密钥禁止进入 repr、日志和异常消息。"""

    api_key: str
    base_url: str = 'https://api.siliconflow.cn/v1'
    model: str = 'BAAI/bge-m3'
    dimension: int = 1024
    embedding_version: str = 'siliconflow-bge-m3-input-v1'
    input_template_version: str = 'bge-m3-unified-v1'
    normalize: bool = True
    batch_size: int = 32
    timeout_seconds: float = 30.0
    max_retries: int = 2
    retry_backoff_seconds: float = 0.5
    max_input_chars: int = 32768
    cache_timeout_seconds: int = 604800
    query_cache_timeout_seconds: int = 300

    def __repr__(self) -> str:
        """显式隐藏密钥，避免调试时意外写入日志。"""

        return (
            'SiliconFlowEmbeddingConfig('
            f"api_key='***', base_url={self.base_url!r}, model={self.model!r}, "
            f'dimension={self.dimension!r}, embedding_version={self.embedding_version!r}, '
            f'input_template_version={self.input_template_version!r}, normalize={self.normalize!r}, '
            f'batch_size={self.batch_size!r}, timeout_seconds={self.timeout_seconds!r}, '
            f'max_retries={self.max_retries!r}, retry_backoff_seconds={self.retry_backoff_seconds!r}, '
            f'max_input_chars={self.max_input_chars!r}, '
            f'cache_timeout_seconds={self.cache_timeout_seconds!r}, '
            f'query_cache_timeout_seconds={self.query_cache_timeout_seconds!r})'
        )

    def __post_init__(self):
        """在发起网络请求前拒绝不完整或危险的配置。"""

        if not self.api_key:
            raise _configuration_error('SiliconFlow API key is not configured.')
        if not self.model or not self.embedding_version or not self.input_template_version:
            raise _configuration_error('Embedding model and version settings cannot be empty.')

        parsed_url = urlsplit(self.base_url)
        if parsed_url.scheme not in {'http', 'https'} or not parsed_url.netloc:
            raise _configuration_error('SiliconFlow base URL must be an absolute HTTP(S) URL.')
        if parsed_url.username or parsed_url.password or parsed_url.query or parsed_url.fragment:
            raise _configuration_error('SiliconFlow base URL cannot contain credentials, query, or fragment.')

        if self.dimension < 1 or self.batch_size < 1 or self.max_input_chars < 1:
            raise _configuration_error('Embedding dimension, batch size, and input limit must be positive.')
        if self.timeout_seconds <= 0 or self.retry_backoff_seconds < 0:
            raise _configuration_error('Embedding timeout must be positive and retry backoff cannot be negative.')
        if (
            self.max_retries < 0
            or self.cache_timeout_seconds < 0
            or self.query_cache_timeout_seconds < 0
        ):
            raise _configuration_error('Embedding retry count and cache timeout cannot be negative.')

    @classmethod
    def from_django_settings(cls) -> SiliconFlowEmbeddingConfig:
        """集中读取后端环境配置，避免业务代码接触 API Key。"""

        return cls(
            api_key=settings.SILICONFLOW_API_KEY,
            base_url=settings.SILICONFLOW_BASE_URL,
            model=settings.RAG_EMBEDDING_MODEL,
            dimension=settings.RAG_EMBEDDING_DIMENSION,
            embedding_version=settings.RAG_EMBEDDING_VERSION,
            input_template_version=settings.RAG_EMBEDDING_INPUT_TEMPLATE_VERSION,
            normalize=settings.RAG_EMBEDDING_NORMALIZE,
            batch_size=settings.RAG_EMBEDDING_BATCH_SIZE,
            timeout_seconds=settings.RAG_EMBEDDING_TIMEOUT_SECONDS,
            max_retries=settings.RAG_EMBEDDING_MAX_RETRIES,
            retry_backoff_seconds=settings.RAG_EMBEDDING_RETRY_BACKOFF_SECONDS,
            max_input_chars=settings.RAG_EMBEDDING_MAX_INPUT_CHARS,
            cache_timeout_seconds=settings.RAG_EMBEDDING_CACHE_TIMEOUT_SECONDS,
            query_cache_timeout_seconds=settings.RAG_QUERY_EMBEDDING_CACHE_TIMEOUT_SECONDS,
        )


class SiliconFlowEmbeddingService(EmbeddingService):
    """提供批量、缓存、有限重试和严格响应校验的 Embedding 服务。"""

    def __init__(
        self,
        config: SiliconFlowEmbeddingConfig,
        *,
        client: httpx.Client | None = None,
        cache_backend=None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        logger: logging.Logger = LOGGER,
    ):
        self.config = config
        # 一个服务实例只创建一个 Client，使连接池能跨批次和调用复用。
        self._client = client or httpx.Client(timeout=config.timeout_seconds)
        self._owns_client = client is None
        self._cache = cache_backend if cache_backend is not None else cache
        self._sleep = sleep
        self._monotonic = monotonic
        self._logger = logger

    @property
    def endpoint(self) -> str:
        return f"{self.config.base_url.rstrip('/')}/embeddings"

    def close(self):
        """只关闭由当前服务创建的 Client，不接管注入客户端的生命周期。"""

        if self._owns_client:
            self._client.close()

    def __enter__(self) -> SiliconFlowEmbeddingService:
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not isinstance(texts, list):
            raise _input_error('Document inputs must be provided as a list of strings.')
        if not texts:
            return []
        return self._embed_many(texts, cache_kind='document')

    def embed_query(self, query: str) -> list[float]:
        return self._embed_many([query], cache_kind='query')[0]

    def build_cache_key(self, *, cache_kind: str, content_hash: str) -> str:
        """缓存键显式绑定模型、两类版本和 chunk/query 内容哈希。"""

        if cache_kind not in {'document', 'query'}:
            raise ValueError('cache_kind must be document or query.')
        if len(content_hash) != 64 or any(char not in '0123456789abcdef' for char in content_hash):
            raise ValueError('content_hash must be a lowercase SHA-256 hexadecimal digest.')
        return (
            f'rag:embedding:{PROVIDER_NAME}:{cache_kind}:{self.config.model}:'
            f'{self.config.embedding_version}:{self.config.input_template_version}:{content_hash}'
            f':normalize={int(self.config.normalize)}'
        )

    def _embed_many(self, texts: list[str], *, cache_kind: str) -> list[list[float]]:
        rendered_inputs = [self._render_input(text, index=index) for index, text in enumerate(texts)]
        cache_timeout = (
            self.config.query_cache_timeout_seconds
            if cache_kind == 'query'
            else self.config.cache_timeout_seconds
        )
        cache_keys = [
            self.build_cache_key(
                cache_kind=cache_kind,
                # 子片段 chunk_hash 就是完整 vector_text 的 SHA-256；查询使用相同算法生成内容哈希。
                content_hash=hashlib.sha256(text.encode('utf-8')).hexdigest(),
            )
            for text in rendered_inputs
        ]
        vectors: list[list[float] | None] = [None] * len(rendered_inputs)

        cached_values = self._cache.get_many(cache_keys) if cache_timeout else {}
        missing_indexes: list[int] = []
        for index, cache_key in enumerate(cache_keys):
            cached_vector = cached_values.get(cache_key)
            if cached_vector is None:
                missing_indexes.append(index)
                continue
            try:
                vectors[index] = self._validate_vector(cached_vector)
            except EmbeddingResponseError:
                # 损坏或旧格式缓存不能污染检索结果，删除后重新向量化。
                self._cache.delete(cache_key)
                missing_indexes.append(index)

        for start in range(0, len(missing_indexes), self.config.batch_size):
            batch_indexes = missing_indexes[start : start + self.config.batch_size]
            batch_inputs = [rendered_inputs[index] for index in batch_indexes]
            batch_vectors = self._request_batch(batch_inputs)
            cache_values = {}
            for index, vector in zip(batch_indexes, batch_vectors, strict=True):
                vectors[index] = vector
                cache_values[cache_keys[index]] = vector
            if cache_values and cache_timeout:
                self._cache.set_many(cache_values, timeout=cache_timeout)

        # 所有缺失项都由批次请求填充；此处检查用于阻断未来修改造成的静默漏项。
        if any(vector is None for vector in vectors):
            raise _response_error('Embedding result assembly is incomplete.')
        return [vector for vector in vectors if vector is not None]

    def _render_input(self, text: str, *, index: int) -> str:
        """BGE-M3 文档和查询统一使用原文模板，版本由配置单独标识。"""

        if not isinstance(text, str):
            raise _input_error(f'Embedding input at index {index} must be a string.')
        if not text.strip():
            raise _input_error(f'Embedding input at index {index} cannot be empty.')
        if len(text) > self.config.max_input_chars:
            raise _input_error(f'Embedding input at index {index} exceeds the configured character limit.')
        # 不裁剪有效空白，使请求内容哈希与第六步基于完整 vector_text 的 chunk_hash 一致。
        return text

    def _request_batch(self, inputs: list[str]) -> list[list[float]]:
        request_hash = hashlib.sha256('\x1f'.join(inputs).encode('utf-8')).hexdigest()
        started_at = self._monotonic()

        for attempt in range(self.config.max_retries + 1):
            try:
                response = self._client.post(
                    self.endpoint,
                    headers={
                        'Authorization': f'Bearer {self.config.api_key}',
                        'Content-Type': 'application/json',
                    },
                    json={
                        'model': self.config.model,
                        'input': inputs,
                        'encoding_format': 'float',
                    },
                    timeout=self.config.timeout_seconds,
                )
            except httpx.TimeoutException:
                if attempt < self.config.max_retries:
                    self._log_retry('timeout', request_hash, len(inputs), attempt + 1)
                    self._sleep_before_retry(attempt)
                    continue
                self._log_failure('timeout', request_hash, len(inputs), started_at, attempt + 1)
                raise EmbeddingTransportError(
                    code='embedding_timeout',
                    message='Embedding provider request timed out.',
                    retryable=True,
                    provider=PROVIDER_NAME,
                ) from None
            except httpx.RequestError:
                if attempt < self.config.max_retries:
                    self._log_retry('network_error', request_hash, len(inputs), attempt + 1)
                    self._sleep_before_retry(attempt)
                    continue
                self._log_failure('network_error', request_hash, len(inputs), started_at, attempt + 1)
                raise EmbeddingTransportError(
                    code='embedding_network_error',
                    message='Embedding provider network request failed.',
                    retryable=True,
                    provider=PROVIDER_NAME,
                ) from None

            if 200 <= response.status_code < 300:
                try:
                    vectors = self._parse_response(response, expected_count=len(inputs))
                except EmbeddingResponseError:
                    self._log_failure(
                        'invalid_response', request_hash, len(inputs), started_at, attempt + 1
                    )
                    raise
                self._log_success(request_hash, len(inputs), started_at, attempt + 1)
                return vectors

            retryable = response.status_code == 429 or 500 <= response.status_code < 600
            if retryable and attempt < self.config.max_retries:
                self._log_retry(f'http_{response.status_code}', request_hash, len(inputs), attempt + 1)
                self._sleep_before_retry(attempt)
                continue

            self._log_failure(
                f'http_{response.status_code}', request_hash, len(inputs), started_at, attempt + 1
            )
            raise EmbeddingProviderError(
                code='embedding_rate_limited' if response.status_code == 429 else 'embedding_provider_error',
                message='Embedding provider rejected the request.',
                retryable=retryable,
                provider=PROVIDER_NAME,
                status_code=response.status_code,
            )

        raise AssertionError('Embedding retry loop exited unexpectedly.')

    def _parse_response(self, response: httpx.Response, *, expected_count: int) -> list[list[float]]:
        try:
            payload = response.json()
        except ValueError:
            raise _response_error('Embedding provider returned invalid JSON.') from None

        data = payload.get('data') if isinstance(payload, dict) else None
        if not isinstance(data, list) or len(data) != expected_count:
            raise _response_error('Embedding provider returned an unexpected vector count.')

        vectors_by_index: dict[int, list[float]] = {}
        for item in data:
            if not isinstance(item, dict) or not isinstance(item.get('index'), int):
                raise _response_error('Embedding provider returned an invalid vector index.')
            index = item['index']
            if index < 0 or index >= expected_count or index in vectors_by_index:
                raise _response_error('Embedding provider returned duplicate or out-of-range vector indexes.')
            vectors_by_index[index] = self._validate_vector(item.get('embedding'))

        if set(vectors_by_index) != set(range(expected_count)):
            raise _response_error('Embedding provider response is missing vector indexes.')
        return [vectors_by_index[index] for index in range(expected_count)]

    def _validate_vector(self, value) -> list[float]:
        if not isinstance(value, (list, tuple)) or len(value) != self.config.dimension:
            raise _response_error('Embedding provider returned an invalid vector dimension.')

        vector: list[float] = []
        for number in value:
            if isinstance(number, bool) or not isinstance(number, (int, float)):
                raise _response_error('Embedding provider returned a non-numeric vector value.')
            converted = float(number)
            if not math.isfinite(converted):
                raise _response_error('Embedding provider returned a non-finite vector value.')
            vector.append(converted)

        if not self.config.normalize:
            return vector

        magnitude = math.sqrt(sum(number * number for number in vector))
        if not math.isfinite(magnitude) or magnitude == 0:
            raise _response_error('Embedding provider returned a zero or invalid vector.')
        return [number / magnitude for number in vector]

    def _sleep_before_retry(self, attempt: int):
        self._sleep(self.config.retry_backoff_seconds * (2**attempt))

    def _log_retry(self, status: str, request_hash: str, batch_size: int, attempt: int):
        self._logger.warning(
            'Embedding request will retry.',
            extra=self._log_fields(status, request_hash, batch_size, attempt),
        )

    def _log_success(
        self, request_hash: str, batch_size: int, started_at: float, attempts: int
    ):
        fields = self._log_fields('success', request_hash, batch_size, attempts)
        fields['embedding_duration_ms'] = round((self._monotonic() - started_at) * 1000, 2)
        self._logger.info('Embedding request completed.', extra=fields)

    def _log_failure(
        self, status: str, request_hash: str, batch_size: int, started_at: float, attempts: int
    ):
        fields = self._log_fields(status, request_hash, batch_size, attempts)
        fields['embedding_duration_ms'] = round((self._monotonic() - started_at) * 1000, 2)
        self._logger.error('Embedding request failed.', extra=fields)

    def _log_fields(
        self, status: str, request_hash: str, batch_size: int, attempts: int
    ) -> dict[str, str | int]:
        # 字段只包含配置标识、数量、状态和哈希，绝不包含密钥或输入正文。
        return {
            'embedding_provider': PROVIDER_NAME,
            'embedding_model': self.config.model,
            'embedding_version': self.config.embedding_version,
            'embedding_input_template_version': self.config.input_template_version,
            'embedding_batch_size': batch_size,
            'embedding_request_hash': request_hash,
            'embedding_status': status,
            'embedding_attempts': attempts,
        }


def _configuration_error(message: str) -> EmbeddingConfigurationError:
    return EmbeddingConfigurationError(
        code='embedding_configuration_error',
        message=message,
        retryable=False,
        provider=PROVIDER_NAME,
    )


def _input_error(message: str) -> EmbeddingInputError:
    return EmbeddingInputError(
        code='embedding_input_error',
        message=message,
        retryable=False,
        provider=PROVIDER_NAME,
    )


def _response_error(message: str) -> EmbeddingResponseError:
    return EmbeddingResponseError(
        code='embedding_invalid_response',
        message=message,
        retryable=False,
        provider=PROVIDER_NAME,
    )


@lru_cache(maxsize=1)
def get_embedding_service() -> EmbeddingService:
    """返回进程级服务实例，使业务调用共享同一个 HTTP 连接池。"""

    provider = settings.RAG_EMBEDDING_PROVIDER.lower()
    if provider != PROVIDER_NAME:
        raise _configuration_error('Configured embedding provider is not supported.')
    return SiliconFlowEmbeddingService(SiliconFlowEmbeddingConfig.from_django_settings())
