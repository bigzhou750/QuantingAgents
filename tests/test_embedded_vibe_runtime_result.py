import asyncio

from vibe_agent_runtime.runtime import EmbeddedAgentRuntime


def test_runtime_hydrates_completed_reply_from_session_store(monkeypatch, tmp_path):
    runtime = EmbeddedAgentRuntime()
    runtime._run_lock = asyncio.Lock()

    class FakeAttempt:
        status = type("Status", (), {"value": "completed"})()
        run_dir = "/runtime/run-1"
        error = None
        metrics = {"sharpe": 1.2}

    class FakeReply:
        content = "最终研究结论"
        tool_trail = [{"tool": "search", "status": "ok"}]
        metadata = {"elapsed_ms": 321}

    class FakeStore:
        def get_session(self, _session_id):
            return object()

        def _session_dir(self, session_id):
            path = tmp_path / session_id
            path.mkdir(parents=True, exist_ok=True)
            return path

        def _write_json(self, *_args):
            return None

        def _session_file(self, session_id):
            return tmp_path / session_id / "session.json"

        def get_attempt(self, _session_id, _attempt_id):
            return FakeAttempt()

        def get_message_for_attempt(self, _session_id, _attempt_id):
            return FakeReply()

    class FakeEventBus:
        def set_loop(self, _loop):
            return None

        def add_listener(self, _listener):
            return None

        def emit(self, *_args):
            return None

    class FakeService:
        def __init__(self, store, event_bus, runs_dir):
            self.store = store
            self.event_bus = event_bus
            self._active_tasks = {}

        async def ensure_session(self, *_args):
            return None

        async def send_message(self, *_args, **_kwargs):
            return {"message_id": "msg-1", "attempt_id": "attempt-1"}

    class FakeEvents:
        EventBus = FakeEventBus

    class FakeModels:
        class Principal:
            def __init__(self, **_kwargs):
                pass

        class AuthMethod:
            FEDERATED_IDENTITY = "federated_identity"

        class Session:
            def __init__(self, **_kwargs):
                pass

    class FakeStoreModule:
        SessionStore = lambda _base_dir: FakeStore()

    class FakeServiceModule:
        SessionService = FakeService

    class FakeLoopModule:
        RUNS_DIR = None
        SESSIONS_DIR = None

    modules = {
        "src.session.events": FakeEvents,
        "src.session.models": FakeModels,
        "src.session.store": FakeStoreModule,
        "src.session.service": FakeServiceModule,
        "src.agent.loop": FakeLoopModule,
    }
    monkeypatch.setattr(runtime, "_load_modules", lambda: tuple(
        modules[name] for name in (
            "src.session.events",
            "src.session.models",
            "src.session.store",
            "src.session.service",
            "src.agent.loop",
        )
    ))
    monkeypatch.setattr("vibe_agent_runtime.runtime.user_runtime_root", lambda _user_id: tmp_path)
    monkeypatch.setattr("vibe_agent_runtime.runtime.session_runtime_root", lambda _user_id, _session_id: tmp_path)

    result = asyncio.run(runtime.run(
        session_id="session-1",
        task_id="task-1",
        prompt="研究",
        title="测试",
        user_id="user-1",
        username="alice",
        sink=lambda *_args: asyncio.sleep(0),
    ))

    assert result["content"] == "最终研究结论"
    assert result["status"] == "completed"
    assert result["tool_trail"][0]["tool"] == "search"
    assert result["elapsed_ms"] == 321
