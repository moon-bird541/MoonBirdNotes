"""Agent 工具的严格参数校验、结构化结果和输出文本预算。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Callable
from uuid import UUID


MAX_TOOL_OUTPUT_TEXT_CHARS = 12000
LONG_TEXT_FIELDS = frozenset(
    {
        'content',
        'markdown_content',
        'matched_child_excerpt',
        'summary',
        'mood',
        'weather',
    }
)


class ToolSchemaError(ValueError):
    """工具参数不满足已发布 JSON Schema。"""


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, object]
    handler: Callable[[dict[str, object]], dict[str, object]]
    risk_level: str = 'read_only'

    def as_function_definition(self) -> dict[str, object]:
        """输出支持严格 Tool Calling 的标准函数定义。"""

        return {
            'type': 'function',
            'function': {
                'name': self.name,
                'description': self.description,
                'parameters': self.parameters,
                'strict': True,
            },
        }


@dataclass(frozen=True, slots=True)
class ToolExecutionResult:
    ok: bool
    tool_name: str
    data: dict[str, object] | None
    error: dict[str, object] | None
    meta: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            'ok': self.ok,
            'tool_name': self.tool_name,
            'data': self.data,
            'error': self.error,
            'meta': self.meta,
        }


def validate_tool_arguments(schema: dict[str, object], arguments: object):
    """校验本项目工具使用的 JSON Schema 子集，并拒绝任何额外字段。"""

    if not isinstance(arguments, dict):
        raise ToolSchemaError('Tool arguments must be a JSON object.')
    properties = schema.get('properties', {})
    required = set(schema.get('required', ()))
    allowed = set(properties)
    missing = required - set(arguments)
    extra = set(arguments) - allowed
    if missing:
        raise ToolSchemaError(f'Missing required arguments: {", ".join(sorted(missing))}.')
    if extra:
        raise ToolSchemaError(f'Unknown arguments: {", ".join(sorted(extra))}.')

    for field_name, value in arguments.items():
        _validate_schema_value(field_name, value, properties[field_name])


def limit_output_text(
    payload: dict[str, object],
    *,
    maximum: int = MAX_TOOL_OUTPUT_TEXT_CHARS,
) -> tuple[dict[str, object], bool, int]:
    """优先压缩正文类字段，同时保证所有字符串总量不超过硬上限。"""

    structural_chars = _count_text(payload, include_long=False)
    limit_all_strings = structural_chars > maximum
    remaining = maximum if limit_all_strings else maximum - structural_chars
    value_count = _count_limited_values(payload, limit_all_strings=limit_all_strings)
    state = {
        'remaining': max(0, remaining),
        'value_count': value_count,
        'truncated': False,
    }
    limited = _limit_value(
        payload,
        state,
        field_name=None,
        limit_all_strings=limit_all_strings,
    )
    text_characters = _count_text(limited, include_long=True)
    return limited, bool(state['truncated']), text_characters


def _validate_schema_value(field_name: str, value: object, rule: dict[str, object]):
    expected_types = rule.get('type')
    if isinstance(expected_types, str):
        expected_types = [expected_types]
    if expected_types and not any(_matches_type(value, item) for item in expected_types):
        raise ToolSchemaError(f'{field_name} has an invalid type.')
    if value is None:
        return
    if 'enum' in rule and value not in rule['enum']:
        raise ToolSchemaError(f'{field_name} has an unsupported value.')

    if isinstance(value, str):
        if len(value) < rule.get('minLength', 0) or len(value) > rule.get(
            'maxLength', len(value)
        ):
            raise ToolSchemaError(f'{field_name} has an invalid length.')
        if pattern := rule.get('pattern'):
            if re.fullmatch(pattern, value) is None:
                raise ToolSchemaError(f'{field_name} has an invalid format.')
        _validate_string_format(field_name, value, rule.get('format'))
    elif isinstance(value, int) and not isinstance(value, bool):
        if value < rule.get('minimum', value) or value > rule.get('maximum', value):
            raise ToolSchemaError(f'{field_name} is outside the allowed range.')
    elif isinstance(value, list):
        if len(value) < rule.get('minItems', 0) or len(value) > rule.get(
            'maxItems', len(value)
        ):
            raise ToolSchemaError(f'{field_name} has an invalid item count.')
        if rule.get('uniqueItems') and any(item in value[:index] for index, item in enumerate(value)):
            raise ToolSchemaError(f'{field_name} must not contain duplicates.')
        item_rule = rule.get('items')
        if item_rule:
            for index, item in enumerate(value):
                _validate_schema_value(f'{field_name}[{index}]', item, item_rule)


def _matches_type(value: object, expected: str) -> bool:
    return {
        'null': value is None,
        'string': isinstance(value, str),
        'integer': isinstance(value, int) and not isinstance(value, bool),
        'array': isinstance(value, list),
        'object': isinstance(value, dict),
        'boolean': isinstance(value, bool),
    }.get(expected, False)


def _validate_string_format(field_name: str, value: str, string_format: object):
    try:
        if string_format == 'date':
            date.fromisoformat(value)
        elif string_format == 'uuid':
            UUID(value)
    except ValueError:
        raise ToolSchemaError(f'{field_name} has an invalid format.') from None


def _count_text(value: object, *, include_long: bool, field_name: str | None = None) -> int:
    if isinstance(value, str):
        return len(value) if include_long or field_name not in LONG_TEXT_FIELDS else 0
    if isinstance(value, dict):
        return sum(
            _count_text(item, include_long=include_long, field_name=key)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return sum(
            _count_text(item, include_long=include_long, field_name=field_name)
            for item in value
        )
    return 0


def _count_limited_values(
    value: object,
    *,
    limit_all_strings: bool,
    field_name: str | None = None,
) -> int:
    if isinstance(value, str):
        return int(limit_all_strings or field_name in LONG_TEXT_FIELDS)
    if isinstance(value, dict):
        return sum(
            _count_limited_values(
                item,
                limit_all_strings=limit_all_strings,
                field_name=key,
            )
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return sum(
            _count_limited_values(
                item,
                limit_all_strings=limit_all_strings,
                field_name=field_name,
            )
            for item in value
        )
    return 0


def _limit_value(
    value: object,
    state: dict[str, int | bool],
    *,
    field_name: str | None,
    limit_all_strings: bool,
):
    if isinstance(value, str):
        if not limit_all_strings and field_name not in LONG_TEXT_FIELDS:
            return value
        count = int(state['value_count'])
        allowance = int(state['remaining']) // count if count else 0
        taken = min(len(value), allowance)
        state['remaining'] = int(state['remaining']) - taken
        state['value_count'] = max(0, count - 1)
        if taken < len(value):
            state['truncated'] = True
            return value[: max(0, taken - 1)] + ('…' if taken else '')
        return value
    if isinstance(value, dict):
        return {
            key: _limit_value(
                item,
                state,
                field_name=key,
                limit_all_strings=limit_all_strings,
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [
            _limit_value(
                item,
                state,
                field_name=field_name,
                limit_all_strings=limit_all_strings,
            )
            for item in value
        ]
    return value
