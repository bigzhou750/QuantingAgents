"""Runtime isolation and audit metrics.

Counters are intentionally small and in-memory so they can be exposed without a
dependency on MongoDB/Redis availability.  Every event carries an immutable
owner id where applicable and never the sensitive resource payload.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock


@dataclass
class IsolationMetrics:
    auth_failures: Counter = field(default_factory=Counter)
    authorization_denials: Counter = field(default_factory=Counter)
    unscoped_persistence: Counter = field(default_factory=Counter)
    quarantine_growth: Counter = field(default_factory=Counter)
    cross_user_key_hits: Counter = field(default_factory=Counter)
    queue_missing_owner: Counter = field(default_factory=Counter)
    events: list[dict] = field(default_factory=list)


_lock = Lock()
_metrics = IsolationMetrics()
_max_events = 200


def record_auth_failure(reason: str, *, request_id: str = "") -> None:
    _record("auth_failure", reason=reason, request_id=request_id)


def record_authorization_denial(user_id: str, resource_type: str, *, reason: str = "owner_mismatch", request_id: str = "") -> None:
    _record("authorization_denial", user_id=user_id, resource_type=resource_type, reason=reason, request_id=request_id)


def record_unscoped_persistence(operation: str, *, reason: str = "missing_scope", request_id: str = "") -> None:
    _record("unscoped_persistence", operation=operation, reason=reason, request_id=request_id)


def record_quarantine_growth(collection: str, count: int) -> None:
    _record("quarantine_growth", collection=collection, count=count)


def record_cross_user_key_hit(scope_key: str, *, request_id: str = "") -> None:
    _record("cross_user_key_hit", scope_key=scope_key, request_id=request_id)


def record_queue_missing_owner(task_id: str, *, request_id: str = "") -> None:
    _record("queue_missing_owner", task_id=task_id, request_id=request_id)


def snapshot() -> dict:
    with _lock:
        return {
            "auth_failures": dict(_metrics.auth_failures),
            "authorization_denials": dict(_metrics.authorization_denials),
            "unscoped_persistence": dict(_metrics.unscoped_persistence),
            "quarantine_growth": dict(_metrics.quarantine_growth),
            "cross_user_key_hits": dict(_metrics.cross_user_key_hits),
            "queue_missing_owner": dict(_metrics.queue_missing_owner),
            "recent_events": list(_metrics.events),
        }


def reset() -> None:
    with _lock:
        _metrics.events.clear()
        _metrics.auth_failures.clear()
        _metrics.authorization_denials.clear()
        _metrics.unscoped_persistence.clear()
        _metrics.quarantine_growth.clear()
        _metrics.cross_user_key_hits.clear()
        _metrics.queue_missing_owner.clear()


def _record(kind: str, **fields) -> None:
    with _lock:
        event = {"kind": kind, "timestamp": datetime.now(timezone.utc).isoformat(), **fields}
        _metrics.events.append(event)
        if len(_metrics.events) > _max_events:
            _metrics.events = _metrics.events[-_max_events:]

        if kind == "auth_failure":
            _metrics.auth_failures[fields.get("reason", "unknown")] += 1
        elif kind == "authorization_denial":
            _metrics.authorization_denials[(fields.get("user_id"), fields.get("resource_type", "unknown"))] += 1
        elif kind == "unscoped_persistence":
            _metrics.unscoped_persistence[fields.get("operation", "unknown")] += 1
        elif kind == "quarantine_growth":
            _metrics.quarantine_growth[fields.get("collection", "unknown")] += fields.get("count", 1)
        elif kind == "cross_user_key_hit":
            _metrics.cross_user_key_hits[fields.get("scope_key", "unknown")] += 1
        elif kind == "queue_missing_owner":
            _metrics.queue_missing_owner[fields.get("task_id", "unknown")] += 1
