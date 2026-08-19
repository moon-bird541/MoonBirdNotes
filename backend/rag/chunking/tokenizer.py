"""与 Embedding 模型匹配的 token 计数接口。"""

from functools import lru_cache
from pathlib import Path
from typing import Protocol

from tokenizers import Tokenizer


DEFAULT_TOKENIZER_MODEL = 'BAAI/bge-m3'


class TokenCounter(Protocol):
    """父子分块只依赖计数协议，不直接依赖具体 tokenizer 库。"""

    def count_tokens(self, text: str) -> int:
        """返回模型实际输入包含的 token 数。"""


class TokenizerLoadError(RuntimeError):
    """匹配 Embedding 模型的 tokenizer 无法加载。"""


@lru_cache(maxsize=4)
def _load_tokenizer(model_name: str, tokenizer_file: str | None) -> Tokenizer:
    """在进程内复用 tokenizer，避免每次分块重复加载 17 MB 配置。"""

    try:
        if tokenizer_file:
            return Tokenizer.from_file(tokenizer_file)
        return Tokenizer.from_pretrained(model_name)
    except Exception as exc:
        raise TokenizerLoadError(
            f'无法加载 {model_name} tokenizer，请预先缓存模型文件或配置本地 tokenizer 文件。'
        ) from exc


class BgeM3TokenCounter:
    """使用 BAAI/bge-m3 tokenizer 计算云端 Embedding 输入长度。

    这里只加载 tokenizer 文件，不加载模型权重；实际向量仍由硅基流动生成。
    """

    def __init__(
        self,
        model_name: str = DEFAULT_TOKENIZER_MODEL,
        tokenizer_file: str | Path | None = None,
        *,
        tokenizer: Tokenizer | None = None,
    ):
        self.model_name = model_name
        self.tokenizer_file = str(tokenizer_file) if tokenizer_file else None
        # 注入入口只服务测试或已由调用方管理的 tokenizer 实例。
        self._injected_tokenizer = tokenizer

    @property
    def tokenizer(self) -> Tokenizer:
        if self._injected_tokenizer is not None:
            return self._injected_tokenizer
        return _load_tokenizer(self.model_name, self.tokenizer_file)

    def count_tokens(self, text: str) -> int:
        if not isinstance(text, str):
            raise TypeError('text must be a string.')
        if not text:
            return 0
        # tokenizer.json 的 post-processor 会计入 <s> 与 </s> 等模型特殊 token。
        return len(self.tokenizer.encode(text).ids)
