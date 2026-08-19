"""RAG 评测集格式、来源和指标计算测试。"""

from types import SimpleNamespace
from unittest.mock import Mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from agent.agents import KnowledgeAgentLlmUsage, KnowledgeAgentResult, KnowledgeSource
from rag.evaluation import (
    REQUIRED_CATEGORIES,
    RagEvaluationCase,
    assess_rag_acceptance,
    dataset_summary,
    evaluate_answers,
    evaluate_retrieval,
    load_evaluation_cases,
)


def evaluation_case(**overrides):
    values = {
        'case_id': 'case-1',
        'question': '校验接口什么时候调用？',
        'categories': ('chinese_semantic', 'note'),
        'filters': {'types': ['note']},
        'expected_note_ids': (5,),
        'expected_heading_paths': (('规范', '接口'),),
        'acceptable_source_heading_paths': (('规范', '接口'),),
        'answerable': True,
        'expected_keywords': ('生成',),
    }
    values.update(overrides)
    if 'acceptable_source_heading_paths' not in overrides:
        # 默认让回答来源口径跟随当前用例的检索章节口径，避免夹具继承旧默认值。
        values['acceptable_source_heading_paths'] = values['expected_heading_paths']
    return RagEvaluationCase(**values)


class RagEvaluationDatasetTests(SimpleTestCase):
    def test_default_dataset_has_required_size_labels_and_categories(self):
        cases = load_evaluation_cases()
        categories = {category for case in cases for category in case.categories}

        self.assertGreaterEqual(len(cases), 30)
        self.assertLessEqual(len(cases), 50)
        self.assertTrue(REQUIRED_CATEGORIES.issubset(categories))
        self.assertEqual(len({case.case_id for case in cases}), len(cases))
        self.assertTrue(all(case.question for case in cases))
        self.assertTrue(all(case.expected_note_ids for case in cases if case.answerable))
        self.assertTrue(all(case.expected_keywords for case in cases if case.answerable))

    def test_dataset_summary_counts_answerability_and_categories(self):
        cases = (
            evaluation_case(),
            evaluation_case(
                case_id='case-2',
                categories=('unanswerable', 'diary'),
                answerable=False,
                expected_note_ids=(),
                expected_heading_paths=(),
                expected_keywords=(),
            ),
        )

        summary = dataset_summary(cases)

        self.assertEqual(summary['case_count'], 2)
        self.assertEqual(summary['answerable_count'], 1)
        self.assertEqual(summary['unanswerable_count'], 1)
        self.assertEqual(summary['category_counts']['diary'], 1)


class RagEvaluationMetricTests(SimpleTestCase):
    def test_retrieval_metrics_measure_note_section_scope_and_empty_unknowns(self):
        cases = (
            evaluation_case(),
            evaluation_case(
                case_id='case-2',
                question='不存在的问题',
                categories=('unanswerable',),
                filters={'types': ['note']},
                expected_note_ids=(),
                expected_heading_paths=(),
                answerable=False,
                expected_keywords=(),
            ),
        )
        candidate = SimpleNamespace(
            note_id=5,
            heading_path=('规范', '接口'),
            document_type='note',
            diary_date=None,
        )
        retrieval = Mock(
            side_effect=(
                SimpleNamespace(
                    results=(candidate,), degraded=False, dense_candidate_count=1
                ),
                SimpleNamespace(results=(), degraded=True, dense_candidate_count=0),
            )
        )
        times = iter((0.0, 0.01, 0.01, 0.03))

        report = evaluate_retrieval(cases, retrieval=retrieval, clock=lambda: next(times))

        self.assertEqual(report['recall_at_5'], 1.0)
        self.assertEqual(report['target_note_hit_rate'], 1.0)
        self.assertEqual(report['target_section_hit_rate'], 1.0)
        self.assertEqual(report['scope_violation_rate'], 0.0)
        self.assertEqual(report['unanswerable_empty_retrieval_rate'], 1.0)
        self.assertEqual(report['no_source_dense_empty_rate'], 1.0)
        self.assertEqual(report['degraded_query_rate'], 0.5)
        self.assertEqual(report['average_retrieval_ms'], 15.0)
        self.assertEqual(report['note_miss_case_ids'], [])
        self.assertEqual(report['section_miss_case_ids'], [])
        self.assertEqual(report['unanswerable_nonempty_case_ids'], [])
        self.assertEqual(report['no_source_dense_nonempty_case_ids'], [])

    def test_answer_metrics_measure_sources_refusal_keywords_and_latency(self):
        cases = (
            evaluation_case(),
            evaluation_case(
                case_id='case-2',
                question='不存在的问题',
                categories=('unanswerable',),
                filters={},
                expected_note_ids=(),
                expected_heading_paths=(),
                answerable=False,
                expected_keywords=(),
            ),
        )
        source = KnowledgeSource(
            note_id=5,
            title='规范',
            heading_path=('规范', '接口'),
            source_hash='a' * 64,
            document_type='note',
            diary_date=None,
        )
        agent_runner = Mock(
            side_effect=(
                KnowledgeAgentResult(
                    answer='用户点击生成时校验。',
                    sources=(source,),
                    insufficient_context=False,
                    tool_steps=2,
                ),
                KnowledgeAgentResult(
                    answer='未能找到资料。',
                    sources=(),
                    insufficient_context=True,
                    tool_steps=1,
                ),
            )
        )
        times = iter((0.0, 0.02, 0.02, 0.06))

        report = evaluate_answers(
            cases,
            user=SimpleNamespace(pk=1),
            agent_runner=agent_runner,
            clock=lambda: next(times),
        )

        self.assertEqual(report['source_accuracy'], 1.0)
        self.assertEqual(report['ungrounded_answer_rate'], 0.0)
        self.assertEqual(report['answerable_success_rate'], 1.0)
        self.assertEqual(report['answerable_refusal_rate'], 0.0)
        self.assertEqual(report['answerable_joint_success_rate'], 1.0)
        self.assertEqual(report['unanswerable_refusal_rate'], 1.0)
        self.assertEqual(report['expected_keyword_hit_rate'], 1.0)
        self.assertEqual(report['average_answer_ms'], 30.0)
        self.assertEqual(report['p95_answer_ms'], 40.0)
        self.assertEqual(report['incorrect_source_case_ids'], [])
        self.assertEqual(report['ungrounded_case_ids'], [])
        self.assertEqual(report['keyword_miss_case_ids'], [])
        self.assertEqual(report['answerable_refusal_case_ids'], [])
        self.assertEqual(report['answerable_joint_failure_case_ids'], [])
        self.assertEqual(report['unanswerable_not_refused_case_ids'], [])

    def test_answer_metrics_aggregate_available_llm_usage_and_cost(self):
        case = evaluation_case()
        source = KnowledgeSource(
            note_id=5,
            title='规范',
            heading_path=('规范', '接口'),
            source_hash='a' * 64,
            document_type='note',
            diary_date=None,
        )
        agent_runner = Mock(return_value=KnowledgeAgentResult(
            answer='生成',
            sources=(source,),
            insufficient_context=False,
            tool_steps=1,
            llm_usage=KnowledgeAgentLlmUsage(
                request_count=2,
                usage_reported_request_count=2,
                usage_status='available',
                prompt_tokens=120,
                completion_tokens=30,
                total_tokens=150,
            ),
        ))

        report = evaluate_answers(
            (case,),
            user=SimpleNamespace(pk=1),
            agent_runner=agent_runner,
            clock=Mock(side_effect=(0.0, 0.02)),
        )

        self.assertEqual(report['llm_request_count'], 2)
        self.assertEqual(report['llm_usage_reported_request_count'], 2)
        self.assertEqual(report['llm_usage_status'], 'available')
        self.assertEqual(report['llm_prompt_tokens'], 120)
        self.assertEqual(report['llm_completion_tokens'], 30)
        self.assertEqual(report['llm_total_tokens'], 150)
        self.assertNotIn('llm_estimated_cost', report)
        self.assertNotIn('llm_cost_currency', report)

    def test_answer_metrics_mark_partial_and_missing_usage_unavailable(self):
        partial = KnowledgeAgentResult(
            answer='生成',
            sources=(),
            insufficient_context=True,
            tool_steps=1,
            llm_usage=KnowledgeAgentLlmUsage(
                request_count=2,
                usage_reported_request_count=1,
                usage_status='partial',
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
            ),
        )
        unavailable = KnowledgeAgentResult(
            answer='生成',
            sources=(),
            insufficient_context=True,
            tool_steps=1,
        )
        clock = Mock(side_effect=(0.0, 0.01, 0.01, 0.03))
        partial_report = evaluate_answers(
            (evaluation_case(),),
            user=SimpleNamespace(pk=1),
            agent_runner=Mock(return_value=partial),
            clock=clock,
        )
        unavailable_report = evaluate_answers(
            (evaluation_case(),),
            user=SimpleNamespace(pk=1),
            agent_runner=Mock(return_value=unavailable),
            clock=clock,
        )

        self.assertEqual(partial_report['llm_request_count'], 2)
        self.assertEqual(partial_report['llm_usage_reported_request_count'], 1)
        self.assertEqual(partial_report['llm_usage_status'], 'partial')
        self.assertIsNone(partial_report['llm_total_tokens'])
        self.assertEqual(unavailable_report['llm_request_count'], 0)
        self.assertEqual(unavailable_report['llm_usage_status'], 'unavailable')
        self.assertNotIn('llm_estimated_cost', unavailable_report)

    def test_answer_diagnostics_list_only_case_ids_for_quality_failures(self):
        case = evaluation_case()
        wrong_source = KnowledgeSource(
            note_id=99,
            title='其他笔记',
            heading_path=('其他章节',),
            source_hash='b' * 64,
            document_type='note',
            diary_date=None,
        )
        agent_runner = Mock(
            return_value=KnowledgeAgentResult(
                answer='没有包含预期词的回答。',
                sources=(wrong_source,),
                insufficient_context=False,
                tool_steps=1,
            )
        )

        report = evaluate_answers(
            (case,),
            user=SimpleNamespace(pk=1),
            agent_runner=agent_runner,
            clock=Mock(side_effect=(0.0, 0.01)),
        )

        self.assertEqual(report['source_accuracy'], 0.0)
        self.assertEqual(report['ungrounded_answer_rate'], 1.0)
        self.assertEqual(report['incorrect_source_case_ids'], ['case-1'])
        self.assertEqual(report['ungrounded_case_ids'], ['case-1'])
        self.assertEqual(report['keyword_miss_case_ids'], ['case-1'])
        self.assertEqual(report['answerable_joint_success_rate'], 0.0)
        self.assertEqual(report['answerable_joint_failure_case_ids'], ['case-1'])

    def test_answerable_refusal_has_zero_source_and_success_metrics(self):
        agent_runner = Mock(
            return_value=KnowledgeAgentResult(
                answer='未能找到资料。',
                sources=(),
                insufficient_context=True,
                tool_steps=1,
            )
        )

        report = evaluate_answers(
            (evaluation_case(),),
            user=SimpleNamespace(pk=1),
            agent_runner=agent_runner,
            clock=Mock(side_effect=(0.0, 0.01)),
        )

        self.assertEqual(report['source_accuracy'], 0.0)
        self.assertEqual(report['answerable_success_rate'], 0.0)
        self.assertEqual(report['answerable_refusal_rate'], 1.0)
        self.assertEqual(report['answerable_joint_success_rate'], 0.0)
        self.assertEqual(report['expected_keyword_hit_rate'], 0.0)
        self.assertEqual(report['answerable_refusal_case_ids'], ['case-1'])
        self.assertEqual(report['answerable_joint_failure_case_ids'], ['case-1'])

    def test_joint_success_requires_expected_answer_keywords(self):
        source = KnowledgeSource(
            note_id=5,
            title='规范',
            heading_path=('规范', '接口'),
            source_hash='a' * 64,
            document_type='note',
            diary_date=None,
        )
        agent_runner = Mock(
            return_value=KnowledgeAgentResult(
                answer='用户提交时校验。',
                sources=(source,),
                insufficient_context=False,
                tool_steps=1,
            )
        )

        report = evaluate_answers(
            (evaluation_case(),),
            user=SimpleNamespace(pk=1),
            agent_runner=agent_runner,
            clock=Mock(side_effect=(0.0, 0.01)),
        )

        self.assertEqual(report['answerable_success_rate'], 1.0)
        self.assertEqual(report['answerable_refusal_rate'], 0.0)
        self.assertEqual(report['source_accuracy'], 1.0)
        self.assertEqual(report['expected_keyword_hit_rate'], 0.0)
        self.assertEqual(report['answerable_joint_success_rate'], 0.0)
        self.assertEqual(report['answerable_joint_failure_case_ids'], ['case-1'])

    def test_keyword_matching_ignores_markdown_inline_code_markers(self):
        case = evaluation_case(expected_keywords=('name + version',))
        source = KnowledgeSource(
            note_id=5,
            title='规范',
            heading_path=('规范', '接口'),
            source_hash='a' * 64,
            document_type='note',
            diary_date=None,
        )
        agent_runner = Mock(
            return_value=KnowledgeAgentResult(
                answer='使用 `name` + `version` 区分。',
                sources=(source,),
                insufficient_context=False,
                tool_steps=1,
            )
        )

        report = evaluate_answers(
            (case,),
            user=SimpleNamespace(pk=1),
            agent_runner=agent_runner,
            clock=Mock(side_effect=(0.0, 0.01)),
        )

        self.assertEqual(report['expected_keyword_hit_rate'], 1.0)
        self.assertEqual(report['answerable_joint_success_rate'], 1.0)


class RagFinalAcceptanceTests(SimpleTestCase):
    def retrieval_report(self, **overrides):
        values = {
            'recall_at_5': 0.95,
            'target_note_hit_rate': 1.0,
            'target_section_hit_rate': 1.0,
            'scope_violation_rate': 0.0,
            'degraded_query_rate': 0.0,
            'no_source_dense_empty_rate': 1.0,
            'failed_case_ids': [],
        }
        values.update(overrides)
        return values

    def answer_report(self, **overrides):
        values = {
            'source_accuracy': 1.0,
            'ungrounded_answer_rate': 0.0,
            'answerable_success_rate': 1.0,
            'answerable_refusal_rate': 0.0,
            'answerable_joint_success_rate': 1.0,
            'expected_keyword_hit_rate': 1.0,
            'unanswerable_refusal_rate': 1.0,
            'failed_case_ids': [],
        }
        values.update(overrides)
        return values

    def test_acceptance_passes_only_when_retrieval_and_answer_thresholds_pass(self):
        report = assess_rag_acceptance(
            self.retrieval_report(),
            self.answer_report(),
        )

        self.assertTrue(report['complete'])
        self.assertTrue(report['passed'])
        self.assertEqual(report['failed_checks'], [])

    def test_acceptance_reports_quality_failures_and_incomplete_runs(self):
        failed = assess_rag_acceptance(
            self.retrieval_report(
                recall_at_5=0.5,
                no_source_dense_empty_rate=0.0,
            ),
            self.answer_report(source_accuracy=0.875, ungrounded_answer_rate=0.1),
        )
        incomplete = assess_rag_acceptance(self.retrieval_report(), None)

        self.assertFalse(failed['passed'])
        self.assertIn('retrieval_recall_at_5', failed['failed_checks'])
        self.assertIn('no_source_dense_empty_rate', failed['failed_checks'])
        self.assertIn('source_accuracy', failed['failed_checks'])
        self.assertIn('ungrounded_answer_rate', failed['failed_checks'])
        self.assertFalse(incomplete['complete'])
        self.assertIn('answer_metrics_present', incomplete['failed_checks'])

    def test_acceptance_rejects_answerable_refusals_and_keyword_misses(self):
        refused = assess_rag_acceptance(
            self.retrieval_report(),
            self.answer_report(
                source_accuracy=0.0,
                answerable_success_rate=0.0,
                answerable_refusal_rate=1.0,
                answerable_joint_success_rate=0.0,
                expected_keyword_hit_rate=0.0,
            ),
        )

        self.assertFalse(refused['passed'])
        self.assertIn('source_accuracy', refused['failed_checks'])
        self.assertIn('answerable_success_rate', refused['failed_checks'])
        self.assertIn('answerable_refusal_rate', refused['failed_checks'])
        self.assertIn('answerable_joint_success_rate', refused['failed_checks'])
        self.assertIn('expected_keyword_hit_rate', refused['failed_checks'])

    def test_acceptance_uses_calibrated_generation_quality_boundaries(self):
        passing = assess_rag_acceptance(
            self.retrieval_report(),
            self.answer_report(
                answerable_success_rate=0.9,
                answerable_refusal_rate=0.1,
                answerable_joint_success_rate=0.9,
                expected_keyword_hit_rate=0.9,
            ),
        )
        failing = assess_rag_acceptance(
            self.retrieval_report(),
            self.answer_report(
                answerable_success_rate=0.899,
                answerable_refusal_rate=0.101,
                answerable_joint_success_rate=0.899,
                expected_keyword_hit_rate=0.899,
            ),
        )

        self.assertTrue(passing['passed'])
        self.assertFalse(failing['passed'])
        self.assertIn('answerable_success_rate', failing['failed_checks'])
        self.assertIn('answerable_refusal_rate', failing['failed_checks'])
        self.assertIn('answerable_joint_success_rate', failing['failed_checks'])
        self.assertIn('expected_keyword_hit_rate', failing['failed_checks'])

    def test_acceptance_fails_closed_when_new_answer_metrics_are_missing(self):
        incomplete_answer_report = self.answer_report()
        for key in (
            'answerable_success_rate',
            'answerable_refusal_rate',
            'answerable_joint_success_rate',
            'expected_keyword_hit_rate',
        ):
            incomplete_answer_report.pop(key)

        report = assess_rag_acceptance(
            self.retrieval_report(),
            incomplete_answer_report,
        )

        self.assertFalse(report['passed'])
        self.assertIn('answerable_success_rate', report['failed_checks'])
        self.assertIn('answerable_refusal_rate', report['failed_checks'])
        self.assertIn('answerable_joint_success_rate', report['failed_checks'])
        self.assertIn('expected_keyword_hit_rate', report['failed_checks'])

    def test_acceptance_command_requires_real_agent_metrics(self):
        with self.assertRaises(CommandError) as context:
            call_command('evaluate_rag', acceptance=True)

        self.assertIn('--acceptance requires --with-agent', str(context.exception))
