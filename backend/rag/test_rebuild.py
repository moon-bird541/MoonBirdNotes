"""全量重建的范围、授权、失败隔离、Collection 重建和命令测试。"""

import hashlib
from datetime import date
from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from notes.models import DiaryEntry, Note

from .indexing import NoteIndexingError
from .models import RagIndexJob, RagIndexState, RagParentChunk
from .qdrant import QdrantOperationError
from .rebuild import (
    RagIndexRebuildService,
    RagRebuildError,
    RebuildFailure,
    RebuildRagResult,
)


class FakeIndexingService:
    def __init__(self):
        self.index_calls = []
        self.delete_calls = []
        self.index_errors = {}
        self.delete_errors = {}
        self.embedding_service = Mock()
        self.vector_store = Mock()

    def index_note(self, note_id):
        self.index_calls.append(note_id)
        error = self.index_errors.get(note_id)
        if error:
            raise error

    def delete_note_index(self, note_id):
        self.delete_calls.append(note_id)
        error = self.delete_errors.get(note_id)
        if error:
            raise error


class FakeVectorStore:
    def __init__(self, *, error=None):
        self.error = error
        self.recreate_calls = 0

    def recreate_collection(self):
        self.recreate_calls += 1
        if self.error:
            raise self.error


class RagIndexRebuildServiceTests(TestCase):
    def setUp(self):
        self.authorized_note = Note.objects.create(
            title='已授权普通笔记',
            markdown_content='# Note',
            rendered_html='',
            ai_indexing_enabled=True,
        )
        self.authorized_diary_note = Note.objects.create(
            title='已授权日记',
            markdown_content='# Diary',
            rendered_html='',
            ai_indexing_enabled=True,
        )
        DiaryEntry.objects.create(
            note=self.authorized_diary_note,
            diary_date=date(2026, 7, 14),
        )
        self.disabled_note = Note.objects.create(
            title='未授权普通笔记',
            markdown_content='# Disabled',
            rendered_html='',
            ai_indexing_enabled=False,
        )
        self.deleted_note = Note.objects.create(
            title='已删除普通笔记',
            markdown_content='# Deleted',
            rendered_html='',
            ai_indexing_enabled=True,
            is_deleted=True,
            deleted_at=timezone.now(),
        )

    def service(self, *, indexing=None, vector=None):
        return RagIndexRebuildService(
            indexing_service=indexing or FakeIndexingService(),
            vector_store=vector or FakeVectorStore(),
        )

    def create_parent_and_state(self, note, *, version=1):
        source_hash = hashlib.sha256(note.markdown_content.encode('utf-8')).hexdigest()
        parent = RagParentChunk.objects.create(
            note=note,
            chunk_index=0,
            heading_path=['标题'],
            content='父片段',
            start_line=1,
            end_line=1,
            source_hash=source_hash,
            section_hash='b' * 64,
            index_version=version,
        )
        state = RagIndexState.objects.create(
            note=note,
            source_hash=source_hash,
            embedding_model='BAAI/bge-m3',
            embedding_version='test-v1',
            index_version=version,
            status=RagIndexState.Status.COMPLETED,
        )
        return parent, state

    def test_all_scope_indexes_authorized_and_cleans_skipped_notes(self):
        indexing = FakeIndexingService()

        result = self.service(indexing=indexing).rebuild()

        self.assertEqual(
            indexing.index_calls,
            [self.authorized_note.id, self.authorized_diary_note.id],
        )
        self.assertEqual(indexing.delete_calls, [self.disabled_note.id, self.deleted_note.id])
        self.assertEqual((result.total, result.succeeded, result.failed, result.skipped), (4, 2, 0, 2))

    def test_note_and_diary_scopes_are_strictly_separated(self):
        note_indexing = FakeIndexingService()
        note_result = self.service(indexing=note_indexing).rebuild(scope='note')

        self.assertEqual(note_indexing.index_calls, [self.authorized_note.id])
        self.assertEqual(note_indexing.delete_calls, [self.disabled_note.id, self.deleted_note.id])
        self.assertEqual(note_result.total, 3)

        diary_indexing = FakeIndexingService()
        diary_result = self.service(indexing=diary_indexing).rebuild(scope='diary')
        self.assertEqual(diary_indexing.index_calls, [self.authorized_diary_note.id])
        self.assertEqual(diary_indexing.delete_calls, [])
        self.assertEqual(diary_result.total, 1)

    def test_note_id_rebuilds_exact_note_or_reports_not_found(self):
        indexing = FakeIndexingService()

        result = self.service(indexing=indexing).rebuild(note_id=self.authorized_diary_note.id)

        self.assertEqual(indexing.index_calls, [self.authorized_diary_note.id])
        self.assertEqual(result.total, 1)

        with self.assertRaises(RagRebuildError) as context:
            self.service().rebuild(note_id=999999)
        self.assertEqual(context.exception.code, 'rebuild_note_not_found')

    def test_one_note_failure_does_not_stop_following_notes(self):
        indexing = FakeIndexingService()
        indexing.index_errors[self.authorized_note.id] = NoteIndexingError(
            code='embedding_timeout',
            message='Embedding provider request timed out.',
            retryable=True,
        )

        result = self.service(indexing=indexing).rebuild()

        self.assertIn(self.authorized_diary_note.id, indexing.index_calls)
        self.assertEqual((result.succeeded, result.failed, result.skipped), (1, 1, 2))
        self.assertEqual(result.failures[0].note_id, self.authorized_note.id)
        self.assertEqual(result.failures[0].code, 'embedding_timeout')
        self.assertTrue(result.failures[0].retryable)

    def test_unexpected_error_is_sanitized_and_processing_continues(self):
        indexing = FakeIndexingService()
        indexing.index_errors[self.authorized_note.id] = RuntimeError('private note and provider body')

        result = self.service(indexing=indexing).rebuild()

        self.assertEqual(result.failures[0].code, 'rebuild_unexpected_error')
        self.assertEqual(result.succeeded, 1)

    def test_skipped_note_cleanup_failure_counts_as_failure(self):
        indexing = FakeIndexingService()
        indexing.delete_errors[self.disabled_note.id] = NoteIndexingError(
            code='qdrant_unavailable',
            message='Qdrant note deletion failed.',
            retryable=True,
        )

        result = self.service(indexing=indexing).rebuild()

        self.assertEqual(result.failed, 1)
        self.assertEqual(result.skipped, 1)
        self.assertEqual(result.failures[0].note_id, self.disabled_note.id)

    def test_repeated_rebuild_processes_same_authorized_set_safely(self):
        indexing = FakeIndexingService()
        service = self.service(indexing=indexing)

        first = service.rebuild(scope='diary')
        second = service.rebuild(scope='diary')

        self.assertEqual(first, second)
        self.assertEqual(
            indexing.index_calls,
            [self.authorized_diary_note.id, self.authorized_diary_note.id],
        )

    def test_recreate_collection_clears_all_derived_mysql_state_then_rebuilds(self):
        original_title = self.authorized_note.title
        self.create_parent_and_state(self.authorized_note)
        self.create_parent_and_state(self.disabled_note)
        vector = FakeVectorStore()
        indexing = FakeIndexingService()

        result = self.service(indexing=indexing, vector=vector).rebuild(
            recreate_collection=True
        )

        self.authorized_note.refresh_from_db()
        self.assertEqual(vector.recreate_calls, 1)
        self.assertEqual(result.cleared_parent_count, 2)
        self.assertEqual(result.cleared_state_count, 2)
        self.assertEqual(RagParentChunk.objects.count(), 0)
        self.assertEqual(RagIndexState.objects.count(), 0)
        self.assertEqual(self.authorized_note.title, original_title)
        self.assertEqual(indexing.index_calls, [self.authorized_note.id, self.authorized_diary_note.id])
        # Collection 已整体清空，未授权和已删除内容无需再逐篇调用 Qdrant 删除。
        self.assertEqual(indexing.delete_calls, [])

    def test_collection_recreation_failure_preserves_mysql_derived_state(self):
        parent, state = self.create_parent_and_state(self.authorized_note)
        vector = FakeVectorStore(
            error=QdrantOperationError(
                code='qdrant_unavailable',
                message='Qdrant collection recreation failed.',
                retryable=True,
            )
        )

        with self.assertRaises(RagRebuildError) as context:
            self.service(vector=vector).rebuild(recreate_collection=True)

        self.assertEqual(context.exception.code, 'qdrant_unavailable')
        self.assertTrue(RagParentChunk.objects.filter(pk=parent.pk).exists())
        self.assertTrue(RagIndexState.objects.filter(pk=state.pk).exists())

    def test_partial_collection_recreation_and_conflicting_options_are_rejected(self):
        invalid_options = (
            {'scope': 'note', 'recreate_collection': True},
            {'note_id': self.authorized_note.id, 'recreate_collection': True},
            {'scope': 'diary', 'note_id': self.authorized_note.id},
        )
        for options in invalid_options:
            with self.subTest(options=options), self.assertRaises(RagRebuildError):
                self.service().rebuild(**options)

    def test_active_job_or_index_state_blocks_rebuild(self):
        RagIndexJob.objects.create(
            note=self.authorized_note,
            target_source_hash='a' * 64,
            reason='running',
            status=RagIndexJob.Status.INDEXING,
            started_at=timezone.now(),
        )

        with self.assertRaises(RagRebuildError) as context:
            self.service().rebuild()
        self.assertEqual(context.exception.code, 'rebuild_indexing_in_progress')

        RagIndexJob.objects.all().delete()
        RagIndexState.objects.create(
            note=self.authorized_note,
            status=RagIndexState.Status.INDEXING,
        )
        with self.assertRaises(RagRebuildError):
            self.service().rebuild()


class RebuildRagIndexCommandTests(TestCase):
    @patch('rag.management.commands.rebuild_rag_index.get_rag_index_rebuild_service')
    def test_command_outputs_failures_summary_and_closes_clients(self, get_service):
        service = get_service.return_value
        service.rebuild.return_value = RebuildRagResult(
            scope='all',
            total=3,
            succeeded=1,
            failed=1,
            skipped=1,
            recreated_collection=True,
            cleared_parent_count=2,
            cleared_state_count=1,
            failures=(RebuildFailure(note_id=9, code='embedding_timeout', retryable=True),),
        )
        service.indexing_service = FakeIndexingService()
        stdout = StringIO()
        stderr = StringIO()

        call_command(
            'rebuild_rag_index',
            scope='all',
            recreate_collection=True,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertIn('Collection recreated', stdout.getvalue())
        self.assertIn('succeeded=1, failed=1, skipped=1', stdout.getvalue())
        self.assertIn('note_id=9', stderr.getvalue())
        self.assertIn('code=embedding_timeout', stderr.getvalue())
        service.indexing_service.embedding_service.close.assert_called_once_with()
        service.indexing_service.vector_store.close.assert_called_once_with()
