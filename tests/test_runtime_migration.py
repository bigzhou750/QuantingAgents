from pathlib import Path

from scripts.validation.migrate_legacy_runtime import migrate
from scripts.validation.rehearse_runtime_migration import rehearse


def test_legacy_runtime_migration_is_dry_run_by_default(tmp_path: Path):
    legacy = tmp_path / "tradingagents"
    legacy.mkdir()
    (legacy / "state.json").write_text("legacy", encoding="utf-8")

    actions = migrate(tmp_path)

    assert any("迁移目录" in action for action in actions)
    assert legacy.exists()
    assert not (tmp_path / "zhitouagent").exists()


def test_runtime_rehearsal_verifies_rollback():
    assert rehearse() == ["backup_created", "migration_verified", "rollback_verified"]
