"""LLM Judge 统一模型通道测试。"""

import json

import pytest
from pydantic import ValidationError

from app.models.eval import ScoreStatus


def test_resolve_default_judge_model_uses_unified_config():
    from app.core.config import settings
    from app.services.eval.judge_config import resolve_default_judge_model

    model = resolve_default_judge_model()
    assert model
    assert model == (settings.EVAL_JUDGE_MODEL or settings.EVAL_JUDGE_MODEL_DEFAULT)


def test_supported_judge_model_validation():
    from app.services.eval.judge_adapters import is_supported_judge_model

    assert is_supported_judge_model("deepseek-chat")
    assert is_supported_judge_model("deepseek-reasoner")
    assert is_supported_judge_model("qwen-plus")
    assert not is_supported_judge_model("some-unknown-model")


def test_run_create_request_rejects_unsupported_judge_model():
    from app.routers.eval import RunCreateRequest

    with pytest.raises(ValidationError):
        RunCreateRequest(dataset_id="ds_1", judge_model="some-unknown-model")


class _MockJudgeAdapter:
    name = "mock"
    provider = "mock"
    model = "mock-judge"

    def is_available(self) -> bool:
        return True

    def availability_reason(self) -> str:
        return ""

    async def generate(self, prompt: str) -> str:
        return json.dumps(
            {
                "dimensions": [],
                "overall_score": 0.8,
                "overall_reason": "ok",
            },
            ensure_ascii=False,
        )


class _MockUnavailableAdapter(_MockJudgeAdapter):
    def is_available(self) -> bool:
        return False

    def availability_reason(self) -> str:
        return "mock credentials missing"

    async def generate(self, prompt: str) -> str:
        raise RuntimeError("should not be called")


@pytest.mark.asyncio
async def test_injected_mock_adapter_records_adapter_and_latency():
    from app.services.eval.scorers.llm_judge_scorer import LLMJudgeScorer

    scorer = LLMJudgeScorer(judge_model="mock-judge", adapter=_MockJudgeAdapter())
    result = await scorer.score(
        {
            "input_data": {"prompt": "分析"},
            "output_data": {"content": "输出"},
        },
        [],
        {"expected_output": {"must_include": ["营收"]}},
    )
    assert result.raw_output["judge_model"] == "mock-judge"
    assert result.raw_output["adapter"] == "mock"
    assert result.raw_output["elapsed_ms"] >= 0


@pytest.mark.asyncio
async def test_unavailable_adapter_returns_not_configured_with_reason():
    from app.services.eval.scorers.llm_judge_scorer import LLMJudgeScorer

    scorer = LLMJudgeScorer(
        judge_model="mock-judge",
        adapter=_MockUnavailableAdapter(),
    )
    result = await scorer.score(
        {
            "input_data": {"prompt": "分析"},
            "output_data": {"content": "输出"},
        },
        [],
        {"expected_output": {"must_include": ["营收"]}},
    )
    assert result.status == ScoreStatus.NOT_CONFIGURED
    assert result.raw_output["error"] == "mock credentials missing"


def test_llm_judge_scorer_no_longer_defaults_to_qwen_plus():
    from app.services.eval.scorers.llm_judge_scorer import LLMJudgeScorer

    scorer = LLMJudgeScorer()
    assert scorer._judge_model != "qwen-plus"
    assert scorer._adapter_name in {"deepseek", "openai_compatible", "dashscope"}
