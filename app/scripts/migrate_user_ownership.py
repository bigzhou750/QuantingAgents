"""Dry-run/idempotent migration helpers for legacy user-owned documents.

The command intentionally never guesses an owner. Documents without one are
copied to an isolation collection and remain invisible to normal APIs.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Iterable


@dataclass
class MigrationReport:
    collection: str
    scanned: int = 0
    mapped: int = 0
    missing: int = 0
    conflicts: int = 0
    isolated: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_documents(
    collection: str,
    documents: Iterable[dict[str, Any]],
    username_to_id: dict[str, str],
    *,
    apply: bool = False,
) -> tuple[MigrationReport, list[dict[str, Any]], list[dict[str, Any]]]:
    """Classify legacy documents without mutating the input.

    Returns ``(report, updates, isolation_records)``. Callers may apply the
    updates transactionally and write isolation records to a protected store.
    """
    report = MigrationReport(collection=collection)
    updates: list[dict[str, Any]] = []
    isolated: list[dict[str, Any]] = []
    for document in documents:
        report.scanned += 1
        if document.get("user_id"):
            report.mapped += 1
            continue
        candidates = {username_to_id.get(str(document.get(key))) for key in ("username", "user")}
        candidates.discard(None)
        if len(candidates) == 1:
            owner = candidates.pop()
            updates.append({"_id": document.get("_id"), "user_id": owner})
            report.mapped += 1
        elif len(candidates) > 1:
            report.conflicts += 1
            report.isolated += 1
            isolated.append(document)
        else:
            report.missing += 1
            report.isolated += 1
            isolated.append(document)
    return report, updates, isolated


async def apply_migration(db: Any, collection: str, updates: list[dict[str, Any]], isolated: list[dict[str, Any]], *, version: int) -> MigrationReport:
    """Apply a previously reviewed classification idempotently."""
    if version <= 0:
        raise ValueError("migration version must be positive")
    report = MigrationReport(collection=collection, mapped=len(updates), isolated=len(isolated))
    report.scanned = len(updates) + len(isolated)
    if updates:
        target = db[collection]
        for item in updates:
            await target.update_one(
                {"_id": item["_id"], "user_id": {"$exists": False}},
                {"$set": {"user_id": item["user_id"], "ownership_migration_version": version}},
            )
    if isolated:
        await db[f"{collection}_isolation"].insert_many(
            [{**item, "isolation_reason": "owner_unresolved", "ownership_migration_version": version} for item in isolated],
            ordered=False,
        )
    await db["migration_versions"].update_one(
        {"collection": collection, "version": version},
        {"$set": {"applied_at": datetime.utcnow()}},
        upsert=True,
    )
    return report


async def require_migration_version(db: Any, collection: str, version: int) -> None:
    """Fail closed when the requested migration version has not been applied."""
    doc = await db["migration_versions"].find_one({"collection": collection, "version": version})
    if not doc:
        raise RuntimeError(f"migration for {collection} version {version} has not been applied")
