"""处理已经到期的 RAG 索引任务。"""

from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from rag.embeddings import get_embedding_service
from rag.indexing import get_note_indexing_service
from rag.jobs import get_rag_index_worker
from rag.qdrant import get_qdrant_store


class Command(BaseCommand):
    help = '领取并处理到期的 RAG 索引和删除任务。'

    def add_arguments(self, parser):
        parser.add_argument(
            '--max-jobs',
            type=int,
            default=100,
            help='本次命令最多处理的任务数，默认 100。',
        )

    def handle(self, *args, **options):
        max_jobs = options['max_jobs']
        if max_jobs < 1:
            raise CommandError('--max-jobs must be a positive integer.')

        worker = get_rag_index_worker()
        counts = Counter()
        processed = 0
        try:
            while processed < max_jobs:
                result = worker.process_next()
                if result is None:
                    break
                counts[result.outcome] += 1
                processed += 1
        finally:
            # 管理命令是短生命周期进程，退出前释放两个外部 HTTP 连接池。
            service = worker.indexing_service
            if hasattr(service.embedding_service, 'close'):
                service.embedding_service.close()
            if hasattr(service.vector_store, 'close'):
                service.vector_store.close()
            get_rag_index_worker.cache_clear()
            get_note_indexing_service.cache_clear()
            get_embedding_service.cache_clear()
            get_qdrant_store.cache_clear()

        self.stdout.write(
            self.style.SUCCESS(
                'RAG jobs processed: '
                f'total={processed}, indexed={counts["indexed"]}, '
                f'deleted={counts["deleted"]}, stale={counts["stale"]}, '
                f'retry={counts["retry"]}, failed={counts["failed"]}'
            )
        )
