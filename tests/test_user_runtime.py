from pathlib import Path

import pytest

from app.core.config import settings
from app.core.user_runtime import user_runtime_path, user_runtime_root


def test_runtime_paths_are_user_scoped(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(settings, "USER_RUNTIME_ROOT", str(tmp_path))
    a = user_runtime_path("user-a", "sessions", create=True)
    b = user_runtime_path("user-b", "sessions", create=True)
    assert a != b
    assert a.parent == tmp_path / "user-a"
    assert b.parent == tmp_path / "user-b"
    assert a.exists() and b.exists()


def test_runtime_rejects_traversal_and_invalid_scope(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(settings, "USER_RUNTIME_ROOT", str(tmp_path))
    with pytest.raises(ValueError):
        user_runtime_root("../other")
    with pytest.raises(ValueError):
        user_runtime_path("user-a", "../../other")
