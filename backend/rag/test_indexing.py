"""单篇索引的成功、重试、并发变化、失败恢复和删除测试。"""

import hashlib
import re
from datetime import date
from unittest.mock import patch

from django.test import TestCase

from notes.models import DiaryEntry, Note, Tag

from .chunking import ChildChunkConfig, ParentChunkConfig
from .embeddings import EmbeddingTransportError
from .indexing import NoteIndexingError, NoteIndexingService
from .models import RagIndexState, RagParentChunk
from .qdrant import QdrantOperationError


class WhitespaceTokenCounter:
    """测试只控制分块边界；真实工厂使用 BGE-M3 tokenizer。"""

    def count_tokens(self, text):
        return len(re.findall(r'\S+', text))


class FakeEmbeddingService:
    def __init__(self, *, error=None, callback=None):
        self.error = error
        self.callback = callback
        self.calls = []

    def embed_documents(self, texts):
        self.calls.append(list(texts))
        if self.callback:
            self.callback()
        if self.error:
            raise self.error
        return [[1.0, 0.0, 0.0] for _text in texts]

    def embed_query(self, query):
        raise AssertionError('单篇索引不应调用查询向量接口。')


class FakeQdrantStore:
    def __init__(self, *, upsert_error=None, upsert_callback=None, fail_delete_versions=()):
        self.upsert_error = upsert_error
        self.upsert_callback = upsert_callback
        self.fail_delete_versions = set(fail_delete_versions)
        self.deleted_versions = []
        self.deleted_notes = []
        self.upsert_batches = []
        self.delete_note_error = None

    def delete_note_version(self, *, note_id, index_version):
        self.deleted_versions.append((note_id, index_version))
        if index_version in self.fail_delete_versions:
            raise QdrantOperationError(
                code='qdrant_unavailable',
                message='Qdrant point deletion failed.',
                retryable=True,
            )

    def upsert_points(self, points):
        self.upsert_batches.append(list(points))
        if self.upsert_callback:
            self.upsert_callback()
        if self.upsert_error:
            error = self.upsert_error
            self.upsert_error = None
            raise error
        return len(points)

    def delete_note(self, *, note_id):
        self.deleted_notes.append(note_id)
        if self.delete_note_error:
            raise self.delete_note_error


class NoteIndexingServiceTests(TestCase):
    """真实 MySQL 测试数据库配合假外部依赖验证版本切换。"""

    def setUp(self):
        self.note = Note.objects.create(
            title='RAG 测试笔记',
            markdown_content='# 标题\n\n这是用于索引的正文。',
            rendered_html='<h1>标题</h1><p>这是用于索引的正文。</p>',
            ai_indexing_enabled=True,
        )
        self.tag = Tag.objects.create(name='Django')
        self.note.tags.set([self.tag])

    def build_service(self, *, embedding=None, qdrant=None):
        return NoteIndexingService(
            token_counter=WhitespaceTokenCounter(),
            embedding_service=embedding or FakeEmbeddingService(),
            vector_store=qdrant or FakeQdrantStore(),
            embedding_model='BAAI/bge-m3',
            embedding_version='siliconflow-bge-m3-input-v1',
            parent_config=ParentChunkConfig(target_tokens=20, max_tokens=100),
            child_config=ChildChunkConfig(
                target_tokens=20,
                max_tokens=100,
                overlap_tokens=5,
            ),
        )

    def create_old_active_version(self):
        source_hash = hashlib.sha256(self.note.markdown_content.encode('utf-8')).hexdigest()
        state = RagIndexState.objects.create(
            note=self.note,
            source_hash=source_hash,
            embedding_model='BAAI/bge-m3',
            embedding_version='old-embedding-v1',
            index_version=1,
            status=RagIndexState.Status.COMPLETED,
        )
        parent = RagParentChunk.objects.create(
            note=self.note,
            chunk_index=0,
            heading_path=['旧标题'],
            content='旧父片段',
            start_line=1,
            end_line=1,
            source_hash=source_hash,
            section_hash='b' * 64,
            index_version=1,
        )
        return state, parent

    def test_requires_explicit_ai_indexing_opt_in(self):
        self.note.ai_indexing_enabled = False
        self.note.save(update_fields=['ai_indexing_enabled'])
        embedding = FakeEmbeddingService()
        qdrant = FakeQdrantStore()

        with self.assertRaises(NoteIndexingError) as context:
            self.build_service(embedding=embedding, qdrant=qdrant).index_note(self.note.id)

        self.assertEqual(context.exception.code, 'ai_indexing_disabled')
        self.assertEqual(embedding.calls, [])
        self.assertEqual(qdrant.upsert_batches, [])
        self.assertFalse(RagIndexState.objects.filter(note=self.note).exists())

    def test_deleted_note_cannot_be_indexed(self):
        self.note.is_deleted = True
        self.note.save(update_fields=['is_deleted'])

        with self.assertRaises(NoteIndexingError) as context:
            self.build_service().index_note(self.note.id)

        self.assertEqual(context.exception.code, 'note_deleted')

    def test_indexes_note_and_activates_matching_mysql_and_qdrant_version(self):
        embedding = FakeEmbeddingService()
        qdrant = FakeQdrantStore()

        result = self.build_service(embedding=embedding, qdrant=qdrant).index_note(self.note.id)

        state = RagIndexState.objects.get(note=self.note)
        parents = list(RagParentChunk.objects.filter(note=self.note))
        points = qdrant.upsert_batches[0]
        expected_hash = hashlib.sha256(self.note.markdown_content.encode('utf-8')).hexdigest()
        self.assertEqual(result.index_version, 1)
        self.assertEqual(result.parent_count, len(parents))
        self.assertEqual(result.child_count, len(points))
        self.assertTrue(result.cleanup_complete)
        self.assertEqual(state.status, RagIndexState.Status.COMPLETED)
        self.assertEqual(state.source_hash, expected_hash)
        self.assertEqual(state.embedding_model, 'BAAI/bge-m3')
        self.assertEqual(state.embedding_version, 'siliconflow-bge-m3-input-v1')
        self.assertEqual({parent.index_version for parent in parents}, {1})
        self.assertEqual({point.payload.index_version for point in points}, {1})
        self.assertEqual({point.payload.source_hash for point in points}, {expected_hash})
        self.assertEqual(points[0].payload.tags, ('Django',))
        self.assertEqual(points[0].payload.document_type, 'note')
        self.assertEqual(len(points[0].payload.chunk_hash), 64)
        self.assertTrue(points[0].payload.content)

    def test_success_log_records_embedding_and_index_versions_without_content(self):
        private_content = self.note.markdown_content

        with patch('rag.indexing.logger.info') as log_info:
            result = self.build_service().index_note(self.note.id)

        extra = log_info.call_args.kwargs['extra']
        self.assertEqual(extra['index_version'], result.index_version)
        self.assertEqual(extra['embedding_model'], 'BAAI/bge-m3')
        self.assertEqual(extra['embedding_version'], 'siliconflow-bge-m3-input-v1')
        self.assertGreaterEqual(extra['indexing_duration_ms'], 0)
        self.assertNotIn(private_content, repr(log_info.call_args))

    def test_diary_uses_date_metadata_and_never_note_tags(self):
        diary_note = Note.objects.create(
            title='今日记录',
            markdown_content='# 日记\n\n今天完成 RAG。',
            rendered_html='',
            ai_indexing_enabled=True,
        )
        diary_note.tags.set([self.tag])
        DiaryEntry.objects.create(
            note=diary_note,
            diary_date=date(2026, 7, 14),
            mood='开心',
            weather='晴',
            summary='完成索引',
        )
        embedding = FakeEmbeddingService()
        qdrant = FakeQdrantStore()

        self.build_service(embedding=embedding, qdrant=qdrant).index_note(diary_note.id)

        point = qdrant.upsert_batches[0][0]
        self.assertEqual(point.payload.document_type, 'diary')
        self.assertEqual(point.payload.diary_date, date(2026, 7, 14))
        self.assertEqual(point.payload.tags, ())
        self.assertIn('心情：开心', embedding.calls[0][0])
        self.assertNotIn('标签：Django', embedding.calls[0][0])

    def test_empty_markdown_activates_zero_chunk_version_without_embedding_request(self):
        self.note.markdown_content = ''
        self.note.save(update_fields=['markdown_content'])
        embedding = FakeEmbeddingService()
        qdrant = FakeQdrantStore()

        result = self.build_service(embedding=embedding, qdrant=qdrant).index_note(self.note.id)

        self.assertEqual(result.parent_count, 0)
        self.assertEqual(result.child_count, 0)
        self.assertEqual(embedding.calls, [[]])
        self.assertEqual(qdrant.upsert_batches, [])
        self.assertEqual(RagIndexState.objects.get(note=self.note).status, 'completed')

    def test_embedding_failure_preserves_old_active_fields_and_parent_version(self):
        old_state, old_parent = self.create_old_active_version()
        embedding = FakeEmbeddingService(
            error=EmbeddingTransportError(
                code='embedding_timeout',
                message='Embedding provider request timed out.',
                retryable=True,
                provider='siliconflow',
            )
        )

        with self.assertRaises(NoteIndexingError) as context:
            self.build_service(embedding=embedding).index_note(self.note.id)

        old_state.refresh_from_db()
        self.assertEqual(context.exception.code, 'embedding_timeout')
        self.assertTrue(context.exception.retryable)
        self.assertEqual(old_state.status, RagIndexState.Status.FAILED)
        self.assertEqual(old_state.index_version, 1)
        self.assertEqual(old_state.latest_attempt_version, 2)
        self.assertEqual(old_state.embedding_version, 'old-embedding-v1')
        self.assertTrue(RagParentChunk.objects.filter(pk=old_parent.pk).exists())
        self.assertFalse(
            RagParentChunk.objects.filter(note=self.note, index_version=2).exists()
        )

    def test_qdrant_failure_removes_new_parents_and_marks_state_failed(self):
        qdrant = FakeQdrantStore(
            upsert_error=QdrantOperationError(
                code='qdrant_unavailable',
                message='Qdrant point upsert failed.',
                retryable=True,
            )
        )

        with self.assertRaises(NoteIndexingError) as context:
            self.build_service(qdrant=qdrant).index_note(self.note.id)

        state = RagIndexState.objects.get(note=self.note)
        self.assertEqual(context.exception.code, 'qdrant_unavailable')
        self.assertEqual(state.status, RagIndexState.Status.FAILED)
        self.assertIn('qdrant_unavailable', state.error_message)
        self.assertEqual(RagParentChunk.objects.filter(note=self.note).count(), 0)
        self.assertGreaterEqual(qdrant.deleted_versions.count((self.note.id, 1)), 2)

    def test_retry_after_partial_failure_uses_a_new_fenced_version(self):
        qdrant = FakeQdrantStore(
            upsert_error=QdrantOperationError(
                code='qdrant_unavailable',
                message='Qdrant point upsert failed.',
                retryable=True,
            )
        )
        service = self.build_service(qdrant=qdrant)

        with self.assertRaises(NoteIndexingError):
            service.index_note(self.note.id)
        first_ids = [point.point_id for point in qdrant.upsert_batches[0]]

        result = service.index_note(self.note.id)
        second_ids = [point.point_id for point in qdrant.upsert_batches[1]]

        self.assertEqual(result.index_version, 2)
        self.assertNotEqual(first_ids, second_ids)
        self.assertEqual(len(second_ids), len(set(second_ids)))
        state = RagIndexState.objects.get(note=self.note)
        self.assertEqual(state.status, 'completed')
        self.assertEqual(state.latest_attempt_version, 2)

    def test_stale_attempt_cannot_activate_or_fail_newer_attempt(self):
        service = self.build_service()
        first_version = service._begin_attempt(self.note.id)
        state = RagIndexState.objects.get(note=self.note)
        state.status = RagIndexState.Status.FAILED
        state.save(update_fields=['status'])
        second_version = service._begin_attempt(self.note.id)
        snapshot = service._load_snapshot(self.note.id)

        with self.assertRaises(NoteIndexingError) as context:
            service._activate_version(snapshot, first_version)
        self.assertEqual(context.exception.code, 'indexing_state_conflict')

        service._mark_attempt_failed(
            self.note.id,
            first_version,
            NoteIndexingError(
                code='stale_attempt',
                message='Stale attempt must not change current state.',
                retryable=False,
            ),
        )

        state.refresh_from_db()
        self.assertEqual(second_version, first_version + 1)
        self.assertEqual(state.status, RagIndexState.Status.INDEXING)
        self.assertEqual(state.latest_attempt_version, second_version)

    def test_repeated_success_replaces_old_version_without_duplicate_active_points(self):
        qdrant = FakeQdrantStore()
        service = self.build_service(qdrant=qdrant)

        first = service.index_note(self.note.id)
        second = service.index_note(self.note.id)

        self.assertEqual((first.index_version, second.index_version), (1, 2))
        self.assertEqual(
            set(RagParentChunk.objects.filter(note=self.note).values_list('index_version', flat=True)),
            {2},
        )
        self.assertIn((self.note.id, 1), qdrant.deleted_versions)
        self.assertEqual(RagIndexState.objects.get(note=self.note).index_version, 2)

    def test_note_change_during_embedding_discards_stale_output_before_upsert(self):
        def change_note():
            Note.objects.filter(pk=self.note.pk).update(markdown_content='# 新内容')

        embedding = FakeEmbeddingService(callback=change_note)
        qdrant = FakeQdrantStore()

        with self.assertRaises(NoteIndexingError) as context:
            self.build_service(embedding=embedding, qdrant=qdrant).index_note(self.note.id)

        self.assertEqual(context.exception.code, 'note_changed_during_indexing')
        self.assertTrue(context.exception.retryable)
        self.assertEqual(qdrant.upsert_batches, [])
        self.assertEqual(RagParentChunk.objects.filter(note=self.note).count(), 0)
        self.assertEqual(RagIndexState.objects.get(note=self.note).status, 'failed')

    def test_note_change_after_upsert_removes_unactivated_new_version(self):
        def change_note():
            Note.objects.filter(pk=self.note.pk).update(title='并发修改后的标题')

        qdrant = FakeQdrantStore(upsert_callback=change_note)

        with self.assertRaises(NoteIndexingError) as context:
            self.build_service(qdrant=qdrant).index_note(self.note.id)

        self.assertEqual(context.exception.code, 'note_changed_during_indexing')
        self.assertEqual(RagParentChunk.objects.filter(note=self.note).count(), 0)
        self.assertGreaterEqual(qdrant.deleted_versions.count((self.note.id, 1)), 2)
        self.assertEqual(RagIndexState.objects.get(note=self.note).status, 'failed')

    def test_old_cleanup_failure_keeps_new_version_active_and_old_parent_traceable(self):
        self.create_old_active_version()
        qdrant = FakeQdrantStore(fail_delete_versions={1})

        result = self.build_service(qdrant=qdrant).index_note(self.note.id)

        state = RagIndexState.objects.get(note=self.note)
        self.assertFalse(result.cleanup_complete)
        self.assertEqual(state.status, RagIndexState.Status.COMPLETED)
        self.assertEqual(state.index_version, 2)
        self.assertIn('cleanup_pending', state.error_message)
        self.assertEqual(
            set(RagParentChunk.objects.filter(note=self.note).values_list('index_version', flat=True)),
            {1, 2},
        )

    def test_unexpected_dependency_error_is_sanitized_in_state(self):
        embedding = FakeEmbeddingService(error=RuntimeError('private provider response body'))

        with self.assertRaises(NoteIndexingError) as context:
            self.build_service(embedding=embedding).index_note(self.note.id)

        state = RagIndexState.objects.get(note=self.note)
        self.assertEqual(context.exception.code, 'indexing_unexpected_error')
        self.assertNotIn('private provider response body', str(context.exception))
        self.assertNotIn('private provider response body', state.error_message)

    def test_indexing_state_conflict_rejects_second_synchronous_attempt(self):
        RagIndexState.objects.create(
            note=self.note,
            status=RagIndexState.Status.INDEXING,
        )

        with self.assertRaises(NoteIndexingError) as context:
            self.build_service().index_note(self.note.id)

        self.assertEqual(context.exception.code, 'indexing_in_progress')
        self.assertTrue(context.exception.retryable)

    def test_invalid_or_missing_note_id_is_structured(self):
        service = self.build_service()

        for note_id, expected_code in ((0, 'invalid_note_id'), (999999, 'note_not_found')):
            with self.subTest(note_id=note_id), self.assertRaises(NoteIndexingError) as context:
                service.index_note(note_id)
            self.assertEqual(context.exception.code, expected_code)

    def test_delete_note_index_removes_only_derived_data(self):
        state, parent = self.create_old_active_version()
        qdrant = FakeQdrantStore()

        result = self.build_service(qdrant=qdrant).delete_note_index(self.note.id)

        self.note.refresh_from_db()
        self.assertEqual(self.note.title, 'RAG 测试笔记')
        self.assertEqual(qdrant.deleted_notes, [self.note.id])
        self.assertEqual(result.deleted_parent_count, 1)
        self.assertEqual(result.deleted_state_count, 1)
        self.assertFalse(RagParentChunk.objects.filter(pk=parent.pk).exists())
        self.assertFalse(RagIndexState.objects.filter(pk=state.pk).exists())

    def test_delete_qdrant_failure_preserves_mysql_index_state(self):
        state, parent = self.create_old_active_version()
        qdrant = FakeQdrantStore()
        qdrant.delete_note_error = QdrantOperationError(
            code='qdrant_unavailable',
            message='Qdrant note point deletion failed.',
            retryable=True,
        )

        with self.assertRaises(NoteIndexingError) as context:
            self.build_service(qdrant=qdrant).delete_note_index(self.note.id)

        self.assertEqual(context.exception.code, 'qdrant_unavailable')
        self.assertTrue(RagParentChunk.objects.filter(pk=parent.pk).exists())
        self.assertTrue(RagIndexState.objects.filter(pk=state.pk).exists())

    def test_delete_rejects_index_currently_in_progress(self):
        RagIndexState.objects.create(note=self.note, status=RagIndexState.Status.INDEXING)
        qdrant = FakeQdrantStore()

        with self.assertRaises(NoteIndexingError) as context:
            self.build_service(qdrant=qdrant).delete_note_index(self.note.id)

        self.assertEqual(context.exception.code, 'indexing_in_progress')
        self.assertEqual(qdrant.deleted_notes, [])
