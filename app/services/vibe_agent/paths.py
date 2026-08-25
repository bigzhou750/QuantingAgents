import re
from pathlib import Path

from app.core.config import settings


SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_.-]+")


class VibePathError(ValueError):
    pass


def safe_scope_id(value: str) -> str:
    cleaned = SAFE_ID_RE.sub("_", str(value).strip())
    cleaned = cleaned.strip("._")
    if not cleaned:
        raise VibePathError("scope id cannot be empty")
    return cleaned[:96]


def vibe_runtime_base() -> Path:
    configured = getattr(settings, "VIBE_AGENT_RUNTIME_ROOT", "~/.quantingagents/runtime/vibe-agent")
    root = Path(configured).expanduser().resolve()
    project_root = Path(__file__).resolve().parents[3]
    if root == project_root or project_root in root.parents:
        raise VibePathError("VIBE_AGENT_RUNTIME_ROOT must be outside the source tree")
    return root


def user_runtime_root(user_id: str) -> Path:
    return vibe_runtime_base() / "users" / safe_scope_id(user_id)


def session_runtime_root(user_id: str, session_id: str) -> Path:
    return user_runtime_root(user_id) / "sessions" / safe_scope_id(session_id)


def attempt_runtime_root(user_id: str, session_id: str, attempt: int) -> Path:
    return session_runtime_root(user_id, session_id) / "attempts" / f"{int(attempt):04d}"


def ensure_session_tree(user_id: str, session_id: str) -> Path:
    root = session_runtime_root(user_id, session_id)
    for child in ("messages", "attempts", "runs", "swarm", "trace", "uploads", "artifacts"):
        (root / child).mkdir(parents=True, exist_ok=True)
    return root


def assert_within_user_scope(path: Path, user_id: str) -> Path:
    resolved = path.expanduser().resolve()
    user_root = user_runtime_root(user_id).resolve()
    if resolved != user_root and user_root not in resolved.parents:
        raise VibePathError("path escapes user runtime scope")
    return resolved


def resolve_user_relative_path(user_id: str, relative_path: str) -> Path:
    candidate = Path(relative_path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise VibePathError("only normalized relative paths are allowed")
    return assert_within_user_scope(user_runtime_root(user_id) / candidate, user_id)
