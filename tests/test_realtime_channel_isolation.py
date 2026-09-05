import asyncio

from app.routers.websocket_notifications import ConnectionManager
from app.services.vibe_agent import service as vibe_service_mod
from app.services.vibe_agent.models import VibeTaskStatus


class _FakeWebSocket:
    def __init__(self):
        self.sent = []
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def send_json(self, payload):
        self.sent.append(payload)

    async def send_text(self, payload):
        self.sent.append(payload)

    async def close(self, code=1000, reason=""):
        self.accepted = False


def test_connection_manager_delivers_only_to_owner_and_cleans_on_disconnect():
    manager = ConnectionManager()
    ws_a = _FakeWebSocket()
    ws_b = _FakeWebSocket()

    async def run():
        await manager.connect(ws_a, "user-a")
        await manager.connect(ws_b, "user-b")
        await manager.send_personal_message({"type": "private", "data": "A secret"}, "user-a")
        assert '"A secret"' in ws_a.sent[0]
        assert ws_b.sent == []
        await manager.disconnect(ws_a, "user-a")
        assert "user-a" not in manager.active_connections
        assert len(manager.active_connections["user-b"]) == 1

    asyncio.run(run())


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, length):
        return self.docs[:length]


class _FakeVibeDb:
    def __init__(self):
        self.collection = _FakeVibeCollection([
            {"user_id": "user-a", "session_id": "s-a", "task_id": "t-a"},
            {"user_id": "user-b", "session_id": "s-b", "task_id": "t-b"},
        ])

    def __getitem__(self, name):
        return self.collection


class _FakeVibeCollection:
    def __init__(self, docs):
        self.docs = docs

    def find(self, query, projection=None):
        return _Cursor(self.docs)


def test_worker_restart_recovers_orphaned_tasks_per_owner(monkeypatch):
    service = object.__new__(vibe_service_mod.VibeAgentService)
    status_calls = []
    event_calls = []

    async def fake_update(user_id, task_id, status, message):
        status_calls.append((user_id, task_id, status.value))

    async def fake_event(user_id, session_id, event_type, payload, task_id):
        event_calls.append((user_id, session_id, task_id))

    service.update_task_status = fake_update
    service.append_event = fake_event
    monkeypatch.setattr(vibe_service_mod, "get_mongo_db", lambda: _FakeVibeDb())

    asyncio.run(service.recover_orphaned_tasks())
    assert sorted(call[0] for call in status_calls) == ["user-a", "user-b"]
    assert all(status == VibeTaskStatus.failed.value for _, _, status in status_calls)
    assert sorted(call[0] for call in event_calls) == ["user-a", "user-b"]
