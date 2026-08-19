"""Knowledge Agent 脱敏运行轨迹的存储、隔离与 API 测试。"""

from datetime import datetime, timedelta
from uuid import uuid4
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from agent.agents.knowledge import KnowledgeAgentLlmUsage, KnowledgeAgentResult
from agent.models import AgentTokenUsage
from agent.tracing import finish_run_trace, get_run_trace, start_run_trace, trace_event


@override_settings(AGENT_KNOWLEDGE_CHAT_RATE='1000/minute')
class RunTraceTests(TestCase):
    def setUp(self):
        cache.clear()
        user_model = get_user_model()
        self.admin = user_model.objects.create_superuser('trace-admin', password='password')
        self.other_admin = user_model.objects.create_superuser(
            'other-trace-admin', password='password'
        )
        self.client = APIClient()

    def tearDown(self):
        cache.clear()

    def create_usage(self, *, created_at, prompt_tokens, completion_tokens):
        return AgentTokenUsage.objects.create(
            user=self.admin,
            run_id=uuid4(),
            request_count=1,
            usage_reported_request_count=1,
            usage_status=AgentTokenUsage.UsageStatus.AVAILABLE,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            duration_ms=100,
            http_status=200,
            created_at=created_at,
        )

    def test_trace_is_saved_for_owner_without_sensitive_content(self):
        run_id = str(uuid4())
        token = start_run_trace(run_id, user_id=self.admin.pk)
        trace_event('agent.started', message_length=18)
        trace_event('agent.completed', source_count=1)
        finish_run_trace(token, http_status=200)

        payload = get_run_trace(run_id, user_id=self.admin.pk)

        self.assertEqual(payload['http_status'], 200)
        self.assertEqual([event['stage'] for event in payload['events']], [
            'agent.started',
            'agent.completed',
        ])
        serialized = repr(payload)
        for secret in ('用户问题正文', '模型完整回答', 'sk-test-secret'):
            self.assertNotIn(secret, serialized)
        self.assertFalse(AgentTokenUsage.objects.filter(run_id=run_id).exists())

    def test_trace_finish_persists_token_usage_without_conversation_dependency(self):
        run_id = str(uuid4())
        token = start_run_trace(run_id, user_id=self.admin.pk)
        trace_event(
            'agent.completed',
            llm_request_count=2,
            llm_usage_reported_request_count=2,
            llm_usage_status='available',
            llm_prompt_tokens=100,
            llm_completion_tokens=25,
            llm_total_tokens=125,
        )

        finish_run_trace(token, http_status=200)

        usage = AgentTokenUsage.objects.get(run_id=run_id)
        self.assertEqual(usage.user, self.admin)
        self.assertEqual(usage.request_count, 2)
        self.assertEqual(usage.total_tokens, 125)
        self.assertEqual(usage.http_status, 200)

        token = start_run_trace(run_id, user_id=self.admin.pk)
        trace_event(
            'agent.completed',
            llm_request_count=1,
            llm_usage_reported_request_count=1,
            llm_usage_status='available',
            llm_prompt_tokens=120,
            llm_completion_tokens=30,
            llm_total_tokens=150,
        )
        finish_run_trace(token, http_status=200)

        usage.refresh_from_db()
        self.assertEqual(AgentTokenUsage.objects.filter(run_id=run_id).count(), 1)
        self.assertEqual(usage.total_tokens, 150)

    def test_trace_is_hidden_from_other_user_and_missing_cache(self):
        run_id = str(uuid4())
        token = start_run_trace(run_id, user_id=self.admin.pk)
        finish_run_trace(token, http_status=200)

        self.assertIsNone(get_run_trace(run_id, user_id=self.other_admin.pk))
        cache.clear()
        self.assertIsNone(get_run_trace(run_id, user_id=self.admin.pk))

    @patch('agent.views.refresh_conversation_memory', return_value=False)
    @patch('agent.views.run_knowledge_agent')
    def test_run_list_is_isolated_and_contains_no_conversation_content(
        self, run_agent, _refresh_memory
    ):
        run_agent.return_value = KnowledgeAgentResult(
            answer='不应进入运行列表的回答',
            sources=(),
            insufficient_context=True,
            tool_steps=0,
            llm_usage=KnowledgeAgentLlmUsage(
                request_count=2,
                usage_reported_request_count=2,
                usage_status='available',
                prompt_tokens=100,
                completion_tokens=25,
                total_tokens=125,
            ),
        )
        self.client.force_authenticate(user=self.admin)
        chat_response = self.client.post(
            '/api/agent/knowledge/chat/',
            {'message': '不应进入运行列表的问题'},
            format='json',
        )
        token = start_run_trace(chat_response.data['run_id'], user_id=self.admin.pk)
        trace_event(
            'agent.completed',
            llm_request_count=2,
            llm_usage_reported_request_count=2,
            llm_usage_status='available',
            llm_prompt_tokens=100,
            llm_completion_tokens=25,
            llm_total_tokens=125,
        )
        finish_run_trace(token, http_status=200)

        response = self.client.get('/api/agent/knowledge/runs/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['results'][0]['run_id'], chat_response.data['run_id'])
        usage_response = self.client.get('/api/agent/knowledge/token-usage/')
        self.assertEqual(usage_response.status_code, 200)
        self.assertEqual(usage_response.data['summary'], {
            'run_count': 1,
            'token_reported_run_count': 1,
            'llm_request_count': 2,
            'prompt_tokens': 100,
            'completion_tokens': 25,
            'total_tokens': 125,
        })
        item = usage_response.data['results'][0]
        self.assertEqual(item['llm_usage']['total_tokens'], 125)
        self.assertTrue(item['trace_available'])
        self.assertNotIn('estimated_cost', item['llm_usage'])
        serialized = repr(response.data) + repr(usage_response.data)
        self.assertNotIn('不应进入运行列表的问题', serialized)
        self.assertNotIn('不应进入运行列表的回答', serialized)

        self.client.force_authenticate(user=self.other_admin)
        other_response = self.client.get('/api/agent/knowledge/runs/')
        self.assertEqual(other_response.data['results'], [])
        other_usage = self.client.get('/api/agent/knowledge/token-usage/')
        self.assertEqual(other_usage.data['results'], [])
        self.assertEqual(other_usage.data['summary']['total_tokens'], 0)

    def test_token_usage_summary_covers_all_filtered_records_before_pagination(self):
        now = timezone.now()
        records = [
            self.create_usage(
                created_at=now - timedelta(minutes=index),
                prompt_tokens=10 + index,
                completion_tokens=2,
            )
            for index in range(3)
        ]
        self.client.force_authenticate(user=self.admin)

        response = self.client.get(
            '/api/agent/knowledge/token-usage/',
            {'page': 1, 'page_size': 2},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['summary'], {
            'run_count': 3,
            'token_reported_run_count': 3,
            'llm_request_count': 3,
            'prompt_tokens': 33,
            'completion_tokens': 6,
            'total_tokens': 39,
        })
        self.assertEqual(response.data['pagination'], {
            'page': 1,
            'page_size': 2,
            'total_count': 3,
            'total_pages': 2,
            'has_previous': False,
            'has_next': True,
        })
        self.assertEqual(
            [item['run_id'] for item in response.data['results']],
            [str(records[0].run_id), str(records[1].run_id)],
        )

    def test_token_usage_filters_by_local_date_and_validates_query(self):
        local_tz = timezone.get_current_timezone()
        for day, prompt_tokens in ((10, 10), (11, 20), (12, 30)):
            self.create_usage(
                created_at=timezone.make_aware(
                    datetime(2026, 7, day, 12),
                    local_tz,
                ),
                prompt_tokens=prompt_tokens,
                completion_tokens=1,
            )
        self.client.force_authenticate(user=self.admin)

        response = self.client.get(
            '/api/agent/knowledge/token-usage/',
            {'date_from': '2026-07-11', 'date_to': '2026-07-11'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['summary']['run_count'], 1)
        self.assertEqual(response.data['summary']['total_tokens'], 21)
        self.assertEqual(len(response.data['results']), 1)

        reversed_dates = self.client.get(
            '/api/agent/knowledge/token-usage/',
            {'date_from': '2026-07-12', 'date_to': '2026-07-11'},
        )
        oversized_page = self.client.get(
            '/api/agent/knowledge/token-usage/',
            {'page_size': 101},
        )

        self.assertEqual(reversed_dates.status_code, 400)
        self.assertEqual(oversized_page.status_code, 400)

    @patch('agent.views.refresh_conversation_memory', return_value=False)
    @patch('agent.views.run_knowledge_agent')
    def test_chat_run_can_be_diagnosed_only_by_owner(self, run_agent, _refresh_memory):
        run_agent.return_value = KnowledgeAgentResult(
            answer='安全回答',
            sources=(),
            insufficient_context=True,
            tool_steps=0,
        )
        self.client.force_authenticate(user=self.admin)
        chat_response = self.client.post(
            '/api/agent/knowledge/chat/',
            {'message': '敏感问题正文'},
            format='json',
        )
        run_id = chat_response.data['run_id']
        # 模拟后端重启或一小时缓存过期，详情必须从 MySQL 轨迹回源。
        cache.clear()

        trace_response = self.client.get(
            f'/api/agent/knowledge/runs/{run_id}/trace/'
        )

        self.assertEqual(trace_response.status_code, 200)
        self.assertEqual(trace_response.data['run_id'], run_id)
        self.assertNotIn('敏感问题正文', repr(trace_response.data))
        self.assertNotIn('安全回答', repr(trace_response.data))

        self.client.force_authenticate(user=self.other_admin)
        hidden_response = self.client.get(
            f'/api/agent/knowledge/runs/{run_id}/trace/'
        )
        self.assertEqual(hidden_response.status_code, 404)
