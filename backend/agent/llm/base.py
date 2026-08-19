"""Knowledge Agent 主对话模型的最小接口与安全错误边界。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


class ChatModelError(RuntimeError):
    def __init__(self, *, code: str, message: str, retryable: bool):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class ChatToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True, slots=True)
class ChatTokenUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    def __post_init__(self):
        token_values = (
            self.prompt_tokens,
            self.completion_tokens,
            self.total_tokens,
        )
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in token_values
        ):
            raise ValueError('Chat token counts must be non-negative integers.')
        if self.total_tokens < self.prompt_tokens + self.completion_tokens:
            raise ValueError('Chat total_tokens cannot be smaller than component counts.')
    def as_dict(self) -> dict[str, object]:
        return {
            'prompt_tokens': self.prompt_tokens,
            'completion_tokens': self.completion_tokens,
            'total_tokens': self.total_tokens,
        }


@dataclass(frozen=True, slots=True)
class ChatCompletion:
    content: str
    tool_calls: tuple[ChatToolCall, ...]
    finish_reason: str
    usage: ChatTokenUsage | None = None


class ChatModel(ABC):
    @abstractmethod
    def complete(
        self,
        messages: list[dict[str, object]],
        *,
        tools: tuple[dict[str, object], ...] = (),
    ) -> ChatCompletion:
        """返回一轮助手文本或工具调用。"""
