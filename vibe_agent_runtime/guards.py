"""Static migration gates for the embedded runtime."""

from __future__ import annotations

import re
from pathlib import Path

FORBIDDEN_SOURCE_MARKERS = (
    ".env",
    ".pycache",
    "__pycache__",
)
EXTERNAL_VIBE_PATH = re.compile(r"/Users/[^\"']*/Vibe-Trading")


def validate_vendor_tree(root: Path) -> list[str]:
    """Return migration gate violations found under the vendored tree."""
    violations: list[str] = []
    for path in root.rglob("*"):
        if any(part in FORBIDDEN_SOURCE_MARKERS for part in path.parts):
            continue
        if path.suffix == ".pyc":
            violations.append(f"forbidden artifact: {path}")
            continue
        if path.is_file() and path.suffix in {".py", ".json", ".yaml", ".yml", ".md"}:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if EXTERNAL_VIBE_PATH.search(text):
                violations.append(f"external source path: {path}")
    return violations
