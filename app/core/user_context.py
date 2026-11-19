"""Request-scoped identity primitives used by API, workers and Agent runtime.

The authenticated user is the only source of tenant identity.  Request
payloads and client supplied owner fields must never replace this context.
"""

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Iterator, Optional

from fastapi import HTTPException


@dataclass(frozen=True, slots=True)
class UserContext:
    """Immutable identity propagated through a request or background task."""

    user_id: str
    username: str
    is_admin: bool = False
    token_version: int = 0

    @property
    def scope_key(self) -> str:
        """Stable storage namespace; usernames are intentionally excluded."""
        return f"user:{self.user_id}"


_current_user: ContextVar[Optional[UserContext]] = ContextVar(
    "current_user_context", default=None
)


def get_current_user_context() -> UserContext:
    """Return the current identity or fail closed when no identity is bound."""
    context = _current_user.get()
    if context is None:
        from app.core.isolation_metrics import record_unscoped_persistence
        record_unscoped_persistence("user_context")
        raise RuntimeError("user context is required for this operation")
    return context


def maybe_current_user_context() -> Optional[UserContext]:
    """Return the current identity without changing the fail-closed contract."""
    return _current_user.get()


@contextmanager
def bind_user_context(context: UserContext) -> Iterator[UserContext]:
    """Bind an identity for the duration of a request, task, or runtime call."""
    token: Token = _current_user.set(context)
    try:
        yield context
    finally:
        _current_user.reset(token)


def require_owner(owner_id: object, *, admin_allowed: bool = False) -> UserContext:
    """Authorize a resource owner against the authenticated context.

    Normal callers can only access their own owner id.  Admin bypass is
    explicit so a future call site cannot accidentally turn every admin check
    into unrestricted cross-user access.
    """
    context = get_current_user_context()
    if str(owner_id) == context.user_id:
        return context
    if admin_allowed and context.is_admin:
        return context
    from app.core.isolation_metrics import record_authorization_denial
    record_authorization_denial(context.user_id, "resource", reason="owner_mismatch")
    raise HTTPException(status_code=404, detail="Resource not found")


def reject_client_owner(client_owner: object) -> None:
    """Reject a client owner field when it differs from authenticated identity."""
    context = get_current_user_context()
    if client_owner is not None and str(client_owner) != context.user_id:
        raise HTTPException(status_code=403, detail="Owner cannot be changed")
