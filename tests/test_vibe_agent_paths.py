from pathlib import Path

import pytest

from app.core.config import settings
from app.services.vibe_agent.paths import (
    assert_within_user_scope,
    session_runtime_root,
    user_runtime_root,
)


def test_vibe_paths_are_separate_per_user(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(settings, "VIBE_AGENT_RUNTIME_ROOT", str(tmp_path))
    a = session_runtime_root("user-a", "session-1")
    b = session_runtime_root("user-b", "session-1")
    assert a != b
    assert user_runtime_root("user-a") in a.parents
    assert user_runtime_root("user-b") in b.parents
    assert assert_within_user_scope(a, "user-a") == a.resolve()


def test_vibe_path_cannot_cross_user_root(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(settings, "VIBE_AGENT_RUNTIME_ROOT", str(tmp_path))
    other = user_runtime_root("user-b") / "sessions" / "session-1"
    with pytest.raises(ValueError):
        assert_within_user_scope(other, "user-a")


def test_memory_path_is_inside_user_scope(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(settings, "VIBE_AGENT_RUNTIME_ROOT", str(tmp_path))
    memory = user_runtime_root("user-a") / "memory"
    assert assert_within_user_scope(memory, "user-a") == memory.resolve()
