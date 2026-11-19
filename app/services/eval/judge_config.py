"""LLM Judge 默认模型与支持集合的统一配置入口。"""

from app.core.config import settings
from app.services.eval.judge_adapters import is_supported_judge_model


def resolve_default_judge_model() -> str:
    """返回唯一的 Judge 默认模型来源。"""
    return (
        settings.EVAL_JUDGE_MODEL
        or settings.EVAL_JUDGE_MODEL_DEFAULT
        or "deepseek-chat"
    )


def validate_judge_model(model: str) -> None:
    """校验模型是否受支持，失败抛出 ValueError。"""
    if not model:
        return
    if not is_supported_judge_model(model):
        raise ValueError(
            f"Unsupported judge model: {model}. "
            "Use a known model such as deepseek-chat, deepseek-reasoner, qwen-*, "
            "gpt-*, or glm-*."
        )


__all__ = [
    "resolve_default_judge_model",
    "validate_judge_model",
]
