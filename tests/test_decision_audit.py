"""决策审计状态、分页和事件名称测试。"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from app.services.vibe_agent.service import VibeAgentService
from app.services.explainability.audit_service import DecisionAuditService
from app.services.explainability.event_names import event_display_name


class _AsyncList:
    def __init__(self, items):
        self._items = items
        self._iterator = iter(items)

    def __aiter__(self):
        self._iterator = iter(self._items)
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration:
            raise StopAsyncIteration


class _Cursor:
    def __init__(self, items):
        self._items = list(items)
        self._iterator = iter(self._items)

    def sort(self, *args, **kwargs):
        return self

    def limit(self, limit):
        return self

    def skip(self, skip):
        return self

    def __aiter__(self):
        self._iterator = iter(self._items)
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration:
            raise StopAsyncIteration

    async def to_list(self, length=None):
        return list(self._items)


class _FakeDecisionStore:
    def __init__(self):
        self.decisions = []

    async def save_decision_record(self, record):
        self.decisions.append(record.model_dump(by_alias=True, exclude={"id"}))
        return {}

    async def list_decision_records(self, **kwargs):
        return list(self.decisions)

    async def list_explanations(self, **kwargs):
        return []

    async def list_validations(self, **kwargs):
        return []

    async def list_reviews(self, **kwargs):
        return []


def test_event_display_name_maps_tool_result_phase_and_unknown():
    assert event_display_name({"event_type": "tool_call", "payload": {"phase": "tool_result"}}) == "工具返回"
    assert event_display_name({"event_type": "tool_call", "payload": {"name": "search"}}) == "调用工具"
    assert event_display_name({"event_type": "custom_event"}) == "custom_event"


def test_audit_status_computation_distinguishes_empty_events_and_partial():
    service = DecisionAuditService()
    assert (
        service._compute_audit_status([], [], [], [], [], [], [], [], "")
        == "empty"
    )
    assert (
        service._compute_audit_status([], [{}], [], [], [], [], [], [], "")
        == "events_without_chain"
    )
    assert (
        service._compute_audit_status(
            [{}],
            [{}],
            [],
            [],
            [],
            [],
            [{}],
            [{}],
            "output",
        )
        == "complete"
    )
    assert (
        service._compute_audit_status([{}], [], [], [], [], [], [], [], "")
        == "partial"
    )


@pytest.mark.asyncio
async def test_audit_returns_evidence_status_and_unavailable_count():
    service = DecisionAuditService()
    trace_event = {
        "_id": "trace_1",
        "event_type": "tool_call",
        "sequence": 1,
        "data": {
            "tool": "get_market_data",
            "evidence_id": "evidence_call-1",
            "evidence_status": "unavailable",
            "status": "error",
            "preview": "{}",
        },
    }
    decision = {
        "decision_id": "dec_1",
        "task_id": "task_1",
        "session_id": "session_1",
        "user_id": "user_1",
        "scenario": "工具选择决策",
        "status": "confirmed",
        "evidence_ids": ["evidence_call-1"],
    }

    task_db = MagicMock()
    trace_db = MagicMock()
    events_db = MagicMock()
    logs_db = MagicMock()
    messages_db = MagicMock()
    trials_db = MagicMock()
    task_db.find_one = AsyncMock(
        return_value={
            "task_id": "task_1",
            "session_id": "session_1",
            "user_id": "user_1",
        }
    )
    trace_db.find = MagicMock(return_value=_Cursor([trace_event]))
    events_db.find = MagicMock(return_value=_Cursor([]))
    logs_db.find = MagicMock(return_value=_Cursor([]))
    messages_db.find_one = AsyncMock(
        return_value={"_id": "msg_1", "content": "最终输出"}
    )
    messages_db.find = MagicMock(return_value=_Cursor([]))
    trials_db.find_one = AsyncMock(return_value=None)
    db = MagicMock()
    db.__getitem__.side_effect = lambda name: {
        "vibe_agent_tasks": task_db,
        "eval_trace_events": trace_db,
        "vibe_agent_events": events_db,
        "operation_logs": logs_db,
        "vibe_agent_messages": messages_db,
        "eval_trials": trials_db,
    }[name]

    with patch(
        "app.services.explainability.audit_service.get_mongo_db",
        return_value=db,
    ), patch.object(
        service.store,
        "list_decision_records",
        new=AsyncMock(return_value=[decision]),
    ), patch.object(
        service.store,
        "list_explanations",
        new=AsyncMock(return_value=[]),
    ), patch.object(
        service.store,
        "list_validations",
        new=AsyncMock(return_value=[]),
    ), patch.object(
        service.store,
        "list_reviews",
        new=AsyncMock(return_value=[]),
    ):
        audit = await service.build_audit("task_1", {"is_admin": True}, scope="task")

    assert audit["evidence_events"][0]["data"]["evidence_status"] == "unavailable"
    assert audit["audit_counts"]["evidence_unavailable"] == 1
    assert audit["audit_counts"]["evidence_events"] == 1
    assert audit["audit_counts"]["decision_records"] == 1


@pytest.mark.asyncio
async def test_decision_record_flows_from_ingest_to_audit_chain():
    store = _FakeDecisionStore()
    service = VibeAgentService()
    decision_payload = {
        "decision_type": "tool",
        "scenario": "工具选择决策",
        "candidates": [
            {"id": "get_market_data", "label": "获取行情"},
            {"id": "get_fund_flow", "label": "获取资金流"},
        ],
        "selected_option": "get_market_data",
        "selection_reason": "需要先获取行情",
        "conclusion": "选择 get_market_data",
        "evidence_ids": ["evidence_call-1"],
        "status": "confirmed",
        "confidence": 0.9,
        "risk_level": "medium",
    }

    with patch.object(service, "_save_standardized_trace", new=AsyncMock()), \
            patch.object(service, "append_event", new=AsyncMock()), \
            patch(
                "app.services.explainability.record_service.decision_record_store",
                store,
            ):
        await service.ingest_worker_event(
            {
                "user_id": "user_1",
                "session_id": "session_1",
                "task_id": "task_1",
                "event_type": "decision.record",
                "payload": decision_payload,
            }
        )

    assert len(store.decisions) == 1

    trace_event = {
        "_id": "trace_1",
        "event_type": "tool_call",
        "sequence": 1,
        "data": {
            "tool": "get_market_data",
            "evidence_id": "evidence_call-1",
            "evidence_status": "available",
            "status": "ok",
            "preview": '{"600021.SH": []}',
        },
    }
    task_db = MagicMock()
    task_db.find_one = AsyncMock(
        return_value={
            "task_id": "task_1",
            "session_id": "session_1",
            "user_id": "user_1",
        }
    )
    trace_db = MagicMock()
    trace_db.find = MagicMock(return_value=_Cursor([trace_event]))
    events_db = MagicMock()
    events_db.find = MagicMock(return_value=_Cursor([]))
    logs_db = MagicMock()
    logs_db.find = MagicMock(return_value=_Cursor([]))
    messages_db = MagicMock()
    messages_db.find_one = AsyncMock(return_value={"_id": "m", "content": "最终输出"})
    messages_db.find = MagicMock(return_value=_Cursor([]))
    trials_db = MagicMock()
    trials_db.find_one = AsyncMock(return_value=None)
    db = MagicMock()
    db.__getitem__.side_effect = lambda name: {
        "vibe_agent_tasks": task_db,
        "eval_trace_events": trace_db,
        "vibe_agent_events": events_db,
        "operation_logs": logs_db,
        "vibe_agent_messages": messages_db,
        "eval_trials": trials_db,
    }[name]

    audit_service = DecisionAuditService()
    audit_service.store = store
    with patch(
        "app.services.explainability.audit_service.get_mongo_db",
        return_value=db,
    ):
        audit = await audit_service.build_audit(
            "task_1",
            {"is_admin": True},
            scope="task",
        )

    assert audit["decision_chain"][0]["scenario"] == "工具选择决策"
    assert audit["decision_chain"][0]["selected_option"] == "get_market_data"
    assert audit["decision_chain"][0]["evidence_ids"] == ["evidence_call-1"]
    assert audit["evidence_events"][0]["data"]["evidence_status"] == "available"
    assert audit["audit_counts"]["decision_records"] == 1


@pytest.mark.asyncio
async def test_list_events_returns_paginated_items():
    service = DecisionAuditService()
    collection = MagicMock()
    collection.count_documents = AsyncMock(return_value=86)
    cursor = MagicMock()
    cursor.sort.return_value = cursor
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.__aiter__ = MagicMock(
        return_value=_AsyncList(
            [
                {
                    "_id": "event_1",
                    "event_type": "tool_call",
                    "payload": {"phase": "tool_result"},
                    "sequence": 1,
                }
            ]
        )
    )
    collection.find.return_value = cursor
    db = MagicMock()
    db.__getitem__.return_value = collection

    with patch(
        "app.services.explainability.audit_service.get_mongo_db",
        return_value=db,
    ):
        with patch.object(
            service,
            "_resolve_task",
            new=AsyncMock(return_value=None),
        ):
            with patch.object(
                service.store,
                "list_decision_records",
                new=AsyncMock(return_value=[]),
            ):
                result = await service.list_events(
                    "task_1",
                    {"is_admin": True},
                    scope="task",
                    page=2,
                    page_size=20,
                )

    assert result["page"] == 2
    assert result["page_size"] == 20
    assert result["total"] == 86
    assert result["has_more"] is True
    assert result["items"][0]["event_name"] == "工具返回"
    assert collection.count_documents.await_args.args[0]["event_type"] == {"$ne": "token"}
    cursor.skip.assert_called_once_with(20)


@pytest.mark.asyncio
async def test_list_events_denies_unauthorized_user():
    service = DecisionAuditService()
    collection = MagicMock()
    collection.count_documents = AsyncMock(return_value=1)
    cursor = MagicMock()
    cursor.__aiter__ = MagicMock(return_value=_AsyncList([]))
    collection.find.return_value = cursor
    sessions = MagicMock()
    sessions.find_one = AsyncMock(return_value=None)
    db = MagicMock()
    db.__getitem__.side_effect = lambda name: collection if name == "vibe_agent_events" else sessions

    with patch(
        "app.services.explainability.audit_service.get_mongo_db",
        return_value=db,
    ):
        with patch.object(
            service,
            "_resolve_task",
            new=AsyncMock(return_value=None),
        ):
            with patch.object(
                service.store,
                "list_decision_records",
                new=AsyncMock(return_value=[]),
            ):
                with pytest.raises(HTTPException) as exc_info:
                    await service.list_events(
                        "task_1",
                        {"is_admin": False, "id": "user_1"},
                        scope="task",
                    )

    assert exc_info.value.status_code == 403
