from django.apps import AppConfig


class AgentConfig(AppConfig):
    """注册只通过受控工具调用业务服务的 Agent 应用。"""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'agent'
