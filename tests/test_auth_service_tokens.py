import jwt
import pytest

from app.core.config import settings
from app.services.auth_service import AuthService


def test_new_token_contains_stable_identity_and_type():
    token = AuthService.create_access_token(
        sub="alice",
        user_id="507f1f77bcf86cd799439011",
        token_type="refresh",
    )
    data = AuthService.verify_token(token)
    assert data is not None
    assert data.user_id == "507f1f77bcf86cd799439011"
    assert data.token_type == "refresh"
    assert data.issuer == settings.AUTH_TOKEN_ISSUER


def test_wrong_secret_is_rejected():
    token = jwt.encode(
        {"sub": "alice", "user_id": "user-a", "type": "access", "exp": 4102444800},
        "wrong-secret",
        algorithm=settings.JWT_ALGORITHM,
    )
    assert AuthService.verify_token(token) is None


def test_legacy_username_token_is_readable_during_compatibility_window():
    token = jwt.encode(
        {"sub": "alice", "exp": 4102444800},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    data = AuthService.verify_token(token)
    assert data is not None
    assert data.sub == "alice"
    assert data.user_id is None
    assert data.token_type == "access"
