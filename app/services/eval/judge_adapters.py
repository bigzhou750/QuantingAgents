"""LLM Judge 的 provider adapter 层。"""

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Optional

logger = logging.getLogger(__name__)


class JudgeLLMClient(ABC):
    """Judge 调用通道的统一接口。"""

    model: str
    provider: str

    @abstractmethod
    def is_available(self) -> bool:
        """返回当前 provider 是否可调用。"""

    @abstractmethod
    def availability_reason(self) -> str:
        """返回不可用时的可读原因。"""

    @abstractmethod
    async def generate(self, prompt: str) -> str:
        """调用模型并返回原始文本。"""


class DashScopeJudgeClient(JudgeLLMClient):
    """保留现有 dashscope SDK 调用，作为兼容 adapter。"""

    def __init__(self, model: str):
        self.model = model
        self.provider = "qwen"
        self.name = "dashscope"

    def is_available(self) -> bool:
        try:
            import dashscope  # noqa: F401
            return True
        except ImportError:
            return False

    def availability_reason(self) -> str:
        if not self.is_available():
            return "dashscope SDK 未安装"
        if not os.environ.get("DASHSCOPE_API_KEY"):
            return "DASHSCOPE_API_KEY 未配置"
        return ""

    async def generate(self, prompt: str) -> str:
        if not self.is_available():
            raise RuntimeError(f"Judge adapter unavailable: {self.availability_reason()}")
        try:
            from dashscope import Generation

            response = Generation.call(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                result_format="message",
                temperature=0.1,
            )
            if response.status_code == 200:
                return response.output.choices[0].message.content
            raise RuntimeError(
                f"DashScope API error: {response.code} - {response.message}"
            )
        except ImportError:
            raise RuntimeError("dashscope SDK not available, judge scoring is not configured")


class OpenAICompatibleJudgeClient(JudgeLLMClient):
    """通过统一 LangChain 客户端调用 OpenAI-compatible provider。"""

    def __init__(
        self,
        model: str,
        provider: str = "openai",
        base_url: Optional[str] = None,
    ):
        self.model = model
        self.provider = provider
        self.name = "openai_compatible"
        self.base_url = base_url

    def _get_llm(self) -> Any:
        from tradingagents.llm_clients import create_llm_client

        client = create_llm_client(
            provider=self.provider,
            model=self.model,
            base_url=self.base_url,
            temperature=0.1,
        )
        return client.get_llm()

    def is_available(self) -> bool:
        try:
            self._get_llm()
            return True
        except Exception as exc:
            logger.debug("Judge adapter %s unavailable: %s", self.name, exc)
            return False

    def availability_reason(self) -> str:
        if self.provider == "deepseek" and not os.environ.get("DEEPSEEK_API_KEY"):
            return "DEEPSEEK_API_KEY 未配置"
        if self.provider == "openai" and not os.environ.get("OPENAI_API_KEY"):
            return "OPENAI_API_KEY 未配置"
        if not self.is_available():
            return f"{self.provider} adapter 初始化失败"
        return ""

    async def generate(self, prompt: str) -> str:
        reason = self.availability_reason()
        if reason:
            raise RuntimeError(f"Judge adapter unavailable: {reason}")
        llm = self._get_llm()
        response = await llm.ainvoke([{"role": "user", "content": prompt}])
        content = getattr(response, "content", response)
        if isinstance(content, list):
            texts = [
                item.get("text", "")
                if isinstance(item, dict)
                else str(item)
                for item in content
            ]
            content = "\n".join(text for text in texts if text)
        return str(content).strip()


class DeepSeekJudgeClient(OpenAICompatibleJudgeClient):
    """DeepSeek 专用 OpenAI-compatible adapter。"""

    def __init__(self, model: str):
        super().__init__(model=model, provider="deepseek")
        self.name = "deepseek"


def resolve_provider_for_model(model: str) -> str:
    """根据模型名推断默认 provider。"""
    lowered = str(model or "").lower()
    if lowered.startswith("deepseek-"):
        return "deepseek"
    if lowered.startswith("qwen-"):
        return "qwen"
    if lowered.startswith("glm-"):
        return "glm"
    if lowered.startswith(("gpt-", "o1-", "o3-", "o4-")):
        return "openai"
    return "openai"


def is_supported_judge_model(model: str) -> bool:
    """判断 judge 模型名是否在受支持集合内。"""
    model = str(model or "").strip()
    if not model:
        return False
    provider = resolve_provider_for_model(model)
    if provider == "deepseek":
        return model in {"deepseek-chat", "deepseek-reasoner"}
    if provider == "qwen":
        return model.startswith("qwen-")
    if provider == "glm":
        return model.startswith("glm-")
    if provider == "openai":
        return model.startswith(("gpt-", "o1-", "o3-", "o4-"))
    return True


def create_judge_client(
    model: str,
    provider: Optional[str] = None,
    adapter: Optional[JudgeLLMClient] = None,
) -> JudgeLLMClient:
    """创建 Judge client；优先使用注入的 mock adapter。"""
    if adapter is not None:
        return adapter
    resolved_provider = (provider or resolve_provider_for_model(model)).lower()
    if resolved_provider in {"qwen", "dashscope"}:
        return DashScopeJudgeClient(model)
    if resolved_provider == "deepseek":
        return DeepSeekJudgeClient(model)
    return OpenAICompatibleJudgeClient(model, provider=resolved_provider)
