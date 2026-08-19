"""RAG 评测集加载、来源校验和检索/回答指标计算。"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from time import perf_counter
from typing import Callable

from notes.models import Note

from agent.agents import (
    KnowledgeAgentError,
    KnowledgeAgentLlmUsage,
    KnowledgeAgentResult,
    run_knowledge_agent,
)
from rag.models import RagParentChunk
from rag.retrieval import HybridRetrievalResult, retrieve


DEFAULT_DATASET_PATH = Path(__file__).with_name('evaluation_dataset.json')
REQUIRED_CATEGORIES = frozenset(
    {
        'chinese_semantic',
        'mixed_technical',
        'exact_identifier',
        'note',
        'diary',
        'date_mood_weather',
        'similar_title',
        'cross_section',
        'unanswerable',
    }
)
ALLOWED_FILTER_KEYS = frozenset({'types', 'tags', 'date_from', 'date_to'})
MIN_ACCEPTANCE_RECALL_AT_5 = 0.9
MIN_ACCEPTANCE_SOURCE_ACCURACY = 1.0
MAX_ACCEPTANCE_UNGROUNDED_ANSWER_RATE = 0.0
MIN_ACCEPTANCE_ANSWERABLE_SUCCESS_RATE = 0.9
MAX_ACCEPTANCE_ANSWERABLE_REFUSAL_RATE = 0.1
MIN_ACCEPTANCE_ANSWERABLE_JOINT_SUCCESS_RATE = 0.9
MIN_ACCEPTANCE_EXPECTED_KEYWORD_HIT_RATE = 0.9
MIN_ACCEPTANCE_NO_SOURCE_DENSE_EMPTY_RATE = 1.0


class RagEvaluationError(ValueError):
    """评测集格式、来源或执行参数不合法。"""


@dataclass(frozen=True, slots=True)
class RagEvaluationCase:
    case_id: str
    question: str
    categories: tuple[str, ...]
    filters: dict[str, object]
    expected_note_ids: tuple[int, ...]
    expected_heading_paths: tuple[tuple[str, ...], ...]
    acceptable_source_heading_paths: tuple[tuple[str, ...], ...]
    answerable: bool
    expected_keywords: tuple[str, ...]


def load_evaluation_cases(
    path: str | Path = DEFAULT_DATASET_PATH,
    *,
    enforce_default_coverage: bool = True,
) -> tuple[RagEvaluationCase, ...]:
    """加载严格 JSON 数据集，并拒绝重复 ID、未知字段和缺失覆盖类别。"""

    dataset_path = Path(path)
    try:
        payload = json.loads(dataset_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise RagEvaluationError('Evaluation dataset cannot be loaded.') from exc
    if not isinstance(payload, list):
        raise RagEvaluationError('Evaluation dataset must be a JSON array.')

    cases = tuple(_parse_case(item, index) for index, item in enumerate(payload, start=1))
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise RagEvaluationError('Evaluation case IDs must be unique.')
    if enforce_default_coverage:
        if not 30 <= len(cases) <= 50:
            raise RagEvaluationError('Default evaluation dataset must contain 30 to 50 cases.')
        categories = {category for case in cases for category in case.categories}
        missing = REQUIRED_CATEGORIES - categories
        if missing:
            raise RagEvaluationError(
                f'Evaluation dataset is missing categories: {", ".join(sorted(missing))}.'
            )
    return cases


def validate_evaluation_sources(cases: tuple[RagEvaluationCase, ...]) -> tuple[str, ...]:
    """确认标注的 Note 和标题路径仍存在，避免旧数据集产生虚假低分。"""

    expected_note_ids = {
        note_id
        for case in cases
        for note_id in case.expected_note_ids
    }
    current_note_ids = set(
        Note.objects.filter(
            pk__in=expected_note_ids,
            is_deleted=False,
            ai_indexing_enabled=True,
        ).values_list('pk', flat=True)
    )
    available_paths = {
        (parent.note_id, tuple(parent.heading_path))
        for parent in RagParentChunk.objects.filter(note_id__in=expected_note_ids)
    }

    errors = []
    for case in cases:
        missing_ids = set(case.expected_note_ids) - current_note_ids
        if missing_ids:
            errors.append(f'{case.case_id}: missing note IDs {sorted(missing_ids)}')
        for heading_path in case.expected_heading_paths:
            if not any(
                (note_id, heading_path) in available_paths
                for note_id in case.expected_note_ids
            ):
                errors.append(
                    f'{case.case_id}: missing heading path {list(heading_path)}'
                )
    return tuple(errors)


def evaluate_retrieval(
    cases: tuple[RagEvaluationCase, ...],
    *,
    retrieval: Callable[..., HybridRetrievalResult] = retrieve,
    top_k: int = 5,
    clock=perf_counter,
) -> dict[str, object]:
    """计算 Recall@K、目标命中、范围越界、降级率和平均检索耗时。"""

    if top_k < 1:
        raise RagEvaluationError('top_k must be positive.')

    recall_values = []
    note_hit_values = []
    section_recall_values = []
    durations = []
    scope_violations = 0
    returned_results = 0
    degraded_queries = 0
    unanswerable_empty = []
    no_source_dense_empty = []
    failed_case_ids = []
    note_miss_case_ids = []
    section_miss_case_ids = []
    scope_violation_case_ids = []
    unanswerable_nonempty_case_ids = []
    no_source_dense_nonempty_case_ids = []

    for case in cases:
        started = clock()
        try:
            result = retrieval(
                case.question,
                final_parent_top_k=top_k,
                **_retrieval_filters(case.filters),
            )
        except Exception:
            # 评测报告只记录 case ID，不把 Provider 或本地异常正文带入结果。
            failed_case_ids.append(case.case_id)
            durations.append((clock() - started) * 1000)
            continue
        durations.append((clock() - started) * 1000)
        degraded_queries += int(result.degraded)
        candidates = result.results[:top_k]
        returned_results += len(candidates)
        case_scope_violations = sum(
            _candidate_outside_scope(candidate, case.filters)
            for candidate in candidates
        )
        scope_violations += case_scope_violations
        if case_scope_violations:
            scope_violation_case_ids.append(case.case_id)

        expected_notes = set(case.expected_note_ids)
        hit_notes = {candidate.note_id for candidate in candidates}
        if expected_notes:
            recall_values.append(len(expected_notes & hit_notes) / len(expected_notes))
            note_hit = bool(expected_notes & hit_notes)
            note_hit_values.append(note_hit)
            if not note_hit:
                note_miss_case_ids.append(case.case_id)

        expected_paths = set(case.acceptable_source_heading_paths)
        if expected_paths:
            hit_paths = {candidate.heading_path for candidate in candidates}
            section_recall = len(expected_paths & hit_paths) / len(expected_paths)
            section_recall_values.append(section_recall)
            if section_recall < 1:
                section_miss_case_ids.append(case.case_id)
        if not case.answerable:
            unanswerable_empty.append(not candidates)
            if candidates:
                unanswerable_nonempty_case_ids.append(case.case_id)
            if not expected_notes:
                dense_empty = getattr(result, 'dense_candidate_count', 0) == 0
                no_source_dense_empty.append(dense_empty)
                if not dense_empty:
                    no_source_dense_nonempty_case_ids.append(case.case_id)

    return {
        'case_count': len(cases),
        'top_k': top_k,
        f'recall_at_{top_k}': _average(recall_values),
        'target_note_hit_rate': _average(note_hit_values),
        'target_section_hit_rate': _average(section_recall_values),
        'scope_violation_rate': (
            round(scope_violations / returned_results, 6)
            if returned_results
            else 0.0
        ),
        'unanswerable_empty_retrieval_rate': _average(unanswerable_empty),
        'no_source_dense_empty_rate': _average(no_source_dense_empty),
        'degraded_query_rate': round(degraded_queries / len(cases), 6) if cases else 0.0,
        'average_retrieval_ms': _average(durations, digits=3),
        'failed_case_ids': failed_case_ids,
        'note_miss_case_ids': note_miss_case_ids,
        'section_miss_case_ids': section_miss_case_ids,
        'scope_violation_case_ids': scope_violation_case_ids,
        'unanswerable_nonempty_case_ids': unanswerable_nonempty_case_ids,
        'no_source_dense_nonempty_case_ids': no_source_dense_nonempty_case_ids,
    }


def evaluate_answers(
    cases: tuple[RagEvaluationCase, ...],
    *,
    user,
    agent_runner: Callable[..., KnowledgeAgentResult] = run_knowledge_agent,
    clock=perf_counter,
) -> dict[str, object]:
    """计算来源正确率、可回答成功率、拒答率、关键词覆盖和回答耗时。"""

    correct_sources = 0
    total_sources = 0
    ungrounded_answers = 0
    answerable_successes = []
    answerable_refusals = []
    answerable_joint_successes = []
    unanswerable_refusals = []
    keyword_hits = []
    durations = []
    failed_case_ids = []
    incorrect_source_case_ids = []
    ungrounded_case_ids = []
    keyword_miss_case_ids = []
    answerable_refusal_case_ids = []
    answerable_joint_failure_case_ids = []
    unanswerable_not_refused_case_ids = []
    llm_usage_summaries: list[KnowledgeAgentLlmUsage] = []

    for case in cases:
        started = clock()
        try:
            result = agent_runner(
                case.question,
                user=user,
                filters=case.filters or None,
            )
        except KnowledgeAgentError:
            failed_case_ids.append(case.case_id)
            durations.append((clock() - started) * 1000)
            continue
        durations.append((clock() - started) * 1000)
        if result.llm_usage is not None:
            llm_usage_summaries.append(result.llm_usage)

        expected_notes = set(case.expected_note_ids)
        acceptable_paths = set(case.acceptable_source_heading_paths)
        valid_sources = [
            source
            for source in result.sources
            if source.note_id in expected_notes
            and (not acceptable_paths or source.heading_path in acceptable_paths)
        ]
        correct_sources += len(valid_sources)
        total_sources += len(result.sources)
        if len(valid_sources) != len(result.sources):
            incorrect_source_case_ids.append(case.case_id)

        if case.answerable:
            answered = not result.insufficient_context
            refused = result.insufficient_context and not result.sources
            all_sources_valid = (
                bool(result.sources) and len(valid_sources) == len(result.sources)
            )
            answerable_success = answered and all_sources_valid
            answerable_successes.append(answerable_success)
            answerable_refusals.append(refused)
            if refused:
                answerable_refusal_case_ids.append(case.case_id)
            if answered and not valid_sources:
                ungrounded_answers += 1
                ungrounded_case_ids.append(case.case_id)
            case_keyword_hits = [
                _answer_contains_keyword(result.answer, keyword)
                for keyword in case.expected_keywords
            ]
            keyword_hits.extend(case_keyword_hits)
            if not all(case_keyword_hits):
                keyword_miss_case_ids.append(case.case_id)
            joint_success = answerable_success and all(case_keyword_hits)
            answerable_joint_successes.append(joint_success)
            if not joint_success:
                answerable_joint_failure_case_ids.append(case.case_id)
        else:
            refused = result.insufficient_context and not result.sources
            unanswerable_refusals.append(refused)
            if not refused:
                ungrounded_answers += 1
                ungrounded_case_ids.append(case.case_id)
                unanswerable_not_refused_case_ids.append(case.case_id)

    completed = len(cases) - len(failed_case_ids)
    llm_usage_report = _aggregate_llm_usage(
        llm_usage_summaries,
        completed_case_count=completed,
    )
    return {
        'case_count': len(cases),
        'completed_case_count': completed,
        'source_accuracy': (
            round(correct_sources / total_sources, 6)
            if total_sources
            else 0.0
        ),
        'ungrounded_answer_rate': (
            round(ungrounded_answers / completed, 6)
            if completed
            else 0.0
        ),
        'answerable_success_rate': _average(answerable_successes),
        'answerable_refusal_rate': _average(answerable_refusals),
        'answerable_joint_success_rate': _average(answerable_joint_successes),
        'unanswerable_refusal_rate': _average(unanswerable_refusals),
        'expected_keyword_hit_rate': _average(keyword_hits),
        'average_answer_ms': _average(durations, digits=3),
        'p95_answer_ms': _percentile(durations, percentile=0.95, digits=3),
        **llm_usage_report,
        'failed_case_ids': failed_case_ids,
        'incorrect_source_case_ids': incorrect_source_case_ids,
        'ungrounded_case_ids': ungrounded_case_ids,
        'keyword_miss_case_ids': keyword_miss_case_ids,
        'answerable_refusal_case_ids': answerable_refusal_case_ids,
        'answerable_joint_failure_case_ids': answerable_joint_failure_case_ids,
        'unanswerable_not_refused_case_ids': unanswerable_not_refused_case_ids,
    }


def dataset_summary(cases: tuple[RagEvaluationCase, ...]) -> dict[str, object]:
    category_counts = Counter(category for case in cases for category in case.categories)
    return {
        'case_count': len(cases),
        'answerable_count': sum(case.answerable for case in cases),
        'unanswerable_count': sum(not case.answerable for case in cases),
        'category_counts': dict(sorted(category_counts.items())),
    }


def assess_rag_acceptance(
    retrieval_report: dict[str, object],
    answer_report: dict[str, object] | None,
) -> dict[str, object]:
    """按第 17、20 步门槛生成机器可判定的最终验收结论。"""

    checks = {
        'retrieval_recall_at_5': (
            retrieval_report.get('recall_at_5', 0) >= MIN_ACCEPTANCE_RECALL_AT_5
        ),
        'target_note_hit_rate': retrieval_report.get('target_note_hit_rate', 0) >= 0.9,
        'target_section_hit_rate': retrieval_report.get('target_section_hit_rate', 0) >= 0.9,
        'scope_violation_rate': retrieval_report.get('scope_violation_rate') == 0,
        'retrieval_failures': not retrieval_report.get('failed_case_ids'),
        'semantic_degradation_rate': retrieval_report.get('degraded_query_rate') == 0,
        'no_source_dense_empty_rate': (
            retrieval_report.get('no_source_dense_empty_rate', 0)
            >= MIN_ACCEPTANCE_NO_SOURCE_DENSE_EMPTY_RATE
        ),
        'answer_metrics_present': answer_report is not None,
    }
    if answer_report is not None:
        checks.update(
            {
                'source_accuracy': (
                    answer_report.get('source_accuracy', 0)
                    >= MIN_ACCEPTANCE_SOURCE_ACCURACY
                ),
                'ungrounded_answer_rate': (
                    answer_report.get('ungrounded_answer_rate')
                    == MAX_ACCEPTANCE_UNGROUNDED_ANSWER_RATE
                ),
                'answerable_success_rate': (
                    answer_report.get('answerable_success_rate', 0)
                    >= MIN_ACCEPTANCE_ANSWERABLE_SUCCESS_RATE
                ),
                'answerable_refusal_rate': (
                    answer_report.get('answerable_refusal_rate', 1)
                    <= MAX_ACCEPTANCE_ANSWERABLE_REFUSAL_RATE
                ),
                'answerable_joint_success_rate': (
                    answer_report.get('answerable_joint_success_rate', 0)
                    >= MIN_ACCEPTANCE_ANSWERABLE_JOINT_SUCCESS_RATE
                ),
                'expected_keyword_hit_rate': (
                    answer_report.get('expected_keyword_hit_rate', 0)
                    >= MIN_ACCEPTANCE_EXPECTED_KEYWORD_HIT_RATE
                ),
                'unanswerable_refusal_rate': (
                    answer_report.get('unanswerable_refusal_rate') == 1.0
                ),
                'answer_failures': not answer_report.get('failed_case_ids'),
            }
        )
    failed_checks = [name for name, passed in checks.items() if not passed]
    return {
        'complete': answer_report is not None,
        'passed': not failed_checks,
        'checks': checks,
        'failed_checks': failed_checks,
        'thresholds': {
            'minimum_recall_at_5': MIN_ACCEPTANCE_RECALL_AT_5,
            'minimum_source_accuracy': MIN_ACCEPTANCE_SOURCE_ACCURACY,
            'maximum_ungrounded_answer_rate': MAX_ACCEPTANCE_UNGROUNDED_ANSWER_RATE,
            'minimum_answerable_success_rate': MIN_ACCEPTANCE_ANSWERABLE_SUCCESS_RATE,
            'maximum_answerable_refusal_rate': MAX_ACCEPTANCE_ANSWERABLE_REFUSAL_RATE,
            'minimum_answerable_joint_success_rate': (
                MIN_ACCEPTANCE_ANSWERABLE_JOINT_SUCCESS_RATE
            ),
            'minimum_expected_keyword_hit_rate': MIN_ACCEPTANCE_EXPECTED_KEYWORD_HIT_RATE,
            'minimum_no_source_dense_empty_rate': MIN_ACCEPTANCE_NO_SOURCE_DENSE_EMPTY_RATE,
            'required_unanswerable_refusal_rate': 1.0,
            'required_scope_violation_rate': 0.0,
        },
    }


def _parse_case(payload: object, index: int) -> RagEvaluationCase:
    required_fields = {
        'id',
        'question',
        'categories',
        'filters',
        'expected_note_ids',
        'expected_heading_paths',
        'answerable',
        'expected_keywords',
    }
    optional_fields = {'acceptable_source_heading_paths'}
    if (
        not isinstance(payload, dict)
        or not required_fields.issubset(payload)
        or set(payload) - required_fields - optional_fields
    ):
        raise RagEvaluationError(f'Evaluation case {index} has invalid fields.')

    case_id = payload['id']
    question = payload['question']
    categories = payload['categories']
    filters = payload['filters']
    note_ids = payload['expected_note_ids']
    heading_paths = payload['expected_heading_paths']
    acceptable_source_paths = payload.get('acceptable_source_heading_paths', heading_paths)
    answerable = payload['answerable']
    keywords = payload['expected_keywords']
    if not isinstance(case_id, str) or not case_id.strip():
        raise RagEvaluationError(f'Evaluation case {index} has an invalid ID.')
    if not isinstance(question, str) or not question.strip():
        raise RagEvaluationError(f'Evaluation case {case_id} has an invalid question.')
    if (
        not isinstance(categories, list)
        or not categories
        or any(not isinstance(item, str) or not item for item in categories)
        or len(categories) != len(set(categories))
    ):
        raise RagEvaluationError(f'Evaluation case {case_id} has invalid categories.')
    _validate_filters(filters, case_id)
    if (
        not isinstance(note_ids, list)
        or any(not isinstance(item, int) or isinstance(item, bool) or item < 1 for item in note_ids)
        or len(note_ids) != len(set(note_ids))
    ):
        raise RagEvaluationError(f'Evaluation case {case_id} has invalid note IDs.')
    if not isinstance(heading_paths, list) or any(
        not isinstance(path, list)
        or not path
        or any(not isinstance(item, str) or not item for item in path)
        for path in heading_paths
    ):
        raise RagEvaluationError(f'Evaluation case {case_id} has invalid heading paths.')
    if not isinstance(acceptable_source_paths, list) or any(
        not isinstance(path, list)
        or not path
        or any(not isinstance(item, str) or not item for item in path)
        for path in acceptable_source_paths
    ):
        raise RagEvaluationError(
            f'Evaluation case {case_id} has invalid acceptable source paths.'
        )
    if not isinstance(answerable, bool):
        raise RagEvaluationError(f'Evaluation case {case_id} has invalid answerable value.')
    if (
        not isinstance(keywords, list)
        or any(not isinstance(item, str) or not item for item in keywords)
        or len(keywords) != len(set(keywords))
    ):
        raise RagEvaluationError(f'Evaluation case {case_id} has invalid keywords.')
    if answerable and (not note_ids or not heading_paths or not keywords):
        raise RagEvaluationError(
            f'Answerable evaluation case {case_id} requires source and keyword labels.'
        )
    return RagEvaluationCase(
        case_id=case_id.strip(),
        question=question.strip(),
        categories=tuple(categories),
        filters=dict(filters),
        expected_note_ids=tuple(note_ids),
        expected_heading_paths=tuple(tuple(path) for path in heading_paths),
        acceptable_source_heading_paths=tuple(
            tuple(path) for path in acceptable_source_paths
        ),
        answerable=answerable,
        expected_keywords=tuple(keywords),
    )


def _validate_filters(filters: object, case_id: str):
    if not isinstance(filters, dict) or set(filters) - ALLOWED_FILTER_KEYS:
        raise RagEvaluationError(f'Evaluation case {case_id} has invalid filters.')
    types = filters.get('types')
    if types is not None and (
        not isinstance(types, list)
        or not types
        or not set(types).issubset({'note', 'diary'})
        or len(types) != len(set(types))
    ):
        raise RagEvaluationError(f'Evaluation case {case_id} has invalid type filters.')
    tags = filters.get('tags')
    if tags is not None and (
        not isinstance(tags, list)
        or any(not isinstance(item, str) or not item for item in tags)
        or len(tags) != len(set(tags))
    ):
        raise RagEvaluationError(f'Evaluation case {case_id} has invalid tag filters.')
    for field_name in ('date_from', 'date_to'):
        value = filters.get(field_name)
        if value is not None:
            try:
                date.fromisoformat(value)
            except (TypeError, ValueError):
                raise RagEvaluationError(
                    f'Evaluation case {case_id} has an invalid date filter.'
                ) from None


def _retrieval_filters(filters: dict[str, object]) -> dict[str, object]:
    values = dict(filters)
    for field_name in ('date_from', 'date_to'):
        if values.get(field_name):
            values[field_name] = date.fromisoformat(values[field_name])
    return values


def _candidate_outside_scope(candidate, filters: dict[str, object]) -> bool:
    types = filters.get('types')
    if types and candidate.document_type not in types:
        return True
    date_from = filters.get('date_from')
    date_to = filters.get('date_to')
    if date_from and (candidate.diary_date is None or candidate.diary_date < date.fromisoformat(date_from)):
        return True
    if date_to and (candidate.diary_date is None or candidate.diary_date > date.fromisoformat(date_to)):
        return True
    return False


def _average(values, *, digits: int = 6) -> float:
    return round(sum(values) / len(values), digits) if values else 0.0


def _percentile(values: list[float], *, percentile: float, digits: int) -> float:
    if not values:
        return 0.0
    rank = max(1, int(len(values) * percentile + 0.999999))
    return round(sorted(values)[rank - 1], digits)


def _aggregate_llm_usage(
    summaries: list[KnowledgeAgentLlmUsage],
    *,
    completed_case_count: int,
) -> dict[str, object]:
    request_count = sum(summary.request_count for summary in summaries)
    reported_request_count = sum(
        summary.usage_reported_request_count for summary in summaries
    )
    usage_available = (
        completed_case_count > 0
        and len(summaries) == completed_case_count
        and request_count > 0
        and reported_request_count == request_count
        and all(summary.usage_status == 'available' for summary in summaries)
    )
    if usage_available:
        prompt_tokens = sum(summary.prompt_tokens for summary in summaries)
        completion_tokens = sum(summary.completion_tokens for summary in summaries)
        total_tokens = sum(summary.total_tokens for summary in summaries)
        return {
            'llm_request_count': request_count,
            'llm_usage_reported_request_count': reported_request_count,
            'llm_usage_status': 'available',
            'llm_prompt_tokens': prompt_tokens,
            'llm_completion_tokens': completion_tokens,
            'llm_total_tokens': total_tokens,
        }

    return {
        'llm_request_count': request_count,
        'llm_usage_reported_request_count': reported_request_count,
        'llm_usage_status': 'partial' if reported_request_count else 'unavailable',
        'llm_prompt_tokens': None,
        'llm_completion_tokens': None,
        'llm_total_tokens': None,
    }


def _answer_contains_keyword(answer: str, keyword: str) -> bool:
    # Inline-code formatting must not turn an exact technical term into a miss.
    normalized_answer = answer.replace('`', '').casefold()
    normalized_keyword = keyword.replace('`', '').casefold()
    return normalized_keyword in normalized_answer
