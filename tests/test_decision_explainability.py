"""Agent 决策可解释与审计能力测试。"""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings


class _FakeCursor:
    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._items:
            raise StopAsyncIteration
        return self._items.pop(0)

    def sort(self, *args, **kwargs):
        return self

    def limit(self, limit):
        return self


class _FakeDb:
    def __init__(self, collections=None):
        self._collections = collections or {}

    def __getitem__(self, name):
        if name not in self._collections:
            collection = _FakeCollection()
            self._collections[name] = collection
        return self._collections[name]


class _FakeCollection:
    def __init__(self):
        self.find_one = AsyncMock(return_value=None)
        self.find = lambda *args, **kwargs: _FakeCursor([])
        self.update_one = AsyncMock(return_value=None)


class TestDecisionRecordModels:
    """决策记录归一化测试"""

    def test_normalize_tool_decision_records_candidates_and_missing_reason(self):
        from app.models.decision import DecisionStatus
        from app.services.explainability.record_service import normalize_event_to_decision

        record = normalize_event_to_decision(
            "tool_call",
            {
                "name": "search_symbol",
                "candidates": [
                    {"id": "search_symbol", "label": "搜索标的"},
                    {"id": "news_search", "label": "搜索新闻"},
                ],
                "sequence": 2,
            },
            task_id="task_1",
            session_id="session_1",
            user_id="user_1",
            business_id="task_1",
        )

        assert record.decision_type == "tool"
        assert record.selected_option == "search_symbol"
        assert record.selection_reason == "reason_unavailable"
        assert record.status == DecisionStatus.UNVERIFIED
        assert len(record.candidates) == 2
        assert record.task_id == "task_1"

    def test_no_candidates_is_marked_unavailable(self):
        from app.services.explainability.record_service import normalize_event_to_decision

        record = normalize_event_to_decision(
            "tool_call",
            {"name": "search_symbol"},
            task_id="task_2",
        )

        assert record.selection_reason == "candidates_unavailable"
        assert record.status.value == "unverified"


class TestExplanationAndValidation:
    """分层解释与一致性校验测试"""

    def _decision(self):
        from app.services.explainability.record_service import normalize_event_to_decision

        return normalize_event_to_decision(
            "tool_call",
            {
                "name": "get_market_data",
                "selected_option": "get_market_data",
                "candidates": [{"id": "get_market_data", "label": "获取行情"}],
                "selection_reason": "需要当前行情作为分析依据",
                "conclusion": "已获取市场行情",
                "confidence": 0.9,
                "risk_level": "low",
            },
            task_id="task_explain",
        )

    def test_user_layer_contains_no_raw_reasoning(self):
        from app.services.explainability.explanation_service import explanation_service

        explanation = explanation_service.generate(self._decision(), output_text="已获取市场行情")

        assert "raw_reasoning" not in explanation.user.text
        assert "reasoning_ref" not in explanation.user.text
        assert "get_market_data" in explanation.user.text

    def test_consistent_explanation(self):
        from app.services.explainability.explanation_service import explanation_service
        from app.services.explainability.validation_service import explanation_validator

        explanation = explanation_service.generate(self._decision(), output_text="已获取市场行情")
        validation = explanation_validator.validate(explanation, self._decision(), output_text="已获取市场行情")

        assert validation.status.value == "consistent"

    def test_contradiction_is_inconsistent(self):
        from app.services.explainability.explanation_service import explanation_service
        from app.services.explainability.validation_service import explanation_validator

        decision = self._decision()
        decision.conclusion = "建议买入"
        explanation = explanation_service.generate(decision, output_text="建议买入")
        explanation.user.text = "系统建议卖出"

        validation = explanation_validator.validate(explanation, decision)

        assert validation.status.value == "inconsistent"

    def test_missing_decision_is_unverifiable(self):
        from app.services.explainability.validation_service import explanation_validator

        validation = explanation_validator.validate({}, None)

        assert validation.status.value == "unverifiable"


class TestTraceDecisionContract:
    """trace 决策事件契约测试"""

    def test_trace_adapter_has_decision_type(self):
        from app.services.eval.trace_adapter import TraceEventType, VIBE_EVENT_TYPE_MAPPING

        assert VIBE_EVENT_TYPE_MAPPING["decision"] == TraceEventType.DECISION
        assert TraceEventType.DECISION.value == "decision"

    def test_adapt_vibe_event_keeps_business_reference(self):
        from app.services.eval.trace_adapter import trace_adapter

        event = trace_adapter.adapt_vibe_event(
            {
                "type": "decision",
                "data": {"scenario": "工具调用", "conclusion": "done"},
            },
            trial_id="task_trial",
            sequence=7,
            business_id="task_audit",
            task_id="task_audit",
            session_id="session_audit",
        )

        assert event.event_type == "decision"
        assert event.business_id == "task_audit"
        assert event.task_id == "task_audit"
        assert event.session_id == "session_audit"


class TestGraphDecisionCapture:
    """TradingAgents graph 决策采集测试"""

    def test_records_have_parent_chain(self):
        from tradingagents.graph.decision_capture import DecisionCapture

        capture = DecisionCapture()
        first = capture.record("Market Analyst", {"market_report": "市场偏强"})
        second = capture.record("Trader", {"trader_investment_plan": "持有观察"})

        assert first["parent_decision_id"] is None
        assert second["parent_decision_id"] == first["decision_id"]
        assert len(capture.snapshot()) == 2
        assert second["status"] == "confirmed"


class TestMetricsAndDegradation:
    """生产指标与降级策略测试"""

    def test_compute_rates_with_empty_samples(self):
        from app.services.explainability.metrics_service import DecisionMetricsService

        summary = DecisionMetricsService.compute([], [])

        assert summary["decision_nodes"] == 0
        assert summary["completeness_rate"] == 1.0
        assert summary["consistency_rate"] == 1.0

    def test_alert_threshold(self, monkeypatch):
        from app.services.explainability.metrics_service import DecisionMetricsService

        monkeypatch.setattr(settings, "EXPLAINABILITY_ALERT_THRESHOLD", 0.8)
        alerts = DecisionMetricsService.check_alerts(
            {"completeness_rate": 0.5, "consistency_rate": 0.4}
        )

        assert len(alerts) == 2

    @pytest.mark.asyncio
    async def test_high_risk_failure_creates_review(self, monkeypatch):
        from app.services.explainability.degradation_service import degradation_service

        monkeypatch.setattr(settings, "EXPLAINABILITY_HIGH_RISK_THRESHOLD", 0.1)
        with patch(
            "app.services.explainability.degradation_service.decision_record_store.create_review",
            new=AsyncMock(return_value={"review_id": "rev_1"}),
        ) as create_review:
            result = await degradation_service.handle_failure(
                task_id="task_risk",
                session_id="session_risk",
                business_id="task_risk",
                decision={
                    "risk_level": "critical",
                    "confidence": 0.9,
                    "decision_id": "dec_risk",
                },
                reason="解释不一致",
            )

        assert result["mode"] == "blocked"
        assert result["review_id"] == "rev_1"
        create_review.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_low_risk_failure_degrades_without_review(self, monkeypatch):
        from app.services.explainability.degradation_service import degradation_service

        monkeypatch.setattr(settings, "EXPLAINABILITY_HIGH_RISK_THRESHOLD", 0.8)
        with patch(
            "app.services.explainability.degradation_service.decision_record_store.create_review",
            new=AsyncMock(),
        ) as create_review:
            result = await degradation_service.handle_failure(
                task_id="task_low",
                session_id="session_low",
                business_id="task_low",
                decision={"risk_level": "low", "confidence": 0.2},
                reason="解释生成不可用",
            )

        assert result["mode"] == "degraded"
        create_review.assert_not_awaited()


class TestBadCaseAuditReferences:
    """Bad Case 审计引用测试"""

    def test_bad_case_model_keeps_optional_audit_fields(self):
        from app.models.eval import BadCaseSource, EvalBadCase

        bad_case = EvalBadCase(
            bad_case_id="bc_1",
            business_id="task_1",
            task_id="task_1",
            session_id="session_1",
            decision_chain_ref="task_1",
            explanation_status="unverifiable",
            source=BadCaseSource.ONLINE_SAMPLING,
            input_data={"prompt": "test"},
        )

        assert bad_case.decision_chain_ref == "task_1"
        assert bad_case.explanation_status == "unverifiable"


class TestDecisionAuditService:
    """统一审计服务测试"""

    @pytest.mark.asyncio
    async def test_unknown_identifier_returns_unavailable(self):
        from app.services.explainability.audit_service import decision_audit_service

        fake_db = _FakeDb()
        task = {
            "task_id": "task_missing",
            "session_id": "session_missing",
            "user_id": "user_1",
        }
        fake_db["vibe_agent_tasks"].find_one = AsyncMock(return_value=task)
        with patch.object(
            decision_audit_service.store,
            "list_decision_records",
            new=AsyncMock(return_value=[]),
        ), patch.object(
            decision_audit_service.store,
            "list_explanations",
            new=AsyncMock(return_value=[]),
        ), patch.object(
            decision_audit_service.store,
            "list_validations",
            new=AsyncMock(return_value=[]),
        ), patch.object(
            decision_audit_service.store,
            "list_reviews",
            new=AsyncMock(return_value=[]),
        ), patch(
            "app.services.explainability.audit_service.get_mongo_db",
            return_value=fake_db,
        ):
            audit = await decision_audit_service.build_audit(
                "task_missing",
                {"id": "user_1", "is_admin": True},
            )

        assert audit["audit_status"] == "unavailable"
        assert audit["task_id"] == "task_missing"

    @pytest.mark.asyncio
    async def test_non_admin_cannot_audit_other_users_task(self):
        from fastapi import HTTPException
        from app.services.explainability.audit_service import decision_audit_service

        fake_db = _FakeDb()
        task = {
            "task_id": "task_other",
            "session_id": "session_other",
            "user_id": "user_other",
        }
        fake_db["vibe_agent_tasks"].find_one = AsyncMock(return_value=task)
        with patch.object(
            decision_audit_service.store,
            "list_decision_records",
            new=AsyncMock(return_value=[]),
        ), patch.object(
            decision_audit_service.store,
            "list_explanations",
            new=AsyncMock(return_value=[]),
        ), patch.object(
            decision_audit_service.store,
            "list_validations",
            new=AsyncMock(return_value=[]),
        ), patch.object(
            decision_audit_service.store,
            "list_reviews",
            new=AsyncMock(return_value=[]),
        ), patch(
            "app.services.explainability.audit_service.get_mongo_db",
            return_value=fake_db,
        ):
            with pytest.raises(HTTPException) as exc:
                await decision_audit_service.build_audit(
                    "task_other",
                    {"id": "user_1", "is_admin": False},
                )

        assert exc.value.status_code == 403
