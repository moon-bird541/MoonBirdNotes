"""RAG 运行监控快照与管理命令测试。"""

import json
from datetime import datetime, timedelta, timezone as datetime_timezone
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from notes.models import Note

from .models import RagIndexDeletionJob, RagIndexJob, RagIndexState
from .monitoring import get_rag_runtime_snapshot


class RagRuntimeMonitoringTests(TestCase):
    def setUp(self):
        self.note = Note.objects.create(
            title='监控测试',
            markdown_content='# 监控测试',
            rendered_html='',
        )

    def create_job(self, status):
        return RagIndexJob.objects.create(
            note=self.note,
            target_source_hash='a' * 64,
            reason=f'monitor_{status}',
            status=status,
        )

    def test_snapshot_counts_backlog_failure_rate_and_oldest_pending_age(self):
        now = datetime(2026, 7, 14, 12, 0, tzinfo=datetime_timezone.utc)
        pending = self.create_job(RagIndexJob.Status.PENDING)
        self.create_job(RagIndexJob.Status.INDEXING)
        self.create_job(RagIndexJob.Status.COMPLETED)
        self.create_job(RagIndexJob.Status.FAILED)
        RagIndexDeletionJob.objects.create(
            note_id=self.note.id + 1000,
            status=RagIndexDeletionJob.Status.PENDING,
        )
        RagIndexJob.objects.filter(pk=pending.pk).update(
            created_at=now - timedelta(seconds=90)
        )
        RagIndexState.objects.create(
            note=self.note,
            status=RagIndexState.Status.FAILED,
        )

        snapshot = get_rag_runtime_snapshot(now=now)

        self.assertEqual(snapshot.backlog_count, 3)
        self.assertEqual(snapshot.deletion_backlog_count, 1)
        self.assertEqual(snapshot.failed_job_rate, 0.5)
        self.assertEqual(snapshot.oldest_pending_age_seconds, 90.0)
        self.assertEqual(snapshot.job_counts['pending'], 1)
        self.assertEqual(snapshot.deletion_job_counts['pending'], 1)
        self.assertEqual(snapshot.state_counts['failed'], 1)

    def test_status_command_outputs_only_aggregate_json(self):
        self.create_job(RagIndexJob.Status.PENDING)
        output = StringIO()

        call_command('rag_status', stdout=output)

        payload = json.loads(output.getvalue())
        self.assertEqual(payload['backlog_count'], 1)
        self.assertIn('failed_job_rate', payload)
        self.assertNotIn('error_message', payload)
        self.assertNotIn('markdown_content', payload)
