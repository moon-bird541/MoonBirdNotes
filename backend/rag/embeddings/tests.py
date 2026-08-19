"""SiliconFlowEmbeddingService 的批量、重试、校验、缓存与脱敏测试。"""

import hashlib
import json
import logging

import httpx
from django.test import SimpleTestCase, override_settings

from .base import (
    EmbeddingConfigurationError,
    EmbeddingInputError,
    EmbeddingProviderError,
    EmbeddingResponseError,
    EmbeddingTransportError,
)
from .siliconflow import (
    SiliconFlowEmbeddingConfig,
    SiliconFlowEmbeddingService,
    get_embedding_service,
)


class MemoryCache:
    """只实现本服务使用的 Django Cache 子集，便于精确观察缓存行为。"""

    def __init__(self):
        self.values = {}
        self.deleted_keys = []
        self.set_timeouts = []

    def get_many(self, keys):
        return {key: self.values[key] for key in keys if key in self.values}

    def set_many(self, values, timeout=None):
        self.values.update(values)
        self.set_timeouts.append(timeout)

    def delete(self, key):
        self.deleted_keys.append(key)
        self.values.pop(key, None)


def make_config(**overrides) -> SiliconFlowEmbeddingConfig:
    """默认使用三维假向量，避免单元测试构造 1024 个无意义数字。"""

    values = {
        'api_key': 'test-secret-key',
        'dimension': 3,
        'batch_size': 2,
        'retry_backoff_seconds': 0.25,
        'cache_timeout_seconds': 60,
    }
    values.update(overrides)
    return SiliconFlowEmbeddingConfig(**values)


def success_response(request: httpx.Request, vectors: list[list[float]]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            'data': [
                {'object': 'embedding', 'index': index, 'embedding': vector}
                for index, vector in enumerate(vectors)
            ]
        },
        request=request,
    )


class SiliconFlowEmbeddingConfigTests(SimpleTestCase):
    """配置错误应在网络调用前暴露，且调试文本不得泄露密钥。"""

    def test_repr_hides_api_key(self):
        config = make_config(api_key='secret-that-must-not-leak')

        self.assertNotIn('secret-that-must-not-leak', repr(config))
        self.assertIn("api_key='***'", repr(config))

    def test_missing_api_key_is_structured_configuration_error(self):
        with self.assertRaises(EmbeddingConfigurationError) as context:
            make_config(api_key='')

        self.assertEqual(context.exception.code, 'embedding_configuration_error')
        self.assertFalse(context.exception.retryable)
        self.assertEqual(context.exception.provider, 'siliconflow')

    def test_base_url_rejects_embedded_credentials(self):
        with self.assertRaises(EmbeddingConfigurationError):
            make_config(base_url='https://user:password@example.com/v1')


class SiliconFlowEmbeddingServiceTests(SimpleTestCase):
    """使用 MockTransport 验证服务契约，不向硅基流动发送测试内容。"""

    def build_service(self, handler, *, config=None, cache_backend=None, sleep=None, logger=None):
        client = httpx.Client(transport=httpx.MockTransport(handler))
        self.addCleanup(client.close)
        return SiliconFlowEmbeddingService(
            config or make_config(),
            client=client,
            cache_backend=cache_backend or MemoryCache(),
            sleep=sleep or (lambda _seconds: None),
            logger=logger or logging.getLogger('rag.embeddings.tests'),
        )

    def test_empty_document_batch_returns_without_request(self):
        calls = []
        service = self.build_service(lambda request: calls.append(request))

        self.assertEqual(service.embed_documents([]), [])
        self.assertEqual(calls, [])

    def test_rejects_non_list_empty_and_overlong_inputs(self):
        service = self.build_service(lambda request: success_response(request, [[1, 0, 0]]))

        invalid_calls = (
            lambda: service.embed_documents(('text',)),
            lambda: service.embed_documents(['  ']),
            lambda: service.embed_documents([123]),
            lambda: SiliconFlowEmbeddingService(
                make_config(max_input_chars=3),
                client=service._client,
                cache_backend=MemoryCache(),
            ).embed_query('four'),
        )
        for invalid_call in invalid_calls:
            with self.subTest(call=invalid_call), self.assertRaises(EmbeddingInputError):
                invalid_call()

    def test_batches_documents_and_preserves_response_index_order(self):
        request_inputs = []

        def handler(request):
            payload = json.loads(request.content)
            request_inputs.append(payload['input'])
            # 倒序返回 data，服务必须按 index 恢复当前批次顺序。
            data = [
                {'index': index, 'embedding': [index + 1, 0, 0]}
                for index in reversed(range(len(payload['input'])))
            ]
            return httpx.Response(200, json={'data': data}, request=request)

        service = self.build_service(handler, config=make_config(batch_size=2))

        vectors = service.embed_documents([' one ', 'two', 'three', 'four', 'five'])

        self.assertEqual(request_inputs, [[' one ', 'two'], ['three', 'four'], ['five']])
        self.assertEqual(vectors, [[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]] * 2 + [[1.0, 0.0, 0.0]])

    def test_sends_model_float_encoding_and_authorization_header(self):
        captured = {}

        def handler(request):
            captured['payload'] = json.loads(request.content)
            captured['authorization'] = request.headers['Authorization']
            return success_response(request, [[3, 4, 0]])

        service = self.build_service(handler)

        vector = service.embed_query('查询')

        self.assertEqual(captured['payload']['model'], 'BAAI/bge-m3')
        self.assertEqual(captured['payload']['encoding_format'], 'float')
        self.assertEqual(captured['authorization'], 'Bearer test-secret-key')
        self.assertEqual(vector, [0.6, 0.8, 0.0])

    def test_document_cache_key_contains_versions_model_and_chunk_hash(self):
        text = '稳定缓存文本'
        content_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
        service = self.build_service(lambda request: success_response(request, [[1, 0, 0]]))

        cache_key = service.build_cache_key(cache_kind='document', content_hash=content_hash)

        self.assertIn('BAAI/bge-m3', cache_key)
        self.assertIn('siliconflow-bge-m3-input-v1', cache_key)
        self.assertIn('bge-m3-unified-v1', cache_key)
        self.assertIn(content_hash, cache_key)
        self.assertTrue(cache_key.endswith('normalize=1'))

    def test_cache_hit_avoids_second_provider_request(self):
        calls = []
        memory_cache = MemoryCache()

        def handler(request):
            calls.append(request)
            return success_response(request, [[3, 4, 0]])

        service = self.build_service(handler, cache_backend=memory_cache)

        first = service.embed_documents(['same text'])
        second = service.embed_documents(['same text'])

        self.assertEqual(first, second)
        self.assertEqual(len(calls), 1)
        self.assertEqual(memory_cache.set_timeouts, [60])

    def test_invalid_cached_vector_is_deleted_and_refetched(self):
        text = 'cached text'
        memory_cache = MemoryCache()
        service = self.build_service(
            lambda request: success_response(request, [[0, 1, 0]]),
            cache_backend=memory_cache,
        )
        cache_key = service.build_cache_key(
            cache_kind='document',
            content_hash=hashlib.sha256(text.encode('utf-8')).hexdigest(),
        )
        memory_cache.values[cache_key] = [1, 2]

        vector = service.embed_documents([text])[0]

        self.assertEqual(vector, [0.0, 1.0, 0.0])
        self.assertEqual(memory_cache.deleted_keys, [cache_key])

    def test_query_uses_separate_cache_namespace(self):
        memory_cache = MemoryCache()
        service = self.build_service(
            lambda request: success_response(request, [[1, 0, 0]]),
            config=make_config(cache_timeout_seconds=60, query_cache_timeout_seconds=15),
            cache_backend=memory_cache,
        )
        content_hash = hashlib.sha256('same'.encode('utf-8')).hexdigest()

        document_key = service.build_cache_key(cache_kind='document', content_hash=content_hash)
        query_key = service.build_cache_key(cache_kind='query', content_hash=content_hash)
        service.embed_query('same')

        self.assertNotEqual(document_key, query_key)
        self.assertEqual(memory_cache.set_timeouts, [15])

    def test_429_retries_with_exponential_backoff_then_succeeds(self):
        calls = []
        sleeps = []

        def handler(request):
            calls.append(request)
            if len(calls) < 3:
                return httpx.Response(429, json={'message': 'limited'}, request=request)
            return success_response(request, [[1, 0, 0]])

        service = self.build_service(
            handler,
            config=make_config(max_retries=2, retry_backoff_seconds=0.25),
            sleep=sleeps.append,
        )

        self.assertEqual(service.embed_query('query'), [1.0, 0.0, 0.0])
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleeps, [0.25, 0.5])

    def test_retryable_5xx_exhaustion_is_structured(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(503, text='internal details', request=request)

        service = self.build_service(handler, config=make_config(max_retries=1))

        with self.assertRaises(EmbeddingProviderError) as context:
            service.embed_query('private query')

        self.assertEqual(len(calls), 2)
        self.assertEqual(context.exception.status_code, 503)
        self.assertTrue(context.exception.retryable)
        self.assertNotIn('internal details', str(context.exception))
        self.assertNotIn('private query', str(context.exception))

    def test_non_retryable_4xx_fails_once(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(400, json={'message': 'bad private input'}, request=request)

        service = self.build_service(handler, config=make_config(max_retries=2))

        with self.assertRaises(EmbeddingProviderError) as context:
            service.embed_query('private query')

        self.assertEqual(len(calls), 1)
        self.assertEqual(context.exception.status_code, 400)
        self.assertFalse(context.exception.retryable)
        self.assertEqual(context.exception.as_dict()['code'], 'embedding_provider_error')

    def test_timeout_retries_and_logs_only_safe_fields(self):
        secret = 'secret-that-must-not-leak'
        private_text = 'full private note body'
        sleeps = []
        logger = logging.getLogger('rag.embeddings.timeout-test')

        def handler(request):
            raise httpx.ReadTimeout('timeout details', request=request)

        service = self.build_service(
            handler,
            config=make_config(api_key=secret, max_retries=1),
            sleep=sleeps.append,
            logger=logger,
        )

        with self.assertLogs(logger, level='WARNING') as captured, self.assertRaises(
            EmbeddingTransportError
        ) as context:
            service.embed_documents([private_text])

        serialized_logs = '\n'.join(
            f'{record.getMessage()} {record.__dict__}' for record in captured.records
        )
        self.assertEqual(sleeps, [0.25])
        self.assertEqual(context.exception.code, 'embedding_timeout')
        self.assertTrue(context.exception.retryable)
        self.assertNotIn(secret, serialized_logs)
        self.assertNotIn(private_text, serialized_logs)
        self.assertNotIn(secret, str(context.exception))
        self.assertNotIn(private_text, str(context.exception))
        self.assertEqual(captured.records[-1].embedding_status, 'timeout')

    def test_response_count_dimension_and_values_are_strictly_validated(self):
        invalid_payloads = (
            {'data': []},
            {'data': [{'index': 0, 'embedding': [1, 2]}]},
            {'data': [{'index': 0, 'embedding': [1, float('nan'), 3]}]},
            {'data': [{'index': 0, 'embedding': [1, True, 3]}]},
            {'data': [{'index': 0, 'embedding': [0, 0, 0]}]},
            {'data': [{'index': 2, 'embedding': [1, 0, 0]}]},
        )

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                service = self.build_service(
                    lambda request, payload=payload: httpx.Response(
                        200,
                        content=json.dumps(payload).encode('utf-8'),
                        headers={'Content-Type': 'application/json'},
                        request=request,
                    )
                )
                with self.assertRaises(EmbeddingResponseError) as context:
                    service.embed_query('query')
                self.assertEqual(context.exception.code, 'embedding_invalid_response')

    def test_normalization_can_be_disabled_explicitly(self):
        service = self.build_service(
            lambda request: success_response(request, [[3, 4, 0]]),
            config=make_config(normalize=False),
        )

        self.assertEqual(service.embed_query('query'), [3.0, 4.0, 0.0])


class EmbeddingServiceFactoryTests(SimpleTestCase):
    """工厂负责 Provider 选择，并在同一进程复用服务及 HTTP Client。"""

    def setUp(self):
        # 全量测试可能在进入本类前已创建进程级实例，先清空以隔离配置覆盖场景。
        get_embedding_service.cache_clear()
        super().setUp()

    def tearDown(self):
        service = get_embedding_service.cache_info().currsize
        if service:
            get_embedding_service().close()
        get_embedding_service.cache_clear()
        super().tearDown()

    @override_settings(
        RAG_EMBEDDING_PROVIDER='siliconflow',
        SILICONFLOW_API_KEY='factory-test-key',
        SILICONFLOW_BASE_URL='https://api.siliconflow.cn/v1',
        RAG_EMBEDDING_MODEL='BAAI/bge-m3',
        RAG_EMBEDDING_DIMENSION=1024,
        RAG_EMBEDDING_VERSION='siliconflow-bge-m3-input-v1',
        RAG_EMBEDDING_INPUT_TEMPLATE_VERSION='bge-m3-unified-v1',
        RAG_EMBEDDING_NORMALIZE=True,
        RAG_EMBEDDING_BATCH_SIZE=32,
        RAG_EMBEDDING_TIMEOUT_SECONDS=30.0,
        RAG_EMBEDDING_MAX_RETRIES=2,
        RAG_EMBEDDING_RETRY_BACKOFF_SECONDS=0.5,
        RAG_EMBEDDING_MAX_INPUT_CHARS=32768,
        RAG_EMBEDDING_CACHE_TIMEOUT_SECONDS=60,
        RAG_QUERY_EMBEDDING_CACHE_TIMEOUT_SECONDS=300,
    )
    def test_factory_reuses_process_service(self):
        first = get_embedding_service()
        second = get_embedding_service()

        self.assertIs(first, second)
        self.assertIs(first._client, second._client)

    @override_settings(RAG_EMBEDDING_PROVIDER='unknown')
    def test_factory_rejects_unknown_provider(self):
        with self.assertRaises(EmbeddingConfigurationError):
            get_embedding_service()
