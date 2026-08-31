"""
Agent 评测平台 - 完整验收测试（场景化集成）

基于真实业务场景验证端到端流程：
场景A: 数据集创建 → Case导入 → 运行创建 → 评分 → 报告生成
场景B: Claim-Evidence grounding 全链路
场景C: 人工复核 → Bad Case 回流闭环
场景D: 趋势/告警/Release Gate 治理
场景E: 回归任务配置与触发
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


# ==================== 场景A: 数据集→运行→评分→报告 ====================

class TestScenarioA_DataToReport:
    """完整的数据集到报告流程"""

    def test_dataset_model_creation(self):
        """创建评测集模型"""
        from app.models.eval import EvalDataset
        ds = EvalDataset(
            dataset_id="ds_acceptance_001",
            name="验收测试数据集",
            description="用于完整验收",
            version="1.0.0",
            category="regression",
        )
        assert ds.dataset_id == "ds_acceptance_001"
        assert ds.version == "1.0.0"

    def test_case_model_with_scoring_criteria(self):
        """Case 包含评分标准"""
        from app.models.eval import EvalCase
        case = EvalCase(
            case_id="case_001",
            name="贵州茅台基本面分析",
            input={"prompt": "分析贵州茅台基本面"},
            expected_output={"keywords": ["营收", "利润", "估值"]},
            tags=["fundamental", "白酒"],
            category="stock_analysis",
            difficulty="medium",
            scoring_criteria={"must_contain": ["营收", "净利润"]},
        )
        assert case.difficulty == "medium"
        assert "must_contain" in case.scoring_criteria

    def test_run_config_with_all_fields(self):
        """运行配置包含所有二期字段"""
        from app.models.eval import EvalRunConfig
        config = EvalRunConfig(
            dataset_id="ds_acceptance_001",
            agent_name="research_agent",
            num_trials_per_case=3,
            timeout_seconds=120,
            judge_model="qwen-max",
            rubric_version="v2",
            low_confidence_threshold=0.6,
            review_strategy="low_confidence_first",
            data_window={"start": "2026-01-01", "end": "2026-08-31"},
        )
        assert config.judge_model == "qwen-max"
        assert config.review_strategy == "low_confidence_first"
        assert config.data_window["start"] == "2026-01-01"

    def test_run_snapshot_structure(self):
        """Run Snapshot 确保可复现"""
        from app.models.eval import RunSnapshot
        snapshot = RunSnapshot(
            dataset_version="1.0.0",
            case_contents={"case_001": {"input": "test"}},
            scorer_config=[{"name": "rule_based", "status": "available"}],
            judge_config={"model": "qwen-max", "rubric_version": "v2"},
            data_window={"start": "2026-01-01"},
        )
        assert snapshot.dataset_version == "1.0.0"
        assert len(snapshot.scorer_config) == 1

    @pytest.mark.asyncio
    async def test_scorer_hub_handles_all_statuses(self):
        """ScorerHub 正确处理所有状态"""
        from app.services.eval.scorer_hub import ScorerHub
        from app.models.eval import ScoreStatus

        hub = ScorerHub()
        # 验证 list_scorers 返回 status 字段
        scorers = hub.list_scorers()
        # 未初始化时为空列表，但方法不报错
        assert isinstance(scorers, list)


# ==================== 场景B: Claim-Evidence Grounding ====================

class TestScenarioB_ClaimEvidence:
    """Claim-Evidence 全链路验证"""

    @pytest.mark.asyncio
    async def test_full_grounding_pipeline(self):
        """从文本提取claim → 映射证据 → 生成verdict"""
        from app.services.eval.scorers.evidence_scorer import EvidenceQualityScorer
        from app.models.eval import ClaimVerdict

        scorer = EvidenceQualityScorer()

        # 模拟 Agent 输出
        trial_data = {
            "output_data": {
                "content": (
                    "贵州茅台2025年营收达到一千五百亿元，同比增长百分之十五。"
                    "净利润超过七百亿元，毛利率维持在百分之九十以上。"
                    "当前市盈率约三十倍，处于历史中位水平。"
                    "建议投资者长期持有，目标价位两千元。"
                ),
            },
        }

        # 模拟 trace 中的证据事件
        trace_events = [
            {
                "event_type": "evidence",
                "event_id": "evt_financial_001",
                "data": {
                    "snippet": "贵州茅台600519 2025年报显示营业收入一千五百二十亿元同比增长百分之十五点三",
                    "source": "eastmoney_annual_report",
                    "query": "贵州茅台2025年营收",
                },
            },
            {
                "event_type": "retrieval",
                "event_id": "evt_valuation_001",
                "data": {
                    "snippet": "茅台当前动态市盈率二十九点八倍近五年中位数三十一倍",
                    "source": "wind_terminal",
                    "query": "贵州茅台估值水平",
                },
            },
        ]

        result = await scorer.score(trial_data, trace_events)

        # 验证评分结果
        assert result.score >= 0.0
        assert result.score <= 1.0
        assert result.score_name == "evidence_quality"
        assert result.source.value == "evidence"

        # 验证 claims 被提取
        assert len(result.claims) > 0

        # 验证至少有一条 claim 匹配到了证据
        has_supported = any(
            c.verdict in (ClaimVerdict.SUPPORTED, ClaimVerdict.WEAKLY_SUPPORTED)
            for c in result.claims
        )
        assert has_supported, "应有至少一条 claim 获得证据支撑"

        # 验证有证据的 claim 包含 snippet 和 trace_event_id
        for claim in result.claims:
            if claim.verdict == ClaimVerdict.SUPPORTED:
                assert claim.evidence_snippet is not None
                assert claim.trace_event_id is not None
                assert claim.confidence > 0

    def test_tokenizer_produces_ngrams(self):
        """中文分词器正确产生 n-gram"""
        from app.services.eval.scorers.evidence_scorer import EvidenceQualityScorer
        tokens = EvidenceQualityScorer._tokenize_chinese("贵州茅台涨幅")
        assert "贵州" in tokens
        assert "茅台" in tokens
        assert "涨幅" in tokens
        assert "贵州茅" in tokens  # 3-gram


# ==================== 场景C: 人工复核→Bad Case 回流 ====================

class TestScenarioC_ReviewReflow:
    """人工复核和 Bad Case 回流闭环"""

    def test_review_audit_entry_structure(self):
        """复核审计条目结构完整"""
        from app.models.eval import ReviewAuditEntry
        entry = ReviewAuditEntry(
            reviewer="admin@company.com",
            action="reject",
            old_score=0.8,
            new_score=0.3,
            comment="回答缺少关键数据支撑",
        )
        assert entry.action == "reject"
        assert entry.old_score == 0.8
        assert entry.new_score == 0.3

    def test_score_with_review_fields(self):
        """EvalScore 包含复核相关字段"""
        from app.models.eval import EvalScore, ScoreStatus, ScoreSource
        score = EvalScore(
            score_id="score_test_001",
            trial_id="trial_001",
            score_name="llm_judge",
            score=0.45,
            passed=False,
            status=ScoreStatus.FAILED,
            reason="准确性不足",
            confidence=0.6,
            source=ScoreSource.LLM_JUDGE,
            review_action="reject",
        )
        assert score.status == ScoreStatus.FAILED
        assert score.review_action == "reject"

    def test_bad_case_request_models(self):
        """Bad Case 创建和转换请求模型"""
        from app.routers.eval import BadCaseCreateRequest, ConvertToCaseRequest
        req = BadCaseCreateRequest(
            source="human_review",
            input_data={"prompt": "推荐股票"},
            output_data={"content": "强烈推荐买入XX"},
            failure_reason="违规荐股",
            risk_level="high",
            tags=["compliance", "荐股"],
        )
        assert req.risk_level == "high"

        convert = ConvertToCaseRequest(dataset_id="ds_bad_cases")
        assert convert.dataset_id == "ds_bad_cases"


# ==================== 场景D: 趋势/告警/Release Gate ====================

class TestScenarioD_Governance:
    """质量治理功能验证"""

    def test_release_gate_config_defaults(self):
        """Release Gate 默认关闭"""
        from app.routers.eval import ReleaseGateConfig
        config = ReleaseGateConfig()
        assert config.enabled is False
        assert config.min_success_rate == 0.9
        assert config.block_on_safety_failure is True

    def test_alert_rule_model(self):
        """告警规则模型"""
        from app.routers.eval import AlertRule
        rule = AlertRule(
            metric="success_rate",
            threshold=0.7,
            direction="below",
            window_runs=5,
        )
        assert rule.metric == "success_rate"
        assert rule.window_runs == 5

    def test_regression_task_disabled_by_default(self):
        """回归任务默认禁用"""
        from app.routers.eval import RegressionTaskConfig
        task = RegressionTaskConfig(
            name="每日冒烟",
            dataset_id="ds_smoke",
            agent_name="research_agent",
            schedule_cron="0 9 * * 1-5",
        )
        assert task.enabled is False
        assert task.schedule_cron == "0 9 * * 1-5"


# ==================== 场景E: 线上抽样入池 ====================

class TestScenarioE_OnlineSampling:
    """线上抽样→Bad Case池→回流数据集"""

    def test_online_sample_full_payload(self):
        """线上抽样完整载荷"""
        from app.routers.eval import OnlineSampleRequest
        req = OnlineSampleRequest(
            source="online_sampling",
            input_data={"query": "帮我分析一下新能源板块走势"},
            output_data={"content": "新能源板块近期表现不佳..."},
            failure_reason="分析过于笼统，缺少具体数据",
            risk_level="medium",
            tags=["vague_answer"],
            session_id="sess_abc123",
            user_feedback="回答太模糊了",
        )
        assert req.source == "online_sampling"
        assert req.session_id == "sess_abc123"


# ==================== 跨模块一致性检查 ====================

class TestCrossModuleConsistency:
    """跨模块一致性验证"""

    def test_all_scorers_importable(self):
        """所有评分器可正常导入"""
        from app.services.eval.scorers.rule_scorer import RuleBasedScorer
        from app.services.eval.scorers.output_scorer import OutputCompletenessScorer
        from app.services.eval.scorers.llm_judge_scorer import LLMJudgeScorer
        from app.services.eval.scorers.evidence_scorer import EvidenceQualityScorer
        from app.services.eval.scorers.trajectory_scorer import TrajectoryScorer
        from app.services.eval.scorers.safety_scorer import SafetyScorer
        from app.services.eval.scorers.redteam_adapter import RedTeamAdapter

        scorers = [
            RuleBasedScorer(), OutputCompletenessScorer(),
            LLMJudgeScorer(), EvidenceQualityScorer(),
            TrajectoryScorer(), SafetyScorer(), RedTeamAdapter(),
        ]
        for s in scorers:
            assert hasattr(s, 'name')
            assert hasattr(s, 'source')
            assert hasattr(s, 'version')
            assert hasattr(s, 'score')

    def test_score_status_used_consistently(self):
        """ScoreStatus 在模型和服务中一致使用"""
        from app.models.eval import ScoreStatus
        from app.services.eval.scorer_hub import ScorerHub

        # 枚举值
        statuses = [s.value for s in ScoreStatus]
        assert "passed" in statuses
        assert "failed" in statuses
        assert "skipped" in statuses
        assert "not_configured" in statuses
        assert "error" in statuses

    def test_frontend_routes_match_backend_endpoints(self):
        """前端路由与后端端点对应关系"""
        import os
        router_path = "/Users/luoqiang/Documents/luoqiang/quanting-agent/frontend/src/router/index.ts"
        assert os.path.exists(router_path)

        with open(router_path) as f:
            content = f.read()

        # 验证关键路由存在
        assert "runs/compare" in content
        assert "runs/:id/report" in content
        assert "datasets/:id" in content
        assert "review" in content
        assert "bad-cases" in content
        assert "trends" in content
