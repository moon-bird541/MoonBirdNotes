from django.apps import AppConfig


class RagConfig(AppConfig):
    """注册不依赖 LLM 的 RAG 数据与检索应用。"""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'rag'

    def ready(self):
        # 导入即注册信号；保持在 ready 中可避免 Django App 尚未加载完成时访问模型。
        from . import signals  # noqa: F401
