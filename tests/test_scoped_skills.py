from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "vibe_agent_runtime" / "vendor"))

from src.tools.skill_writer_tool import SaveSkillTool
from src.agent.skills import SkillsLoader
from src.tools.load_skill_tool import LoadSkillTool
import pytest


def test_user_skill_writer_uses_explicit_scope(tmp_path):
    a_dir = tmp_path / "a" / "skills" / "user"
    b_dir = tmp_path / "b" / "skills" / "user"
    SaveSkillTool(user_skills_dir=a_dir).execute(name="private-a", content="A credential-free workflow")
    SaveSkillTool(user_skills_dir=b_dir).execute(name="private-b", content="B credential-free workflow")

    assert (a_dir / "private-a" / "SKILL.md").exists()
    assert (b_dir / "private-b" / "SKILL.md").exists()
    assert not (a_dir / "private-b").exists()

    loaded = LoadSkillTool(skills_loader=SkillsLoader(user_skills_dir=a_dir)).execute(name="private-a")
    assert "A credential-free workflow" in loaded
    assert "B credential-free workflow" not in loaded


def test_user_skill_writer_without_scope_fails_closed():
    with pytest.raises(RuntimeError, match="scope"):
        SaveSkillTool()
