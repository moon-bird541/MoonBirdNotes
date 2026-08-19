"""父片段标题路径、合并、超限切分和确定性测试。"""

import re

from django.test import SimpleTestCase

from .parent import split_parent_chunks
from .schemas import ParentChunkConfig


class _WhitespaceTokenCounter:
    """测试只控制 token 边界；生产代码使用 BAAI/bge-m3 tokenizer。"""

    def count_tokens(self, text):
        return len(re.findall(r'\S+', text))


class ParentChunkConfigTests(SimpleTestCase):
    def test_rejects_non_positive_target(self):
        with self.assertRaises(ValueError):
            ParentChunkConfig(target_tokens=0, max_tokens=10)

    def test_rejects_maximum_below_target(self):
        with self.assertRaises(ValueError):
            ParentChunkConfig(target_tokens=10, max_tokens=9)


class ParentChunkSplitterTests(SimpleTestCase):
    def setUp(self):
        self.counter = _WhitespaceTokenCounter()

    def split(self, markdown, *, target=4, maximum=20):
        return split_parent_chunks(
            markdown,
            token_counter=self.counter,
            config=ParentChunkConfig(
                target_tokens=target,
                max_tokens=maximum,
            ),
        )

    def test_requires_explicit_model_token_counter(self):
        with self.assertRaises(TypeError):
            split_parent_chunks('正文')

    def test_maintains_full_heading_path(self):
        markdown = """# 项目

总览

## API

接口说明

### 认证

认证说明"""

        chunks = self.split(markdown, target=2, maximum=20)

        self.assertEqual(
            [chunk.heading_path for chunk in chunks],
            [('项目',), ('项目', 'API'), ('项目', 'API', '认证')],
        )

    def test_heading_path_uses_visible_inline_text(self):
        chunks = self.split('# **项目** [文档](https://example.com)\n\n正文')

        self.assertEqual(chunks[0].heading_path, ('项目 文档',))

    def test_merges_adjacent_short_siblings_under_same_parent(self):
        markdown = """# 文档

## 第一节

甲

## 第二节

乙"""

        chunks = self.split(markdown, target=10, maximum=20)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].heading_path, ('文档',))
        self.assertIn('## 第一节', chunks[0].content)
        self.assertIn('## 第二节', chunks[0].content)

    def test_does_not_merge_short_sections_from_different_top_level_headings(self):
        markdown = """# A

## 第一节

甲

# B

## 第二节

乙"""

        chunks = self.split(markdown, target=20, maximum=40)

        self.assertEqual(len(chunks), 2)
        self.assertEqual([chunk.heading_path[0] for chunk in chunks], ['A', 'B'])

    def test_splits_long_section_by_top_level_blocks(self):
        markdown = """# 标题

one two three four

five six seven eight

nine ten eleven twelve"""

        chunks = self.split(markdown, target=4, maximum=7)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.token_count <= 7 for chunk in chunks))
        self.assertEqual([chunk.chunk_index for chunk in chunks], list(range(len(chunks))))

    def test_long_section_prefers_internal_heading_boundary(self):
        markdown = """## 主节

one two three four five

#### 内部

six seven eight nine ten"""

        chunks = self.split(markdown, target=5, maximum=9)

        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].heading_path, ('主节',))
        self.assertEqual(chunks[1].heading_path, ('主节', '内部'))
        self.assertTrue(chunks[1].content.startswith('#### 内部'))

    def test_oversized_single_line_uses_token_checked_fallback(self):
        markdown = ' '.join(f'token-{index}' for index in range(20))

        chunks = self.split(markdown, target=3, maximum=5)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.token_count <= 5 for chunk in chunks))
        self.assertEqual(''.join(chunk.content for chunk in chunks), markdown)

    def test_long_single_paragraph_keeps_heading_with_first_fragment(self):
        markdown = '# 标题\n\n' + ' '.join(f'token-{index}' for index in range(20))

        chunks = self.split(markdown, target=4, maximum=7)

        self.assertTrue(chunks[0].content.startswith('# 标题\n\n'))
        self.assertGreater(chunks[0].token_count, 2)
        self.assertTrue(all(chunk.token_count <= 7 for chunk in chunks))

    def test_headingless_note_has_empty_heading_path(self):
        chunks = self.split('没有标题的正文内容', target=2, maximum=10)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].heading_path, ())

    def test_line_ranges_remain_in_source_order(self):
        markdown = '# 标题\n\n第一段\n\n第二段\n\n第三段'

        chunks = self.split(markdown, target=2, maximum=3)

        self.assertEqual(
            [chunk.start_line for chunk in chunks],
            sorted(chunk.start_line for chunk in chunks),
        )
        self.assertTrue(all(chunk.start_line <= chunk.end_line for chunk in chunks))

    def test_same_input_produces_stable_order_and_hashes(self):
        markdown = '# 标题\n\n正文一\n\n正文二'

        first = self.split(markdown, target=2, maximum=4)
        second = self.split(markdown, target=2, maximum=4)

        self.assertEqual(first, second)
        self.assertTrue(all(len(chunk.section_hash) == 64 for chunk in first))

    def test_empty_markdown_produces_no_parent_chunks(self):
        self.assertEqual(self.split(''), [])
