"""从 MySQL Note 重建全部或指定范围的 RAG 派生索引。"""

from django.core.management.base import BaseCommand, CommandError

from rag.embeddings import get_embedding_service
from rag.indexing import get_note_indexing_service
from rag.qdrant import get_qdrant_store
from rag.rebuild import RagRebuildError, get_rag_index_rebuild_service


class Command(BaseCommand):
    help = '从 MySQL 重建全部、普通笔记、日记或指定 Note 的 RAG 索引。'

    def add_arguments(self, parser):
        parser.add_argument(
            '--scope',
            choices=('all', 'note', 'diary'),
            default='all',
            help='重建范围：all、note 或 diary，默认 all。',
        )
        parser.add_argument(
            '--note-id',
            type=int,
            help='只重建指定 Note；不能与 note/diary scope 组合。',
        )
        parser.add_argument(
            '--recreate-collection',
            action='store_true',
            help='显式删除并重建当前 Collection；只允许全范围重建。',
        )

    def handle(self, *args, **options):
        service = get_rag_index_rebuild_service()
        try:
            result = service.rebuild(
                scope=options['scope'],
                note_id=options.get('note_id'),
                recreate_collection=options['recreate_collection'],
            )
        except RagRebuildError as exc:
            raise CommandError(f'{exc.code}: {exc}') from None
        finally:
            # 管理命令退出前释放在线 Embedding 和 Qdrant 连接池。
            indexing_service = service.indexing_service
            if hasattr(indexing_service.embedding_service, 'close'):
                indexing_service.embedding_service.close()
            if hasattr(indexing_service.vector_store, 'close'):
                indexing_service.vector_store.close()
            get_rag_index_rebuild_service.cache_clear()
            get_note_indexing_service.cache_clear()
            get_embedding_service.cache_clear()
            get_qdrant_store.cache_clear()

        if result.recreated_collection:
            self.stdout.write(
                'Collection recreated: '
                f'cleared_parents={result.cleared_parent_count}, '
                f'cleared_states={result.cleared_state_count}'
            )
        for failure in result.failures:
            self.stderr.write(
                f'note_id={failure.note_id} failed: '
                f'code={failure.code}, retryable={str(failure.retryable).lower()}'
            )
        self.stdout.write(
            self.style.SUCCESS(
                'RAG rebuild completed: '
                f'scope={result.scope}, total={result.total}, '
                f'succeeded={result.succeeded}, failed={result.failed}, '
                f'skipped={result.skipped}'
            )
        )
