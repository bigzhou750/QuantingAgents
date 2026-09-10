#!/usr/bin/env python3
"""Build a minimal zhitouagent release tree for scanning and packaging.

The builder excludes non-delivery artifacts such as the legacy Streamlit app,
development docs, reports, caches, tests and environment files.
"""

from __future__ import annotations

import argparse
import fnmatch
import shutil
import sys
from pathlib import Path


EXCLUDED_DIRS = {
    ".git",
    ".codegraph",
    "node_modules",
    "__pycache__",
    ".venv",
    "dist",
    "build",
    "tests",
    "reports",
    "results",
    "logs",
    "data",
    "cache",
    "install",
    "web",
    "docs",
    "debug",
    "archived",
    "deployment",
    "maintenance",
    "development",
    "setup",
    "startup",
    "docker",
    "git",
    "runtime",
    "tmp",
    "temp",
}

EXCLUDED_PATTERNS = (
    ".env",
    ".env.*",
    "*.log",
    "*.db",
    "*.sqlite",
    "*.sqlite3",
    "*.egg-info",
    "*.pyc",
    "*.pyo",
    "*.sock",
    "test_*",
)

ROOT_ALLOWED_DIRS = {
    "app",
    "cli",
    "config",
    "deploy",
    "docker",
    "frontend",
    "nginx",
    "scripts",
    "tradingagents",
    "vibe_agent_runtime",
}

ROOT_ALLOWED_FILES = {
    ".dockerignore",
    "COPYRIGHT.md",
    "Dockerfile.backend",
    "Dockerfile.backend.base",
    "Dockerfile.frontend",
    "LICENSE",
    "README.md",
    "VERSION",
    "docker-compose.hub.nginx.arm.yml",
    "docker-compose.hub.nginx.yml",
    "docker-compose.yml",
    "pyproject.toml",
    "requirements-lock.txt",
    "requirements.txt",
}


def _ignore(src_dir: Path, names: list[str]) -> set[str]:
    ignored = set()
    for name in names:
        path = Path(src_dir) / name
        if path.is_dir() and name in EXCLUDED_DIRS:
            ignored.add(name)
        if any(fnmatch.fnmatch(name, pattern) for pattern in EXCLUDED_PATTERNS):
            ignored.add(name)
    return ignored


def build_release_tree(source: Path, dest: Path) -> int:
    source = source.resolve()
    dest = dest.resolve()
    if dest.exists():
        print(f"error: destination already exists: {dest}")
        return 1
    dest.parent.mkdir(parents=True, exist_ok=True)

    def ignore(root_dir: str, names: list[str]) -> set[str]:
        root = Path(root_dir).resolve()
        ignored = _ignore(Path(root_dir), names)
        if root == source:
            for name in names:
                if name not in ROOT_ALLOWED_DIRS and name not in ROOT_ALLOWED_FILES:
                    ignored.add(name)
        return ignored

    shutil.copytree(source, dest, ignore=ignore, symlinks=False)
    print(f"Built release tree: {dest}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", default=".", help="repository root")
    parser.add_argument("dest", help="destination release tree")
    args = parser.parse_args()
    return build_release_tree(Path(args.source), Path(args.dest))


if __name__ == "__main__":
    sys.exit(main())
