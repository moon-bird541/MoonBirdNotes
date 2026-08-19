"""DeepSeek Chat Completions 配置、工具调用、重试和脱敏测试。"""

import json
from unittest.mock import Mock, patch

import httpx
from django.test import SimpleTestCase, override_settings

from .base import ChatModelError
from .deepseek import DeepSeekChatConfig, DeepSeekChatService, get_chat_model


def make_config(**overrides):
    values = {
        'api_key': 'deepseek-private-key',
        'timeout_seconds': 5,
        'max_output_tokens': 512,
        'max_retries': 1,
        'retry_backoff_seconds': 0.01,
    }
    values.update(overrides)
    return DeepSeekChatConfig(**values)


class DeepSeekChatConfigTests(SimpleTestCase):
    def test_repr_hides_api_key_and_defaults_to_confirmed_model(self):
        config = make_config()

        self.assertNotIn('deepseek-private-key', repr(config))
        self.assertIn("api_key='***'", repr(config))
        self.assertEqual(config.base_url, 'https://api.deepseek.com')
        self.assertEqual(config.model, 'deepseek-v4-flash')

    def test_rejects_missing_key_bad_url_and_invalid_limits(self):
        invalid = (
            {'api_key': ''},
            {'base_url': './local'},
            {'base_url': 'https://user:secret@example.com'},
            {'timeout_seconds': 0},
            {'max_output_tokens': 0},
            {'max_retries': 4},
        )
        for overrides in invalid:
            with self.subTest(overrides=overrides), self.assertRaises(ChatModelError):
                make_config(**overrides)

    @override_settings(
        AGENT_LLM_PROVIDER='unsupported',
        AGENT_LLM_API_KEY='secret',
        AGENT_LLM_BASE_URL='https://example.com',
        AGENT_LLM_MODEL='model',
        AGENT_LLM_TIMEOUT_SECONDS=5,
        AGENT_LLM_MAX_OUTPUT_TOKENS=100,
        AGENT_LLM_MAX_RETRIES=0,
        AGENT_LLM_RETRY_BACKOFF_SECONDS=0,
    )
    def test_django_settings_reject_unconfirmed_provider(self):
        with self.assertRaises(ChatModelError) as context:
            DeepSeekChatConfig.from_django_settings()
        self.assertEqual(context.exception.code, 'llm_configuration_error')


class DeepSeekChatServiceTests(SimpleTestCase):
    def service(self, handler, *, config=None, sleep=None):
        client = httpx.Client(
            transport=httpx.MockTransport(handler),
            headers={'Authorization': 'Bearer deepseek-private-key'},
        )
        return DeepSeekChatService(
            config or make_config(),
            client=client,
            sleep=sleep or (lambda _: None),
        )

    @patch('agent.llm.deepseek.logger.info')
    def test_sends_openai_compatible_tools_and_parses_tool_call(self, log_info):
        captured = {}

        def handler(request):
            captured['payload'] = json.loads(request.content)
            captured['authorization'] = request.headers['Authorization']
            return httpx.Response(
                200,
                json={
                    'choices': [
                        {
                            'message': {
                                'content': None,
                                'tool_calls': [
                                    {
                                        'id': 'call-1',
                                        'type': 'function',
                                        'function': {
                                            'name': 'search_notes',
                                            'arguments': '{"query":"测试"}',
                                        },
                                    }
                                ],
                            },
                            'finish_reason': 'tool_calls',
                        }
                    ]
                },
            )

        tools = (
            {
                'type': 'function',
                'function': {'name': 'search_notes', 'parameters': {'type': 'object'}},
            },
        )
        completion = self.service(handler).complete(
            [
                {'role': 'system', 'content': 'system'},
                {'role': 'user', 'content': 'private-user-question'},
            ],
            tools=tools,
        )

        self.assertEqual(captured['payload']['model'], 'deepseek-v4-flash')
        self.assertEqual(captured['payload']['tool_choice'], 'auto')
        self.assertEqual(captured['payload']['max_tokens'], 512)
        self.assertEqual(captured['payload']['temperature'], 0)
        self.assertEqual(captured['authorization'], 'Bearer deepseek-private-key')
        self.assertEqual(completion.tool_calls[0].name, 'search_notes')
        self.assertEqual(completion.tool_calls[0].arguments, '{"query":"测试"}')
        self.assertIsNone(completion.usage)
        self.assertNotIn('private-user-question', str(log_info.call_args))
        self.assertNotIn('deepseek-private-key', str(log_info.call_args))

    @patch('agent.llm.deepseek.logger.info')
    def test_parses_usage_without_logging_content(self, log_info):
        def handler(request):
            return httpx.Response(
                200,
                json={
                    'choices': [{
                        'message': {'content': '{"answer":"ok"}'},
                        'finish_reason': 'stop',
                    }],
                    'usage': {
                        'prompt_tokens': 1200,
                        'completion_tokens': 300,
                        'total_tokens': 1500,
                    },
                },
            )

        completion = self.service(handler).complete([
            {'role': 'user', 'content': 'private-user-question'}
        ])

        self.assertEqual(completion.usage.prompt_tokens, 1200)
        self.assertEqual(completion.usage.completion_tokens, 300)
        self.assertEqual(completion.usage.total_tokens, 1500)
        extra = log_info.call_args.kwargs['extra']
        self.assertEqual(extra['total_tokens'], 1500)
        self.assertNotIn('private-user-question', repr(log_info.call_args))

    def test_malformed_or_inconsistent_usage_is_ignored(self):
        usages = (
            {'prompt_tokens': '1200', 'completion_tokens': 300, 'total_tokens': 1500},
            {'prompt_tokens': 1200, 'completion_tokens': -1, 'total_tokens': 1199},
            {'prompt_tokens': 1200, 'completion_tokens': 300, 'total_tokens': 1499},
        )

        for usage in usages:
            with self.subTest(usage=usage):
                completion = self.service(lambda request: httpx.Response(
                    200,
                    json={
                        'choices': [{
                            'message': {'content': '{"answer":"ok"}'},
                            'finish_reason': 'stop',
                        }],
                        'usage': usage,
                    },
                )).complete([{'role': 'user', 'content': 'hello'}])
                self.assertIsNone(completion.usage)

    def test_retries_retryable_status_then_returns_final_content(self):
        attempts = []
        sleep = Mock()

        def handler(request):
            attempts.append(request)
            if len(attempts) == 1:
                return httpx.Response(500, json={'error': {'message': 'private body'}})
            return httpx.Response(
                200,
                json={
                    'choices': [
                        {
                            'message': {'content': '{"answer":"ok"}'},
                            'finish_reason': 'stop',
                        }
                    ]
                },
            )

        completion = self.service(handler, sleep=sleep).complete(
            [{'role': 'user', 'content': 'hello'}]
        )

        self.assertEqual(completion.content, '{"answer":"ok"}')
        self.assertEqual(len(attempts), 2)
        sleep.assert_called_once()

    def test_rejected_and_malformed_responses_are_sanitized(self):
        def rejected(request):
            return httpx.Response(401, json={'error': {'message': 'private provider detail'}})

        with self.assertRaises(ChatModelError) as context:
            self.service(rejected).complete([{'role': 'user', 'content': 'hello'}])
        self.assertEqual(context.exception.code, 'llm_request_rejected')
        self.assertNotIn('private provider', str(context.exception))

        def malformed(request):
            return httpx.Response(200, json={'choices': []})

        with self.assertRaises(ChatModelError) as context:
            self.service(malformed).complete([{'role': 'user', 'content': 'hello'}])
        self.assertEqual(context.exception.code, 'llm_invalid_response')

    def test_transport_failure_and_invalid_messages_are_structured(self):
        def transport_failure(request):
            raise httpx.ConnectError('private network path', request=request)

        with self.assertRaises(ChatModelError) as context:
            self.service(transport_failure, config=make_config(max_retries=0)).complete(
                [{'role': 'user', 'content': 'hello'}]
            )
        self.assertEqual(context.exception.code, 'llm_transport_error')
        self.assertTrue(context.exception.retryable)

        with self.assertRaises(ChatModelError) as context:
            self.service(lambda request: httpx.Response(200)).complete([])
        self.assertEqual(context.exception.code, 'llm_input_error')

    def tearDown(self):
        if get_chat_model.cache_info().currsize:
            get_chat_model().close()
        get_chat_model.cache_clear()
        super().tearDown()
