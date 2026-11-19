from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "vibe_agent_runtime" / "vendor"))

from src.session.search import SessionSearchIndex


def test_session_search_indexes_are_independent(tmp_path: Path):
    a = SessionSearchIndex(tmp_path / "a.db")
    b = SessionSearchIndex(tmp_path / "b.db")
    a.index_session("a-session", "Alice private")
    a.index_message("a-session", "user", "alice-secret-preference")
    b.index_session("b-session", "Bob private")
    b.index_message("b-session", "user", "bob-secret-preference")
    assert [match.session_id for match in a.search("alice-secret-preference")] == ["a-session"]
    assert all(match.session_id != "a-session" for match in b.search("alice-secret-preference"))
    a.close()
    b.close()
