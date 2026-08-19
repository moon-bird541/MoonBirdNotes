"""历史会话数量上限与过期清理命令测试。"""

from datetime import timedelta
from io import StringIO
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from .conversation_store import get_or_create_conversation
from .models import AgentTokenUsage, KnowledgeConversation


class ConversationCleanupTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username='cleanup-admin',
            password='strong-password',
        )

    @override_settings(AGENT_CONVERSATION_MAX_PER_USER=2)
    def test_creating_conversation_prunes_only_current_users_oldest_excess(self):
        first = get_or_create_conversation(user=self.user, conversation_id=None, message='第一条')
        second = get_or_create_conversation(user=self.user, conversation_id=None, message='第二条')
        third = get_or_create_conversation(user=self.user, conversation_id=None, message='第三条')

        remaining = set(
            KnowledgeConversation.objects.filter(user=self.user).values_list('pk', flat=True)
        )
        self.assertNotIn(first.pk, remaining)
        self.assertEqual(remaining, {second.pk, third.pk})

    def test_cleanup_command_previews_then_deletes_expired_conversations(self):
        expired = KnowledgeConversation.objects.create(user=self.user, title='过期会话')
        current = KnowledgeConversation.objects.create(user=self.user, title='当前会话')
        KnowledgeConversation.objects.filter(pk=expired.pk).update(
            updated_at=timezone.now() - timedelta(days=181)
        )
        usage = AgentTokenUsage.objects.create(
            user=self.user,
            run_id=uuid4(),
            request_count=1,
            usage_reported_request_count=1,
            usage_status=AgentTokenUsage.UsageStatus.AVAILABLE,
            prompt_tokens=100,
            completion_tokens=20,
            total_tokens=120,
            duration_ms=500,
            http_status=200,
        )
        preview = StringIO()

        call_command('cleanup_agent_conversations', '--days', '180', stdout=preview)

        self.assertIn('mode=preview conversations=1', preview.getvalue())
        self.assertTrue(KnowledgeConversation.objects.filter(pk=expired.pk).exists())

        call_command('cleanup_agent_conversations', '--days', '180', '--apply', stdout=StringIO())
        self.assertFalse(KnowledgeConversation.objects.filter(pk=expired.pk).exists())
        self.assertTrue(KnowledgeConversation.objects.filter(pk=current.pk).exists())
        self.assertTrue(AgentTokenUsage.objects.filter(pk=usage.pk).exists())
