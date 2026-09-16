"""Small in-memory index linking tool executions to audit evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bounded(value: Any, limit: int = 500) -> Any:
    if isinstance(value, str):
        return value[:limit]
    if isinstance(value, dict):
        return {str(key): _bounded(item, 200) for key, item in list(value.items())[:50]}
    if isinstance(value, list):
        return [_bounded(item, 200) for item in value[:50]]
    return value


@dataclass
class ToolEvidence:
    evidence_id: str
    call_id: str
    tool: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    result_status: Optional[str] = None
    preview: str = ""
    error: Optional[str] = None
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ToolEvidenceIndex:
    """Correlate tool call/result events without making them decisions."""

    def __init__(self) -> None:
        self._by_call: Dict[str, ToolEvidence] = {}
        self._not_requested: Dict[str, ToolEvidence] = {}

    @staticmethod
    def evidence_id_for(call_id: str) -> str:
        return f"evidence_{call_id or 'unknown'}"

    def record_call(
        self,
        *,
        call_id: str,
        tool: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> str:
        call_id = str(call_id or "unknown")
        existing = self._by_call.get(call_id)
        if existing is None:
            existing = ToolEvidence(
                evidence_id=self.evidence_id_for(call_id),
                call_id=call_id,
                tool=str(tool or ""),
                arguments=_bounded(arguments or {}),
            )
            self._by_call[call_id] = existing
        else:
            if tool:
                existing.tool = str(tool)
            if arguments:
                existing.arguments = _bounded(arguments)
            existing.updated_at = _utc_now()
        return existing.evidence_id

    def record_result(
        self,
        *,
        call_id: str,
        tool: str = "",
        status: str = "ok",
        preview: str = "",
        error: Optional[str] = None,
    ) -> ToolEvidence:
        evidence_id = self.record_call(call_id=call_id, tool=tool)
        evidence = self._by_call[str(call_id or "unknown")]
        normalized_status = str(status or "error").lower()
        empty = str(preview or "").strip().lower() in {"", "[]", "{}", "null", "none"}
        evidence.status = "unavailable" if normalized_status != "ok" or empty else "available"
        evidence.result_status = normalized_status
        evidence.preview = str(preview or "")[:500]
        evidence.error = str(error)[:500] if error else None
        evidence.updated_at = _utc_now()
        return evidence

    def mark_not_requested(self, tools: Iterable[str]) -> list[str]:
        ids: list[str] = []
        for tool in tools:
            name = str(tool or "").strip()
            if not name:
                continue
            evidence_id = f"evidence_not_requested_{name}"
            self._not_requested[name] = ToolEvidence(
                evidence_id=evidence_id,
                call_id="",
                tool=name,
                status="not_requested",
            )
            ids.append(evidence_id)
        return ids

    def get(self, call_id: str) -> Optional[ToolEvidence]:
        return self._by_call.get(str(call_id or ""))

    def snapshot(self) -> list[Dict[str, Any]]:
        return [item.to_dict() for item in [*self._by_call.values(), *self._not_requested.values()]]
