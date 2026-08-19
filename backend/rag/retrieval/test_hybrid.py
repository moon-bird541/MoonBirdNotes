"""混合检索融合、当前来源校验、过滤与降级测试。"""

import hashlib
from datetime import date
from unittest.mock import Mock, patch
from uuid import uuid4

from django.test import TestCase

from notes.models import DiaryEntry, Note, Tag
from rag.embeddings import EmbeddingTransportError
from rag.models import RagIndexState, RagParentChunk
from rag.qdrant import QdrantOperationError, QdrantScoredPoint

from .hybrid import HybridRetrievalError, HybridRetrievalService


class FakeEmbeddingService:
    def __init__(self, *, error=None):
        self.error = error
        self.query_calls = []

    def embed_query(self, query):
        self.query_calls.append(query)
        if self.error:
            raise self.error
        return [1.0, 0.0, 0.0]


class FakeVectorStore:
    def __init__(self, points=(), *, error=None):
        self.points = tuple(points)
        self.error = error
        self.calls = []

    def search_points(self, query_vector, *, point_filter, limit, score_threshold):
        self.calls.append((query_vector, point_filter, limit, score_threshold))
        if self.error:
            raise self.error
        return tuple(
            point for point in self.points
            if point.score >= score_threshold
        )[:limit]


class HybridRetrievalTests(TestCase):
    embedding_version = 'test-embedding-v1'

    def create_indexed_note(
        self,
        *,
        title,
        content,
        heading='主题',
        tags=(),
        diary_date=None,
        chunk_index=0,
    ):
        note = Note.objects.create(
            title=title,
            markdown_content=content,
            rendered_html='',
        )
        if tags:
            note.tags.set(tags)
        if diary_date:
            DiaryEntry.objects.create(note=note, diary_date=diary_date)
        source_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
        parent = RagParentChunk.objects.create(
            note=note,
            chunk_index=chunk_index,
            heading_path=[heading],
            content=content,
            start_line=1,
            end_line=max(1, len(content.splitlines())),
            source_hash=source_hash,
            section_hash=hashlib.sha256(f'{note.id}:{heading}'.encode()).hexdigest(),
            index_version=1,
        )
        RagIndexState.objects.create(
            note=note,
            source_hash=source_hash,
            embedding_model='BAAI/bge-m3',
            embedding_version=self.embedding_version,
            index_version=1,
            status=RagIndexState.Status.COMPLETED,
        )
        return note, parent

    def dense_point(self, parent, *, excerpt=None, score=0.9, **payload_overrides):
        diary = getattr(parent.note, 'diary_entry', None)
        payload = {
            'note_id': parent.note_id,
            'parent_id': str(parent.pk),
            'type': 'diary' if diary else 'note',
            'source_hash': parent.source_hash,
            'index_version': parent.index_version,
            'embedding_version': self.embedding_version,
            'content': excerpt or parent.content,
        }
        payload.update(payload_overrides)
        return QdrantScoredPoint(
            point_id=str(uuid4()),
            score=score,
            payload=payload,
        )

    def service(
        self,
        *,
        points=(),
        embedding_error=None,
        qdrant_error=None,
        clock=None,
        retrieval_logger=None,
    ):
        embedding = FakeEmbeddingService(error=embedding_error)
        vector = FakeVectorStore(points, error=qdrant_error)
        service = HybridRetrievalService(
            embedding_service=embedding,
            vector_store=vector,
            embedding_version=self.embedding_version,
            dense_score_threshold=0.5,
            clock=clock or (lambda: 0),
            retrieval_logger=retrieval_logger or Mock(),
        )
        return service, embedding, vector

    def test_logs_latency_and_versions_without_query_text(self):
        note, parent = self.create_indexed_note(
            title='监控说明',
            content='不能进入日志的私密查询命中内容',
        )
        retrieval_logger = Mock()
        times = iter((10.0, 10.125))
        service, _, _ = self.service(
            points=(self.dense_point(parent),),
            clock=lambda: next(times),
            retrieval_logger=retrieval_logger,
        )

        result = service.retrieve('不能进入日志的私密查询')

        self.assertEqual([item.note_id for item in result.results], [note.id])
        extra = retrieval_logger.info.call_args.kwargs['extra']
        self.assertEqual(extra['retrieval_duration_ms'], 125.0)
        self.assertEqual(extra['embedding_version'], self.embedding_version)
        self.assertEqual(extra['dense_score_threshold'], 0.5)
        self.assertEqual(extra['result_count'], 1)
        self.assertNotIn('私密查询', repr(retrieval_logger.info.call_args))

    def test_trace_candidate_keeps_diary_navigation_metadata(self):
        diary_date = date(2026, 7, 14)
        note, parent = self.create_indexed_note(
            title='工具日记',
            content='日记正文',
            diary_date=diary_date,
        )
        service, _, _ = self.service(points=(self.dense_point(parent),))

        with patch('rag.retrieval.hybrid.trace_event') as trace_event:
            result = service.retrieve('日记正文')

        self.assertEqual(result.results[0].note_id, note.id)
        candidate = trace_event.call_args.kwargs['candidates'][0]
        self.assertEqual(trace_event.call_args.kwargs['dense_score_threshold'], 0.5)
        self.assertEqual(candidate['type'], 'diary')
        self.assertEqual(candidate['diary_date'], diary_date.isoformat())

    def test_fuses_semantic_and_exact_keyword_candidates(self):
        semantic_note, semantic_parent = self.create_indexed_note(
            title='认证设计',
            content='签名令牌负责短期身份认证。',
        )
        exact_note, exact_parent = self.create_indexed_note(
            title='支付错误码',
            content='额度不足时返回 ERR_PAYMENT_409。',
        )
        service, _, _ = self.service(
            points=(
                self.dense_point(semantic_parent),
                self.dense_point(exact_parent),
            )
        )

        result = service.retrieve('ERR_PAYMENT_409')

        self.assertTrue(result.semantic_available)
        self.assertEqual(result.degradation_code, None)
        self.assertEqual(result.results[0].note_id, exact_note.id)
        self.assertEqual(
            {item.note_id for item in result.results},
            {semantic_note.id, exact_note.id},
        )

    def test_dense_score_threshold_filters_weak_semantic_candidate(self):
        _, parent = self.create_indexed_note(
            title='阈值边界',
            content='只用于弱语义候选测试',
        )
        service, _, vector = self.service(
            points=(self.dense_point(parent, score=0.499),)
        )

        result = service.retrieve('完全不同的语义问题')

        self.assertEqual(result.results, ())
        self.assertEqual(result.dense_candidate_count, 0)
        self.assertEqual(vector.calls[-1][3], 0.5)

    def test_multiple_dense_children_return_one_parent_with_weak_extra_weight(self):
        _, parent = self.create_indexed_note(
            title='长章节',
            content='同一父片段包含多个可召回子片段。',
        )
        service, _, _ = self.service(
            points=(
                self.dense_point(parent, excerpt='第一个子片段'),
                self.dense_point(parent, excerpt='第二个子片段', score=0.8),
            )
        )

        result = service.retrieve('没有关键词命中的语义问题')

        self.assertEqual(len(result.results), 1)
        self.assertEqual(result.results[0].parent_id, str(parent.pk))
        self.assertEqual(result.results[0].matched_child_excerpt, '第一个子片段')
        self.assertEqual(
            result.results[0].score,
            round(1 / 61 + 0.1 / 62, 8),
        )

    def test_stale_qdrant_hash_version_and_stale_mysql_parent_are_filtered(self):
        note, parent = self.create_indexed_note(
            title='并发更新',
            content='旧版本正文。',
        )
        service, _, _ = self.service(
            points=(self.dense_point(parent, source_hash='f' * 64),)
        )

        self.assertEqual(service.retrieve('语义问题').results, ())

        service, _, _ = self.service(
            points=(self.dense_point(parent, index_version=parent.index_version + 1),)
        )

        self.assertEqual(service.retrieve('版本不一致问题').results, ())

        note.markdown_content = '已经保存的新版本正文。'
        note.save(update_fields=['markdown_content'])
        service, _, _ = self.service(points=(self.dense_point(parent),))

        self.assertEqual(service.retrieve('另一个语义问题').results, ())

    def test_active_parent_remains_readable_during_or_after_rebuild_attempt(self):
        _, parent = self.create_indexed_note(
            title='Active version',
            content='ACTIVE_VERSION_TOKEN',
        )

        for status in (RagIndexState.Status.INDEXING, RagIndexState.Status.FAILED):
            with self.subTest(status=status):
                RagIndexState.objects.filter(note=parent.note).update(status=status)
                service, _, _ = self.service(points=(self.dense_point(parent),))

                result = service.retrieve('semantic query without an exact match')

                self.assertEqual(
                    [item.parent_id for item in result.results],
                    [str(parent.pk)],
                )

    def test_parent_without_an_activated_source_hash_is_not_readable(self):
        _, parent = self.create_indexed_note(
            title='Never activated',
            content='NEVER_ACTIVATED_TOKEN',
        )
        RagIndexState.objects.filter(note=parent.note).update(
            source_hash='',
            status=RagIndexState.Status.INDEXING,
        )
        service, _, _ = self.service(points=(self.dense_point(parent),))

        result = service.retrieve('semantic query without an exact match')

        self.assertEqual(result.results, ())

    def test_filters_are_passed_to_qdrant_and_rechecked_in_mysql(self):
        api_tag = Tag.objects.create(name='API')
        api_note, api_parent = self.create_indexed_note(
            title='API 笔记',
            content='共同检索词',
            tags=(api_tag,),
        )
        _, other_parent = self.create_indexed_note(
            title='无标签笔记',
            content='共同检索词',
        )
        diary_note, diary_parent = self.create_indexed_note(
            title='日期日记',
            content='共同检索词',
            diary_date=date(2026, 7, 14),
        )
        points = (
            self.dense_point(api_parent),
            self.dense_point(other_parent),
            self.dense_point(diary_parent),
        )

        service, _, vector = self.service(points=points)
        tag_result = service.retrieve('共同检索词', tags=('API',))
        tag_filter = vector.calls[-1][1]

        self.assertEqual([item.note_id for item in tag_result.results], [api_note.id])
        self.assertEqual(tag_filter.tags, ('API',))

        date_result = service.retrieve(
            '共同检索词',
            date_from=date(2026, 7, 1),
            date_to=date(2026, 7, 31),
        )
        date_filter = vector.calls[-1][1]

        self.assertEqual([item.note_id for item in date_result.results], [diary_note.id])
        self.assertEqual(date_filter.diary_date_from, date(2026, 7, 1))

        note_result = service.retrieve('共同检索词', types=('note',))
        self.assertEqual(
            {item.document_type for item in note_result.results},
            {'note'},
        )
        self.assertEqual(vector.calls[-1][1].document_type, 'note')

    def test_deleted_or_ai_disabled_notes_are_rejected_after_dense_recall(self):
        deleted_note, deleted_parent = self.create_indexed_note(
            title='已删除',
            content='删除前内容',
        )
        disabled_note, disabled_parent = self.create_indexed_note(
            title='已关闭',
            content='关闭前内容',
        )
        Note.objects.filter(pk=deleted_note.pk).update(is_deleted=True)
        Note.objects.filter(pk=disabled_note.pk).update(ai_indexing_enabled=False)
        service, _, _ = self.service(
            points=(
                self.dense_point(deleted_parent),
                self.dense_point(disabled_parent),
            )
        )

        result = service.retrieve('只走语义通道的问题')

        self.assertEqual(result.results, ())

    def test_embedding_failure_degrades_to_keyword_results(self):
        note, parent = self.create_indexed_note(
            title='降级说明',
            content='精确降级标识 FALLBACK_CODE_17',
        )
        error = EmbeddingTransportError(
            code='embedding_timeout',
            message='Embedding provider request timed out.',
            retryable=True,
            provider='siliconflow',
        )
        service, _, vector = self.service(embedding_error=error)

        result = service.retrieve('FALLBACK_CODE_17')

        self.assertFalse(result.semantic_available)
        self.assertTrue(result.degraded)
        self.assertEqual(result.degradation_code, 'embedding_timeout')
        self.assertEqual([item.note_id for item in result.results], [note.id])
        self.assertEqual(result.results[0].parent_id, str(parent.pk))
        self.assertEqual(vector.calls, [])

    def test_embedding_failure_returns_current_section_before_first_index_activation(self):
        content = (
            '# 无关章节\n\n这里只介绍部署。\n\n'
            '# 当前接口\n\nPENDING_FALLBACK_TOKEN 位于当前正文。'
        )
        note = Note.objects.create(title='待索引笔记', markdown_content=content, rendered_html='')
        state = RagIndexState.objects.create(note=note, status=RagIndexState.Status.PENDING)
        error = EmbeddingTransportError(
            code='embedding_timeout',
            message='Embedding provider request timed out.',
            retryable=True,
            provider='siliconflow',
        )

        for status in (RagIndexState.Status.PENDING, RagIndexState.Status.FAILED):
            with self.subTest(status=status):
                state.status = status
                state.save(update_fields=['status'])
                service, _, _ = self.service(embedding_error=error)

                result = service.retrieve('PENDING_FALLBACK_TOKEN')

                self.assertFalse(result.semantic_available)
                self.assertEqual(len(result.results), 1)
                candidate = result.results[0]
                self.assertEqual(candidate.note_id, note.id)
                self.assertIsNone(candidate.parent_id)
                self.assertEqual(candidate.heading_path, ('当前接口',))
                self.assertIn('PENDING_FALLBACK_TOKEN', candidate.content)
                self.assertEqual(
                    candidate.source_hash,
                    hashlib.sha256(content.encode('utf-8')).hexdigest(),
                )

    def test_inline_keyword_candidate_rechecks_ai_indexing_permission(self):
        note = Note.objects.create(
            title='本地私有笔记',
            markdown_content='# 私有\n\nDISABLED_INLINE_TOKEN',
            rendered_html='',
            ai_indexing_enabled=False,
        )
        error = EmbeddingTransportError(
            code='embedding_timeout',
            message='Embedding provider request timed out.',
            retryable=True,
            provider='siliconflow',
        )
        service, _, _ = self.service(embedding_error=error)

        result = service.retrieve('DISABLED_INLINE_TOKEN')

        self.assertEqual(result.keyword_candidate_count, 1)
        self.assertEqual(result.results, ())
        self.assertTrue(Note.objects.filter(pk=note.pk).exists())

    def test_qdrant_failure_also_degrades_without_hiding_keyword_results(self):
        note, _ = self.create_indexed_note(
            title='Qdrant 降级',
            content='精确标识 QDRANT_FALLBACK_21',
        )
        error = QdrantOperationError(
            code='qdrant_unavailable',
            message='Qdrant dense vector search failed.',
            retryable=True,
        )
        service, _, _ = self.service(qdrant_error=error)

        result = service.retrieve('QDRANT_FALLBACK_21')

        self.assertFalse(result.semantic_available)
        self.assertEqual(result.degradation_code, 'qdrant_unavailable')
        self.assertEqual([item.note_id for item in result.results], [note.id])

    def test_qdrant_failure_degrades_to_natural_language_keyword_terms(self):
        note, _ = self.create_indexed_note(
            title='SaaS 接口对接规范',
            content='平台目前提供五个核心接口，分别用于创建、查询、更新、删除和回调。',
        )
        error = QdrantOperationError(
            code='qdrant_unavailable',
            message='Qdrant dense vector search failed.',
            retryable=True,
        )
        service, _, _ = self.service(qdrant_error=error)

        result = service.retrieve('请问 SaaS 平台的接口有几个？')

        self.assertFalse(result.semantic_available)
        self.assertEqual(result.degradation_code, 'qdrant_unavailable')
        self.assertEqual([item.note_id for item in result.results], [note.id])

    def test_result_contains_current_parent_content_and_json_shape(self):
        note, parent = self.create_indexed_note(
            title='结构化结果',
            content='# 标题\n\nSTRUCTURED_CODE',
            heading='标题',
        )
        service, _, _ = self.service(points=(self.dense_point(parent),))

        result = service.retrieve('STRUCTURED_CODE')
        candidate = result.results[0]
        payload = result.as_dict()

        self.assertEqual(candidate.note_id, note.id)
        self.assertEqual(candidate.content, parent.content)
        self.assertEqual(candidate.heading_path, ('标题',))
        self.assertEqual(
            set(payload['results'][0]),
            {
                'note_id',
                'parent_id',
                'type',
                'title',
                'heading_path',
                'source_hash',
                'score',
                'matched_child_excerpt',
                'content',
                'start_line',
                'end_line',
                'diary_date',
            },
        )

    def test_invalid_parameters_return_stable_codes(self):
        service, _, _ = self.service()
        invalid_cases = (
            ({'query': ''}, 'keyword_query_empty'),
            ({'query': 'x', 'types': ()}, 'retrieval_types_invalid'),
            ({'query': 'x', 'tags': ('',)}, 'retrieval_tags_invalid'),
            (
                {
                    'query': 'x',
                    'date_from': date(2026, 7, 2),
                    'date_to': date(2026, 7, 1),
                },
                'retrieval_date_range_reversed',
            ),
            ({'query': 'x', 'dense_top_k': 0}, 'retrieval_dense_top_k_invalid'),
            ({'query': 'x', 'keyword_top_k': 0}, 'keyword_limit_invalid'),
            (
                {'query': 'x', 'final_parent_top_k': 21},
                'retrieval_final_parent_top_k_invalid',
            ),
        )

        for kwargs, expected_code in invalid_cases:
            with self.subTest(expected_code=expected_code), self.assertRaises(
                HybridRetrievalError
            ) as context:
                service.retrieve(**kwargs)
            self.assertEqual(context.exception.code, expected_code)
