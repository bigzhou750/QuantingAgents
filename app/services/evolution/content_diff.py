"""自进化候选内容的结构化 diff 构建与一致性校验。"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List


def _markdown_sections(content: str) -> Dict[str, str]:
    matches = list(re.finditer(r"(?m)^(#{1,6})[ \t]+(.+?)\s*$", content or ""))
    sections: Dict[str, str] = {}
    for index, match in enumerate(matches):
        title = match.group(2).strip().rstrip("#").strip()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        sections[title] = content[match.start():end].strip()
    return sections


def _snapshot_hash(snapshot: Dict[str, Any]) -> str:
    import json

    return hashlib.sha256(
        json.dumps(snapshot or {}, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def build_structured_diff(
    *,
    artifact_id: str,
    artifact_type: str,
    source_version: str,
    source_snapshot: Dict[str, Any] | None,
    candidate_snapshot: Dict[str, Any],
    requested_sections: List[str] | None = None,
    description: str = "",
) -> Dict[str, Any]:
    """构建可审计的候选 diff，不修改输入快照。"""
    source = source_snapshot or {}
    candidate = candidate_snapshot or {}
    changes: List[Dict[str, Any]] = []

    if artifact_type == "skill":
        before_content = str(source.get("content", "") or "")
        after_content = str(candidate.get("content", "") or "")
        before_sections = _markdown_sections(before_content)
        after_sections = _markdown_sections(after_content)
        section_names = list(dict.fromkeys([
            *(requested_sections or []),
            *before_sections.keys(),
            *after_sections.keys(),
        ]))
        for name in section_names:
            before = before_sections.get(name)
            after = after_sections.get(name)
            if before is None and after is not None:
                operation = "add"
            elif before is not None and after is None:
                operation = "delete"
            elif before != after:
                operation = "update"
            else:
                operation = "unchanged"
            if operation != "unchanged" or name in (requested_sections or []):
                changes.append({
                    "section": name,
                    "operation": operation,
                    "before": before,
                    "after": after,
                })
    else:
        changes.append({
            "section": "content_snapshot",
            "operation": "update" if source != candidate else "unchanged",
            "before": source,
            "after": candidate,
        })

    result = {
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "source_version": source_version,
        "candidate_version": "candidate",
        "operation": "update" if source != candidate else "unchanged",
        "change_description": description,
        "changes": changes,
        "candidate_snapshot": candidate,
        "source_snapshot_hash": _snapshot_hash(source),
        "candidate_snapshot_hash": _snapshot_hash(candidate),
        "content_diff_status": "complete",
    }
    return result


def validate_structured_diff(diff: Dict[str, Any]) -> Dict[str, Any]:
    """校验结构化 diff 的源版本、变更单元和候选快照。"""
    errors: List[str] = []
    candidate = diff.get("candidate_snapshot")
    changes = diff.get("changes")
    if not isinstance(candidate, dict):
        errors.append("candidate_snapshot is missing")
    if not isinstance(changes, list) or not changes:
        errors.append("structured changes are missing")
    else:
        for index, change in enumerate(changes):
            if not isinstance(change, dict):
                errors.append(f"change[{index}] is not an object")
                continue
            operation = change.get("operation")
            if operation not in {"add", "update", "delete", "unchanged"}:
                errors.append(f"change[{index}] has invalid operation")
            if operation == "add" and change.get("before") not in (None, ""):
                errors.append(f"change[{index}] add must have empty before")
            if operation == "delete" and change.get("after") not in (None, ""):
                errors.append(f"change[{index}] delete must have empty after")
            if operation in {"add", "update"} and change.get("after") is None:
                errors.append(f"change[{index}] after is missing")
    if errors:
        return {"passed": False, "errors": errors, "status": "invalid"}
    return {"passed": True, "errors": [], "status": "complete"}
