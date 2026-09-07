from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import websocket_notifications as ws_mod
from app.services.auth_service import TokenData


class _FakeTaskDb:
    def __init__(self):
        self.tasks = {
            "T1": {"task_id": "T1", "user_id": "user-a"},
            "T2": {"task_id": "T2", "user_id": "user-b"},
        }

    def __getitem__(self, name):
        return self

    def __getattr__(self, name):
        if name == "analysis_tasks":
            return self
        raise AttributeError(name)

    async def find_one(self, query, projection=None):
        task_id = query.get("task_id")
        task = self.tasks.get(task_id)
        owner_conditions = query.get("$or", [{"user_id": query.get("user_id")}])
        if task and any(task.get(key) == value for condition in owner_conditions for key, value in condition.items()):
            return {"_id": task_id}
        return None


def _make_app():
    app = FastAPI()
    app.include_router(ws_mod.router, prefix="/api")
    return app


def _patch_token(monkeypatch, *, user_id="user-a", token_type="access", token_version=0, valid=True):
    def fake_verify(token):
        if not valid:
            return None
        return TokenData(sub=user_id, user_id=user_id, token_type=token_type, token_version=token_version, exp=4102444800)
    monkeypatch.setattr(ws_mod.AuthService, "verify_token", staticmethod(fake_verify))


def _patch_user(monkeypatch, *, is_active=True, token_version=0):
    async def fake_get(user_id):
        return SimpleNamespace(id=user_id, username="alice", is_active=is_active, token_version=token_version)
    monkeypatch.setattr(ws_mod.user_service, "get_user_by_id", fake_get)


def test_notification_websocket_requires_valid_token_and_active_account(monkeypatch):
    app = _make_app()
    _patch_token(monkeypatch, user_id="user-a")
    _patch_user(monkeypatch)
    client = TestClient(app)
    with client.websocket_connect("/api/ws/notifications?token=good") as ws:
        data = ws.receive_json()
        assert data["type"] == "connected"
        assert data["data"]["user_id"] == "user-a"

    _patch_token(monkeypatch, valid=False)
    with pytest.raises(Exception):
        with client.websocket_connect("/api/ws/notifications?token=bad"):
            pass

    _patch_token(monkeypatch, user_id="user-a")
    _patch_user(monkeypatch, is_active=False)
    with pytest.raises(Exception):
        with client.websocket_connect("/api/ws/notifications?token=disabled"):
            pass


def test_task_websocket_rejects_cross_user_and_invalid_token_version(monkeypatch):
    app = _make_app()
    _patch_token(monkeypatch, user_id="user-a")
    _patch_user(monkeypatch, is_active=True, token_version=0)
    monkeypatch.setattr(ws_mod, "get_mongo_db", lambda: _FakeTaskDb())
    client = TestClient(app)

    with client.websocket_connect("/api/ws/tasks/T1?token=good") as ws:
        data = ws.receive_json()
        assert data["data"]["task_id"] == "T1"

    with pytest.raises(Exception):
        with client.websocket_connect("/api/ws/tasks/T2?token=good"):
            pass

    _patch_token(monkeypatch, user_id="user-a", token_version=1)
    with pytest.raises(Exception):
        with client.websocket_connect("/api/ws/tasks/T1?token=stale"):
            pass
