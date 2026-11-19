import asyncio
from pathlib import Path

import pytest

from app.services.vibe_agent.models import VibeCommand, new_id, utc_now
from app.services.vibe_agent.paths import (
    VibePathError,
    assert_within_user_scope,
    resolve_user_relative_path,
    safe_scope_id,
    session_runtime_root,
)
from app.services.vibe_agent.protocol import encode_command, session_event_channel, task_event_channel
from app.services.vibe_agent.service import VibeAgentService


def test_safe_scope_id_normalizes_untrusted_values():
    assert safe_scope_id(" user/../../abc ") == "user_.._.._abc"
    assert safe_scope_id("u:1@example.com") == "u_1_example.com"


def test_session_runtime_root_is_user_scoped(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.vibe_agent.paths.settings.VIBE_AGENT_RUNTIME_ROOT", str(tmp_path))
    root = session_runtime_root("user/1", "session:2")

    assert root == tmp_path.resolve() / "users" / "user_1" / "sessions" / "session_2"
    assert_within_user_scope(root / "trace" / "events.jsonl", "user/1")


def test_relative_path_rejects_absolute_and_parent_segments(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.vibe_agent.paths.settings.VIBE_AGENT_RUNTIME_ROOT", str(tmp_path))

    with pytest.raises(VibePathError):
        resolve_user_relative_path("user-1", "../other-user/secret.txt")

    with pytest.raises(VibePathError):
        resolve_user_relative_path("user-1", str(Path("/tmp/secret.txt")))


def test_redis_protocol_envelope_contains_worker_scope():
    command = VibeCommand(
        command_id=new_id("cmd"),
        command_type="run_research",
        user_id="user-1",
        username="alice",
        session_id="session-1",
        task_id="task-1",
        idempotency_key="idem-1",
        runtime_root="/runtime/vibe-agent/users/user-1/sessions/session-1",
        payload={"prompt": "研究 NVDA"},
        created_at=utc_now(),
    )

    encoded = encode_command(command)

    assert set(encoded) == {"data"}
    assert '"user_id":"user-1"' in encoded["data"]
    assert '"task_id":"task-1"' in encoded["data"]
    assert session_event_channel("session-1") == "vibe_agent:events:session-1"
    assert task_event_channel("task-1") == "vibe_agent:tasks:task-1"


def test_audit_context_is_scoped_to_authenticated_user():
    context = VibeAgentService.audit_context(
        {
            "id": "user-1",
            "username": "alice",
            "roles": ["researcher"],
            "is_admin": False,
        },
        "session-1",
        "task-1",
    )

    assert context == {
        "user_id": "user-1",
        "username": "alice",
        "session_id": "session-1",
        "task_id": "task-1",
        "roles": ["researcher"],
        "is_admin": False,
    }


def test_task_center_row_keeps_agent_isolated_from_stock_analysis():
    row = VibeAgentService().task_center_row(
        {
            "task_id": "task-1",
            "session_id": "session-1",
            "status": "queued",
            "created_at": "2026-08-25T00:00:00+00:00",
        }
    )

    assert row["task_type"] == "vibe_agent"
    assert row["task_source"] == "embedded_vibe_agent_runtime"
    assert row["analysis_type"] == "natural_language_research"
    assert row["stock_code"] == ""
    assert row["result_url"].startswith("/research-agent?session_id=session-1")


def test_event_stream_replays_history_before_connected(monkeypatch):
    service = VibeAgentService()
    replayed = []

    async def fake_replay_events(user_id: str, session_id: str, after: int = 0):
        replayed.append((user_id, session_id, after))
        return [
            {
                "sequence": 8,
                "event_id": "evt-8",
                "event_type": "tool_call",
                "session_id": session_id,
                "user_id": user_id,
                "payload": {"name": "screen_market"},
            }
        ]

    class FakePubSub:
        async def subscribe(self, _channel):
            return None

        async def get_message(self, ignore_subscribe_messages=True, timeout=1.0):
            return None

        async def unsubscribe(self, _channel):
            return None

        async def close(self):
            return None

    class FakeRedis:
        def pubsub(self):
            return FakePubSub()

    monkeypatch.setattr("app.services.vibe_agent.service.get_redis_client", lambda: FakeRedis())
    async def fake_get_session(user_id: str, session_id: str):
        return {"user_id": user_id, "session_id": session_id}

    monkeypatch.setattr(service, "get_session", fake_get_session)
    monkeypatch.setattr(service, "replay_events", fake_replay_events)

    async def collect_first_frames():
        stream = service.event_stream("user-1", "session-1", after=7)
        first = await stream.__anext__()
        second = await stream.__anext__()
        await stream.aclose()
        return first, second

    first, second = asyncio.run(collect_first_frames())

    assert replayed == [("user-1", "session-1", 7)]
    assert "event: event" in first
    assert '"sequence": 8' in first
    assert 'event: connected' in second


def test_short_follow_up_prompt_explicitly_carries_previous_turn():
    prompt = VibeAgentService._augment_follow_up_prompt(
        "需要",
        [
            {"role": "user", "content": "分析格力电器今天的持仓表现"},
            {"role": "assistant", "content": "已完成行情和风险分析"},
        ],
    )

    assert "上一轮用户问题" in prompt
    assert "分析格力电器今天的持仓表现" in prompt
    assert "当前用户消息：需要" in prompt


def test_normal_prompt_is_not_rewritten():
    content = "请分析格力电器的基本面和风险"
    assert VibeAgentService._augment_follow_up_prompt(content, []) == content


def test_profile_context_requires_explicit_request_consent():
    profile = {"risk_preference": "aggressive", "context_injection_enabled": True}
    assert not VibeAgentService.should_include_profile_context(None, profile)
    assert not VibeAgentService.should_include_profile_context("stale-profile-id", profile)
    assert VibeAgentService.should_include_profile_context("current_user_profile", profile)


def test_profile_context_saved_setting_can_disable_explicit_request():
    profile = {"context_injection_enabled": False}
    assert not VibeAgentService.should_include_profile_context("current_user_profile", profile)
