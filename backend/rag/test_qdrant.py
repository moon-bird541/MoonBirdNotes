"""Qdrant 访问层的配置、Collection、CRUD、Filter 和失败路径测试。"""

from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings
from qdrant_client import models
from qdrant_client.http.exceptions import ApiException

from .qdrant import (
    PAYLOAD_INDEXES,
    QdrantChunkPayload,
    QdrantChunkPoint,
    QdrantCollectionError,
    QdrantCollectionSummary,
    QdrantConfig,
    QdrantConfigurationError,
    QdrantInputError,
    QdrantOperationError,
    QdrantPointFilter,
    QdrantScoredPoint,
    QdrantVectorStore,
)


PARENT_ID = '338bc47e-0000-0000-0000-000000000000'
POINT_ID = '7b20dc74-a83f-5fc2-bd0b-7f9d969f8bb8'


def make_config(**overrides) -> QdrantConfig:
    values = {'vector_size': 3, 'timeout_seconds': 5}
    values.update(overrides)
    return QdrantConfig(**values)


def make_payload(**overrides) -> QdrantChunkPayload:
    values = {
        'note_id': 15,
        'parent_id': PARENT_ID,
        'document_type': 'note',
        'title': 'SaaS 接口规范',
        'heading_path': ('接口详情', '校验接口'),
        'tags': ('API', 'Django'),
        'diary_date': None,
        'chunk_index': 2,
        'content': '校验接口正文。',
        'chunk_hash': 'b' * 64,
        'source_hash': 'a' * 64,
        'index_version': 3,
        'embedding_version': 'siliconflow-bge-m3-input-v1',
    }
    values.update(overrides)
    return QdrantChunkPayload(**values)


def make_payload_schema(**overrides):
    schema = {
        field_name: models.PayloadIndexInfo(data_type=data_type, points=0)
        for field_name, data_type in PAYLOAD_INDEXES.items()
    }
    schema.update(overrides)
    return schema


def make_collection(
    *,
    vector_name='dense',
    vector_size=3,
    distance=models.Distance.COSINE,
    payload_schema=None,
    extra_vectors=None,
):
    vectors = {
        vector_name: models.VectorParams(size=vector_size, distance=distance),
        **(extra_vectors or {}),
    }
    return SimpleNamespace(
        config=SimpleNamespace(params=SimpleNamespace(vectors=vectors)),
        payload_schema=payload_schema if payload_schema is not None else make_payload_schema(),
    )


class QdrantConfigTests(SimpleTestCase):
    """连接配置必须拒绝嵌入式路径、维度漂移和密钥泄漏。"""

    def test_repr_hides_api_key(self):
        config = make_config(api_key='qdrant-secret-value')

        self.assertNotIn('qdrant-secret-value', repr(config))
        self.assertIn("api_key='***'", repr(config))

    def test_rejects_non_http_and_credential_urls(self):
        invalid_urls = ('./qdrant-data', 'https://user:password@example.com')

        for url in invalid_urls:
            with self.subTest(url=url), self.assertRaises(QdrantConfigurationError):
                make_config(url=url)

    @override_settings(
        QDRANT_URL='http://127.0.0.1:6333',
        QDRANT_API_KEY='',
        QDRANT_COLLECTION='test_collection',
        QDRANT_VECTOR_NAME='dense',
        QDRANT_VECTOR_SIZE=1024,
        QDRANT_TIMEOUT_SECONDS=10,
        RAG_EMBEDDING_DIMENSION=768,
    )
    def test_django_config_rejects_embedding_dimension_drift(self):
        with self.assertRaises(QdrantConfigurationError):
            QdrantConfig.from_django_settings()


class QdrantPayloadTests(SimpleTestCase):
    """Payload 只接受可从 MySQL 与分块规则重建的完整字段。"""

    def test_note_payload_serializes_expected_fields(self):
        payload = make_payload().as_dict()

        self.assertEqual(
            set(payload),
            {
                'note_id',
                'parent_id',
                'type',
                'title',
                'heading_path',
                'tags',
                'diary_date',
                'chunk_index',
                'content',
                'chunk_hash',
                'source_hash',
                'index_version',
                'embedding_version',
            },
        )
        self.assertEqual(payload['type'], 'note')
        self.assertIsNone(payload['diary_date'])

    def test_diary_requires_date_and_rejects_note_tags(self):
        with self.assertRaises(QdrantInputError):
            make_payload(document_type='diary', tags=(), diary_date=None)
        with self.assertRaises(QdrantInputError):
            make_payload(document_type='diary', diary_date=date(2026, 7, 14))

        payload = make_payload(
            document_type='diary',
            tags=(),
            diary_date=date(2026, 7, 14),
        ).as_dict()
        self.assertEqual(payload['diary_date'], '2026-07-14')

    def test_rejects_invalid_runtime_types_and_hashes(self):
        invalid_overrides = (
            {'note_id': '15'},
            {'parent_id': 'not-a-uuid'},
            {'heading_path': ['heading']},
            {'tags': ['tag']},
            {'chunk_index': True},
            {'content': '  '},
            {'chunk_hash': 'short'},
            {'source_hash': 'short'},
            {'index_version': 0},
        )

        for overrides in invalid_overrides:
            with self.subTest(overrides=overrides), self.assertRaises(QdrantInputError):
                make_payload(**overrides)


class QdrantCollectionTests(SimpleTestCase):
    """Collection 初始化必须幂等，并拒绝模型或索引配置漂移。"""

    def test_health_check_calls_real_client_boundary(self):
        client = Mock()
        client.get_collections.return_value = SimpleNamespace(collections=[])
        store = QdrantVectorStore(make_config(), client=client)

        self.assertTrue(store.health_check())
        client.get_collections.assert_called_once_with()

    def test_service_failure_is_structured_and_hides_client_details(self):
        client = Mock()
        client.get_collections.side_effect = ApiException('private response and secret')
        store = QdrantVectorStore(make_config(), client=client)

        with self.assertRaises(QdrantOperationError) as context:
            store.health_check()

        self.assertEqual(context.exception.code, 'qdrant_unavailable')
        self.assertTrue(context.exception.retryable)
        self.assertNotIn('private response', str(context.exception))
        self.assertNotIn('secret', str(context.exception))

    def test_creates_named_collection_and_all_payload_indexes(self):
        client = Mock()
        client.collection_exists.return_value = False
        client.create_collection.return_value = True
        client.get_collection.side_effect = [
            make_collection(payload_schema={}),
            make_collection(payload_schema=make_payload_schema()),
        ]
        store = QdrantVectorStore(make_config(), client=client)

        summary = store.ensure_collection()

        create_kwargs = client.create_collection.call_args.kwargs
        vector = create_kwargs['vectors_config']['dense']
        self.assertEqual(create_kwargs['collection_name'], 'moonbird_note_chunks_bge_m3_v1')
        self.assertEqual(vector.size, 3)
        self.assertEqual(vector.distance, models.Distance.COSINE)
        self.assertEqual(client.create_payload_index.call_count, len(PAYLOAD_INDEXES))
        created_indexes = {
            call.kwargs['field_name']: call.kwargs['field_schema']
            for call in client.create_payload_index.call_args_list
        }
        self.assertEqual(created_indexes, PAYLOAD_INDEXES)
        self.assertEqual(summary.vector_name, 'dense')
        self.assertEqual(summary.vector_size, 3)
        self.assertEqual(summary.distance, 'Cosine')

    def test_existing_valid_collection_is_not_recreated_or_reindexed(self):
        client = Mock()
        client.collection_exists.return_value = True
        client.get_collection.return_value = make_collection()
        store = QdrantVectorStore(make_config(), client=client)

        first = store.ensure_collection()
        second = store.ensure_collection()

        self.assertEqual(first, second)
        client.create_collection.assert_not_called()
        client.create_payload_index.assert_not_called()

    def test_recreate_collection_deletes_only_configured_collection_then_initializes(self):
        client = Mock()
        client.collection_exists.side_effect = [True, False]
        client.delete_collection.return_value = True
        client.create_collection.return_value = True
        client.get_collection.side_effect = [
            make_collection(payload_schema={}),
            make_collection(payload_schema=make_payload_schema()),
        ]
        store = QdrantVectorStore(make_config(), client=client)

        summary = store.recreate_collection()

        client.delete_collection.assert_called_once_with('moonbird_note_chunks_bge_m3_v1')
        client.create_collection.assert_called_once()
        self.assertEqual(summary.vector_size, 3)
        self.assertEqual(len(summary.payload_indexes), len(PAYLOAD_INDEXES))

    def test_recreate_collection_stops_when_deletion_is_not_confirmed(self):
        client = Mock()
        client.collection_exists.return_value = True
        client.delete_collection.return_value = False
        store = QdrantVectorStore(make_config(), client=client)

        with self.assertRaises(QdrantOperationError) as context:
            store.recreate_collection()

        self.assertEqual(context.exception.code, 'qdrant_collection_delete_failed')
        client.create_collection.assert_not_called()

    def test_rejects_wrong_vector_size_distance_name_or_extra_vectors(self):
        invalid_collections = (
            make_collection(vector_size=4),
            make_collection(distance=models.Distance.DOT),
            make_collection(vector_name='other'),
            make_collection(
                extra_vectors={
                    'unverified_sparse': models.VectorParams(
                        size=3,
                        distance=models.Distance.COSINE,
                    )
                }
            ),
        )

        for collection in invalid_collections:
            with self.subTest(collection=collection):
                client = Mock()
                client.collection_exists.return_value = True
                client.get_collection.return_value = collection
                store = QdrantVectorStore(make_config(), client=client)
                with self.assertRaises(QdrantCollectionError):
                    store.ensure_collection()
                client.create_collection.assert_not_called()

    def test_rejects_wrong_or_missing_payload_index_after_initialization(self):
        wrong_schema = make_payload_schema(
            note_id=models.PayloadIndexInfo(
                data_type=models.PayloadSchemaType.KEYWORD,
                points=0,
            )
        )
        client = Mock()
        client.collection_exists.return_value = True
        client.get_collection.return_value = make_collection(payload_schema=wrong_schema)
        store = QdrantVectorStore(make_config(), client=client)

        with self.assertRaises(QdrantCollectionError):
            store.ensure_collection()

        client = Mock()
        client.collection_exists.return_value = True
        client.get_collection.side_effect = [
            make_collection(payload_schema={}),
            make_collection(payload_schema={}),
        ]
        store = QdrantVectorStore(make_config(), client=client)
        with self.assertRaises(QdrantCollectionError):
            store.ensure_collection()


class QdrantPointOperationTests(SimpleTestCase):
    """批量写入、版本删除和 Payload Filter 不依赖真实容器即可验证。"""

    def test_batch_upsert_uses_named_vectors_and_complete_payloads(self):
        client = Mock()
        store = QdrantVectorStore(make_config(), client=client)
        points = [
            QdrantChunkPoint(
                point_id=POINT_ID,
                vector=(1.0, 0.0, 0.0),
                payload=make_payload(),
            ),
            QdrantChunkPoint(
                point_id='267423e9-1d74-58ba-84cf-bc147c622f8a',
                vector=(0.0, 1.0, 0.0),
                payload=make_payload(chunk_index=3),
            ),
        ]

        count = store.upsert_points(points)

        self.assertEqual(count, 2)
        call_kwargs = client.upsert.call_args.kwargs
        self.assertTrue(call_kwargs['wait'])
        self.assertEqual(call_kwargs['points'][0].vector, {'dense': [1.0, 0.0, 0.0]})
        self.assertEqual(call_kwargs['points'][0].payload['source_hash'], 'a' * 64)

    def test_empty_batch_is_noop_and_duplicate_ids_are_rejected(self):
        client = Mock()
        store = QdrantVectorStore(make_config(), client=client)

        self.assertEqual(store.upsert_points([]), 0)
        client.upsert.assert_not_called()

        point = QdrantChunkPoint(
            point_id=POINT_ID,
            vector=(1.0, 0.0, 0.0),
            payload=make_payload(),
        )
        with self.assertRaises(QdrantInputError):
            store.upsert_points([point, point])

    def test_rejects_wrong_dimension_non_numeric_and_non_finite_vectors(self):
        invalid_vectors = (
            (1.0, 0.0),
            (1.0, True, 0.0),
            (1.0, 'bad', 0.0),
            (1.0, float('inf'), 0.0),
        )

        for vector in invalid_vectors:
            with self.subTest(vector=vector):
                store = QdrantVectorStore(make_config(), client=Mock())
                point = QdrantChunkPoint(
                    point_id=POINT_ID,
                    vector=vector,
                    payload=make_payload(),
                )
                with self.assertRaises(QdrantInputError):
                    store.upsert_points([point])

    def test_delete_requires_note_and_index_version_filter(self):
        client = Mock()
        store = QdrantVectorStore(make_config(), client=client)

        store.delete_note_version(note_id=15, index_version=3)

        selector = client.delete.call_args.kwargs['points_selector']
        conditions = {condition.key: condition.match.value for condition in selector.filter.must}
        self.assertEqual(conditions, {'note_id': 15, 'index_version': 3})
        self.assertTrue(client.delete.call_args.kwargs['wait'])

    def test_delete_note_filters_all_versions_by_note_id(self):
        client = Mock()
        store = QdrantVectorStore(make_config(), client=client)

        store.delete_note(note_id=15)

        selector = client.delete.call_args.kwargs['points_selector']
        conditions = {condition.key: condition.match.value for condition in selector.filter.must}
        self.assertEqual(conditions, {'note_id': 15})

    def test_scroll_builds_indexed_filters_and_returns_safe_page(self):
        client = Mock()
        client.scroll.return_value = (
            [
                models.Record(
                    id=POINT_ID,
                    payload=make_payload().as_dict(),
                    vector={'dense': [1.0, 0.0, 0.0]},
                )
            ],
            UUID('267423e9-1d74-58ba-84cf-bc147c622f8a'),
        )
        store = QdrantVectorStore(make_config(), client=client)
        point_filter = QdrantPointFilter(
            note_id=15,
            parent_id=PARENT_ID,
            document_type='note',
            tags=('API', 'Django'),
            diary_date_from=date(2026, 7, 1),
            diary_date_to=date(2026, 7, 31),
            source_hash='a' * 64,
            index_version=3,
            embedding_version='siliconflow-bge-m3-input-v1',
        )

        page = store.scroll_points(point_filter, limit=20, with_vectors=True)

        call_kwargs = client.scroll.call_args.kwargs
        conditions = call_kwargs['scroll_filter'].must
        self.assertEqual(
            [condition.key for condition in conditions],
            [
                'note_id',
                'parent_id',
                'type',
                'source_hash',
                'index_version',
                'embedding_version',
                'tags',
                'tags',
                'diary_date',
            ],
        )
        self.assertEqual(call_kwargs['with_vectors'], ['dense'])
        self.assertEqual(page.points[0].point_id, POINT_ID)
        self.assertEqual(page.points[0].payload['note_id'], 15)
        self.assertEqual(
            page.next_offset,
            UUID('267423e9-1d74-58ba-84cf-bc147c622f8a'),
        )

    def test_scroll_rejects_invalid_filter_limit_and_offset(self):
        store = QdrantVectorStore(make_config(), client=Mock())

        invalid_calls = (
            lambda: store.scroll_points('not-a-filter'),
            lambda: store.scroll_points(QdrantPointFilter(), limit=0),
            lambda: store.scroll_points(QdrantPointFilter(), limit='10'),
            lambda: store.scroll_points(QdrantPointFilter(), offset='not-a-uuid'),
        )
        for invalid_call in invalid_calls:
            with self.subTest(call=invalid_call), self.assertRaises(QdrantInputError):
                invalid_call()

    def test_dense_search_uses_named_vector_filter_and_safe_results(self):
        client = Mock()
        client.query_points.return_value = SimpleNamespace(
            points=[
                SimpleNamespace(
                    id=POINT_ID,
                    score=0.91,
                    payload=make_payload().as_dict(),
                )
            ]
        )
        store = QdrantVectorStore(make_config(), client=client)
        point_filter = QdrantPointFilter(document_type='note', tags=('API',))

        results = store.search_points(
            (1.0, 0.0, 0.0),
            point_filter=point_filter,
            limit=5,
            score_threshold=0.5,
        )

        call_kwargs = client.query_points.call_args.kwargs
        self.assertEqual(call_kwargs['using'], 'dense')
        self.assertEqual(call_kwargs['query'], [1.0, 0.0, 0.0])
        self.assertEqual(call_kwargs['limit'], 5)
        self.assertEqual(call_kwargs['score_threshold'], 0.5)
        self.assertFalse(call_kwargs['with_vectors'])
        self.assertEqual(
            [condition.key for condition in call_kwargs['query_filter'].must],
            ['type', 'tags'],
        )
        self.assertEqual(
            results,
            (
                QdrantScoredPoint(
                    point_id=POINT_ID,
                    score=0.91,
                    payload=make_payload().as_dict(),
                ),
            ),
        )

    def test_dense_search_rejects_invalid_inputs_and_scores(self):
        store = QdrantVectorStore(make_config(), client=Mock())
        invalid_calls = (
            lambda: store.search_points((1.0, 0.0)),
            lambda: store.search_points((1.0, 0.0, 0.0), point_filter='bad'),
            lambda: store.search_points((1.0, 0.0, 0.0), limit=0),
            lambda: store.search_points(
                (1.0, 0.0, 0.0), score_threshold=float('nan')
            ),
        )

        for invalid_call in invalid_calls:
            with self.subTest(call=invalid_call), self.assertRaises(QdrantInputError):
                invalid_call()

        client = Mock()
        client.query_points.return_value = SimpleNamespace(
            points=[SimpleNamespace(id=POINT_ID, score=float('nan'), payload={})]
        )
        store = QdrantVectorStore(make_config(), client=client)
        with self.assertRaises(QdrantOperationError) as context:
            store.search_points((1.0, 0.0, 0.0))
        self.assertEqual(context.exception.code, 'qdrant_invalid_response')


class InitializeQdrantCommandTests(SimpleTestCase):
    """管理命令只输出可安全公开的 Collection 摘要。"""

    @patch('rag.management.commands.initialize_qdrant.get_qdrant_store')
    def test_command_runs_health_check_and_idempotent_initialization(self, get_store):
        store = get_store.return_value
        store.health_check.return_value = True
        store.ensure_collection.return_value = QdrantCollectionSummary(
            collection_name='moonbird_note_chunks_bge_m3_v1',
            vector_name='dense',
            vector_size=1024,
            distance='Cosine',
            payload_indexes=tuple(sorted(PAYLOAD_INDEXES)),
        )
        stdout = Mock()

        call_command('initialize_qdrant', stdout=stdout)

        store.health_check.assert_called_once_with()
        store.ensure_collection.assert_called_once_with()
        store.close.assert_called_once_with()
        get_store.cache_clear.assert_called_once_with()
        output = ''.join(call.args[0] for call in stdout.write.call_args_list)
        self.assertIn('size=1024', output)
        self.assertIn('payload_indexes=8', output)
