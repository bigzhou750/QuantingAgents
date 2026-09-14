"""决策审计状态、分页和事件名称测试。"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

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
