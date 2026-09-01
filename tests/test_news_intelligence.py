"""
新闻智能闭环测试

覆盖:
- 模型枚举和数据类
- 聚合服务降级链逻辑
- Agent schema 校验和规则降级
- 合规过滤
- 告警状态机
- 复盘判定
- 闭环指标计算
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.models.news_intelligence import (
    NewsSourceStatus,
    AlertStatus,
    AlertAction,
    ReviewVerdict,
    AggregatedNewsResult,
    NewsAnalysisRecord,
    HoldingImpactCard,
    ClosedLoopMetrics,
    ANALYSIS_SCHEMA_FIELDS,
)


# ==================== 模型测试 ====================

class TestNewsIntelligenceModels:
    def test_source_status_enum(self):
        assert NewsSourceStatus.SUCCESS.value == "success"
        assert NewsSourceStatus.FAILED.value == "failed"
        assert NewsSourceStatus.RATE_LIMITED.value == "rate_limited"
        assert NewsSourceStatus.AUTH_FAILED.value == "auth_failed"
        assert NewsSourceStatus.EMPTY.value == "empty"

    def test_alert_status_enum(self):
        assert AlertStatus.PENDING.value == "pending"
        assert AlertStatus.CONFIRMED.value == "confirmed"
        assert AlertStatus.IGNORED.value == "ignored"
        assert AlertStatus.CONVERTED.value == "converted"
        assert AlertStatus.REVIEWED.value == "reviewed"

    def test_review_verdict_enum(self):
        assert ReviewVerdict.VERIFIED.value == "verified"
        assert ReviewVerdict.UNVERIFIED.value == "unverified"
        assert ReviewVerdict.CONTRADICTED.value == "contradicted"

    def test_analysis_schema_has_17_fields(self):
        assert len(ANALYSIS_SCHEMA_FIELDS) == 17
        assert "event_summary" in ANALYSIS_SCHEMA_FIELDS
        assert "non_advisory_note" in ANALYSIS_SCHEMA_FIELDS

    def test_aggregated_result_to_dict(self):
        result = AggregatedNewsResult(
            direct_count=5,
            indirect_count=2,
            freshness="2026-08-31T10:00:00",
        )
        d = result.to_dict()
        assert d["direct_count"] == 5
        assert d["indirect_count"] == 2
        assert d["news_list"] == []

    def test_analysis_record_to_doc(self):
        record = NewsAnalysisRecord(
            news_ids=["n1"],
            result={"event_summary": "test"},
            degraded=False,
        )
        doc = record.to_doc()
        assert doc["analysis_id"] != ""
        assert doc["prompt_version"] == "v1"
        assert doc["schema_version"] == "v1"
        assert doc["degraded"] is False

    def test_holding_impact_card_to_dict(self):
        card = HoldingImpactCard(
            stock_code="000001",
            direction="positive",
            strength=4,
            is_direct=True,
        )
        d = card.to_dict()
        assert d["stock_code"] == "000001"
        assert d["refresh_state"] == "current"

    def test_closed_loop_metrics_to_dict(self):
        m = ClosedLoopMetrics(
            coverage_rate=0.85,
            analysis_success_rate=0.92,
            total_news=100,
        )
        d = m.to_dict()
        assert d["coverage_rate"] == 0.85
        assert d["total_news"] == 100


# ==================== Agent Schema 校验测试 ====================

class TestAgentSchemaValidation:
    @pytest.fixture
    def service(self):
        from app.services.news_impact_agent_service import NewsImpactAgentService
        return NewsImpactAgentService()

    def test_valid_json_passes(self, service):
        import json
        valid = {f: "" for f in ANALYSIS_SCHEMA_FIELDS}
        valid["impact_strength"] = 3
        raw = json.dumps(valid)
        result = service._validate_schema(raw)
        assert result is not None
        assert result["impact_strength"] == 3

    def test_markdown_code_block_extraction(self, service):
        import json
        valid = {f: "" for f in ANALYSIS_SCHEMA_FIELDS}
        valid["impact_strength"] = 2
        raw = f"```json\n{json.dumps(valid)}\n```"
        result = service._validate_schema(raw)
        assert result is not None

    def test_missing_few_fields_auto_fill(self, service):
        import json
        partial = {f: "" for f in ANALYSIS_SCHEMA_FIELDS[:14]}
        partial["impact_strength"] = 1
        raw = json.dumps(partial)
        result = service._validate_schema(raw)
        # 缺失3个以内应自动补全
        assert result is not None

    def test_missing_many_fields_returns_none(self, service):
        import json
        minimal = {"event_summary": "test"}
        raw = json.dumps(minimal)
        result = service._validate_schema(raw)
        assert result is None

    def test_invalid_json_returns_none(self, service):
        result = service._validate_schema("not json at all")
        assert result is None


# ==================== 规则降级测试 ====================

class TestRuleBasedFallback:
    @pytest.fixture
    def service(self):
        from app.services.news_impact_agent_service import NewsImpactAgentService
        return NewsImpactAgentService()

    def test_positive_sentiment_fallback(self, service):
        news = {"title": "业绩大增", "sentiment": "positive", "symbol": "000001"}
        result = service._rule_based_fallback(news)
        assert result["impact_direction"] == "positive"
        assert result["evidence_strength"] == "weak"
        assert "000001" in result["direct_symbols"]

    def test_negative_sentiment_fallback(self, service):
        news = {"title": "亏损扩大", "sentiment": "negative"}
        result = service._rule_based_fallback(news)
        assert result["impact_direction"] == "negative"

    def test_neutral_sentiment_fallback(self, service):
        news = {"title": "公司公告"}
        result = service._rule_based_fallback(news)
        assert result["impact_direction"] == "neutral"


# ==================== 告警状态机测试 ====================

class TestAlertStateMachine:
    @pytest.fixture
    def service(self):
        from app.services.news_closed_loop_service import NewsClosedLoopService
        return NewsClosedLoopService()

    def test_valid_transitions_from_pending(self, service):
        valid = service.VALID_TRANSITIONS[AlertStatus.PENDING.value]
        assert AlertStatus.CONFIRMED.value in valid
        assert AlertStatus.IGNORED.value in valid
        assert AlertStatus.CONVERTED.value in valid

    def test_confirmed_can_only_go_to_reviewed(self, service):
        valid = service.VALID_TRANSITIONS[AlertStatus.CONFIRMED.value]
        assert valid == [AlertStatus.REVIEWED.value]

    def test_ignored_is_terminal(self, service):
        valid = service.VALID_TRANSITIONS[AlertStatus.IGNORED.value]
        assert valid == []

    def test_reviewed_is_terminal(self, service):
        valid = service.VALID_TRANSITIONS[AlertStatus.REVIEWED.value]
        assert valid == []


# ==================== 复盘判定测试 ====================

class TestReviewVerdict:
    @pytest.fixture
    def service(self):
        from app.services.news_closed_loop_service import NewsClosedLoopService
        return NewsClosedLoopService()

    def test_predicted_positive_actual_up(self, service):
        verdict = service._compute_verdict("positive", 5.0)
        assert verdict == ReviewVerdict.VERIFIED.value

    def test_predicted_negative_actual_down(self, service):
        verdict = service._compute_verdict("negative", -3.0)
        assert verdict == ReviewVerdict.VERIFIED.value

    def test_predicted_positive_actual_down(self, service):
        verdict = service._compute_verdict("positive", -5.0)
        assert verdict == ReviewVerdict.CONTRADICTED.value

    def test_predicted_negative_actual_up(self, service):
        verdict = service._compute_verdict("negative", 4.0)
        assert verdict == ReviewVerdict.CONTRADICTED.value

    def test_small_change_unverified(self, service):
        verdict = service._compute_verdict("positive", 0.5)
        assert verdict == ReviewVerdict.UNVERIFIED.value

    def test_neutral_always_unverified(self, service):
        verdict = service._compute_verdict("neutral", 10.0)
        assert verdict == ReviewVerdict.UNVERIFIED.value


# ==================== 去重测试 ====================

class TestDeduplication:
    @pytest.fixture
    def service(self):
        from app.services.news_aggregator_service import NewsAggregatorService
        return NewsAggregatorService()

    def test_url_exact_dedup(self, service):
        news = [
            {"title": "新闻A", "url": "http://example.com/1"},
            {"title": "新闻B", "url": "http://example.com/1"},  # 同URL
            {"title": "新闻C", "url": "http://example.com/2"},
        ]
        result = service._deduplicate(news)
        assert len(result) == 2

    def test_title_similarity_dedup(self, service):
        news = [
            {"title": "贵州茅台发布年报业绩增长20%", "url": "http://a.com/1"},
            {"title": "贵州茅台发布年报业绩增长20%", "url": "http://b.com/2"},  # 同标题不同URL
            {"title": "平安银行季报出炉", "url": "http://c.com/3"},
        ]
        result = service._deduplicate(news)
        assert len(result) == 2

    def test_no_dedup_for_different_news(self, service):
        news = [
            {"title": "新闻A", "url": "http://a.com/1"},
            {"title": "完全不同的新闻B", "url": "http://b.com/2"},
        ]
        result = service._deduplicate(news)
        assert len(result) == 2


# ==================== 修复路径回归测试 ====================

class TestRegressionFixedPaths:
    """覆盖复测阶段修复的 6 个 bug 对应路径"""

    @pytest.fixture
    def agent_service(self):
        from app.services.news_impact_agent_service import NewsImpactAgentService
        return NewsImpactAgentService()

    @pytest.fixture
    def aggregator(self):
        from app.services.news_aggregator_service import NewsAggregatorService
        return NewsAggregatorService()

    @pytest.mark.asyncio
    async def test_fetch_news_builds_query_params(self, aggregator):
        """_fetch_news 必须以 NewsQueryParams（datetime 窗口）调用 query_news"""
        from datetime import timedelta
        from app.services.news_data_service import NewsQueryParams

        captured = {}

        class FakeService:
            async def query_news(self, params):
                captured["params"] = params
                return [{"title": "t", "url": "u", "publish_time": "2026-08-30"}]

        with patch(
            "app.services.news_data_service.NewsDataService", return_value=FakeService()
        ):
            news, status = await aggregator._fetch_news("000001", timedelta(hours=72))

        assert news and status.status == "success"
        p = captured["params"]
        assert isinstance(p, NewsQueryParams)
        assert p.symbol == "000001"
        assert p.start_time is not None and p.end_time is not None

    def test_compliance_filter_rewrites_advisory_text(self, agent_service):
        """合规过滤应改写含交易建议措辞的文本而不抛异常"""
        result = {
            "event_summary": "建议立即买入该股票",
            "market_confirmation": "市场已有反应",
            "non_advisory_note": "",
            "impact_paths": ["建议卖出以规避风险"],
        }
        filtered = agent_service._apply_compliance_filter(result)
        # 不抛异常，且 non_advisory_note 始终存在
        assert filtered.get("non_advisory_note")
        # 原建议措辞应被改写
        assert "买入" not in filtered["event_summary"] or filtered["event_summary"] != result["event_summary"]

    @pytest.mark.asyncio
    async def test_fallback_windows_overwrite_not_accumulate(self, aggregator):
        """72h 命中少量新闻时，7d 窗口结果应覆盖而非累加（嵌套窗口去重）"""
        from datetime import timedelta

        call_windows = []

        async def fake_fetch(symbol, window):
            call_windows.append(window)
            if window == timedelta(hours=72):
                return [{"title": "A", "url": "u1"}], MagicMock()
            if window == timedelta(days=7):
                # 7d 包含 72h 的 A + 新增 B
                return [{"title": "A", "url": "u1"}, {"title": "B", "url": "u2"}], MagicMock()
            return [], MagicMock()

        aggregator._fetch_news = fake_fetch
        aggregator._log_health = AsyncMock()

        result = await aggregator.aggregate("000001")

        # 直接新闻计数应 ≤ 2（非 1+2=3），去重后不重复计 A
        assert result.direct_count <= 2
        titles = [n["title"] for n in result.news_list]
        assert titles.count("A") == 1
