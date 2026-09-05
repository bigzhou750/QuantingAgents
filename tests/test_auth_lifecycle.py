"""Unit tests for refresh session rotation and auth abuse controls."""

import logging
from datetime import datetime, timedelta

import pytest

from app.core.auth_guard import AuthAttemptGuard
from app.services.auth_service import AuthService
from app.services.user_service import user_service


class _FakeSessionCollection:
    def __init__(self):
        self.sessions = []

    def create_index(self, *args, **kwargs):
        return None

    def insert_one(self, doc):
        self.sessions.append(doc)
        return True

    def find_one_and_update(self, query, update, **kwargs):
        for session in self.sessions:
            if (
                session["user_id"] == query["user_id"]
                and session["jti"] == query["jti"]
                and not session["revoked"]
                and session["expires_at"] > query["expires_at"]["$gt"]
            ):
                session.update(update["$set"])
                return session
        return None

    def update_many(self, query, update):
        updated = 0
        for session in self.sessions:
            if all(session.get(key) == value for key, value in query.items()):
                session.update(update["$set"])
                updated += 1
        return type("Result", (), {"modified_count": updated})()


class _FakeUserCollection:
    def __init__(self, docs):
        self.docs = docs

    def find_one(self, query, projection=None):
        if "_id" in query:
            for doc in self.docs.values():
                if str(doc.get("_id")) == str(query["_id"]):
                    return doc
            return None
        return self.docs.get(query.get("username"))

    def update_one(self, query, update):
        doc = self.docs.get(query["username"])
        if doc is None:
            return type("Result", (), {"matched_count": 0, "modified_count": 0})()
        if "$inc" in update:
            for key, value in update["$inc"].items():
                doc[key] = doc.get(key, 0) + value
        if "$set" in update:
            doc.update(update["$set"])
        return type("Result", (), {"matched_count": 1, "modified_count": 1})()


@pytest.mark.asyncio
async def test_password_reset_disable_and_logout_revoke_refresh_sessions():
    fake_users = _FakeUserCollection({"alice": {
        "_id": "user-a",
        "username": "alice",
        "hashed_password": "not-used",
        "is_active": True,
        "token_version": 0,
        "updated_at": datetime.utcnow(),
    }})
    fake_sessions = _FakeSessionCollection()
    old_users = user_service.users_collection
    old_db = user_service.db
    user_service.users_collection = fake_users
    user_service.db = type("FakeDb", (), {"refresh_sessions": fake_sessions})()
    try:
        assert await user_service.reset_password("alice", "NewPass1")
        assert fake_users.docs["alice"]["token_version"] == 1
        assert await user_service.deactivate_user("alice")
        assert fake_users.docs["alice"]["is_active"] is False
        assert fake_users.docs["alice"]["token_version"] == 2
        assert await user_service.revoke_tokens("alice")
        assert fake_users.docs["alice"]["token_version"] == 3
    finally:
        user_service.users_collection = old_users
        user_service.db = old_db


@pytest.mark.asyncio
async def test_authenticate_user_logs_do_not_include_plain_password_or_hash(caplog):
    fake_users = _FakeUserCollection({"alice": {
        "_id": "user-a",
        "username": "alice",
        "email": "alice@example.com",
        "hashed_password": "$2b$12$not-a-real-hash-value",
        "is_active": True,
        "token_version": 0,
    }})
    old_users = user_service.users_collection
    user_service.users_collection = fake_users
    try:
        caplog.set_level(logging.DEBUG, logger="user_service")
        await user_service.authenticate_user("alice", "super-secret-password")
        logs = caplog.text
        assert "super-secret-password" not in logs
        assert "$2b$12$not-a-real-hash-value" not in logs
    finally:
        user_service.users_collection = old_users


@pytest.mark.asyncio
async def test_refresh_session_rotation_rejects_replay_and_preserves_other_devices():
    fake = _FakeSessionCollection()
    old_db = user_service.db
    user_service.db = type("FakeDb", (), {"refresh_sessions": fake})()
    try:
        now = datetime.utcnow()
        assert await user_service.create_refresh_session(user_id="u1", jti="jti-a", expires_at=now + timedelta(days=7))
        assert await user_service.create_refresh_session(user_id="u1", jti="jti-b", expires_at=now + timedelta(days=7))

        assert await user_service.rotate_refresh_session(user_id="u1", old_jti="jti-a", new_jti="jti-c", expires_at=now + timedelta(days=7))
        assert await user_service.rotate_refresh_session(user_id="u1", old_jti="jti-b", new_jti="jti-d", expires_at=now + timedelta(days=7))

        # Old tokens cannot be replayed after rotation.
        assert not await user_service.rotate_refresh_session(user_id="u1", old_jti="jti-a", new_jti="jti-e", expires_at=now + timedelta(days=7))
        assert not await user_service.rotate_refresh_session(user_id="u1", old_jti="jti-b", new_jti="jti-f", expires_at=now + timedelta(days=7))

        # Both device families are independently active after rotation.
        jtis = {s["jti"] for s in fake.sessions if not s["revoked"]}
        assert jtis == {"jti-c", "jti-d"}
    finally:
        user_service.db = old_db


def test_access_and_refresh_tokens_carry_unique_jti():
    first = AuthService.create_access_token(sub="alice", user_id="u1", token_type="access")
    second = AuthService.create_access_token(sub="alice", user_id="u1", token_type="access")
    assert AuthService.verify_token(first).jti != AuthService.verify_token(second).jti


def test_auth_guard_limits_target_without_blocking_other_account(caplog):
    caplog.set_level(logging.DEBUG)
    guard = AuthAttemptGuard(limit=2, window_seconds=60)
    assert guard.allow("ip:1.2.3.4", "account:alice")
    assert guard.allow("ip:1.2.3.4", "account:alice")
    assert not guard.allow("ip:1.2.3.4", "account:alice")
    assert guard.allow("ip:9.9.9.9", "account:bob")


def test_token_logs_never_contain_token_value_or_hash(caplog):
    caplog.set_level(logging.DEBUG, logger="app.services.auth_service")
    AuthService.verify_token("header.payload.signature-secret-value")
    logs = caplog.text
    assert "header.payload.signature-secret-value" not in logs
    assert "signature-secret-value" not in logs
    assert "$2b$" not in logs
