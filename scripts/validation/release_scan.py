#!/usr/bin/env python3
"""Scan a release tree for product identity leaks and sensitive artifacts.

The scanner intentionally treats third-party license and dependency metadata as
an allowlisted category. It is a release gate, not a generic source-code linter.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path
from typing import Iterable


FORBIDDEN_PATTERNS = {
    "legacy_brand": re.compile(r"tradingagents(?:-cn)?|trading-agent|vibe[-_]trading|vibeagent|vibe_agent", re.I),
    "legacy_email": re.compile(
        r"hsliup@163\.com|contact@tauric\.ai|support@tauric\.ai|docs@tauric\.ai|"
        r"business@your-domain\.com|vibe-trading@example\.com|admin@tradingagents\.cn",
        re.I,
    ),
    "legacy_project_url": re.compile(
        r"(?:github\.com/(?:hsliuping|TauricResearch)|gitee\.com/bigzhou750/quanting-agent)",
        re.I,
    ),
    "secret_like_value": re.compile(
        r"(?i)(?:api[_-]?key|secret[_-]?key|access[_-]?token|password)\s*[=:]\s*['\"]?[A-Za-z0-9_./+=:-]{16,}"
    ),
}

ALLOWED_LICENSE_GLOBS = {
    "LICENSE",
    "*/LICENSE",
    "**/LICENSE",
    "COPYRIGHT.md",
    "LICENSING.md",
    "ACKNOWLEDGMENTS.md",
    "THIRD_PARTY_NOTICES.md",
    "app/LICENSE",
    "frontend/LICENSE",
    "vibe_agent_runtime/vendor/LICENSE",
    "**/NOTICE",
}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "dist", "build"}
TEXT_SUFFIXES = {
    ".py", ".ts", ".tsx", ".js", ".vue", ".json", ".toml", ".yaml", ".yml", ".md", ".txt", ".env",
    ".sh", ".ps1", ".sql", ".html", ".scss", ".css", ".xml", ".ini", ".conf",
}


def is_allowed_license(path: Path) -> bool:
    normalized = path.as_posix()
    return any(fnmatch.fnmatch(normalized, pattern) or fnmatch.fnmatch(path.name, pattern) for pattern in ALLOWED_LICENSE_GLOBS)


def iter_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file() or any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in TEXT_SUFFIXES or path.name in {
            "Dockerfile", ".dockerignore", "LICENSE", "NOTICE", "NOTICE.md",
            "COPYRIGHT.md", "LICENSING.md", "ACKNOWLEDGMENTS.md",
            "THIRD_PARTY_NOTICES.md",
        }:
            yield path


def scan(root: Path) -> dict:
    findings = []
    scanned = 0
    for path in iter_files(root):
        scanned += 1
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        relative = path.relative_to(root).as_posix()
        allowed = is_allowed_license(path)
        for line_number, line in enumerate(text.splitlines(), 1):
            for category, pattern in FORBIDDEN_PATTERNS.items():
                if pattern.search(line):
                    severity = "allowed-license" if allowed and category in {"legacy_brand", "legacy_email", "legacy_project_url"} else "forbidden"
                    findings.append({
                        "file": relative,
                        "line": line_number,
                        "category": category,
                        "severity": severity,
                        "text": line.strip()[:240],
                    })
    forbidden = [item for item in findings if item["severity"] == "forbidden"]
    return {"root": str(root), "scanned_files": scanned, "findings": findings, "forbidden": forbidden, "passed": not forbidden}


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan a zhitouagent release tree")
    parser.add_argument("root", nargs="?", default=".", help="release tree to scan")
    parser.add_argument("--json", action="store_true", dest="as_json", help="emit JSON")
    args = parser.parse_args()
    result = scan(Path(args.root).resolve())
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Scanned {result['scanned_files']} files")
        print(f"Forbidden findings: {len(result['forbidden'])}")
        for item in result["findings"][:50]:
            print(f"[{item['severity']}] {item['file']}:{item['line']} {item['category']}: {item['text']}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
