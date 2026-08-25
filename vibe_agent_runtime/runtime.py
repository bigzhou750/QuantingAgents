"""QuantingAgents adapter for the vendored Vibe Agent runtime.

The vendored package keeps its upstream ``src.*`` imports.  This module adds
only the internal vendor directory to ``sys.path`` and supplies the host
application's runtime root and event callback.  No external Vibe source path
is accepted here.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import os
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.core.config import settings
from app.core.unified_config import unified_config
from app.services.vibe_agent.paths import (
    safe_scope_id,
    session_runtime_root,
    user_runtime_root,
    vibe_runtime_base,
)
from .policy import disabled_tool_names

logger = logging.getLogger(__name__)
EventSink = Callable[[str, dict[str, Any]], Awaitable[None]]


class EmbeddedAgentRuntime:
    """Lazy, process-local facade around the migrated Vibe AgentLoop."""

    def __init__(self) -> None:
        self._bootstrapped = False
        self._active: dict[str, tuple[str, Any, Any, EventSink]] = {}
        # Vibe's AgentLoop retains a few module-level path variables. The
        # lock prevents concurrent executions from changing those variables
        # while another user's run is writing artifacts.
        self._run_lock = asyncio.Lock()

    @property
    def vendor_root(self) -> Path:
        return Path(__file__).resolve().parent / "vendor"

    @staticmethod
    def _default_provider_for_model(model_name: str) -> str:
        model = (model_name or "").strip().lower()
        if not model:
            return "qwen"
        if "/" in model:
            prefix = model.split("/", 1)[0]
            if prefix in {
                "openai",
                "anthropic",
                "openrouter",
                "requesty",
                "deepseek",
                "dashscope",
                "qwen",
                "zhipu",
                "glm",
                "gemini",
                "moonshot",
                "kimi",
                "nvidia",
                "groq",
                "spark",
                "iflytek",
                "ollama",
                "copilot",
                "github-copilot",
                "openai-codex",
                "openai_codex",
            }:
                return prefix
        if model.startswith("qwen") or "qwen" in model:
            return "qwen"
        if model.startswith("gpt") or "gpt-" in model or "openai" in model:
            return "openai"
        if model.startswith("claude") or "claude" in model:
            return "anthropic"
        if model.startswith("deepseek") or "deepseek" in model:
            return "deepseek"
        if model.startswith("gemini") or "gemini" in model:
            return "gemini"
        if model.startswith("glm") or "glm" in model:
            return "glm"
        if "moonshot" in model or "kimi" in model:
            return "moonshot"
        return "qwen"

    @staticmethod
    def _is_valid_api_key(value: str | None) -> bool:
        if not value:
            return False
        key = value.strip()
        if not key:
            return False
        if key.startswith("your_") or key.startswith("your-"):
            return False
        if key.endswith("_here") or key.endswith("-here"):
            return False
        if "..." in key:
            return False
        return len(key) > 10

    def _sync_runtime_llm_env(self) -> None:
        default_model = (
            unified_config.get_default_model()
            or unified_config.get_quick_analysis_model()
            or "qwen-turbo"
        ).strip()
        provider = self._default_provider_for_model(default_model)
        api_key = ""
        base_url = ""

        try:
            from app.core.database import get_mongo_db_sync

            db = get_mongo_db_sync()
            doc = db.system_configs.find_one({"is_active": True}, sort=[("version", -1)])
            if doc:
                for config in doc.get("llm_configs", []) or []:
                    if str(config.get("model_name") or "").strip() == default_model:
                        provider = str(config.get("provider") or provider).strip().lower() or provider
                        base_url = str(config.get("api_base") or "").strip()
                        break
            if not base_url and provider:
                provider_doc = db.llm_providers.find_one({"name": provider})
                if provider_doc is None and provider == "qwen":
                    provider_doc = db.llm_providers.find_one({"name": "dashscope"})
                if provider_doc and not base_url:
                    base_url = str(provider_doc.get("default_base_url") or "").strip()
        except Exception:
            logger.debug("embedded Vibe runtime model lookup fell back to heuristics", exc_info=True)

        try:
            from src.providers.capabilities import provider_env_names
        except Exception:
            provider_env_names = None  # type: ignore[assignment]

        key_env = base_env = None
        if provider_env_names is not None:
            key_env, base_env = provider_env_names(provider, default_model)

        env_api_key = ""
        for candidate_name in filter(None, [key_env, "OPENAI_API_KEY"]):
            candidate = os.getenv(candidate_name, "").strip()
            if self._is_valid_api_key(candidate):
                env_api_key = candidate
                break

        if env_api_key:
            api_key = env_api_key

        try:
            from app.core.database import get_mongo_db_sync

            db = get_mongo_db_sync()
            doc = db.system_configs.find_one({"is_active": True}, sort=[("version", -1)])
            if doc:
                for config in doc.get("llm_configs", []) or []:
                    if str(config.get("model_name") or "").strip() == default_model:
                        if not api_key:
                            candidate = str(config.get("api_key") or "").strip()
                            if self._is_valid_api_key(candidate):
                                api_key = candidate
                        break
            provider_doc = None
            if provider:
                provider_doc = db.llm_providers.find_one({"name": provider})
                if provider_doc is None and provider == "qwen":
                    provider_doc = db.llm_providers.find_one({"name": "dashscope"})
            if provider_doc:
                if not api_key:
                    candidate = str(provider_doc.get("api_key") or "").strip()
                    if self._is_valid_api_key(candidate):
                        api_key = candidate
                if not base_url:
                    base_url = str(provider_doc.get("default_base_url") or "").strip()
        except Exception:
            logger.debug("embedded Vibe runtime model lookup fell back to heuristics", exc_info=True)

        os.environ["LANGCHAIN_PROVIDER"] = provider
        os.environ["LANGCHAIN_MODEL_NAME"] = default_model

        if api_key:
            if key_env:
                os.environ[key_env] = api_key
            os.environ["OPENAI_API_KEY"] = api_key
        elif key_env and os.getenv(key_env):
            os.environ["OPENAI_API_KEY"] = os.getenv(key_env, "")

        if base_url:
            if base_env:
                os.environ[base_env] = base_url
            os.environ["OPENAI_BASE_URL"] = base_url
            os.environ["OPENAI_API_BASE"] = base_url
        elif base_env and os.getenv(base_env):
            resolved_base = os.getenv(base_env, "")
            if resolved_base:
                os.environ["OPENAI_BASE_URL"] = resolved_base
                os.environ["OPENAI_API_BASE"] = resolved_base

        try:
            from src.config.accessor import reset_env_config

            reset_env_config()
        except Exception:
            logger.debug("embedded Vibe runtime env cache reset skipped", exc_info=True)

    def _bootstrap(self) -> None:
        vendor_root = self.vendor_root.resolve()
        if not vendor_root.is_dir():
            raise RuntimeError(f"embedded Vibe runtime is missing: {vendor_root}")
        if not self._bootstrapped and str(vendor_root) not in sys.path:
            sys.path.insert(0, str(vendor_root))
        runtime_root = vibe_runtime_base() / "embedded"
        runtime_root.mkdir(parents=True, exist_ok=True)
        os.environ["VIBE_TRADING_HOME"] = str(runtime_root)
        os.environ["QUANTINGAGENTS_DISABLED_VIBE_TOOLS"] = ",".join(
            sorted(disabled_tool_names())
        )
        self._sync_runtime_llm_env()
        self._bootstrapped = True

    def _load_modules(self) -> tuple[Any, Any, Any, Any, Any]:
        self._bootstrap()
        events = importlib.import_module("src.session.events")
        models = importlib.import_module("src.session.models")
        store_module = importlib.import_module("src.session.store")
        service_module = importlib.import_module("src.session.service")
        loop_module = importlib.import_module("src.agent.loop")
        return events, models, store_module, service_module, loop_module

    def _on_event(self, event: Any, task_id: str, sink: EventSink) -> None:
        active = self._active.get(str(event.session_id))
        if active is None:
            return
        payload = dict(event.data or {})
        payload.setdefault("session_id", event.session_id)
        payload.setdefault("task_id", task_id)
        loop = active[2]._loop
        if loop is None or loop.is_closed():
            return
        future = asyncio.run_coroutine_threadsafe(
            sink(str(event.event_type), payload),
            loop,
        )
        future.add_done_callback(self._log_sink_failure)

    @staticmethod
    def _log_sink_failure(future: Any) -> None:
        try:
            future.result()
        except Exception:
            logger.exception("embedded Vibe event sink failed")

    async def ensure_session(self, service: Any, models: Any, session_id: str, title: str, user_id: str, username: str) -> None:
        if service.store.get_session(session_id) is not None:
            return
        principal = models.Principal(
            subject=str(user_id),
            auth_method=models.AuthMethod.FEDERATED_IDENTITY,
            display_name=username,
        )
        # The authenticated API already owns the public session id. Persist a
        # matching embedded record rather than letting the upstream service
        # generate a second, unreferenced id.
        session = models.Session(
            session_id=session_id,
            title=title,
            owner=principal,
        )
        # The QuantingAgents API creates the scoped artifact directories
        # before scheduling the task. Upstream SessionStore treats an
        # existing directory as a duplicate session, so initialize its
        # session.json in place when the directory already exists.
        session_dir = service.store._session_dir(session_id)
        if session_dir.exists():
            service.store._write_json(service.store._session_file(session_id), session.to_dict())
        else:
            try:
                service.store.create_session(session)
            except ValueError:
                # Another API/reload worker may have initialized it between
                # the existence check and this write.
                if service.store.get_session(session_id) is None:
                    raise
        service.event_bus.emit(session_id, "session.created", {"session_id": session_id, "title": title})

    async def run(
        self,
        *,
        session_id: str,
        task_id: str,
        prompt: str,
        title: str,
        user_id: str,
        username: str,
        sink: EventSink,
    ) -> dict[str, Any]:
        async with self._run_lock:
            events, models, store_module, service_module, loop_module = self._load_modules()
            event_bus = events.EventBus()
            event_bus.set_loop(asyncio.get_running_loop())
            user_root = user_runtime_root(user_id)
            session_root = session_runtime_root(user_id, session_id)
            for child in ("messages", "attempts", "runs", "swarm", "trace", "uploads", "artifacts"):
                (session_root / child).mkdir(parents=True, exist_ok=True)
            service = service_module.SessionService(
                store=store_module.SessionStore(user_root / "sessions"),
                event_bus=event_bus,
                runs_dir=session_root / "runs",
            )
            event_bus.add_listener(lambda event: self._on_event(event, task_id, sink))
            await self.ensure_session(service, models, session_id, title, user_id, username)
            # AgentLoop resolves these directories at module scope. They are
            # set only while the serialized run lock is held.
            loop_module.RUNS_DIR = session_root / "runs"
            loop_module.SESSIONS_DIR = user_root / "sessions"
            self._active[session_id] = (task_id, service, event_bus, sink)
            try:
                result = await service.send_message(
                    session_id,
                    prompt,
                    role="user",
                    include_shell_tools=False,
                )
                task = service._active_tasks.get(session_id)
                if task is not None:
                    await task
                attempt_id = str(result.get("attempt_id") or "")
                attempt = (
                    service.store.get_attempt(session_id, attempt_id)
                    if attempt_id
                    else None
                )
                reply = (
                    service.store.get_message_for_attempt(session_id, attempt_id)
                    if attempt_id
                    else None
                )
                # send_message() returns the enqueue envelope. The completed
                # assistant reply is persisted by SessionService._run_attempt,
                # so hydrate it before crossing back into the QuantingAgents
                # Mongo/SSE adapter.
                return {
                    **result,
                    "status": attempt.status.value if attempt else "failed",
                    "content": reply.content if reply else "",
                    "run_dir": attempt.run_dir if attempt else None,
                    "reason": attempt.error if attempt else None,
                    "metrics": attempt.metrics if attempt else None,
                    "tool_trail": reply.tool_trail if reply else [],
                    "elapsed_ms": (
                        reply.metadata.get("elapsed_ms")
                        if reply and isinstance(reply.metadata, dict)
                        else None
                    ),
                }
            finally:
                self._active.pop(session_id, None)

    async def cancel(self, session_id: str) -> bool:
        active = self._active.get(session_id)
        return bool(active and active[1].cancel_current(session_id))

    def capabilities(self) -> dict[str, Any]:
        """Return tools, skills and Swarm preset diagnostics."""
        try:
            self._bootstrap()
            skills = importlib.import_module("src.agent.skills")
            presets = importlib.import_module("src.swarm.presets")
            result: dict[str, Any] = {
                "available": True,
                "vendor_root": str(self.vendor_root),
                "skills": sorted(item.name for item in skills.SkillsLoader().skills),
                "skill_count": len(skills.SkillsLoader().skills),
                "swarm_presets": presets.list_presets(),
            }
            try:
                tools = importlib.import_module("src.tools")
                registry = tools.build_registry(include_shell_tools=False)
                result.update(
                    {
                        "tools": sorted(registry.tool_names),
                        "tool_count": len(registry),
                        "tool_import_failures": registry.import_failures,
                        "tool_registration_failures": registry.registration_failures,
                    }
                )
            except Exception as exc:
                result.update(
                    {
                        "tools": [],
                        "tool_count": 0,
                        "tool_import_failures": {},
                        "tool_registration_failures": {},
                        "tools_available": False,
                        "tools_error": f"{type(exc).__name__}: {exc}",
                    }
                )
            return result
        except Exception as exc:
            return {
                "available": False,
                "vendor_root": str(self.vendor_root),
                "error": f"{type(exc).__name__}: {exc}",
            }


embedded_agent_runtime = EmbeddedAgentRuntime()
