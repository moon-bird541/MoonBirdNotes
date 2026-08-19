"""Knowledge Agent API 的严格请求参数校验。"""

from collections.abc import Mapping

from django.conf import settings
from rest_framework import serializers

from .conversation import (
    MAX_HISTORY_MESSAGES,
    MAX_HISTORY_MESSAGE_CHARS,
    MAX_HISTORY_TOTAL_CHARS,
)


class StrictFieldsSerializer(serializers.Serializer):
    """拒绝未声明字段，避免客户端参数被静默忽略。"""

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            unknown_fields = sorted(set(data) - set(self.fields))
            if unknown_fields:
                raise serializers.ValidationError(
                    {
                        field_name: ['This field is not supported.']
                        for field_name in unknown_fields
                    }
                )
        return super().to_internal_value(data)


class ISODateStringField(serializers.DateField):
    """校验 ISO 日期，同时保留 Agent 工具 JSON Schema 所需的字符串类型。"""

    def to_internal_value(self, value):
        return super().to_internal_value(value).isoformat()


class StrictStringField(serializers.CharField):
    """拒绝 DRF 对数字等 JSON 类型的隐式字符串转换。"""

    def to_internal_value(self, value):
        if not isinstance(value, str):
            raise serializers.ValidationError('Expected a string.')
        return super().to_internal_value(value)


class KnowledgeFiltersSerializer(StrictFieldsSerializer):
    types = serializers.ListField(
        child=serializers.ChoiceField(choices=('note', 'diary')),
        min_length=1,
        max_length=2,
        required=False,
    )
    tags = serializers.ListField(
        child=StrictStringField(min_length=1, max_length=50, trim_whitespace=True),
        max_length=20,
        required=False,
    )
    date_from = ISODateStringField(required=False, allow_null=True)
    date_to = ISODateStringField(required=False, allow_null=True)

    def validate(self, attrs):
        for field_name in ('types', 'tags'):
            values = attrs.get(field_name)
            if values is not None and len(values) != len(set(values)):
                raise serializers.ValidationError(
                    {field_name: ['Duplicate values are not allowed.']}
                )

        date_from = attrs.get('date_from')
        date_to = attrs.get('date_to')
        if date_from and date_to and date_from > date_to:
            raise serializers.ValidationError(
                {'date_to': ['date_to must not be earlier than date_from.']}
            )
        return attrs


class ConversationTurnSerializer(StrictFieldsSerializer):
    """客户端只能传当前对话框中的用户和助手纯文本消息。"""

    role = serializers.ChoiceField(choices=('user', 'assistant'))
    content = StrictStringField(
        allow_blank=False,
        trim_whitespace=True,
        max_length=MAX_HISTORY_MESSAGE_CHARS,
    )


class KnowledgeChatRequestSerializer(StrictFieldsSerializer):
    message = StrictStringField(allow_blank=False, trim_whitespace=True)
    filters = KnowledgeFiltersSerializer(required=False)
    history = ConversationTurnSerializer(
        many=True,
        required=False,
        max_length=MAX_HISTORY_MESSAGES,
    )
    # 持久化会话存在时，服务端从数据库加载可信历史并忽略客户端 history。
    conversation_id = serializers.UUIDField(required=False)
    # 旧客户端兼容字段；持久化历史使用 conversation_id。
    session_id = serializers.UUIDField(required=False)

    def validate_message(self, value):
        maximum = settings.AGENT_KNOWLEDGE_MAX_INPUT_CHARS
        if len(value) > maximum:
            raise serializers.ValidationError(
                f'Ensure this field has no more than {maximum} characters.'
            )
        return value

    def validate_history(self, value):
        if sum(len(item['content']) for item in value) > MAX_HISTORY_TOTAL_CHARS:
            raise serializers.ValidationError('Conversation history is too long.')
        return value


class KnowledgeTokenUsageQuerySerializer(StrictFieldsSerializer):
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    page = serializers.IntegerField(default=1, min_value=1)
    page_size = serializers.IntegerField(default=20, min_value=1, max_value=100)

    def validate(self, attrs):
        date_from = attrs.get('date_from')
        date_to = attrs.get('date_to')
        if date_from and date_to and date_from > date_to:
            raise serializers.ValidationError(
                {'date_to': ['date_to must not be earlier than date_from.']}
            )
        return attrs
