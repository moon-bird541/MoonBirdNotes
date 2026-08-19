from django.apps import apps
from django.test import SimpleTestCase


class AgentAppConfigTests(SimpleTestCase):
    """确认 Agent App 使用显式 AppConfig 注册。"""

    def test_agent_app_is_registered(self):
        app_config = apps.get_app_config('agent')

        self.assertEqual(app_config.name, 'agent')
