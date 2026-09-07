from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "vibe_agent_runtime" / "vendor"))

from app.services.vibe_agent.scoped_memory import ScopedPersistentMemory


def test_persistent_memory_isolated_by_user_directory(tmp_path):
    a = ScopedPersistentMemory(user_id="a", memory_dir=tmp_path / "a")
    b = ScopedPersistentMemory(user_id="b", memory_dir=tmp_path / "b")
    a.save("investment preference", "A private preference for value stocks")
    b.save("investment preference", "B private preference for growth stocks")

    assert [entry.body for entry in a.recall("investment preference") if "A private" in entry.body]
    assert not any("A private" in entry.body for entry in b.recall("investment preference"))
    assert a.stats()["count"] == 1
    assert a.remove("investment preference")
    assert b.stats()["count"] == 1


def test_persistent_memory_without_scope_fails_closed():
    with pytest.raises(RuntimeError, match="scope"):
        ScopedPersistentMemory(user_id="", memory_dir=Path("/tmp/memory"))
    with pytest.raises(RuntimeError, match="scope"):
        ScopedPersistentMemory(user_id="a", memory_dir="")
