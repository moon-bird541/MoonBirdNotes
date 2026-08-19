"""BGE-M3 token 计数适配器测试。"""

from types import SimpleNamespace

from django.test import SimpleTestCase

from .tokenizer import BgeM3TokenCounter


class _FakeTokenizer:
    """模拟 tokenizer.json 已配置的两个特殊 token。"""

    def encode(self, text):
        return SimpleNamespace(ids=[0, *range(len(text.split())), 2])


class BgeM3TokenCounterTests(SimpleTestCase):
    def test_counts_model_special_tokens_from_tokenizer_result(self):
        counter = BgeM3TokenCounter(tokenizer=_FakeTokenizer())

        self.assertEqual(counter.count_tokens('Django RAG'), 4)

    def test_empty_text_has_no_chunk_tokens(self):
        counter = BgeM3TokenCounter(tokenizer=_FakeTokenizer())

        self.assertEqual(counter.count_tokens(''), 0)

    def test_rejects_non_string_input(self):
        counter = BgeM3TokenCounter(tokenizer=_FakeTokenizer())

        with self.assertRaises(TypeError):
            counter.count_tokens(None)
