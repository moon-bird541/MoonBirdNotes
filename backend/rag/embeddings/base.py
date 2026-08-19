"""Embedding 服务抽象与不包含敏感信息的结构化异常。"""

from abc import ABC, abstractmethod


class EmbeddingServiceError(RuntimeError):
    """所有 Embedding 故障的统一、可序列化错误边界。"""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        retryable: bool,
        provider: str = '',
        status_code: int | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.provider = provider
        self.status_code = status_code

    def as_dict(self) -> dict[str, str | bool | int | None]:
        """只暴露稳定分类和安全消息，供后续索引任务与检索降级判断。"""

        return {
            'code': self.code,
            'message': str(self),
            'retryable': self.retryable,
            'provider': self.provider,
            'status_code': self.status_code,
        }


class EmbeddingConfigurationError(EmbeddingServiceError):
    """Embedding 配置缺失或不合法。"""


class EmbeddingInputError(EmbeddingServiceError):
    """调用方提供了空文本、超长文本或错误输入类型。"""


class EmbeddingTransportError(EmbeddingServiceError):
    """请求超时或网络连接失败。"""


class EmbeddingProviderError(EmbeddingServiceError):
    """云端 Provider 返回非成功 HTTP 状态。"""


class EmbeddingResponseError(EmbeddingServiceError):
    """云端响应的数量、维度、索引或数值不符合契约。"""


class EmbeddingService(ABC):
    """业务层只依赖此接口，不直接依赖硅基流动请求细节。"""

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """按输入顺序返回一组文档向量。"""

    @abstractmethod
    def embed_query(self, query: str) -> list[float]:
        """返回单条查询向量。"""
