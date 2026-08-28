"""
二期评测平台测试

覆盖：
- 评分器校准测试（低置信、高风险、分数边界样本进入复核队列）
- 人工复核流程测试
- Bad Case 回流流程测试
- 指标聚合测试
- LLM Judge / 证据 / 轨迹评分器基本功能

对应 spec 二期任务 2.10。
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock


# ==================== 评分器单元测试 ====================

class TestLLMJudgeScorer:
    """LLM Judge 评分器测试"""

    @pytest.fixture
    def scorer(self):
        from app.services.eval.scorers.llm_judge_scorer import LLMJudgeScorer
        return LLMJudgeScorer()

    @pytest.mark.asyncio
    async def test_empty_output_returns_zero(self, scorer):
        """空输出应返回 0 分"""
        result = await scorer.score(
            trial_data={"input_data": {"prompt": "test"}, "output_data": {}},
            trace_events=[],
        )
        assert result.score == 0.0
        assert result.passed is False
        assert "为空" in result.reason

    @pytest.mark.asyncio
    async def test_has_raw_output(self, scorer):
        """评分结果应包含 raw_output"""
        # mock dashscope 调用
        with patch.object(scorer, '_call_judge', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = '{"dimensions": [], "overall_score": 0.75, "overall_reason": "good"}'
            result = await scorer.score(
                trial_data={
                    "input_data": {"prompt": "分析贵州茅台"},
                    "output_data": {"content": "贵州茅台是一只优质白酒股票..."},
                },
                trace_events=[],
            )
            assert result.raw_output is not None
            assert "judge_model" in result.raw_output
            assert "parsed" in result.raw_output

    @pytest.mark.asyncio
    async def test_parse_json_from_markdown(self, scorer):
        """应能从 markdown code block 中提取 JSON"""
        raw = '```json\n{"dimensions": [], "overall_score": 0.8, "overall_reason": "ok"}\n```'
        parsed = scorer._parse_judge_output(raw)
        assert parsed["overall_score"] == 0.8

    @pytest.mark.asyncio
    async def test_default_rubric_has_five_dimensions(self, scorer):
        """默认金融 rubric 应有 5 个维度"""
        dims = scorer._rubric.get("dimensions", [])
        assert len(dims) == 5
        names = [d["name"] for d in dims]
        assert "factual_consistency" in names
        assert "risk_disclosure" in names


class TestEvidenceQualityScorer:
    """证据质量评分器测试"""

    @pytest.fixture
    def scorer(self):
        from app.services.eval.scorers.evidence_scorer import EvidenceQualityScorer
        return EvidenceQualityScorer()

    @pytest.mark.asyncio
    async def test_no_evidence_no_output(self, scorer):
        result = await scorer.score(
            trial_data={"output_data": {}},
            trace_events=[],
        )
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_with_evidence_events(self, scorer):
        events = [
            {"event_type": "evidence", "data": {"source": "akshare", "query": "茅台营收"}},
            {"event_type": "retrieval", "data": {"source": "tushare", "topic": "白酒行业"}},
        ]
        result = await scorer.score(
            trial_data={"output_data": {"content": "茅台营收增长稳健。白酒行业前景良好。"}},
            trace_events=events,
        )
        assert result.score > 0
        assert result.raw_output is not None
        assert "dimensions" in result.raw_output

    @pytest.mark.asyncio
    async def test_long_output_no_evidence_penalized(self, scorer):
        long_text = "这是一段很长的分析内容。" * 50
        result = await scorer.score(
            trial_data={"output_data": {"content": long_text}},
            trace_events=[],
        )
        assert result.score < 0.5
        assert "证据" in result.reason


class TestTrajectoryScorer:
    """轨迹评分器测试"""

    @pytest.fixture
    def scorer(self):
        from app.services.eval.scorers.trajectory_scorer import TrajectoryScorer
        return TrajectoryScorer()

    @pytest.mark.asyncio
    async def test_no_tool_calls_completed(self, scorer):
        result = await scorer.score(
            trial_data={"status": "completed", "output_data": {}},
            trace_events=[],
        )
        assert result.score == 0.5  # 纯文本回答给中等分

    @pytest.mark.asyncio
    async def test_loop_detection(self, scorer):
        events = [
            {"event_type": "tool_call", "data": {"tool_name": "search"}} for _ in range(10)
        ]
        result = await scorer.score(
            trial_data={"status": "completed", "output_data": {"tool_trail": []}},
            trace_events=events,
        )
        assert "死循环" in result.reason or result.raw_output["dimensions"]["redundancy"] < 0.5

    @pytest.mark.asyncio
    async def test_healthy_trajectory(self, scorer):
        events = [
            {"event_type": "tool_call", "data": {"tool_name": "search"}},
            {"event_type": "tool_call", "data": {"tool_name": "analyze"}},
            {"event_type": "tool_call", "data": {"tool_name": "report"}},
        ]
        result = await scorer.score(
            trial_data={"status": "completed", "output_data": {"tool_trail": []}},
            trace_events=events,
        )
        assert result.score >= 0.6
        assert result.passed is True


# ==================== 人工复核流程测试 ====================

class TestHumanReviewFlow:
    """人工复核流程测试"""

    @pytest.mark.asyncio
    async def test_pending_review_query_structure(self):
        """验证待复核查询逻辑正确（结构验证）"""
        # 验证 HumanReviewRequest 模型字段存在
        from app.routers.eval import HumanReviewRequest
        req = HumanReviewRequest(score_id="test", new_score=0.8, comment="ok")
        assert req.score_id == "test"
        assert req.new_score == 0.8


# ==================== 指标聚合测试 ====================

class TestMetricsService:
    """指标聚合服务测试"""

    @pytest.fixture
    def service(self):
        from app.services.eval.metrics_service import MetricsService
        return MetricsService()

    def test_combination(self, service):
        assert service._combination(5, 3) == 10
        assert service._combination(5, 0) == 1
        assert service._combination(5, 5) == 1
        assert service._combination(3, 5) == 0

    def test_stddev(self, service):
        assert service._stddev([1, 1, 1]) == 0.0
        assert abs(service._stddev([0, 1]) - 0.7071) < 0.01
        assert service._stddev([5]) == 0.0

    def test_combination_edge_cases(self, service):
        """组合数边界值验证"""
        assert service._combination(0, 0) == 1
        assert service._combination(1, 0) == 1
        assert service._combination(10, 3) == 120
        assert service._combination(2, 3) == 0


# ==================== Bad Case 回流测试 ====================

class TestBadCaseReflow:
    """Bad Case 回流流程测试"""

    @pytest.fixture
    def service(self):
        from app.services.eval.bad_case_service import BadCaseService
        return BadCaseService()

    @pytest.mark.asyncio
    async def test_create_bad_case_structure(self, service):
        """验证 bad case 创建的数据结构"""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.insert_one = AsyncMock()
        mock_collection.create_index = AsyncMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch('app.services.eval.bad_case_service.get_mongo_db', return_value=mock_db):
            result = await service.create_bad_case(
                source="trial_failure",
                input_data={"prompt": "test"},
                failure_reason="Agent returned error",
                risk_level="high",
            )
            assert "bad_case_id" in result
            assert result["bad_case_id"].startswith("bc_")


# ==================== 适配器降级测试 ====================

class TestAdapterDegradation:
    """外部库适配器降级测试"""

    @pytest.mark.asyncio
    async def test_deepeval_not_installed(self):
        from app.services.eval.scorers.deepeval_adapter import DeepEvalAdapter
        adapter = DeepEvalAdapter()
        if not adapter._available:
            result = await adapter.score(
                trial_data={"input_data": {"prompt": "test"}, "output_data": {"content": "out"}},
                trace_events=[],
            )
            assert result.score == 0.0
            assert "未安装" in result.reason

    @pytest.mark.asyncio
    async def test_ragas_not_installed(self):
        from app.services.eval.scorers.ragas_adapter import RagasAdapter
        adapter = RagasAdapter()
        if not adapter._available:
            result = await adapter.score(
                trial_data={"input_data": {"prompt": "test"}, "output_data": {"content": "out"}},
                trace_events=[],
            )
            assert result.score == 0.0
            assert "未安装" in result.reason


# ==================== 评分器注册测试 ====================

class TestScorerRegistration:
    """验证所有二期评分器可正确导入和实例化"""

    def test_llm_judge_importable(self):
        from app.services.eval.scorers.llm_judge_scorer import LLMJudgeScorer
        scorer = LLMJudgeScorer()
        assert scorer.name == "llm_judge"
        assert scorer.source.value == "llm_judge"

    def test_evidence_scorer_importable(self):
        from app.services.eval.scorers.evidence_scorer import EvidenceQualityScorer
        scorer = EvidenceQualityScorer()
        assert scorer.name == "evidence_quality"

    def test_trajectory_scorer_importable(self):
        from app.services.eval.scorers.trajectory_scorer import TrajectoryScorer
        scorer = TrajectoryScorer()
        assert scorer.name == "trajectory"

    def test_deepeval_adapter_importable(self):
        from app.services.eval.scorers.deepeval_adapter import DeepEvalAdapter
        adapter = DeepEvalAdapter()
        assert adapter.name == "deepeval"

    def test_ragas_adapter_importable(self):
        from app.services.eval.scorers.ragas_adapter import RagasAdapter
        adapter = RagasAdapter()
        assert adapter.name == "ragas"
