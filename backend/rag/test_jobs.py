"""后台 RAG 任务的防抖、signals、领取、重试与租约测试。"""

import hashlib
from datetime import date, timedelta
from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from notes.models import DiaryEntry, Note, Tag

from .indexing import NoteIndexingError
from .jobs import (
    JobProcessResult,
    RagIndexWorker,
    enqueue_note_deletion,
    enqueue_note_index,
    enqueue_note_index_on_commit,
    note_source_hash,
)
from .models import RagIndexDeletionJob, RagIndexJob, RagIndexState
from .qdrant import QdrantOperationError


class FakeIndexingService:
    """Worker 测试只观察编排，不执行真实 Embedding 或 Qdrant。"""

    def __init__(self, *, index_error=None, delete_error=None):
        self.index_error = index_error
        self.delete_error = delete_error
        self.index_calls = []
        self.delete_calls = []
        self.embedding_service = Mock()
        self.vector_store = Mock()

    def index_note(self, note_id):
        self.index_calls.append(note_id)
        if self.index_error:
            raise self.index_error

    def delete_note_index(self, note_id):
        self.delete_calls.append(note_id)
        if self.delete_error:
            raise self.delete_error


@override_settings(
    RAG_INDEX_DEBOUNCE_SECONDS=10,
    RAG_INDEX_MAX_ATTEMPTS=3,
    RAG_INDEX_RETRY_BASE_SECONDS=5,
    RAG_INDEX_LEASE_SECONDS=60,
)
class RagIndexQueueTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.note = Note.objects.create(
            title='后台索引测试',
            markdown_content='# 初始内容',
            rendered_html='',
            ai_indexing_enabled=True,
        )

    def test_debounce_coalesces_pending_job_to_latest_source_hash(self):
        first = enqueue_note_index(self.note.id, reason='first_save', now=self.now)
        Note.objects.filter(pk=self.note.pk).update(markdown_content='# 最新内容')

        second = enqueue_note_index(
            self.note.id,
            reason='second_save',
            now=self.now + timedelta(seconds=2),
        )

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(RagIndexJob.objects.filter(status='pending').count(), 1)
        second.refresh_from_db()
        self.assertEqual(
            second.target_source_hash,
            hashlib.sha256('# 最新内容'.encode('utf-8')).hexdigest(),
        )
        self.assertEqual(second.reason, 'second_save')
        self.assertEqual(second.available_at, self.now + timedelta(seconds=12))
        self.assertEqual(second.attempts, 0)

    def test_immediate_job_skips_debounce_for_agent_changes(self):
        job = enqueue_note_index(
            self.note.id,
            reason='agent_modified',
            immediate=True,
            now=self.now,
        )

        self.assertEqual(job.available_at, self.now)

    def test_on_commit_does_not_create_job_before_transaction_commit(self):
        with self.captureOnCommitCallbacks(execute=True):
            enqueue_note_index_on_commit(self.note.id, reason='note_saved')
            self.assertEqual(RagIndexJob.objects.count(), 0)

        self.assertEqual(RagIndexJob.objects.count(), 1)

    def test_note_signal_queues_relevant_change_but_ignores_importance(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.note.importance = 3
            self.note.save(update_fields=['importance'])
        self.assertEqual(RagIndexJob.objects.count(), 0)

        with self.captureOnCommitCallbacks(execute=True):
            self.note.markdown_content = '# 修改后的内容'
            self.note.save(update_fields=['markdown_content'])
        self.assertEqual(RagIndexJob.objects.count(), 1)
        self.assertEqual(RagIndexJob.objects.get().reason, 'note_saved')

    def test_ai_indexing_toggle_queues_cleanup_or_index(self):
        disabled_note = Note.objects.create(
            title='显式关闭',
            markdown_content='正文',
            rendered_html='',
            ai_indexing_enabled=False,
        )
        with self.captureOnCommitCallbacks(execute=True):
            disabled_note.ai_indexing_enabled = True
            disabled_note.save(update_fields=['ai_indexing_enabled'])
        self.assertEqual(RagIndexJob.objects.get(note=disabled_note).reason, 'ai_indexing_changed')

        with self.captureOnCommitCallbacks(execute=True):
            disabled_note.ai_indexing_enabled = False
            disabled_note.save(update_fields=['ai_indexing_enabled'])
        self.assertEqual(RagIndexJob.objects.filter(note=disabled_note, status='pending').count(), 1)

    def test_new_note_enables_ai_indexing_and_queues_job_by_default(self):
        with self.captureOnCommitCallbacks(execute=True):
            note = Note.objects.create(
                title='默认允许向量化',
                markdown_content='正文',
                rendered_html='',
            )

        self.assertTrue(note.ai_indexing_enabled)
        self.assertEqual(RagIndexJob.objects.get(note=note).reason, 'note_created')

    def test_tag_and_diary_metadata_signals_coalesce_jobs(self):
        tag = Tag.objects.create(name='Django')
        with self.captureOnCommitCallbacks(execute=True):
            self.note.tags.add(tag)
        job = RagIndexJob.objects.get(note=self.note, status='pending')
        self.assertEqual(job.reason, 'note_tags_changed')

        diary_note = Note.objects.create(
            title='日记',
            markdown_content='# 日记',
            rendered_html='',
            ai_indexing_enabled=True,
        )
        with self.captureOnCommitCallbacks(execute=True):
            diary = DiaryEntry.objects.create(note=diary_note, diary_date=date(2026, 7, 14))
        self.assertEqual(
            RagIndexJob.objects.get(note=diary_note, status='pending').reason,
            'diary_metadata_changed',
        )

        with self.captureOnCommitCallbacks(execute=True):
            diary.mood = '开心'
            diary.save(update_fields=['mood'])
        self.assertEqual(RagIndexJob.objects.filter(note=diary_note, status='pending').count(), 1)

    def test_tag_rename_queues_all_enabled_notes(self):
        tag = Tag.objects.create(name='旧名称')
        self.note.tags.add(tag)
        RagIndexJob.objects.all().delete()

        with self.captureOnCommitCallbacks(execute=True):
            tag.name = '新名称'
            tag.save(update_fields=['name'])

        self.assertEqual(RagIndexJob.objects.get(note=self.note).reason, 'tag_renamed')

    def test_enqueue_while_job_is_indexing_creates_one_latest_pending_job(self):
        RagIndexJob.objects.create(
            note=self.note,
            target_source_hash=note_source_hash(self.note.markdown_content),
            reason='running',
            status=RagIndexJob.Status.INDEXING,
            available_at=self.now,
            started_at=self.now,
        )

        first_pending = enqueue_note_index(self.note.id, reason='save_1', now=self.now)
        second_pending = enqueue_note_index(self.note.id, reason='save_2', now=self.now)

        self.assertEqual(first_pending.pk, second_pending.pk)
        self.assertEqual(RagIndexJob.objects.filter(note=self.note, status='pending').count(), 1)
        self.assertEqual(RagIndexJob.objects.filter(note=self.note, status='indexing').count(), 1)

    def test_permanent_delete_job_survives_note_cascade_and_is_idempotent(self):
        note_id = self.note.id
        first = enqueue_note_deletion(note_id, now=self.now)

        self.note.delete()
        second = enqueue_note_deletion(note_id, now=self.now)

        self.assertEqual(first.pk, second.pk)
        self.assertFalse(Note.objects.filter(pk=note_id).exists())
        self.assertEqual(RagIndexDeletionJob.objects.filter(note_id=note_id).count(), 1)
        self.assertEqual(second.status, RagIndexDeletionJob.Status.PENDING)


@override_settings(RAG_INDEX_DEBOUNCE_SECONDS=10)
class RagIndexWorkerTests(TestCase):
    def setUp(self):
        self.clock = [timezone.now()]
        self.note = Note.objects.create(
            title='Worker 测试',
            markdown_content='# 当前内容',
            rendered_html='',
            ai_indexing_enabled=True,
        )

    def worker(self, service=None, *, max_attempts=3, retry_base=5, lease=60):
        return RagIndexWorker(
            indexing_service=service or FakeIndexingService(),
            max_attempts=max_attempts,
            retry_base_seconds=retry_base,
            lease_seconds=lease,
            now=lambda: self.clock[0],
        )

    def create_job(self, **overrides):
        values = {
            'note': self.note,
            'target_source_hash': note_source_hash(self.note.markdown_content),
            'reason': 'test',
            'status': RagIndexJob.Status.PENDING,
            'available_at': self.clock[0],
        }
        values.update(overrides)
        return RagIndexJob.objects.create(**values)

    def create_deletion_job(self, **overrides):
        values = {
            'note_id': self.note.id + 1000,
            'status': RagIndexDeletionJob.Status.PENDING,
            'available_at': self.clock[0],
        }
        values.update(overrides)
        return RagIndexDeletionJob.objects.create(**values)

    def test_not_yet_available_job_is_not_claimed(self):
        self.create_job(available_at=self.clock[0] + timedelta(seconds=1))

        self.assertIsNone(self.worker().process_next())
        self.assertEqual(RagIndexJob.objects.get().status, 'pending')

    def test_successful_job_indexes_note_and_records_completion(self):
        job = self.create_job()
        service = FakeIndexingService()

        result = self.worker(service).process_next()

        job.refresh_from_db()
        self.assertEqual(result.outcome, 'indexed')
        self.assertEqual(result.attempts, 1)
        self.assertEqual(service.index_calls, [self.note.id])
        self.assertEqual(job.status, RagIndexJob.Status.COMPLETED)
        self.assertIsNotNone(job.completed_at)

    def test_deletion_job_removes_all_qdrant_versions_after_note_is_gone(self):
        job = self.create_deletion_job()
        service = FakeIndexingService()

        result = self.worker(service).process_next()

        job.refresh_from_db()
        self.assertEqual(result.outcome, 'deleted')
        self.assertEqual(result.note_id, job.note_id)
        service.vector_store.delete_note.assert_called_once_with(note_id=job.note_id)
        self.assertEqual(job.status, RagIndexDeletionJob.Status.COMPLETED)
        self.assertIsNotNone(job.completed_at)

    def test_retryable_deletion_failure_is_retried_without_note_foreign_key(self):
        job = self.create_deletion_job()
        service = FakeIndexingService()
        service.vector_store.delete_note.side_effect = QdrantOperationError(
            code='qdrant_unavailable',
            message='Qdrant note deletion failed.',
            retryable=True,
        )
        worker = self.worker(service)

        first = worker.process_next()
        job.refresh_from_db()

        self.assertEqual(first.outcome, 'retry')
        self.assertEqual(job.status, RagIndexDeletionJob.Status.PENDING)
        self.assertEqual(job.available_at, self.clock[0] + timedelta(seconds=5))
        self.assertEqual(job.error_message, 'qdrant_unavailable')

        service.vector_store.delete_note.side_effect = None
        self.clock[0] += timedelta(seconds=5)
        second = worker.process_next()
        job.refresh_from_db()

        self.assertEqual(second.outcome, 'deleted')
        self.assertEqual(job.attempts, 2)
        self.assertEqual(job.status, RagIndexDeletionJob.Status.COMPLETED)

    def test_retryable_deletion_is_not_abandoned_at_index_attempt_limit(self):
        job = self.create_deletion_job(attempts=2)
        service = FakeIndexingService()
        service.vector_store.delete_note.side_effect = QdrantOperationError(
            code='qdrant_unavailable',
            message='Qdrant note deletion failed.',
            retryable=True,
        )

        result = self.worker(service, max_attempts=3).process_next()

        job.refresh_from_db()
        self.assertEqual(result.outcome, 'retry')
        self.assertEqual(job.attempts, 3)
        self.assertEqual(job.status, RagIndexDeletionJob.Status.PENDING)
        self.assertEqual(job.available_at, self.clock[0] + timedelta(seconds=20))

    def test_stale_source_hash_is_skipped_and_latest_job_is_queued(self):
        stale_job = self.create_job(target_source_hash='a' * 64)

        result = self.worker().process_next()

        stale_job.refresh_from_db()
        latest = RagIndexJob.objects.get(note=self.note, status='pending')
        self.assertEqual(result.outcome, 'stale')
        self.assertEqual(stale_job.error_message, 'stale_source_hash')
        self.assertEqual(latest.target_source_hash, note_source_hash(self.note.markdown_content))

    def test_disabled_or_deleted_note_runs_index_deletion(self):
        for field, value in (('ai_indexing_enabled', False), ('is_deleted', True)):
            with self.subTest(field=field):
                RagIndexJob.objects.all().delete()
                Note.objects.filter(pk=self.note.pk).update(
                    ai_indexing_enabled=True,
                    is_deleted=False,
                )
                Note.objects.filter(pk=self.note.pk).update(**{field: value})
                self.create_job()
                service = FakeIndexingService()

                result = self.worker(service).process_next()

                self.assertEqual(result.outcome, 'deleted')
                self.assertEqual(service.delete_calls, [self.note.id])
                self.assertEqual(service.index_calls, [])

    def test_retryable_error_uses_exponential_delay_then_succeeds(self):
        job = self.create_job()
        service = FakeIndexingService(
            index_error=NoteIndexingError(
                code='qdrant_unavailable',
                message='Qdrant point upsert failed.',
                retryable=True,
            )
        )
        worker = self.worker(service)

        first = worker.process_next()
        job.refresh_from_db()

        self.assertEqual(first.outcome, 'retry')
        self.assertEqual(job.status, 'pending')
        self.assertEqual(job.attempts, 1)
        self.assertEqual(job.available_at, self.clock[0] + timedelta(seconds=5))
        self.assertIsNone(worker.process_next())

        service.index_error = None
        self.clock[0] += timedelta(seconds=5)
        second = worker.process_next()
        job.refresh_from_db()
        self.assertEqual(second.outcome, 'indexed')
        self.assertEqual(job.attempts, 2)
        self.assertEqual(job.status, 'completed')

    def test_retryable_error_at_max_attempts_is_failed(self):
        job = self.create_job(attempts=2)
        service = FakeIndexingService(
            index_error=NoteIndexingError(
                code='embedding_timeout',
                message='Embedding provider request timed out.',
                retryable=True,
            )
        )

        result = self.worker(service, max_attempts=3).process_next()

        job.refresh_from_db()
        self.assertEqual(result.outcome, 'failed')
        self.assertEqual(job.attempts, 3)
        self.assertEqual(job.status, 'failed')

    def test_non_retryable_and_unexpected_errors_are_safely_failed(self):
        errors = (
            NoteIndexingError(
                code='indexing_chunking_error',
                message='Note cannot be chunked safely.',
                retryable=False,
            ),
            RuntimeError('private dependency response'),
        )
        for error in errors:
            with self.subTest(error=type(error).__name__):
                RagIndexJob.objects.all().delete()
                job = self.create_job()
                service = FakeIndexingService(index_error=error)

                result = self.worker(service).process_next()

                job.refresh_from_db()
                self.assertEqual(result.outcome, 'failed')
                self.assertNotIn('private dependency response', job.error_message)

    def test_note_changed_error_completes_old_job_and_enqueues_latest(self):
        old_job = self.create_job()
        service = FakeIndexingService(
            index_error=NoteIndexingError(
                code='note_changed_during_indexing',
                message='Note changed during indexing.',
                retryable=True,
            )
        )

        result = self.worker(service).process_next()

        old_job.refresh_from_db()
        self.assertEqual(result.outcome, 'stale')
        self.assertEqual(old_job.status, 'completed')
        self.assertEqual(RagIndexJob.objects.filter(note=self.note, status='pending').count(), 1)

    def test_expired_worker_lease_releases_job_and_index_state(self):
        job = self.create_job(
            status=RagIndexJob.Status.INDEXING,
            attempts=1,
            started_at=self.clock[0] - timedelta(seconds=61),
        )
        state = RagIndexState.objects.create(
            note=self.note,
            status=RagIndexState.Status.INDEXING,
        )
        service = FakeIndexingService()

        result = self.worker(service, lease=60).process_next()

        job.refresh_from_db()
        state.refresh_from_db()
        self.assertEqual(result.outcome, 'indexed')
        self.assertEqual(job.attempts, 2)
        self.assertEqual(job.status, 'completed')
        self.assertEqual(state.status, 'failed')
        self.assertEqual(state.error_message, 'worker_lease_expired')

    def test_expired_lease_at_max_attempts_is_not_reclaimed(self):
        job = self.create_job(
            status=RagIndexJob.Status.INDEXING,
            attempts=3,
            started_at=self.clock[0] - timedelta(seconds=61),
        )

        result = self.worker(max_attempts=3, lease=60).process_next()

        job.refresh_from_db()
        self.assertIsNone(result)
        self.assertEqual(job.status, 'failed')
        self.assertEqual(job.error_message, 'worker_lease_expired_max_attempts')

    def test_expired_deletion_lease_is_reclaimed_and_completed(self):
        job = self.create_deletion_job(
            status=RagIndexDeletionJob.Status.INDEXING,
            attempts=1,
            started_at=self.clock[0] - timedelta(seconds=61),
        )
        service = FakeIndexingService()

        result = self.worker(service, lease=60).process_next()

        job.refresh_from_db()
        self.assertEqual(result.outcome, 'deleted')
        self.assertEqual(job.attempts, 2)
        self.assertEqual(job.status, RagIndexDeletionJob.Status.COMPLETED)


class ProcessRagJobsCommandTests(TestCase):
    @patch('rag.management.commands.process_rag_jobs.get_rag_index_worker')
    def test_command_processes_until_empty_and_closes_clients(self, get_worker):
        worker = get_worker.return_value
        worker.process_next.side_effect = [
            JobProcessResult('job-1', 1, 'indexed', 1),
            JobProcessResult('delete:2', 2, 'deleted', 1),
            JobProcessResult('job-3', 3, 'retry', 1),
            None,
        ]
        worker.indexing_service = FakeIndexingService()
        stdout = StringIO()

        call_command('process_rag_jobs', max_jobs=10, stdout=stdout)

        output = stdout.getvalue()
        self.assertIn('total=3', output)
        self.assertIn('indexed=1', output)
        self.assertIn('deleted=1', output)
        self.assertIn('retry=1', output)
        worker.indexing_service.embedding_service.close.assert_called_once_with()
        worker.indexing_service.vector_store.close.assert_called_once_with()
