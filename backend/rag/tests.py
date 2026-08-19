from django.apps import apps
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase

from notes.models import Note

from .models import RagIndexDeletionJob, RagIndexJob, RagIndexState, RagParentChunk


class RagAppConfigTests(SimpleTestCase):
    """确认 RAG App 使用显式 AppConfig 注册。"""

    def test_rag_app_is_registered(self):
        app_config = apps.get_app_config('rag')

        self.assertEqual(app_config.name, 'rag')


class RagModelTests(TestCase):
    """在真实数据库约束层验证 RAG 派生数据的关键不变量。"""

    def setUp(self):
        self.note = Note.objects.create(
            title='RAG 测试笔记',
            markdown_content='# 标题\n\n正文',
            rendered_html='<h1>标题</h1><p>正文</p>',
        )

    def create_parent_chunk(self, **overrides):
        """创建默认合法父片段，并允许单个测试只覆盖关心的字段。"""

        values = {
            'note': self.note,
            'chunk_index': 0,
            'heading_path': ['标题'],
            'content': '# 标题\n\n正文',
            'start_line': 1,
            'end_line': 3,
            'source_hash': 'a' * 64,
            'section_hash': 'b' * 64,
            'index_version': 1,
        }
        values.update(overrides)
        return RagParentChunk.objects.create(**values)

    def test_deleting_note_cascades_all_rag_records(self):
        note_id = self.note.id
        self.create_parent_chunk()
        RagIndexState.objects.create(note=self.note, source_hash='a' * 64)
        RagIndexJob.objects.create(
            note=self.note,
            target_source_hash='a' * 64,
            reason='note_saved',
        )

        self.note.delete()

        self.assertEqual(RagParentChunk.objects.count(), 0)
        self.assertEqual(RagIndexState.objects.count(), 0)
        self.assertEqual(RagIndexJob.objects.count(), 0)
        deletion_job = RagIndexDeletionJob.objects.get(note_id=note_id)
        self.assertEqual(deletion_job.status, RagIndexDeletionJob.Status.PENDING)

    def test_note_can_have_only_one_index_state(self):
        RagIndexState.objects.create(note=self.note, source_hash='a' * 64)

        with self.assertRaises(IntegrityError), transaction.atomic():
            RagIndexState.objects.create(note=self.note, source_hash='b' * 64)

    def test_parent_chunk_index_is_unique_per_note_and_version(self):
        self.create_parent_chunk()

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_parent_chunk(section_hash='c' * 64)

    def test_parent_chunk_rejects_reversed_line_range(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_parent_chunk(start_line=4, end_line=3)

    def test_index_state_rejects_unknown_status(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            RagIndexState.objects.create(
                note=self.note,
                source_hash='a' * 64,
                status='unknown',
            )

    def test_same_source_can_be_reindexed_for_a_different_reason(self):
        # 正文不变时，模型或分块规则变化仍需要创建新的索引任务。
        RagIndexJob.objects.create(
            note=self.note,
            target_source_hash='a' * 64,
            reason='note_saved',
        )
        RagIndexJob.objects.create(
            note=self.note,
            target_source_hash='a' * 64,
            reason='embedding_model_changed',
        )

        self.assertEqual(RagIndexJob.objects.count(), 2)
