from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import auth_db
from app.routers.auth_db import get_current_user, router


def _make_app(role: str):
    app = FastAPI()
    app.include_router(router, prefix="/api/auth")

    if role == "admin":
        app.dependency_overrides[get_current_user] = lambda: {"id": "admin-1", "username": "admin", "is_admin": True}
    else:
        app.dependency_overrides[get_current_user] = lambda: {"id": "user-1", "username": "alice", "is_admin": False}
    return app


def test_admin_user_management_requires_admin_and_handles_missing_user(monkeypatch):
    monkeypatch.setattr(auth_db, "log_operation", _async_return(None))
    monkeypatch.setattr(auth_db.user_service, "list_users", _async_return([]))
    monkeypatch.setattr(auth_db.user_service, "deactivate_user", _async_return(True))
    monkeypatch.setattr(auth_db.user_service, "activate_user", _async_return(True))
    monkeypatch.setattr(auth_db.user_service, "set_admin_role", _async_return(True))
    monkeypatch.setattr(auth_db.user_service, "reset_password", _async_return(True))

    admin_client = TestClient(_make_app("admin"))
    assert admin_client.get("/api/auth/users").status_code == 200
    assert admin_client.patch("/api/auth/users/bob/status", json={"is_active": False}).status_code == 200
    assert admin_client.patch("/api/auth/users/bob/role", json={"is_admin": True}).status_code == 200
    assert admin_client.post("/api/auth/reset-password", json={"username": "bob", "new_password": "StrongPass1"}).status_code == 200

    missing_client = TestClient(_make_app("admin"))
    missing_client.app.dependency_overrides.clear()
    missing_client.app.dependency_overrides[get_current_user] = lambda: {"id": "admin-1", "username": "admin", "is_admin": True}
    monkeypatch.setattr(auth_db.user_service, "deactivate_user", _async_return(False))
    monkeypatch.setattr(auth_db.user_service, "set_admin_role", _async_return(False))
    monkeypatch.setattr(auth_db.user_service, "reset_password", _async_return(False))
    assert missing_client.patch("/api/auth/users/missing/status", json={"is_active": False}).status_code == 404
    assert missing_client.patch("/api/auth/users/missing/role", json={"is_admin": True}).status_code == 404
    assert missing_client.post("/api/auth/reset-password", json={"username": "missing", "new_password": "StrongPass1"}).status_code == 404


def test_regular_user_cannot_manage_accounts(monkeypatch):
    monkeypatch.setattr(auth_db, "log_operation", _async_return(None))
    client = TestClient(_make_app("user"))
    assert client.get("/api/auth/users").status_code == 403
    assert client.patch("/api/auth/users/alice/status", json={"is_active": False}).status_code == 403
    assert client.patch("/api/auth/users/alice/role", json={"is_admin": True}).status_code == 403
    assert client.post("/api/auth/reset-password", json={"username": "alice", "new_password": "StrongPass1"}).status_code == 403
    assert client.post("/api/auth/create-user", json={"username": "mallory", "email": "m@example.com", "password": "StrongPass1"}).status_code == 403


def test_admin_create_user_never_accepts_client_role_without_audit(monkeypatch):
    captured = {}
    async def capture(**kwargs):
        captured.update(kwargs)
    monkeypatch.setattr(auth_db, "log_operation", capture)
    monkeypatch.setattr(auth_db.user_service, "create_user", _async_return(SimpleNamespace(id="new-1", username="bob", email="bob@example.com")))
    monkeypatch.setattr(auth_db.user_service, "set_admin_role", _async_return(True))

    client = TestClient(_make_app("admin"))
    resp = client.post("/api/auth/create-user", json={"username": "bob", "email": "bob@example.com", "password": "StrongPass1", "is_admin": True})
    assert resp.status_code == 200
    assert captured["action_type"] == auth_db.ActionType.USER_MANAGEMENT
    assert captured["details"]["target_username"] == "bob"


def _async_return(value):
    async def _inner(*args, **kwargs):
        return value
    return _inner
