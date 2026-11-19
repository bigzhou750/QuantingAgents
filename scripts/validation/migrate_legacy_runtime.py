#!/usr/bin/env python3
"""Migrate legacy runtime directories and environment keys to zhitouagent."""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


def migrate(root: Path, *, dry_run: bool = True) -> list[str]:
    actions: list[str] = []
    mappings = {
        root / "tradingagents": root / "zhitouagent",
        root / "data" / "tradingagents": root / "data" / "zhitouagent",
        Path.home() / "Documents" / "TradingAgents": Path.home() / "Documents" / "zhitouagent",
        Path.home() / ".vibe-trading": Path.home() / ".zhitouagent",
    }
    for source, target in mappings.items():
        if not source.exists() or source == target:
            continue
        if target.exists():
            actions.append(f"保留已存在目标目录: {target}")
            continue
        actions.append(f"迁移目录: {source} -> {target}")
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))

    for key, value in list(os.environ.items()):
        if key.startswith("TRADINGAGENTS_"):
            actions.append(f"兼容环境变量: {key} -> ZHITOUAGENT_{key[len('TRADINGAGENTS_'):]}")
    return actions


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate legacy zhitouagent runtime state")
    parser.add_argument("--root", default=".")
    parser.add_argument("--apply", action="store_true", help="perform filesystem moves")
    args = parser.parse_args()
    for action in migrate(Path(args.root).resolve(), dry_run=not args.apply):
        print(action)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
