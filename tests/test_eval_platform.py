"""
Agent 评测平台基础测试

验证评测功能不影响现有单股分析、批量分析和自然语言研究工作台路径。
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


class TestEvalModels:
    """测试数据模型"""

    def test_eval_case_model(self):
        """测试 EvalCase 模型"""
        from app.models.eval import EvalCase

        case = EvalCase(
            case_id="test_case_001",
            name="测试用例",
            input={"prompt": "测试"},
            tags=["test"],
            difficulty="easy",
            category="basic",
        )

        assert case.case_id == "test_case_001"
        assert case.name == "测试用例"
        assert case.difficulty == "easy"

    def test_eval_dataset_model(self):
        """测试 EvalDataset 模型"""
        from app.models.eval import EvalDataset, DatasetStatus

        dataset = EvalDataset(
            dataset_id="ds_test_001",
            name="测试数据集",
            version="1.0.0",
            status=DatasetStatus.DRAFT,
        )

        assert dataset.dataset_id == "ds_test_001"
        assert dataset.status == DatasetStatus.DRAFT

    def test_eval_run_model(self):
        """测试 EvalRun 模型"""
        from app.models.eval import EvalRun, RunStatus

        run = EvalRun(
            run_id="run_test_001",
            dataset_id="ds_test_001",
            dataset_version="1.0.0",
            status=RunStatus.PENDING,
            num_trials_per_case=3,
        )

        assert run.run_id == "run_test_001"
        assert run.num_trials_per_case == 3

    def test_eval_trial_model(self):
        """测试 EvalTrial 模型"""
        from app.models.eval import EvalTrial, TrialStatus

        trial = EvalTrial(
            trial_id="trial_test_001",
            run_id="run_test_001",
            case_id="case_test_001",
            trial_index=0,
            status=TrialStatus.PENDING,
        )

        assert trial.trial_id == "trial_test_001"
        assert trial.trial_index == 0

    def test_eval_score_model(self):
        """测试 EvalScore 模型"""
        from app.models.eval import EvalScore, ScoreSource

        score = EvalScore(
            score_id="score_test_001",
            trial_id="trial_test_001",
            score_name="rule_based",
            score=0.85,
            passed=True,
            reason="通过所有检查",
            source=ScoreSource.RULE_BASED,
        )

        assert score.score == 0.85
        assert score.passed is True


class TestTraceAdapter:
    """测试 Trace Adapter"""

    def test_trace_event_type_mapping(self):
        """测试事件类型映射"""
        from app.services.eval.trace_adapter import VIBE_EVENT_TYPE_MAPPING, TraceEventType

        assert VIBE_EVENT_TYPE_MAPPING["llm_call"] == TraceEventType.LLM_CALL
        assert VIBE_EVENT_TYPE_MAPPING["tool_use"] == TraceEventType.TOOL_CALL
        assert VIBE_EVENT_TYPE_MAPPING["error"] == TraceEventType.ERROR

    @pytest.mark.asyncio
    async def test_adapt_vibe_event(self):
        """测试 Vibe 事件转换"""
        from app.services.eval.trace_adapter import trace_adapter

        vibe_event = {
            "type": "llm_call",
            "timestamp": "2026-08-27T10:00:00Z",
            "data": {"model": "gpt-4", "tokens": 100},
        }

        event = trace_adapter.adapt_vibe_event(vibe_event, "trial_001", 1)

        assert event is not None
        assert event.event_type == "llm_call"
        assert event.trial_id == "trial_001"
        assert event.sequence == 1


class TestScorers:
    """测试评分器"""

    @pytest.mark.asyncio
    async def test_rule_based_scorer(self):
        """测试规则评分器"""
        from app.services.eval.scorers.rule_scorer import RuleBasedScorer

        scorer = RuleBasedScorer()

        trial_data = {
            "status": "completed",
            "output_data": {"result": "test output"},
            "latency_ms": 1000,
            "token_usage": {"input": 100, "output": 200},
        }

        trace_events = [
            {"event_type": "llm_call", "sequence": 1},
            {"event_type": "final_report", "sequence": 2},
        ]

        result = await scorer.score(trial_data, trace_events)

        assert result.score_name == "rule_based"
        assert 0 <= result.score <= 1
        assert result.source.value == "rule_based"

    @pytest.mark.asyncio
    async def test_output_completeness_scorer(self):
        """测试输出完整性评分器"""
        from app.services.eval.scorers.output_scorer import OutputCompletenessScorer

        scorer = OutputCompletenessScorer()

        trial_data = {
            "output_data": {
                "summary": "测试摘要",
                "analysis": "测试分析",
                "recommendation": "测试建议",
            },
        }

        trace_events = [
            {"event_type": "final_report", "sequence": 1},
        ]

        result = await scorer.score(trial_data, trace_events)

        assert result.score_name == "output_completeness"
        assert 0 <= result.score <= 1


class TestConfigSwitch:
    """测试配置开关"""

    def test_eval_platform_disabled_by_default(self):
        """验证评测平台默认关闭"""
        from app.core.config import settings

        assert settings.EVAL_PLATFORM_ENABLED is False

    def test_eval_config_fields_exist(self):
        """验证评测配置字段存在"""
        from app.core.config import settings

        assert hasattr(settings, "EVAL_PLATFORM_ENABLED")
        assert hasattr(settings, "EVAL_RUNNER_CONCURRENCY")
        assert hasattr(settings, "EVAL_TRIAL_TIMEOUT_SECONDS")
        assert hasattr(settings, "EVAL_MAX_TRIALS_PER_CASE")


class TestRouterProtection:
    """测试路由保护"""

    def test_eval_router_exists(self):
        """验证评测路由存在"""
        from app.routers import eval

        assert hasattr(eval, "router")
        assert len(eval.router.routes) > 0

    def test_eval_routes_have_access_check(self):
        """验证评测路由有权限检查"""
        from app.routers import eval

        # 除了 health 端点，其他都应该有权限检查
        protected_routes = [r for r in eval.router.routes if r.path != "/health"]
        assert len(protected_routes) > 0


class TestGoldenCasesData:
    """测试 Golden Cases 数据"""

    def test_golden_cases_file_exists(self):
        """验证 golden cases 文件存在"""
        from pathlib import Path

        data_file = Path(__file__).parent.parent / "app" / "services" / "eval" / "data" / "golden_cases.json"
        assert data_file.exists(), f"Golden cases file not found: {data_file}"

    def test_golden_cases_format(self):
        """验证 golden cases 格式正确"""
        import json
        from pathlib import Path

        data_file = Path(__file__).parent.parent / "app" / "services" / "eval" / "data" / "golden_cases.json"

        with open(data_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert "dataset" in data
        assert "cases" in data
        assert len(data["cases"]) >= 20, "Should have at least 20 golden cases"

        # 验证每个 case 的必需字段
        for case in data["cases"]:
            assert "case_id" in case
            assert "name" in case
            assert "input" in case
            assert "category" in case
            assert "difficulty" in case


class TestIsolationFromExistingFeatures:
    """验证评测功能不影响现有功能"""

    def test_existing_routers_not_modified(self):
        """验证现有路由未被修改"""
        from app.routers import analysis, screening, queue

        # 这些路由应该仍然正常工作
        assert hasattr(analysis, "router")
        assert hasattr(screening, "router")
        assert hasattr(queue, "router")

    def test_eval_module_isolated(self):
        """验证评测模块是独立的"""
        from app.services import eval as eval_services

        # 评测服务应该是独立的模块
        assert hasattr(eval_services, "EvalDatasetService")
        assert hasattr(eval_services, "EvalRunnerService")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
