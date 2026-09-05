"""User-scoped filesystem paths for sessions, runs, memory and exports."""

from pathlib import Path
import os
import re

from app.core.config import settings


def _safe_user_id(user_id: str) -> str:
    value = str(user_id).strip()
    if not value or value in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("invalid user id for runtime scope")
    return value


def user_runtime_root(user_id: str) -> Path:
    """Return a user root below the configured runtime root, never a fallback."""
    root = Path(os.path.expanduser(settings.USER_RUNTIME_ROOT)).resolve()
    target = (root / _safe_user_id(user_id)).resolve()
    if target.parent != root:
        raise ValueError("runtime scope escaped configured root")
    return target


def user_runtime_path(user_id: str, *parts: str, create: bool = False) -> Path:
    root = user_runtime_root(user_id)
    target = (root.joinpath(*parts)).resolve()
    if target != root and root not in target.parents:
        raise ValueError("runtime path escaped user scope")
    if create:
        target.mkdir(parents=True, exist_ok=True)
    return target
