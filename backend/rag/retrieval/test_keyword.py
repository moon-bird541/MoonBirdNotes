"""MySQL 关键词检索的字段覆盖、范围边界和结构化候选测试。"""

import hashlib
from datetime import date

from django.test import TestCase
from django.utils import timezone

from notes.models import DiaryEntry, Note, Tag
from rag.models import RagIndexState, RagParentChunk

from .keyword import KeywordSearchError, _section_specificity, search_keywords


class KeywordSearchTests(TestCase):
    def setUp(self):
        self.api_tag = Tag.objects.create(name='支付API')
        self.note = Note.objects.create(
            title='订单校验设计',
            source_filename='billing_service.py.md',
            markdown_content=(
                '# 接口详情\n\n'
                'POST /api/orders/verify/ 由 OrderVerifier 处理，失败返回 ERR_QUOTA_409。'
            ),
            rendered_html='',
        )
        self.note.tags.set([self.api_tag])

        self.diary_note = Note.objects.create(
            title='发布日记',
            markdown_content='# 工作记录\n\n今天处理 Python 发布流程。',
            rendered_html='',
        )
        self.diary = DiaryEntry.objects.create(
            note=self.diary_note,
            diary_date=date(2026, 7, 14),
            summary='完成检索服务',
            mood='平静',
            weather='晴',
        )

        self.shared_note = Note.objects.create(
            title='Python 普通笔记',
            markdown_content='普通笔记正文',
            rendered_html='',
        )
        self.deleted_note = Note.objects.create(
            title='删除后的 Python 内容',
            markdown_content='不应被检索',
            rendered_html='',
            is_deleted=True,
            deleted_at=timezone.now(),
        )
        self.disabled_note = Note.objects.create(
            title='仅本地关键词',
            markdown_content='LOCAL_ONLY_TOKEN',
            rendered_html='',
            ai_indexing_enabled=False,
        )

    def _create_current_parent(self, note, *, content=None, heading_path=None):
        source_hash = hashlib.sha256(note.markdown_content.encode('utf-8')).hexdigest()
        parent = RagParentChunk.objects.create(
            note=note,
            chunk_index=0,
            heading_path=heading_path or ['接口详情'],
            content=content or note.markdown_content,
            start_line=1,
            end_line=max(1, len(note.markdown_content.splitlines())),
            source_hash=source_hash,
            section_hash='a' * 64,
            index_version=1,
        )
        RagIndexState.objects.create(
            note=note,
            source_hash=source_hash,
            embedding_model='BAAI/bge-m3',
            embedding_version='test-v1',
            index_version=1,
            status=RagIndexState.Status.COMPLETED,
        )
        return parent

    def test_note_scope_searches_all_required_note_fields(self):
        queries = ('订单校验', 'OrderVerifier', 'billing_service.py.md', '支付API')

        for query in queries:
            with self.subTest(query=query):
                results = search_keywords(query, types=('note',))

                self.assertEqual([item.note_id for item in results], [self.note.id])
                self.assertEqual(results[0].document_type, 'note')

    def test_diary_scope_searches_all_required_diary_fields(self):
        queries = ('发布日记', '发布流程', '2026-07', '检索服务', '平静', '晴')

        for query in queries:
            with self.subTest(query=query):
                results = search_keywords(query, types=('diary',))

                self.assertEqual([item.note_id for item in results], [self.diary_note.id])
                self.assertEqual(results[0].diary_date, date(2026, 7, 14))

    def test_note_scope_excludes_diaries_but_global_scope_includes_both(self):
        note_results = search_keywords('Python', types=('note',))
        global_results = search_keywords('Python')

        self.assertEqual({item.note_id for item in note_results}, {self.shared_note.id})
        self.assertEqual(
            {item.note_id for item in global_results},
            {self.shared_note.id, self.diary_note.id},
        )

    def test_deleted_notes_are_excluded_but_local_search_ignores_cloud_permission(self):
        deleted_results = search_keywords('删除后的 Python')
        disabled_results = search_keywords('LOCAL_ONLY_TOKEN', types=('note',))

        self.assertEqual(deleted_results, ())
        self.assertEqual([item.note_id for item in disabled_results], [self.disabled_note.id])

    def test_exact_technical_identifiers_are_preserved_in_excerpts(self):
        identifiers = (
            '/api/orders/verify/',
            'OrderVerifier',
            'billing_service.py.md',
            'ERR_QUOTA_409',
        )

        for identifier in identifiers:
            with self.subTest(identifier=identifier):
                candidate = search_keywords(identifier, types=('note',))[0]

                self.assertIn(identifier, candidate.matched_excerpt)
                self.assertGreater(candidate.score, 0)

    def test_candidate_uses_current_parent_and_json_friendly_shape(self):
        parent = self._create_current_parent(self.note)

        candidate = search_keywords('OrderVerifier', types=('note',))[0]
        payload = candidate.as_dict()

        self.assertEqual(candidate.parent_id, str(parent.pk))
        self.assertEqual(candidate.heading_path, ('接口详情',))
        self.assertEqual(candidate.source_hash, parent.source_hash)
        self.assertEqual(payload['type'], 'note')
        self.assertEqual(payload['heading_path'], ['接口详情'])
        self.assertIn('markdown_content', payload['matched_fields'])

    def test_stale_parent_is_not_returned_as_current_source(self):
        self._create_current_parent(self.note)
        self.note.markdown_content = '# 新内容\n\nNEW_CURRENT_TOKEN'
        self.note.save(update_fields=['markdown_content'])

        candidate = search_keywords('NEW_CURRENT_TOKEN', types=('note',))[0]

        self.assertIsNone(candidate.parent_id)
        self.assertEqual(candidate.heading_path, ('新内容',))
        self.assertIn('NEW_CURRENT_TOKEN', candidate.content)
        self.assertEqual(
            candidate.source_hash,
            hashlib.sha256(self.note.markdown_content.encode('utf-8')).hexdigest(),
        )

    def test_natural_language_terms_select_the_relevant_current_parent(self):
        content = (
            '# 系统说明\n\n本节只介绍部署方式。\n\n'
            '# 接口统计\n\nSaaS 平台提供五个核心接口。'
        )
        note = Note.objects.create(title='平台规范', markdown_content=content, rendered_html='')
        source_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
        first = RagParentChunk.objects.create(
            note=note,
            chunk_index=0,
            heading_path=['系统说明'],
            content='# 系统说明\n\n本节只介绍部署方式。',
            start_line=1,
            end_line=3,
            source_hash=source_hash,
            section_hash='b' * 64,
            index_version=1,
        )
        second = RagParentChunk.objects.create(
            note=note,
            chunk_index=1,
            heading_path=['接口统计'],
            content='# 接口统计\n\nSaaS 平台提供五个核心接口。',
            start_line=5,
            end_line=7,
            source_hash=source_hash,
            section_hash='c' * 64,
            index_version=1,
        )
        RagIndexState.objects.create(
            note=note,
            source_hash=source_hash,
            embedding_model='BAAI/bge-m3',
            embedding_version='test-v1',
            index_version=1,
            status=RagIndexState.Status.COMPLETED,
        )

        candidate = search_keywords('请问 SaaS 平台的接口有几个？', types=('note',))[0]

        self.assertNotEqual(candidate.parent_id, str(first.pk))
        self.assertEqual(candidate.parent_id, str(second.pk))
        self.assertEqual(candidate.heading_path, ('接口统计',))
        self.assertIn('五个核心接口', candidate.matched_excerpt)

    def test_section_tie_break_prefers_complete_query_wording(self):
        terms = (
            'PyInstaller 打包命令和输出',
            'PyInstaller',
            '打包',
            '命令和输出',
        )
        partial = _section_specificity(
            'PyInstaller 用于打包 Windows 程序。',
            terms,
        )
        complete = _section_specificity(
            'PyInstaller 打包命令如下，并说明输出目录。',
            terms,
        )

        self.assertGreater(complete, partial)

    def test_note_without_active_parent_returns_the_matching_temporary_section(self):
        note = Note.objects.create(
            title='待索引规范',
            markdown_content=(
                '# 无关章节\n\n这里只介绍部署。\n\n'
                '# 当前接口\n\nPENDING_SECTION_TOKEN 位于当前正文。'
            ),
            rendered_html='',
        )
        RagIndexState.objects.create(note=note, status=RagIndexState.Status.PENDING)

        candidate = search_keywords('PENDING_SECTION_TOKEN', types=('note',))[0]

        self.assertIsNone(candidate.parent_id)
        self.assertEqual(candidate.heading_path, ('当前接口',))
        self.assertEqual(candidate.start_line, 5)
        self.assertEqual(candidate.end_line, 7)
        self.assertIn('PENDING_SECTION_TOKEN', candidate.content)

    def test_active_parent_remains_readable_during_or_after_rebuild_attempt(self):
        parent = self._create_current_parent(self.note)

        for status in (RagIndexState.Status.INDEXING, RagIndexState.Status.FAILED):
            with self.subTest(status=status):
                RagIndexState.objects.filter(note=self.note).update(status=status)

                candidate = search_keywords('OrderVerifier', types=('note',))[0]

                self.assertEqual(candidate.parent_id, str(parent.pk))

    def test_parent_without_an_activated_source_hash_is_not_readable(self):
        self._create_current_parent(self.note)
        RagIndexState.objects.filter(note=self.note).update(
            source_hash='',
            status=RagIndexState.Status.INDEXING,
        )

        candidate = search_keywords('OrderVerifier', types=('note',))[0]

        self.assertIsNone(candidate.parent_id)

    def test_exact_title_ranks_before_body_match_and_limit_is_applied(self):
        body_match = Note.objects.create(
            title='其他主题',
            markdown_content='正文包含 UNIQUE_RANK_TOKEN',
            rendered_html='',
        )
        title_match = Note.objects.create(
            title='UNIQUE_RANK_TOKEN',
            markdown_content='无关正文',
            rendered_html='',
        )

        results = search_keywords('UNIQUE_RANK_TOKEN', types=('note',), limit=1)

        self.assertEqual([item.note_id for item in results], [title_match.id])
        self.assertNotEqual(results[0].note_id, body_match.id)
        self.assertEqual(results[0].score, 1.0)

    def test_invalid_inputs_return_stable_error_codes(self):
        invalid_cases = (
            ({'query': '   '}, 'keyword_query_empty'),
            ({'query': 'x' * 501}, 'keyword_query_too_long'),
            ({'query': 'x', 'types': ()}, 'keyword_types_invalid'),
            ({'query': 'x', 'types': ('unknown',)}, 'keyword_types_invalid'),
            ({'query': 'x', 'limit': 0}, 'keyword_limit_invalid'),
            ({'query': 'x', 'limit': 101}, 'keyword_limit_invalid'),
        )

        for kwargs, expected_code in invalid_cases:
            with self.subTest(expected_code=expected_code), self.assertRaises(
                KeywordSearchError
            ) as context:
                search_keywords(**kwargs)
            self.assertEqual(context.exception.code, expected_code)

    def test_tag_filter_requires_all_tags_and_excludes_diaries(self):
        django_tag = Tag.objects.create(name='Django')
        self.note.tags.add(django_tag)

        results = search_keywords(
            '订单校验',
            tags=('支付API', 'Django'),
        )

        self.assertEqual([item.note_id for item in results], [self.note.id])
        self.assertEqual(search_keywords('发布日记', tags=('支付API',)), ())

    def test_date_filter_limits_results_to_matching_diaries(self):
        in_range = search_keywords(
            '发布日记',
            date_from=date(2026, 7, 1),
            date_to=date(2026, 7, 31),
        )
        out_of_range = search_keywords(
            '发布日记',
            date_from=date(2026, 8, 1),
        )

        self.assertEqual([item.note_id for item in in_range], [self.diary_note.id])
        self.assertEqual(out_of_range, ())
