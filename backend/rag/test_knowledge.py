"""Knowledge Agent 只读领域服务的当前来源与产品边界测试。"""

import hashlib
from datetime import date
from uuid import uuid4

from django.test import TestCase, override_settings
from django.utils import timezone

from notes.models import DiaryEntry, Note, Tag

from .knowledge import (
    KnowledgeReadError,
    list_knowledge_tags,
    read_current_parent_chunks,
    read_diary_by_date,
    read_note,
    read_note_section,
)
from .models import RagIndexState, RagParentChunk


@override_settings(RAG_EMBEDDING_VERSION='test-embedding-v1')
class KnowledgeReadServiceTests(TestCase):
    def setUp(self):
        self.regular_tag = Tag.objects.create(name='知识库')
        self.note = Note.objects.create(
            title='工具说明',
            source_filename='tools.md',
            markdown_content=(
                '# 工具说明\n\n导言。\n\n'
                '## 检索流程\n\n先搜索。\n\n'
                '### 来源校验\n\n必须校验哈希。\n\n'
                '## 其他章节\n\n结束。'
            ),
            rendered_html='',
        )
        self.note.tags.set([self.regular_tag])
        self.parent = self.create_parent(
            self.note,
            heading_path=['工具说明', '检索流程'],
            content='## 检索流程\n\n先搜索。',
        )

        self.diary_note = Note.objects.create(
            title='当天日记',
            markdown_content='# 当天日记\n\n完成工具测试。',
            rendered_html='',
        )
        self.diary = DiaryEntry.objects.create(
            note=self.diary_note,
            diary_date=date(2026, 7, 14),
            summary='工具完成',
            mood='平静',
            weather='晴',
        )
        self.diary_parent = self.create_parent(
            self.diary_note,
            heading_path=['当天日记'],
        )

        self.disabled_tag = Tag.objects.create(name='关闭内容')
        self.disabled_note = Note.objects.create(
            title='关闭 AI 的笔记',
            markdown_content='不应提供给 Knowledge Agent。',
            rendered_html='',
            ai_indexing_enabled=False,
        )
        self.disabled_note.tags.set([self.disabled_tag])

        self.deleted_tag = Tag.objects.create(name='回收站内容')
        self.deleted_note = Note.objects.create(
            title='回收站笔记',
            markdown_content='已删除正文。',
            rendered_html='',
            is_deleted=True,
            deleted_at=timezone.now(),
        )
        self.deleted_note.tags.set([self.deleted_tag])

    def create_parent(self, note, *, heading_path, content=None, chunk_index=0):
        source_hash = hashlib.sha256(note.markdown_content.encode('utf-8')).hexdigest()
        parent = RagParentChunk.objects.create(
            note=note,
            chunk_index=chunk_index,
            heading_path=heading_path,
            content=content or note.markdown_content,
            start_line=1,
            end_line=max(1, len(note.markdown_content.splitlines())),
            source_hash=source_hash,
            section_hash=hashlib.sha256(f'{note.id}:{chunk_index}'.encode()).hexdigest(),
            index_version=1,
        )
        RagIndexState.objects.create(
            note=note,
            source_hash=source_hash,
            embedding_model='BAAI/bge-m3',
            embedding_version='test-embedding-v1',
            index_version=1,
            status=RagIndexState.Status.COMPLETED,
        )
        return parent

    def test_reads_current_parent_chunks_in_requested_order_and_reports_missing(self):
        missing_id = str(uuid4())

        payload = read_current_parent_chunks(
            (str(self.diary_parent.pk), missing_id, str(self.parent.pk))
        )

        self.assertEqual(
            [item['parent_id'] for item in payload['chunks']],
            [str(self.diary_parent.pk), str(self.parent.pk)],
        )
        self.assertEqual(payload['chunks'][0]['type'], 'diary')
        self.assertEqual(payload['missing_parent_ids'], [missing_id])

    def test_parent_reader_rejects_only_missing_or_stale_sources(self):
        with self.assertRaises(KnowledgeReadError) as context:
            read_current_parent_chunks((str(uuid4()),))
        self.assertEqual(context.exception.code, 'parent_chunks_not_found')

        self.note.markdown_content = '已经更新但尚未重新索引。'
        self.note.save(update_fields=['markdown_content'])
        with self.assertRaises(KnowledgeReadError):
            read_current_parent_chunks((str(self.parent.pk),))

    def test_parent_reader_serves_active_version_during_or_after_rebuild_attempt(self):
        for status in (RagIndexState.Status.INDEXING, RagIndexState.Status.FAILED):
            with self.subTest(status=status):
                RagIndexState.objects.filter(note=self.note).update(status=status)

                payload = read_current_parent_chunks((str(self.parent.pk),))

                self.assertEqual(
                    [item['parent_id'] for item in payload['chunks']],
                    [str(self.parent.pk)],
                )

    def test_parent_reader_rejects_state_without_an_activated_source_hash(self):
        RagIndexState.objects.filter(note=self.note).update(
            source_hash='',
            status=RagIndexState.Status.INDEXING,
        )

        with self.assertRaises(KnowledgeReadError) as context:
            read_current_parent_chunks((str(self.parent.pk),))

        self.assertEqual(context.exception.code, 'parent_chunks_not_found')

    def test_read_note_returns_current_regular_note_and_validates_hash(self):
        payload = read_note(self.note.id)

        self.assertEqual(payload['type'], 'note')
        self.assertEqual(payload['tags'], ['知识库'])
        self.assertEqual(payload['markdown_content'], self.note.markdown_content)

        with self.assertRaises(KnowledgeReadError) as context:
            read_note(self.note.id, expected_source_hash='f' * 64)
        self.assertEqual(context.exception.code, 'source_hash_mismatch')
        self.assertEqual(context.exception.category, 'stale_source')

    def test_read_note_excludes_diary_deleted_and_ai_disabled_notes(self):
        for note in (self.diary_note, self.deleted_note, self.disabled_note):
            with self.subTest(note_id=note.id), self.assertRaises(KnowledgeReadError) as context:
                read_note(note.id)
            self.assertEqual(context.exception.code, 'note_not_found')

    def test_read_note_section_uses_exact_heading_path_and_source_lines(self):
        payload = read_note_section(
            self.note.id,
            ('工具说明', '检索流程'),
        )

        self.assertIn('### 来源校验', payload['content'])
        self.assertNotIn('## 其他章节', payload['content'])
        self.assertEqual(payload['heading_path'], ['工具说明', '检索流程'])
        self.assertLessEqual(payload['start_line'], payload['end_line'])

    def test_read_note_section_distinguishes_missing_and_ambiguous_paths(self):
        with self.assertRaises(KnowledgeReadError) as context:
            read_note_section(self.note.id, ('工具说明', '不存在'))
        self.assertEqual(context.exception.code, 'note_section_not_found')

        duplicate = Note.objects.create(
            title='重复标题',
            markdown_content='# 根\n\n## 重复\n\n一。\n\n## 重复\n\n二。',
            rendered_html='',
        )
        with self.assertRaises(KnowledgeReadError) as context:
            read_note_section(duplicate.id, ('根', '重复'))
        self.assertEqual(context.exception.code, 'note_section_ambiguous')

    def test_read_diary_by_date_returns_metadata_and_excludes_unavailable(self):
        payload = read_diary_by_date(date(2026, 7, 14))

        self.assertEqual(payload['type'], 'diary')
        self.assertEqual(payload['summary'], '工具完成')
        self.assertEqual(payload['note_id'], self.diary_note.id)

        Note.objects.filter(pk=self.diary_note.pk).update(is_deleted=True)
        with self.assertRaises(KnowledgeReadError) as context:
            read_diary_by_date(date(2026, 7, 14))
        self.assertEqual(context.exception.code, 'diary_not_found')

    def test_list_tags_counts_only_authorized_active_regular_notes(self):
        # 历史脏数据中的日记标签不能出现在 Knowledge Agent 标签列表。
        diary_only_tag = Tag.objects.create(name='日记脏标签')
        self.diary_note.tags.add(diary_only_tag)

        payload = list_knowledge_tags()
        filtered = list_knowledge_tags(query='知识', limit=1)

        self.assertEqual(payload['tags'], [
            {'id': self.regular_tag.id, 'name': '知识库', 'note_count': 1}
        ])
        self.assertEqual(filtered, payload)
