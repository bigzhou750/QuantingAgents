"""Application boundary for user-scoped persistent Agent memory."""

from pathlib import Path
import sys
from typing import Any

from app.core.isolation_metrics import record_unscoped_persistence


class ScopedPersistentMemory:
    """Persistent memory facade that cannot be created without an owner scope."""

    def __init__(self, *, user_id: str, memory_dir: str | Path):
        if not user_id or not memory_dir:
            record_unscoped_persistence("persistent_memory_init")
            raise RuntimeError("persistent memory requires user scope and directory")
        self.user_id = str(user_id)
        vendor_root = Path(__file__).resolve().parents[3] / "vibe_agent_runtime" / "vendor"
        if str(vendor_root) not in sys.path:
            sys.path.insert(0, str(vendor_root))
        from src.memory.persistent import PersistentMemory
        self._memory = PersistentMemory(memory_dir=Path(memory_dir))

    def save(self, name: str, content: str, memory_type: str = "project", description: str = ""):
        return self._memory.add(name, content, memory_type, description)

    def recall(self, query: str, max_results: int = 5):
        return self._memory.find_relevant(query, max_results=max_results)

    def remove(self, name: str) -> bool:
        return self._memory.remove(name)

    def list_entries(self):
        return self._memory.list_entries()

    def stats(self) -> dict[str, Any]:
        entries = self.list_entries()
        return {"user_id": self.user_id, "count": len(entries)}

    def clear(self) -> int:
        removed = 0
        for entry in list(self.list_entries()):
            removed += int(self._memory.remove_entry(entry))
        return removed
