import asyncio
from datetime import datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import auth_db
from app.routers.auth_db import get_current_user, router
from app.models.user import UserAdminResponse, UserListResult, UserPreferences, UserResponse


def _async_return(value):
    async def _inner(*args, **kwargs):
        return value
    return _inner


def _make_app(role: str):
    app = FastAPI()
    app.include_router(router, prefix="/api/auth")

    if role == "admin":
        app.dependency_overrides[get_current_user] = lambda: {"id": "admin-1", "username": "admin", "is_admin": True}
    else:
        app.dependency_overrides[get_current_user] = lambda: {"id": "user-1", "username": "alice", "is_admin": False}
    return app


def _user_response(username: str = "bob", balance: float = 0.0):
    return UserResponse(
        id="u1",
        username=username,
        email=f"{username}@example.com",
        is_active=True,
        is_verified=True,
        is_admin=False,
        is_archived=False,
        created_at=datetime(2026, 1, 1),
        last_login=None,
        preferences=UserPreferences(),
        daily_quota=1000,
        concurrent_limit=3,
        total_analyses=0,
        successful_analyses=0,
        failed_analyses=0,
        balance=balance,
    )


def _admin_detail(username: str = "bob", email: str = None, is_active: bool = True, is_admin: bool = False, is_archived: bool = False, balance: float = 0.0):
    return UserAdminResponse(
        id="u1",
        username=username,
        email=email or f"{username}@example.com",
        is_active=is_active,
        is_verified=True,
        is_admin=is_admin,
        is_archived=is_archived,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 2),
        last_login=None,
        preferences=UserPreferences(),
        daily_quota=1000,
        concurrent_limit=3,
        total_analyses=1,
        successful_analyses=1,
        failed_analyses=0,
        balance=balance,
    )


def test_admin_can_list_search_and_view_users(monkeypatch):
    monkeypatch.setattr(
        auth_db.user_service,
        "list_users",
        _async_return(UserListResult(users=[_user_response(balance=12.5)], total=1)),
    )
    monkeypatch.setattr(auth_db.user_service, "get_user_admin_detail", _async_return(_admin_detail()))

    client = TestClient(_make_app("admin"))
    resp = client.get("/api/auth/users", params={"keyword": "bob", "status": "active", "skip": 0, "limit": 10})
    assert resp.status_code == 200
    payload = resp.json()["data"]
    assert payload["total"] == 1
    assert payload["users"][0]["username"] == "bob"
    assert payload["users"][0]["is_admin"] is False
    assert payload["users"][0]["is_archived"] is False
    assert payload["users"][0]["balance"] == 12.5

    assert client.get("/api/auth/users", params={"status": "bad"}).status_code == 400

    detail_resp = client.get("/api/auth/users/bob")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["data"]["username"] == "bob"
    assert detail_resp.json()["data"]["balance"] == 0.0
    assert "hashed_password" not in detail_resp.json()["data"]


def test_admin_update_and_archive_user_with_audit(monkeypatch):
    logs = []

    async def capture_log(**kwargs):
        logs.append(kwargs)

    monkeypatch.setattr(auth_db, "log_operation", capture_log)
    monkeypatch.setattr(auth_db.user_service, "get_user_admin_detail", _async_return(_admin_detail()))
    monkeypatch.setattr(
        auth_db.user_service,
        "update_user_admin",
        _async_return(_admin_detail(email="new@example.com")),
    )
    monkeypatch.setattr(auth_db.user_service, "archive_user", _async_return(True))

    client = TestClient(_make_app("admin"))

    update_resp = client.patch(
        "/api/auth/users/bob",
        json={"email": "new@example.com", "daily_quota": 500, "concurrent_limit": 5},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["data"]["email"] == "new@example.com"

    archive_resp = client.delete("/api/auth/users/bob")
    assert archive_resp.status_code == 200
    assert archive_resp.json()["data"]["is_archived"] is True

    assert len(logs) == 2
    assert all(log["action_type"] == auth_db.ActionType.USER_MANAGEMENT for log in logs)


def test_admin_self_protection(monkeypatch):
    monkeypatch.setattr(
        auth_db.user_service,
        "get_user_admin_detail",
        _async_return(_admin_detail(username="admin", is_admin=True)),
    )

    client = TestClient(_make_app("admin"))
    assert client.delete("/api/auth/users/admin").status_code == 400
    assert client.patch("/api/auth/users/admin/status", json={"is_active": False}).status_code == 400
    assert client.patch("/api/auth/users/admin/role", json={"is_admin": False}).status_code == 400


def test_missing_user_returns_404(monkeypatch):
    monkeypatch.setattr(auth_db.user_service, "get_user_admin_detail", _async_return(None))
    monkeypatch.setattr(auth_db.user_service, "archive_user", _async_return(False))
    monkeypatch.setattr(auth_db.user_service, "reset_password", _async_return(False))
    monkeypatch.setattr(auth_db.user_service, "update_user_admin", _async_return(None))

    client = TestClient(_make_app("admin"))
    assert client.get("/api/auth/users/missing").status_code == 404
    assert client.patch("/api/auth/users/missing", json={"email": "new@example.com"}).status_code == 404
    assert client.delete("/api/auth/users/missing").status_code == 404
    assert client.patch("/api/auth/users/missing/status", json={"is_active": False}).status_code == 404
    assert client.patch("/api/auth/users/missing/role", json={"is_admin": True}).status_code == 404
    assert client.post("/api/auth/reset-password", json={"username": "missing", "new_password": "StrongPass1"}).status_code == 404


def test_regular_user_cannot_manage_accounts(monkeypatch):
    monkeypatch.setattr(auth_db, "log_operation", _async_return(None))
    client = TestClient(_make_app("user"))

    assert client.get("/api/auth/users").status_code == 403
    assert client.get("/api/auth/users/alice").status_code == 403
    assert client.patch("/api/auth/users/alice", json={"email": "new@example.com"}).status_code == 403
    assert client.delete("/api/auth/users/alice").status_code == 403
    assert client.patch("/api/auth/users/alice/status", json={"is_active": False}).status_code == 403
    assert client.patch("/api/auth/users/alice/role", json={"is_admin": True}).status_code == 403
    assert client.post("/api/auth/reset-password", json={"username": "alice", "new_password": "StrongPass1"}).status_code == 403
    assert client.post("/api/auth/create-user", json={"username": "mallory", "email": "m@example.com", "password": "StrongPass1"}).status_code == 403


def test_admin_create_user_never_accepts_client_role_without_audit(monkeypatch):
    captured = {}

    async def capture(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(
        auth_db,
        "token_billing_service",
        SimpleNamespace(grant_registration_bonus=_async_return({"txn_id": "GFT_001"})),
    )
    monkeypatch.setattr(auth_db, "log_operation", capture)
    monkeypatch.setattr(
        auth_db.user_service,
        "create_user",
        _async_return(SimpleNamespace(id="new-1", username="bob", email="bob@example.com")),
    )
    monkeypatch.setattr(auth_db.user_service, "set_admin_role", _async_return(True))

    client = TestClient(_make_app("admin"))
    resp = client.post(
        "/api/auth/create-user",
        json={"username": "bob", "email": "bob@example.com", "password": "StrongPass1", "is_admin": True},
    )
    assert resp.status_code == 200
    assert captured["action_type"] == auth_db.ActionType.USER_MANAGEMENT
    assert captured["details"]["target_username"] == "bob"
    assert captured["details"]["bonus_yuan"] == 5.0
    assert resp.json()["data"]["bonus"]["txn_id"] == "GFT_001"


def test_public_register_grants_registration_bonus_and_logs(monkeypatch):
    captured = {}

    async def capture(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(
        auth_db.user_service,
        "create_user",
        _async_return(SimpleNamespace(id="new-2", username="carol", email="carol@example.com")),
    )
    monkeypatch.setattr(
        auth_db,
        "token_billing_service",
        SimpleNamespace(grant_registration_bonus=_async_return({"txn_id": "GFT_002"})),
    )
    monkeypatch.setattr(auth_db, "log_operation", capture)

    app = FastAPI()
    app.include_router(router, prefix="/api/auth")
    client = TestClient(app)
    resp = client.post("/api/auth/register", json={
        "username": "carol",
        "email": "carol@example.com",
        "password": "StrongPass1",
        "confirm_password": "StrongPass1",
        "agreement": True,
    })

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["bonus"]["amount_yuan"] == 5.0
    assert data["bonus"]["txn_id"] == "GFT_002"
    assert captured["action_type"] == auth_db.ActionType.USER_REGISTER
    assert captured["details"]["bonus_yuan"] == 5.0


def test_archived_accounts_are_rejected_by_auth(monkeypatch):
    app = FastAPI()
    app.include_router(router, prefix="/api/auth")
    client = TestClient(app)

    monkeypatch.setattr(
        auth_db.AuthService,
        "verify_token",
        lambda token: SimpleNamespace(sub="archived", user_id="u1", token_type="access", token_version=0),
    )
    monkeypatch.setattr(
        auth_db.user_service,
        "get_user_by_id",
        _async_return(SimpleNamespace(
            id="u1",
            username="archived",
            email="archived@example.com",
            is_active=True,
            is_archived=True,
            is_admin=False,
            preferences=None,
        )),
    )
    monkeypatch.setattr(auth_db.user_service, "get_user_by_username", _async_return(None))

    assert client.get("/api/auth/me", headers={"Authorization": "Bearer fake"}).status_code == 401

    monkeypatch.setattr(
        auth_db.AuthService,
        "verify_token",
        lambda token: SimpleNamespace(sub="archived", user_id="u1", token_type="refresh", token_version=0),
    )
    assert client.post("/api/auth/refresh", json={"refresh_token": "fake"}).status_code == 401


def test_authenticate_user_rejects_archived_account(monkeypatch):
    class FakeCollection:
        def __init__(self, doc):
            self.doc = doc

        def find_one(self, *args, **kwargs):
            return self.doc

    monkeypatch.setattr(
        auth_db.user_service,
        "users_collection",
        FakeCollection({
            "username": "archived",
            "email": "archived@example.com",
            "hashed_password": "$2b$12$abcdefghijklmnopqrstuv",
            "is_active": True,
            "is_archived": True,
        }),
    )
    monkeypatch.setattr(auth_db.user_service, "verify_password", lambda plain, hashed: True)

    result = asyncio.run(auth_db.user_service.authenticate_user("archived", "password"))
    assert result is None


def test_archive_user_only_marks_account_and_revokes_sessions(monkeypatch):
    calls = []

    class FakeUsersCollection:
        def update_one(self, filter, update):
            calls.append("update_user")
            return SimpleNamespace(matched_count=1)

        def find_one(self, filter, projection=None):
            return {"_id": "u1"}

    class FakeRefreshSessions:
        def update_many(self, filter, update):
            calls.append("revoke_sessions")

    monkeypatch.setattr(auth_db.user_service, "users_collection", FakeUsersCollection())
    monkeypatch.setattr(
        auth_db.user_service,
        "db",
        SimpleNamespace(refresh_sessions=FakeRefreshSessions()),
    )

    assert asyncio.run(auth_db.user_service.archive_user("bob")) is True
    assert calls == ["update_user", "revoke_sessions"]
