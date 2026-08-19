"""Knowledge Agent 六个只读工具的允许列表、执行器和安全日志。"""

from __future__ import annotations

import logging
from datetime import date
from time import perf_counter

from rag.services import (
    HybridRetrievalError,
    KnowledgeReadError,
    list_knowledge_tags,
    read_current_parent_chunks,
    read_diary_by_date,
    read_note,
    read_note_section,
    retrieve,
)

from .base import (
    MAX_TOOL_OUTPUT_TEXT_CHARS,
    ToolExecutionResult,
    ToolSchemaError,
    ToolSpec,
    limit_output_text,
    validate_tool_arguments,
)


logger = logging.getLogger(__name__)
KNOWLEDGE_WRITE_TOOL_NAMES: tuple[str, ...] = ()
MAX_SEARCH_TOP_K = 10
MAX_PARENT_IDS = 10
MAX_TAG_RESULTS = 100
SOURCE_HASH_PATTERN = '^[0-9a-f]{64}$'


def _object_schema(properties, *, required=()):
    return {
        'type': 'object',
        'properties': properties,
        'required': list(required),
        'additionalProperties': False,
    }


SEARCH_NOTES_SCHEMA = _object_schema(
    {
        'query': {'type': 'string', 'minLength': 1, 'maxLength': 500},
        'types': {
            'type': 'array',
            'items': {'type': 'string', 'enum': ['note', 'diary']},
            'minItems': 1,
            'maxItems': 2,
            'uniqueItems': True,
        },
        'tags': {
            'type': 'array',
            'items': {'type': 'string', 'minLength': 1, 'maxLength': 50},
            'maxItems': 20,
            'uniqueItems': True,
        },
        'date_from': {'type': ['string', 'null'], 'format': 'date'},
        'date_to': {'type': ['string', 'null'], 'format': 'date'},
        'dense_top_k': {'type': 'integer', 'minimum': 1, 'maximum': 100},
        'keyword_top_k': {'type': 'integer', 'minimum': 1, 'maximum': 100},
        'top_k': {'type': 'integer', 'minimum': 1, 'maximum': MAX_SEARCH_TOP_K},
    },
    required=('query',),
)

GET_PARENT_CHUNKS_SCHEMA = _object_schema(
    {
        'parent_ids': {
            'type': 'array',
            'items': {'type': 'string', 'format': 'uuid'},
            'minItems': 1,
            'maxItems': MAX_PARENT_IDS,
            'uniqueItems': True,
        }
    },
    required=('parent_ids',),
)

GET_NOTE_SCHEMA = _object_schema(
    {
        'note_id': {'type': 'integer', 'minimum': 1},
        'source_hash': {
            'type': ['string', 'null'],
            'pattern': SOURCE_HASH_PATTERN,
        },
    },
    required=('note_id',),
)

GET_NOTE_SECTION_SCHEMA = _object_schema(
    {
        'note_id': {'type': 'integer', 'minimum': 1},
        'heading_path': {
            'type': 'array',
            'items': {'type': 'string', 'minLength': 1, 'maxLength': 255},
            'minItems': 1,
            'maxItems': 6,
        },
        'source_hash': {
            'type': ['string', 'null'],
            'pattern': SOURCE_HASH_PATTERN,
        },
    },
    required=('note_id', 'heading_path'),
)

GET_DIARY_BY_DATE_SCHEMA = _object_schema(
    {'diary_date': {'type': 'string', 'format': 'date'}},
    required=('diary_date',),
)

LIST_TAGS_SCHEMA = _object_schema(
    {
        'query': {'type': 'string', 'maxLength': 50},
        'limit': {'type': 'integer', 'minimum': 1, 'maximum': MAX_TAG_RESULTS},
    }
)


def _search_notes(arguments: dict[str, object]) -> dict[str, object]:
    result = retrieve(
        arguments['query'],
        types=arguments.get('types'),
        tags=arguments.get('tags'),
        date_from=_optional_date(arguments.get('date_from')),
        date_to=_optional_date(arguments.get('date_to')),
        dense_top_k=arguments.get('dense_top_k', 20),
        keyword_top_k=arguments.get('keyword_top_k', 20),
        final_parent_top_k=arguments.get('top_k', 5),
    )
    payload = result.as_dict()
    # 持久化父片段通过 get_parent_chunks 读取；无活动索引的临时章节没有可复用 UUID，
    # 因此保留其已校验正文，并继续受统一工具输出预算约束。
    for item in payload['results']:
        if item.get('parent_id') is not None:
            item.pop('content', None)
    return payload


def _get_parent_chunks(arguments: dict[str, object]) -> dict[str, object]:
    return read_current_parent_chunks(tuple(arguments['parent_ids']))


def _get_note(arguments: dict[str, object]) -> dict[str, object]:
    return read_note(
        arguments['note_id'],
        expected_source_hash=arguments.get('source_hash'),
    )


def _get_note_section(arguments: dict[str, object]) -> dict[str, object]:
    return read_note_section(
        arguments['note_id'],
        tuple(arguments['heading_path']),
        expected_source_hash=arguments.get('source_hash'),
    )


def _get_diary_by_date(arguments: dict[str, object]) -> dict[str, object]:
    return read_diary_by_date(date.fromisoformat(arguments['diary_date']))


def _list_tags(arguments: dict[str, object]) -> dict[str, object]:
    return list_knowledge_tags(
        query=arguments.get('query', ''),
        limit=arguments.get('limit', 50),
    )


KNOWLEDGE_TOOL_SPECS: dict[str, ToolSpec] = {
    spec.name: spec
    for spec in (
        ToolSpec(
            name='search_notes',
            description='Search current authorized notes and diaries and return source candidates.',
            parameters=SEARCH_NOTES_SCHEMA,
            handler=_search_notes,
        ),
        ToolSpec(
            name='get_parent_chunks',
            description='Read current parent chunk context for one or more search results.',
            parameters=GET_PARENT_CHUNKS_SCHEMA,
            handler=_get_parent_chunks,
        ),
        ToolSpec(
            name='get_note',
            description='Read the latest current Markdown for one ordinary note.',
            parameters=GET_NOTE_SCHEMA,
            handler=_get_note,
        ),
        ToolSpec(
            name='get_note_section',
            description='Read one exact heading path from the latest ordinary note Markdown.',
            parameters=GET_NOTE_SECTION_SCHEMA,
            handler=_get_note_section,
        ),
        ToolSpec(
            name='get_diary_by_date',
            description='Read the current diary for an exact date.',
            parameters=GET_DIARY_BY_DATE_SCHEMA,
            handler=_get_diary_by_date,
        ),
        ToolSpec(
            name='list_tags',
            description='List tags used by current authorized ordinary notes.',
            parameters=LIST_TAGS_SCHEMA,
            handler=_list_tags,
        ),
    )
}
KNOWLEDGE_READ_TOOL_NAMES = tuple(KNOWLEDGE_TOOL_SPECS)


def get_knowledge_tool_definitions() -> tuple[dict[str, object], ...]:
    return tuple(spec.as_function_definition() for spec in KNOWLEDGE_TOOL_SPECS.values())


def execute_knowledge_tool(
    tool_name: str,
    arguments: object,
    *,
    user,
) -> ToolExecutionResult:
    """只允许当前管理员调用固定只读工具，并统一记录安全执行摘要。"""

    started = perf_counter()
    result: ToolExecutionResult
    if not getattr(user, 'is_authenticated', False):
        result = _error_result(
            tool_name,
            code='authentication_required',
            category='unauthorized',
            message='Authentication is required for knowledge tools.',
        )
    elif not getattr(user, 'is_active', False) or not getattr(user, 'is_staff', False):
        result = _error_result(
            tool_name,
            code='permission_denied',
            category='forbidden',
            message='The current user cannot use knowledge tools.',
        )
    elif tool_name not in KNOWLEDGE_TOOL_SPECS:
        result = _error_result(
            tool_name,
            code='tool_not_allowed',
            category='forbidden',
            message='This tool is not allowed for the Knowledge Agent.',
        )
    else:
        spec = KNOWLEDGE_TOOL_SPECS[tool_name]
        try:
            validate_tool_arguments(spec.parameters, arguments)
            data = spec.handler(arguments)
            limited, truncated, text_characters = limit_output_text(data)
            result = ToolExecutionResult(
                ok=True,
                tool_name=tool_name,
                data=limited,
                error=None,
                meta={
                    'duration_ms': 0,
                    'result_count': _result_count(tool_name, limited),
                    'text_characters': text_characters,
                    'max_text_characters': MAX_TOOL_OUTPUT_TEXT_CHARS,
                    'truncated': truncated,
                    'read_only': True,
                    'content_is_untrusted': True,
                },
            )
        except ToolSchemaError as exc:
            result = _error_result(
                tool_name,
                code='invalid_arguments',
                category='invalid_request',
                message=str(exc),
            )
        except HybridRetrievalError as exc:
            result = _error_result(
                tool_name,
                code=exc.code,
                category='invalid_request',
                message=str(exc),
            )
        except KnowledgeReadError as exc:
            result = _error_result(
                tool_name,
                code=exc.code,
                category=exc.category,
                message=str(exc),
                retryable=exc.retryable,
            )
        except Exception:
            # 不把数据库、本地路径、Provider 响应或其他内部异常返回给 Agent。
            result = _error_result(
                tool_name,
                code='tool_system_error',
                category='system',
                message='Knowledge tool execution failed.',
                retryable=True,
            )

    duration_ms = round((perf_counter() - started) * 1000, 3)
    result.meta['duration_ms'] = duration_ms
    _log_execution(result, user=user, arguments=arguments)
    return result


def _error_result(
    tool_name: str,
    *,
    code: str,
    category: str,
    message: str,
    retryable: bool = False,
) -> ToolExecutionResult:
    return ToolExecutionResult(
        ok=False,
        tool_name=tool_name,
        data=None,
        error={
            'code': code,
            'category': category,
            'message': message,
            'retryable': retryable,
        },
        meta={
            'duration_ms': 0,
            'result_count': 0,
            'text_characters': 0,
            'max_text_characters': MAX_TOOL_OUTPUT_TEXT_CHARS,
            'truncated': False,
            'read_only': True,
            'content_is_untrusted': True,
        },
    )


def _optional_date(value: object) -> date | None:
    return date.fromisoformat(value) if value else None


def _result_count(tool_name: str, data: dict[str, object]) -> int:
    collection_field = {
        'search_notes': 'results',
        'get_parent_chunks': 'chunks',
        'list_tags': 'tags',
    }.get(tool_name)
    if collection_field and isinstance(data.get(collection_field), list):
        return len(data[collection_field])
    return 1


def _argument_summary(arguments: object) -> dict[str, object]:
    if not isinstance(arguments, dict):
        return {'argument_type': type(arguments).__name__}
    summary = {'argument_keys': sorted(arguments)}
    if isinstance(arguments.get('query'), str):
        summary['query_length'] = len(arguments['query'])
    if isinstance(arguments.get('parent_ids'), list):
        summary['parent_id_count'] = len(arguments['parent_ids'])
    if isinstance(arguments.get('heading_path'), list):
        summary['heading_depth'] = len(arguments['heading_path'])
    for field_name in ('top_k', 'dense_top_k', 'keyword_top_k', 'limit'):
        if isinstance(arguments.get(field_name), int):
            summary[field_name] = arguments[field_name]
    return summary


def _log_execution(result: ToolExecutionResult, *, user, arguments: object):
    logger.info(
        'Knowledge tool execution completed.',
        extra={
            'tool_name': result.tool_name,
            'user_id': getattr(user, 'pk', None),
            'status': 'success' if result.ok else 'error',
            'error_code': result.error['code'] if result.error else '',
            'duration_ms': result.meta['duration_ms'],
            'result_count': result.meta['result_count'],
            'truncated': result.meta['truncated'],
            'argument_summary': _argument_summary(arguments),
        },
    )
