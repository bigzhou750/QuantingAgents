from fastapi import HTTPException
import pytest

from app.core.user_context import (
    UserContext,
    bind_user_context,
    get_current_user_context,
    reject_client_owner,
    require_owner,
)


def test_context_uses_immutable_user_id_scope():
    context = UserContext(user_id="507f1f77bcf86cd799439011", username="alice")
    with bind_user_context(context):
        assert get_current_user_context() == context
        assert context.scope_key == "user:507f1f77bcf86cd799439011"
        assert require_owner(context.user_id) == context


def test_context_is_fail_closed_outside_binding():
    with pytest.raises(RuntimeError, match="user context is required"):
        get_current_user_context()


def test_cross_user_owner_is_not_revealed():
    context = UserContext(user_id="user-a", username="alice")
    with bind_user_context(context):
        with pytest.raises(HTTPException) as error:
            require_owner("user-b")
    assert error.value.status_code == 404


def test_client_cannot_override_owner():
    context = UserContext(user_id="user-a", username="alice")
    with bind_user_context(context):
        with pytest.raises(HTTPException) as error:
            reject_client_owner("user-b")
    assert error.value.status_code == 403
