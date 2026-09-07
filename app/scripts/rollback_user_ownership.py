"""Roll back ownership migration bookkeeping without exposing isolated data.

This script only removes migration-version bookkeeping. Owner fields and
isolation collections are intentionally preserved so a rollback can never
re-expose documents that were not safely attributable.
"""

from __future__ import annotations

import argparse

from app.core.config import settings


def rollback_versions(db, version: int) -> dict:
    result = db["migration_versions"].delete_many({"version": version})
    return {
        "rolled_back_entries": result.deleted_count,
        "owner_fields_preserved": True,
        "isolation_preserved": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Roll back multi-account ownership migration bookkeeping")
    parser.add_argument("--version", type=int, required=True, help="migration version to roll back")
    args = parser.parse_args()

    from pymongo import MongoClient
    client = MongoClient(settings.MONGO_URI)
    try:
        db = client[settings.MONGO_DB]
        print(rollback_versions(db, args.version))
    finally:
        client.close()


if __name__ == "__main__":
    main()
