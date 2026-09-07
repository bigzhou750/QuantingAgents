"""Small, explicit helpers for user-owned MongoDB resources."""

from typing import Any
import logging

from fastapi import HTTPException

logger = logging.getLogger(__name__)

OWNER_INDEXES: dict[str, list[tuple[list[tuple[str, int]], bool]]] = {
    "analysis_tasks": [([("user_id", 1), ("created_at", -1)], False)],
    "analysis_reports": [([("user_id", 1), ("created_at", -1)], False)],
    "notifications": [([("user_id", 1), ("created_at", -1)], False)],
    "favorites": [([("user_id", 1), ("stock_code", 1)], True)],
    "news_watch_configs": [([("user_id", 1), ("created_at", -1)], False)],
    "investment_profiles": [([("user_id", 1)], True)],
    "investment_strategies": [([("user_id", 1), ("created_at", -1)], False)],
    "investment_observations": [([("user_id", 1), ("created_at", -1)], False)],
    "user_tags": [([("user_id", 1), ("name", 1)], True)],
    "vibe_agent_sessions": [([("user_id", 1), ("updated_at", -1)], False)],
    "vibe_agent_tasks": [([("user_id", 1), ("created_at", -1)], False)],
}


def owner_filter(user_id: str, **extra: Any) -> dict[str, Any]:
    """Build a query whose owner is always supplied by the server context."""
    return {**extra, "user_id": str(user_id)}


def assert_owner(document: dict[str, Any] | None, user_id: str) -> dict[str, Any]:
    """Return a document only when it belongs to the requested user."""
    if not document or str(document.get("user_id")) != str(user_id):
        raise HTTPException(status_code=404, detail="Resource not found")
    return document


async def ensure_owner_indexes(db: Any) -> None:
    """Create owner query/uniqueness indexes without making startup brittle."""
    for collection_name, specs in OWNER_INDEXES.items():
        collection = db[collection_name]
        for fields, unique in specs:
            try:
                await collection.create_index(fields, unique=unique)
            except Exception as exc:
                # Existing legacy duplicates are reported and remain hidden by
                # owner filters; migration must resolve them before uniqueness.
                logger.warning("owner index unavailable for %s: %s", collection_name, type(exc).__name__)
