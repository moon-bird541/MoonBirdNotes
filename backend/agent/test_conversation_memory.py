"""六轮完整上下文和更早问答滚动摘要测试。"""

import json
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase

from agent.llm import ChatCompletion

from .conversation_memory import refresh_conversation_memory
from .conversation_store import build_persisted_history
from .models import KnowledgeConversation, KnowledgeConversationTurn


class FakeSummaryModel:
    def __init__(self, summaries):
        self.summaries = list(summaries)
        self.calls = []

    def complete(self, messages, *, tools=()):
        self.calls.append(messages)
        value = self.summaries.pop(0)
        payload = value if isinstance(value, dict) else {
            'summary': value,
            'entities': [],
            'decisions': [],
            'constraints': [],
            'open_items': [],
        }
        return ChatCompletion(
            content=json.dumps(payload, ensure_ascii=False),
            tool_calls=(),
            finish_reason='stop',
        )


class ConversationMemoryTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username='memory-admin',
            password='strong-password',
        )
        self.conversation = KnowledgeConversation.objects.create(
            user=self.user,
            title='六轮记忆测试',
        )

    def create_turn(self, index):
        return KnowledgeConversationTurn.objects.create(
            conversation=self.conversation,
            run_id=uuid4(),
            question=f'问题 {index}',
            answer=f'回答 {index}',
            status=KnowledgeConversationTurn.Status.COMPLETED,
        )

    def test_recent_six_turns_remain_complete_and_older_turns_are_incrementally_summarized(self):
        for index in range(1, 8):
            self.create_turn(index)
        model = FakeSummaryModel(['问题 1 与回答 1 的关键摘要'])

        compressed = refresh_conversation_memory(
            self.conversation,
            chat_model=model,
        )
        self.conversation.refresh_from_db()
        history = build_persisted_history(self.conversation)

        self.assertTrue(compressed)
        self.assertEqual(self.conversation.summarized_turn_count, 1)
        self.assertIn('问题 1', self.conversation.memory_summary)
        self.assertEqual(len(history), 12)
        self.assertEqual(history[0], {'role': 'user', 'content': '问题 2'})
        self.assertEqual(history[-1], {'role': 'assistant', 'content': '回答 7'})

        self.create_turn(8)
        second_model = FakeSummaryModel(['问题 1 至问题 2 的合并关键摘要'])
        self.assertTrue(refresh_conversation_memory(
            self.conversation,
            chat_model=second_model,
        ))
        self.conversation.refresh_from_db()
        payload = json.loads(second_model.calls[0][1]['content'])
        self.assertEqual(self.conversation.summarized_turn_count, 2)
        self.assertIn('问题 1 与回答 1 的关键摘要', payload['existing_summary'])
        self.assertEqual(payload['new_turns'], [{'question': '问题 2', 'answer': '回答 2'}])

    def test_missing_critical_anchor_retries_before_writing_summary(self):
        KnowledgeConversationTurn.objects.create(
            conversation=self.conversation,
            run_id=uuid4(),
            question='扣费接口是什么？',
            answer='使用 /api/tool/consume，错误码 INTEGRAL_NOT_ENOUGH，2026-07-16 上线。',
            status=KnowledgeConversationTurn.Status.COMPLETED,
        )
        for index in range(2, 8):
            self.create_turn(index)
        model = FakeSummaryModel([
            {
                'summary': '扣费接口已经确定。',
                'entities': [],
                'decisions': [],
                'constraints': [],
                'open_items': [],
            },
            {
                'summary': '扣费接口使用 /api/tool/consume，错误码 INTEGRAL_NOT_ENOUGH，2026-07-16 上线。',
                'entities': ['/api/tool/consume', 'INTEGRAL_NOT_ENOUGH', '2026-07-16'],
                'decisions': [],
                'constraints': [],
                'open_items': [],
            },
        ])

        self.assertTrue(refresh_conversation_memory(self.conversation, chat_model=model))
        self.conversation.refresh_from_db()
        retry_payload = json.loads(model.calls[1][1]['content'])

        self.assertEqual(len(model.calls), 2)
        self.assertIn('/api/tool/consume', retry_payload['required_anchors'])
        self.assertIn('INTEGRAL_NOT_ENOUGH', self.conversation.memory_summary)
        self.assertIn('2026-07-16', self.conversation.memory_summary)

    def test_two_invalid_summaries_keep_previous_memory_and_progress(self):
        for index in range(1, 8):
            self.create_turn(index)
        self.conversation.memory_summary = '旧摘要'
        self.conversation.summarized_turn_count = 0
        self.conversation.save(update_fields=('memory_summary', 'summarized_turn_count'))
        model = FakeSummaryModel([
            {'summary': '遗漏数字', 'entities': [], 'decisions': [], 'constraints': [], 'open_items': []},
            {'summary': '仍然遗漏', 'entities': [], 'decisions': [], 'constraints': [], 'open_items': []},
        ])

        self.assertFalse(refresh_conversation_memory(self.conversation, chat_model=model))
        self.conversation.refresh_from_db()

        self.assertEqual(self.conversation.memory_summary, '旧摘要')
        self.assertEqual(self.conversation.summarized_turn_count, 0)
