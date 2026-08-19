"""Markdown 结构解析器的成功路径与边界测试。"""

from django.test import SimpleTestCase

from .parser import parse_markdown


class MarkdownParserTests(SimpleTestCase):
    def test_parses_heading_levels_one_through_six(self):
        markdown = '\n'.join(f'{"#" * level} 标题 {level}' for level in range(1, 7))

        blocks = parse_markdown(markdown)

        self.assertEqual([block.block_type for block in blocks], ['heading'] * 6)
        self.assertEqual([block.heading_level for block in blocks], list(range(1, 7)))
        self.assertEqual([block.start_line for block in blocks], list(range(1, 7)))

    def test_preserves_fenced_code_and_language_markers(self):
        markdown = """```python
print('ok')
```

~~~javascript
console.log('ok')
~~~"""

        blocks = parse_markdown(markdown)

        self.assertEqual([block.block_type for block in blocks], ['code_fence', 'code_fence'])
        self.assertEqual(blocks[0].content, "```python\nprint('ok')\n```")
        self.assertEqual(blocks[1].content, "~~~javascript\nconsole.log('ok')\n~~~")
        self.assertEqual((blocks[0].start_line, blocks[0].end_line), (1, 3))

    def test_inline_code_and_link_remain_in_paragraph_source(self):
        markdown = '使用 `Note.save()`，参考 [Django 文档](https://docs.djangoproject.com/)。'

        blocks = parse_markdown(markdown)

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].block_type, 'paragraph')
        self.assertEqual(blocks[0].content, markdown)

    def test_groups_ordered_and_unordered_lists_as_top_level_blocks(self):
        markdown = """- 第一项
- 第二项

1. 步骤一
2. 步骤二"""

        blocks = parse_markdown(markdown)

        self.assertEqual([block.block_type for block in blocks], ['list', 'list'])
        self.assertIn('- 第二项', blocks[0].content)
        self.assertIn('2. 步骤二', blocks[1].content)

    def test_groups_blockquote_as_one_top_level_block(self):
        markdown = '> 第一行\n>\n> 第二行'

        blocks = parse_markdown(markdown)

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].block_type, 'blockquote')
        self.assertEqual(blocks[0].content, markdown)

    def test_recognizes_table_and_preserves_separator_row(self):
        markdown = """| 名称 | 状态 |
| --- | --- |
| RAG | 完成 |"""

        blocks = parse_markdown(markdown)

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].block_type, 'table')
        self.assertIn('| --- | --- |', blocks[0].content)

    def test_recognizes_standalone_image_but_not_inline_image(self):
        markdown = """[![架构图](images/rag.png)](https://example.com/rag)

正文中的 ![图标](images/icon.png) 不能与句子拆开。"""

        blocks = parse_markdown(markdown)

        self.assertEqual([block.block_type for block in blocks], ['image', 'paragraph'])
        self.assertIn('images/rag.png', blocks[0].content)
        self.assertIn('images/icon.png', blocks[1].content)

    def test_recognizes_horizontal_rule(self):
        block = parse_markdown('---')[0]

        self.assertEqual(block.block_type, 'horizontal_rule')
        self.assertEqual(block.content, '---')

    def test_empty_section_is_represented_by_adjacent_headings(self):
        markdown = '## 空章节\n\n## 下一节\n\n正文'

        blocks = parse_markdown(markdown)

        self.assertEqual([block.block_type for block in blocks], ['heading', 'heading', 'paragraph'])
        self.assertEqual([block.start_line for block in blocks], [1, 3, 5])

    def test_headingless_note_falls_back_to_paragraph(self):
        blocks = parse_markdown('没有标题的笔记正文。')

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].block_type, 'paragraph')
        self.assertIsNone(blocks[0].heading_level)

    def test_unclosed_fence_is_preserved_as_code_block(self):
        markdown = '```python\nprint("未闭合")'

        blocks = parse_markdown(markdown)

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].block_type, 'code_fence')
        self.assertEqual(blocks[0].content, markdown)

    def test_incomplete_inline_markdown_remains_a_paragraph(self):
        markdown = '这是 **尚未闭合的加粗和 [链接](https://example.com'

        blocks = parse_markdown(markdown)

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].content, markdown)

    def test_reference_link_definition_is_not_dropped(self):
        markdown = '[查看文档][docs]\n\n[docs]: https://example.com/api/v1'

        blocks = parse_markdown(markdown)

        self.assertEqual([block.start_line for block in blocks], [1, 3])
        self.assertEqual(blocks[1].block_type, 'paragraph')
        self.assertIn('https://example.com/api/v1', blocks[1].content)

    def test_same_input_produces_equal_block_sequence(self):
        markdown = '# 标题\n\n正文\n\n- A\n- B'

        self.assertEqual(parse_markdown(markdown), parse_markdown(markdown))

    def test_empty_markdown_produces_no_blocks(self):
        self.assertEqual(parse_markdown(''), [])
