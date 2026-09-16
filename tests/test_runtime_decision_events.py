import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings
from app.services.vibe_agent.models import VibeEventType
from app.services.vibe_agent.service import VibeAgentService


@pytest.fixture(autouse=True)
def _runtime_bootstrap(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.services.vibe_agent.paths.settings.VIBE_AGENT_RUNTIME_ROOT",
        str(tmp_path),
    )
    from vibe_agent_runtime import embedded_agent_runtime

    embedded_agent_runtime._bootstrap()


def test_tool_evidence_index_correlates_parallel_results():
    from src.agent.evidence import ToolEvidenceIndex

    index = ToolEvidenceIndex()
    first_id = index.record_call(
        call_id="call-1",
        tool="get_market_data",
        arguments={"code": "600021.SH"},
    )
    second_id = index.record_call(
        call_id="call-2",
        tool="get_fund_flow",
        arguments={"code": "600021.SH"},
    )

    second = index.record_result(
        call_id="call-2",
        tool="get_fund_flow",
        status="ok",
        preview="{}",
    )
    first = index.record_result(
        call_id="call-1",
        tool="get_market_data",
        status="ok",
        preview='{"600021.SH": [{"close": 13.75}]}',
    )

    assert first.evidence_id == first_id
    assert second.evidence_id == second_id
    assert first.tool == "get_market_data"
    assert first.status == "available"
    assert second.tool == "get_fund_flow"
    assert second.status == "unavailable"


def test_agent_loop_emits_tool_selection_decision(tmp_path):
    from src.agent.loop import AgentLoop

    events = []
    registry = SimpleNamespace(tool_names=["get_market_data", "search_symbol"])
    memory = SimpleNamespace(run_dir=str(tmp_path))
    agent = AgentLoop(
        registry=registry,
        llm=SimpleNamespace(model_name="test-model"),
        memory=memory,
        event_callback=lambda event_type, payload: events.append((event_type, payload)),
    )
    tool_call = SimpleNamespace(
        id="call-1",
        name="get_market_data",
        arguments={"code": "600021.SH"},
    )

    agent._emit_tool_selection_decision(tool_call, 1)

    event_type, payload = events[0]
    assert event_type == "decision.record"
    assert payload["selected_option"] == "get_market_data"
    assert {item["id"] for item in payload["candidates"]} == {
        "get_market_data",
        "search_symbol",
    }
    assert payload["selection_reason"] == "reason_unavailable"
    assert payload["status"] == "unverified"
    assert payload["evidence_ids"] == ["evidence_call-1"]


def test_grounding_emits_identity_decision(tmp_path):
    from src.agent.grounding import GroundingLedger

    events = []
    ledger = GroundingLedger(
        run_dir=tmp_path,
        user_message="分析上海电力",
        event_callback=lambda event_type, payload: events.append((event_type, payload)),
    )
    ledger.ingest_tool_result(
        tool_name="search_symbol",
        arguments={"query": "上海电力"},
        result=json.dumps(
            {
                "ok": True,
                "data": {
                    "query": "上海电力",
                    "candidates": [
                        {
                            "symbol": "600021.SH",
                            "name": "上海电力",
                            "source": "eastmoney",
                        }
                    ],
                    "sources": {"eastmoney": "ok"},
                },
            },
            ensure_ascii=False,
        ),
        call_id="call-resolve",
        success=True,
    )

    decisions = [payload for event_type, payload in events if event_type == "decision.record"]
    assert decisions
    assert decisions[-1]["selected_option"] == "600021.SH"
    assert decisions[-1]["status"] == "confirmed"
    assert decisions[-1]["evidence_ids"] == ["evidence_call-resolve"]


def test_grounding_emits_blocked_authorization_decision(tmp_path):
    from src.agent.grounding import GroundingLedger

    events = []
    ledger = GroundingLedger(
        run_dir=tmp_path,
        user_message="分析上海电力",
        event_callback=lambda event_type, payload: events.append((event_type, payload)),
    )
    result = ledger.authorize_tool_call(
        "get_market_data",
        {"code": "600021.SH"},
        batch_authorized_symbols=[],
        batch_identity_status="unresolved",
        call_id="call-market",
    )

    assert result.allowed is False
    decisions = [payload for event_type, payload in events if event_type == "decision.record"]
    assert decisions[-1]["scenario"] == "工具授权决策"
    assert decisions[-1]["selected_option"] == "block"
    assert decisions[-1]["status"] == "blocked"


def test_grounding_emits_validation_decision(tmp_path):
    from src.agent.grounding import GroundingLedger

    events = []
    ledger = GroundingLedger(
        run_dir=tmp_path,
        user_message="分析上海电力",
        event_callback=lambda event_type, payload: events.append((event_type, payload)),
    )
    ledger.validate_final_answer("该股基本面并未发生变化，无价格声明。")

    decisions = [payload for event_type, payload in events if event_type == "decision.record"]
    assert decisions
    assert decisions[-1]["scenario"] == "最终回答校验决策"
    assert decisions[-1]["selected_option"] in {"release", "reject"}


def test_ingest_decision_record_and_ignore_lifecycle(monkeypatch):
    service = VibeAgentService()
    persisted = AsyncMock()
    traced = AsyncMock()
    appended = AsyncMock()
    updated = AsyncMock()

    async def run():
        with patch.object(service, "_persist_decision_record", persisted), \
                patch.object(service, "_save_standardized_trace", traced), \
                patch.object(service, "append_event", appended), \
                patch.object(service, "update_task_status", updated), \
                patch("app.services.vibe_agent.service.log_operation", new=AsyncMock()):
            await service.ingest_worker_event(
                {
                    "user_id": "user-1",
                    "session_id": "session-1",
                    "task_id": "task-1",
                    "event_type": "decision.record",
                    "payload": {
                        "scenario": "工具选择",
                        "selected_option": "search_symbol",
                        "selection_reason": "需要先锁定标的",
                        "conclusion": "选择搜索工具",
                        "status": "confirmed",
                    },
                }
            )
            assert persisted.await_count == 1
            assert persisted.await_args.args[0] == "decision.record"
            assert appended.await_args.args[2] == VibeEventType.decision

            persisted.reset_mock()
            await service.ingest_worker_event(
                {
                    "user_id": "user-1",
                    "session_id": "session-1",
                    "task_id": None,
                    "event_type": "attempt.completed",
                    "payload": {"summary": "完成"},
                }
            )
            persisted.assert_not_awaited()

            await service.ingest_worker_event(
                {
                    "user_id": "user-1",
                    "session_id": "session-1",
                    "task_id": None,
                    "event_type": "tool_call",
                    "payload": {"tool": "get_market_data", "call_id": "call-1"},
                }
            )
            persisted.assert_not_awaited()

    import asyncio

    asyncio.run(run())


def test_feature_flag_rollback_keeps_event_stream_but_skips_persistence(monkeypatch):
    service = VibeAgentService()
    save_decision = AsyncMock()
    appended = AsyncMock()
    traced = AsyncMock()

    async def run():
        with patch.object(settings, "EXPLAINABILITY_ENABLED", False), \
                patch.object(service, "_save_standardized_trace", traced), \
                patch(
                    "app.services.explainability.record_service.decision_record_store.save_decision_record",
                    new=save_decision,
                ), \
                patch.object(service, "append_event", appended):
            await service.ingest_worker_event(
                {
                    "user_id": "user-1",
                    "session_id": "session-1",
                    "task_id": "task-1",
                    "event_type": "decision.record",
                    "payload": {"scenario": "工具选择", "status": "confirmed"},
                }
            )
        save_decision.assert_not_awaited()
        assert appended.await_count == 1

    import asyncio

    asyncio.run(run())


def test_finalize_without_records_does_not_fake_decision():
    service = VibeAgentService()
    persist = AsyncMock()
    list_records = AsyncMock(return_value=[])
    metrics = AsyncMock()

    async def run():
        with patch.object(service, "_persist_decision_record", persist), \
                patch(
                    "app.services.explainability.record_service.decision_record_store.list_decision_records",
                    new=list_records,
                ), \
                patch(
                    "app.services.explainability.metrics_service.decision_metrics_service.record_task_metrics",
                    new=metrics,
                ):
            await service._finalize_task_explainability(
                user_id="user-1",
                session_id="session-1",
                task_id="task-1",
                content="最终输出",
            )
        persist.assert_not_awaited()
        metrics.assert_awaited_once()

    import asyncio

    asyncio.run(run())
