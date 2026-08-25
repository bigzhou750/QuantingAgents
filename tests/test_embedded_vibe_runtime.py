from pathlib import Path

import pytest

from app.services.vibe_agent.paths import VibePathError, resolve_user_relative_path
from vibe_agent_runtime import embedded_agent_runtime
from vibe_agent_runtime.guards import validate_vendor_tree
from vibe_agent_runtime.policy import disabled_tool_names


def test_vendored_runtime_has_no_external_source_or_runtime_artifacts():
    root = Path("vibe_agent_runtime/vendor")
    assert root.joinpath("src/agent/loop.py").is_file()
    assert root.joinpath("src/tools/__init__.py").is_file()
    assert root.joinpath("src/agent/skills.py").is_file()
    assert root.joinpath("src/swarm/runtime.py").is_file()
    assert not validate_vendor_tree(root)


def test_capability_inventory_discovers_migrated_runtime(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.services.vibe_agent.paths.settings.VIBE_AGENT_RUNTIME_ROOT",
        str(tmp_path),
    )
    result = embedded_agent_runtime.capabilities()
    assert result["available"] is True
    assert result["tool_count"] >= 1
    assert result["skill_count"] >= 1
    assert result["swarm_presets"]


def test_runtime_relative_paths_cannot_escape_scope(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.services.vibe_agent.paths.settings.VIBE_AGENT_RUNTIME_ROOT",
        str(tmp_path),
    )
    with pytest.raises(VibePathError):
        resolve_user_relative_path("user-1", "../user-2/trace.jsonl")
    with pytest.raises(VibePathError):
        resolve_user_relative_path("user-1", str(Path("/tmp/trace.jsonl")))


def test_agent_loop_and_core_runtime_construct(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.services.vibe_agent.paths.settings.VIBE_AGENT_RUNTIME_ROOT",
        str(tmp_path),
    )
    embedded_agent_runtime._bootstrap()
    from src.agent.loop import AgentLoop
    from src.agent.tools import ToolRegistry
    from src.agent.skills import SkillsLoader

    class StubLLM:
        model_name = "test-model"

    agent = AgentLoop(registry=ToolRegistry(), llm=StubLLM(), max_iterations=1)
    assert agent.max_iterations == 1
    assert SkillsLoader().skills


def test_high_risk_tools_are_disabled_by_default():
    disabled = disabled_tool_names()
    assert "trading_place_order" in disabled
    assert "write_file" in disabled
    assert "save_skill" in disabled
