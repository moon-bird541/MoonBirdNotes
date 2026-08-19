"""输出不含正文和错误详情的 RAG 运行状态。"""

import json

from django.core.management.base import BaseCommand

from rag.monitoring import get_rag_runtime_snapshot


class Command(BaseCommand):
    help = '输出索引积压、失败率和当前索引状态的 JSON 快照。'

    def handle(self, *args, **options):
        snapshot = get_rag_runtime_snapshot()
        self.stdout.write(
            json.dumps(snapshot.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)
        )
