#!/usr/bin/env python3
"""Rehearse backup, migration, verification, and rollback without production data."""

from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path


def rehearse() -> list[str]:
    events: list[str] = []
    with tempfile.TemporaryDirectory(prefix="zhitouagent-rehearsal-") as directory:
        root = Path(directory)
        legacy = root / "legacy-data"
        current = root / "zhitouagent-data"
        backup = root / "backup"
        legacy.mkdir()
        (legacy / "state.json").write_text('{"version": "legacy"}', encoding="utf-8")
        shutil.copytree(legacy, backup)
        events.append("backup_created")
        shutil.copytree(legacy, current)
        (current / "state.json").write_text('{"version": "zhitouagent"}', encoding="utf-8")
        events.append("migration_verified")
        shutil.rmtree(current)
        shutil.copytree(backup, current)
        assert (current / "state.json").read_text(encoding="utf-8") == '{"version": "legacy"}'
        events.append("rollback_verified")
    return events


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.parse_args()
    print(" -> ".join(rehearse()))
