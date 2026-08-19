"""校验并执行当前 RAG 评测集。"""

import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from agent.agents import get_knowledge_agent
from agent.llm import get_chat_model
from rag.embeddings import get_embedding_service
from rag.evaluation import (
    DEFAULT_DATASET_PATH,
    RagEvaluationError,
    assess_rag_acceptance,
    dataset_summary,
    evaluate_answers,
    evaluate_retrieval,
    load_evaluation_cases,
    validate_evaluation_sources,
)
from rag.qdrant import get_qdrant_store
from rag.retrieval.hybrid import get_hybrid_retrieval_service


class Command(BaseCommand):
    help = '校验真实 RAG 评测集，并计算检索及可选 Knowledge Agent 回答指标。'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dataset',
            default=str(DEFAULT_DATASET_PATH),
            help='评测集 JSON 路径，默认使用仓库内置真实笔记评测集。',
        )
        parser.add_argument(
            '--top-k',
            type=int,
            default=5,
            help='最终父片段数量，默认 5。',
        )
        parser.add_argument(
            '--validate-only',
            action='store_true',
            help='只校验数据格式与当前来源，不调用在线 Embedding 或模型。',
        )
        parser.add_argument(
            '--with-agent',
            action='store_true',
            help='额外调用 Knowledge Agent 计算来源正确率和无依据回答率。',
        )
        parser.add_argument(
            '--admin-username',
            help='启用 --with-agent 时使用的当前管理员用户名。',
        )
        parser.add_argument(
            '--acceptance',
            action='store_true',
            help='按最终门槛判定并在未通过时返回非零退出码；必须同时使用 --with-agent。',
        )

    def handle(self, *args, **options):
        if options['acceptance'] and not options['with_agent']:
            raise CommandError('--acceptance requires --with-agent.')
        try:
            cases = load_evaluation_cases(options['dataset'])
        except RagEvaluationError as exc:
            raise CommandError(str(exc)) from None
        source_errors = validate_evaluation_sources(cases)
        if source_errors:
            raise CommandError(
                'Evaluation dataset references stale sources: ' + '; '.join(source_errors)
            )

        report = {'dataset': dataset_summary(cases)}
        if not options['validate_only']:
            report['retrieval'] = evaluate_retrieval(cases, top_k=options['top_k'])
        if options['with_agent']:
            if options['validate_only']:
                raise CommandError('--with-agent cannot be combined with --validate-only.')
            username = options.get('admin_username')
            if not username:
                raise CommandError('--admin-username is required with --with-agent.')
            user = get_user_model().objects.filter(
                username=username,
                is_active=True,
                is_staff=True,
            ).first()
            if user is None:
                raise CommandError('The requested active administrator was not found.')
            report['answers'] = evaluate_answers(cases, user=user)
        if options['acceptance']:
            report['acceptance'] = assess_rag_acceptance(
                report['retrieval'],
                report.get('answers'),
            )

        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        self._close_external_services()
        if options['acceptance'] and not report['acceptance']['passed']:
            raise CommandError('RAG final acceptance thresholds were not met.')

    def _close_external_services(self):
        # 管理命令退出前释放在线模型、Embedding 和 Qdrant 的连接池。
        for getter in (get_chat_model, get_embedding_service, get_qdrant_store):
            if getter.cache_info().currsize:
                service = getter()
                if hasattr(service, 'close'):
                    service.close()
                getter.cache_clear()
        get_knowledge_agent.cache_clear()
        get_hybrid_retrieval_service.cache_clear()
