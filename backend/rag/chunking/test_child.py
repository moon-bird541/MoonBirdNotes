"""子片段结构边界、向量文本、重叠和稳定哈希测试。"""

import re
from datetime import date

from django.test import SimpleTestCase

from .child import (
    ChildChunkingError,
    build_vector_text,
    markdown_to_embedding_text,
    split_child_chunks,
)
from .schemas import (
    ChildChunkConfig,
    ParentChunk,
    RagDocumentMetadata,
)


class _WhitespaceTokenCounter:
    """测试只控制边界；真实集成检查使用 BAAI/bge-m3 tokenizer。"""

    def count_tokens(self, text):
        return len(re.findall(r'\S+', text))


class RagDocumentMetadataTests(SimpleTestCase):
    def test_diary_requires_date(self):
        with self.assertRaises(ValueError):
            RagDocumentMetadata(document_type='diary', title='日记')

    def test_diary_rejects_note_tags(self):
        with self.assertRaises(ValueError):
            RagDocumentMetadata(
                document_type='diary',
                title='日记',
                diary_date=date(2026, 7, 13),
                tags=('错误标签',),
            )

    def test_note_rejects_diary_fields(self):
        with self.assertRaises(ValueError):
            RagDocumentMetadata(
                document_type='note',
                title='笔记',
                mood='平静',
            )


class ChildChunkConfigTests(SimpleTestCase):
    def test_rejects_maximum_below_target(self):
        with self.assertRaises(ValueError):
            ChildChunkConfig(target_tokens=10, max_tokens=9, overlap_tokens=2)

    def test_rejects_overlap_at_or_above_target(self):
        with self.assertRaises(ValueError):
            ChildChunkConfig(target_tokens=10, max_tokens=20, overlap_tokens=10)


class VectorTextTests(SimpleTestCase):
    def test_builds_note_vector_metadata(self):
        metadata = RagDocumentMetadata(
            document_type='note',
            title='接口规范',
            tags=('API', 'Django'),
        )

        vector_text = build_vector_text(
            metadata,
            ('接口详情', '校验接口'),
            '校验正文',
        )

        self.assertIn('类型：普通笔记', vector_text)
        self.assertIn('标题：接口规范', vector_text)
        self.assertIn('标签：API、Django', vector_text)
        self.assertIn('章节：接口详情 > 校验接口', vector_text)

    def test_builds_diary_vector_metadata(self):
        metadata = RagDocumentMetadata(
            document_type='diary',
            title='今日记录',
            diary_date=date(2026, 7, 13),
            mood='平静',
            weather='晴',
            summary='完成 RAG',
        )

        vector_text = build_vector_text(metadata, ('工作记录',), '今天完成测试。')

        self.assertIn('类型：日记', vector_text)
        self.assertIn('日期：2026-07-13', vector_text)
        self.assertIn('心情：平静', vector_text)
        self.assertIn('天气：晴', vector_text)
        self.assertIn('摘要：完成 RAG', vector_text)
        self.assertNotIn('标签：', vector_text)

    def test_embedding_text_keeps_alt_and_link_text_but_removes_paths(self):
        markdown = '![架构图](private/images/rag.png) [接口文档](https://example.com/api)'

        semantic = markdown_to_embedding_text(markdown)

        self.assertIn('架构图', semantic)
        self.assertIn('接口文档', semantic)
        self.assertNotIn('private/images/rag.png', semantic)
        self.assertNotIn('https://example.com/api', semantic)


class ChildChunkSplitterTests(SimpleTestCase):
    def setUp(self):
        self.counter = _WhitespaceTokenCounter()
        self.metadata = RagDocumentMetadata(
            document_type='note',
            title='RAG 测试',
            tags=('RAG',),
        )

    @staticmethod
    def parent(content, heading_path=('文档',)):
        return ParentChunk(
            chunk_index=0,
            heading_path=heading_path,
            content=content,
            start_line=1,
            end_line=max(1, len(content.splitlines())),
            token_count=max(1, len(content.split())),
            section_hash='a' * 64,
        )

    def split(self, content, *, target=12, maximum=18, overlap=3, heading_path=('文档',)):
        return split_child_chunks(
            self.parent(content, heading_path),
            parent_id='parent-001',
            metadata=self.metadata,
            token_counter=self.counter,
            config=ChildChunkConfig(
                target_tokens=target,
                max_tokens=maximum,
                overlap_tokens=overlap,
            ),
        )

    def test_children_keep_parent_id_order_limit_and_stable_hash(self):
        content = '第一段 one two。\n\n第二段 three four。\n\n第三段 five six。'

        first = self.split(content, target=8, maximum=12, overlap=0)
        second = self.split(content, target=8, maximum=12, overlap=0)

        self.assertEqual(first, second)
        self.assertEqual([chunk.parent_id for chunk in first], ['parent-001'] * len(first))
        self.assertEqual([chunk.chunk_index for chunk in first], list(range(len(first))))
        self.assertTrue(all(chunk.token_count <= 12 for chunk in first))
        self.assertTrue(all(len(chunk.chunk_hash) == 64 for chunk in first))

    def test_child_heading_path_tracks_specific_sibling_section(self):
        content = '## 第一节\n\n正文一\n\n## 第二节\n\n正文二'

        chunks = self.split(content, target=20, maximum=30, overlap=3)

        self.assertEqual(
            [chunk.heading_path for chunk in chunks],
            [('文档', '第一节'), ('文档', '第二节')],
        )
        self.assertTrue(all(chunk.overlap_token_count == 0 for chunk in chunks))

    def test_code_block_stays_atomic_when_it_fits(self):
        code = """```python
def add(a, b):
    return a + b
```"""

        chunks = self.split(code, target=20, maximum=30, overlap=0)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].content, code)

    def test_long_code_block_splits_by_lines_and_repeats_fence(self):
        code = """```python
line_one = one two three
line_two = four five six
line_three = seven eight nine
```"""

        chunks = self.split(code, target=8, maximum=12, overlap=0)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.content.startswith('```python') for chunk in chunks))
        self.assertTrue(all(chunk.content.endswith('```') for chunk in chunks))
        self.assertTrue(all(chunk.token_count <= 12 for chunk in chunks))

    def test_list_splits_only_between_complete_items(self):
        content = '\n'.join(
            f'- item-{index} value-{index}'
            for index in range(6)
        )

        chunks = self.split(content, target=8, maximum=11, overlap=0)

        self.assertGreater(len(chunks), 1)
        combined = '\n'.join(chunk.content for chunk in chunks)
        for index in range(6):
            self.assertEqual(combined.count(f'- item-{index} value-{index}'), 1)

    def test_oversized_single_list_item_returns_clear_error(self):
        content = '- ' + ' '.join(f'value-{index}' for index in range(20))

        with self.assertRaisesMessage(ChildChunkingError, '单个列表项'):
            self.split(content, target=7, maximum=8, overlap=0)

    def test_long_table_splits_by_rows_and_repeats_header(self):
        content = '\n'.join([
            '| 名称 | 状态 |',
            '| --- | --- |',
            *[f'| row-{index} | value-{index} |' for index in range(6)],
        ])

        chunks = self.split(content, target=8, maximum=11, overlap=0)

        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            lines = chunk.content.splitlines()
            self.assertEqual(lines[0], '| 名称 | 状态 |')
            self.assertEqual(lines[1], '| --- | --- |')
            self.assertLessEqual(chunk.token_count, 11)

    def test_oversized_single_table_row_returns_clear_error(self):
        content = '\n'.join([
            '| 名称 | 状态 |',
            '| --- | --- |',
            '| row | ' + ' '.join(f'value-{index}' for index in range(20)) + ' |',
        ])

        with self.assertRaisesMessage(ChildChunkingError, '单个表格行'):
            self.split(content, target=7, maximum=8, overlap=0)

    def test_forced_split_adds_overlap_within_same_heading(self):
        content = '\n\n'.join(
            f'paragraph-{index} one two.'
            for index in range(6)
        )

        chunks = self.split(content, target=10, maximum=15, overlap=2)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(any(chunk.overlap_token_count >= 2 for chunk in chunks[1:]))

    def test_overlap_chooses_complete_units_closest_to_target(self):
        content = '\n\n'.join(
            f'paragraph-{index} one two.'
            for index in range(6)
        )

        chunks = self.split(content, target=10, maximum=15, overlap=4)

        self.assertGreater(len(chunks), 1)
        self.assertEqual(chunks[1].overlap_token_count, 3)

    def test_chunk_hash_changes_when_vector_metadata_changes(self):
        parent = self.parent('正文 one two')
        config = ChildChunkConfig(target_tokens=10, max_tokens=20, overlap_tokens=0)
        first = split_child_chunks(
            parent,
            parent_id='parent-001',
            metadata=self.metadata,
            token_counter=self.counter,
            config=config,
        )[0]
        changed_metadata = RagDocumentMetadata(
            document_type='note',
            title='不同标题',
            tags=('RAG',),
        )
        second = split_child_chunks(
            parent,
            parent_id='parent-001',
            metadata=changed_metadata,
            token_counter=self.counter,
            config=config,
        )[0]

        self.assertNotEqual(first.chunk_hash, second.chunk_hash)

    def test_empty_parent_content_produces_no_children(self):
        parent = self.parent('')

        chunks = split_child_chunks(
            parent,
            parent_id='parent-001',
            metadata=self.metadata,
            token_counter=self.counter,
        )

        self.assertEqual(chunks, [])
