"""预览或清理超过保留期限的 Knowledge Agent 历史会话。"""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from agent.models import KnowledgeConversation


class Command(BaseCommand):
    help = 'Preview or delete Knowledge Agent conversations older than the retention period.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=settings.AGENT_CONVERSATION_RETENTION_DAYS,
            help='Delete conversations not updated for this many days.',
        )
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Actually delete matching conversations; default only previews the count.',
        )

    def handle(self, *args, **options):
        days = options['days']
        if days < 1:
            raise CommandError('--days must be a positive integer.')
        cutoff = timezone.now() - timedelta(days=days)
        queryset = KnowledgeConversation.objects.filter(updated_at__lt=cutoff)
        conversation_count = queryset.count()
        turn_count = sum(item.turns.count() for item in queryset.prefetch_related('turns'))

        if options['apply'] and conversation_count:
            queryset.delete()
        mode = 'deleted' if options['apply'] else 'preview'
        self.stdout.write(
            f'mode={mode} conversations={conversation_count} turns={turn_count} retention_days={days}'
        )
