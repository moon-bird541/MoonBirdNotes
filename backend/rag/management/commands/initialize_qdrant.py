"""检查独立 Qdrant 服务并幂等初始化 RAG Collection。"""

from django.core.management.base import BaseCommand, CommandError

from rag.qdrant import QdrantStoreError, get_qdrant_store


class Command(BaseCommand):
    help = '检查 Qdrant 健康状态并创建或校验 RAG Collection。'

    def handle(self, *args, **options):
        store = get_qdrant_store()
        try:
            store.health_check()
            summary = store.ensure_collection()
        except QdrantStoreError as exc:
            # 命令只展示脱敏后的稳定错误，不输出 Qdrant 响应正文或 API Key。
            raise CommandError(f'{exc.code}: {exc}') from None
        finally:
            # 管理命令是短生命周期进程，退出前显式释放连接池。
            store.close()
            get_qdrant_store.cache_clear()

        self.stdout.write(
            self.style.SUCCESS(
                f'Qdrant ready: collection={summary.collection_name}, '
                f'vector={summary.vector_name}, size={summary.vector_size}, '
                f'distance={summary.distance}, payload_indexes={len(summary.payload_indexes)}'
            )
        )
