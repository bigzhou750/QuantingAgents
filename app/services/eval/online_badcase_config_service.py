"""线上 Bad Case 自动发现配置服务。"""

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.database import get_mongo_db
from app.models.eval import (
    OnlineBadcaseConfig,
    OnlineBadcaseConfigStatus,
)
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)

CONFIG_CACHE_TTL_SECONDS = 30
DEFAULT_CONFIG_KEY = "default"


def _config_from_settings() -> Dict[str, Any]:
    return {
        "enabled": settings.ONLINE_BADCASE_ENABLED,
        "enable_judge": settings.ONLINE_BADCASE_ENABLE_JUDGE,
        "soft_sample_rate": settings.ONLINE_BADCASE_SOFT_SAMPLE_RATE,
        "confidence_threshold": settings.ONLINE_BADCASE_CONFIDENCE_THRESHOLD,
        "judge_threshold": settings.ONLINE_BADCASE_JUDGE_THRESHOLD,
        "evidence_threshold": settings.ONLINE_BADCASE_EVIDENCE_THRESHOLD,
        "max_content_length": settings.ONLINE_BADCASE_MAX_CONTENT_LENGTH,
        "status": OnlineBadcaseConfigStatus.PUBLISHED.value,
        "source": "env",
        "updated_by": "system",
        "change_reason": "environment defaults",
    }


def validate_config(data: Dict[str, Any]) -> None:
    """校验配置字段和边界；非法时抛出 ValueError。"""
    for key in (
        "soft_sample_rate",
        "confidence_threshold",
        "judge_threshold",
        "evidence_threshold",
    ):
        value = data.get(key)
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{key} must be a number")
        if not 0.0 <= number <= 1.0:
            raise ValueError(f"{key} must be between 0 and 1")
    max_length = data.get("max_content_length")
    if max_length is not None:
        try:
            length = int(max_length)
        except (TypeError, ValueError):
            raise ValueError("max_content_length must be an integer")
        if not 1000 <= length <= 200000:
            raise ValueError("max_content_length must be between 1000 and 200000")
    if data.get("enable_judge") and not (
        settings.EVAL_JUDGE_MODEL or settings.EVAL_JUDGE_MODEL_DEFAULT
    ):
        raise ValueError("enable_judge requires EVAL_JUDGE_MODEL or EVAL_JUDGE_MODEL_DEFAULT")


class OnlineBadcaseConfigService:
    """配置读取、发布、历史与缓存。"""

    COLLECTION = "online_badcase_configs"

    def __init__(self) -> None:
        self._initialized = False
        self._cache_config: Optional[Dict[str, Any]] = None
        self._cache_expires_at = 0.0
        self._last_valid_config: Optional[Dict[str, Any]] = None

    async def initialize(self) -> None:
        if self._initialized:
            return
        db = get_mongo_db()
        await db[self.COLLECTION].create_index(
            [("config_key", 1), ("version", 1)],
            unique=True,
        )
        await db[self.COLLECTION].create_index("status")
        existing = await db[self.COLLECTION].count_documents(
            {"config_key": DEFAULT_CONFIG_KEY, "status": OnlineBadcaseConfigStatus.PUBLISHED.value}
        )
        if not existing:
            defaults = _config_from_settings()
            doc = OnlineBadcaseConfig(
                config_id=f"badcase_cfg_{uuid.uuid4().hex[:8]}",
                config_key=DEFAULT_CONFIG_KEY,
                version=1,
                **defaults,
            )
            await db[self.COLLECTION].insert_one(
                doc.model_dump(by_alias=True, exclude={"id"})
            )
        self._initialized = True

    @staticmethod
    def _safe_disabled_defaults() -> Dict[str, Any]:
        return {
            "enabled": False,
            "enable_judge": False,
            "soft_sample_rate": 0.1,
            "confidence_threshold": 0.8,
            "judge_threshold": 0.6,
            "evidence_threshold": 0.6,
            "max_content_length": 5000,
            "status": "published",
            "source": "fail_closed",
            "updated_by": "system",
            "change_reason": "no valid published config; fail closed",
        }

    async def get_effective_config(self) -> Dict[str, Any]:
        if (
            self._cache_config
            and time.monotonic() < self._cache_expires_at
        ):
            return self._cache_config
        try:
            if not self._initialized:
                db = get_mongo_db()
                config_count = await db[self.COLLECTION].count_documents(
                    {"status": OnlineBadcaseConfigStatus.PUBLISHED.value}
                )
                if config_count:
                    self._initialized = True
            if not self._initialized:
                await self.initialize()
            db = get_mongo_db()
            doc = await db[self.COLLECTION].find_one(
                {
                    "config_key": DEFAULT_CONFIG_KEY,
                    "status": OnlineBadcaseConfigStatus.PUBLISHED.value,
                },
                sort=[("version", -1)],
            )
            if not doc:
                config = self._safe_disabled_defaults()
            else:
                config = OnlineBadcaseConfig(**doc).model_dump()
            validate_config(config)
            self._cache_config = config
            self._cache_expires_at = time.monotonic() + CONFIG_CACHE_TTL_SECONDS
            self._last_valid_config = config
            return config
        except Exception as exc:
            logger.warning("Failed to read online badcase config: %s", exc)
            if self._last_valid_config:
                self._cache_config = self._last_valid_config
                self._cache_expires_at = time.monotonic() + CONFIG_CACHE_TTL_SECONDS
                return self._last_valid_config
            config = self._safe_disabled_defaults()
            self._cache_config = config
            self._cache_expires_at = time.monotonic() + CONFIG_CACHE_TTL_SECONDS
            self._last_valid_config = config
            return config

    def invalidate_cache(self) -> None:
        self._cache_config = None
        self._cache_expires_at = 0.0

    async def list_configs(self) -> List[Dict[str, Any]]:
        await self.initialize()
        db = get_mongo_db()
        cursor = db[self.COLLECTION].find(
            {"config_key": DEFAULT_CONFIG_KEY}
        ).sort("version", 1)
        docs = []
        async for doc in cursor:
            docs.append(OnlineBadcaseConfig(**doc).model_dump())
        return docs

    async def create_draft(
        self,
        data: Dict[str, Any],
        updated_by: str = "",
    ) -> Dict[str, Any]:
        await self.initialize()
        validate_config(data)
        db = get_mongo_db()
        next_version = await db[self.COLLECTION].count_documents(
            {"config_key": DEFAULT_CONFIG_KEY}
        )
        doc = OnlineBadcaseConfig(
            config_id=f"badcase_cfg_{uuid.uuid4().hex[:8]}",
            config_key=DEFAULT_CONFIG_KEY,
            version=max(1, next_version + 1),
            status=OnlineBadcaseConfigStatus.DRAFT,
            source="db",
            updated_by=updated_by or "admin",
            change_reason=str(data.get("change_reason") or ""),
            enabled=bool(data.get("enabled", False)),
            enable_judge=bool(data.get("enable_judge", False)),
            soft_sample_rate=float(data.get("soft_sample_rate", 0.1)),
            confidence_threshold=float(data.get("confidence_threshold", 0.8)),
            judge_threshold=float(data.get("judge_threshold", 0.6)),
            evidence_threshold=float(data.get("evidence_threshold", 0.6)),
            max_content_length=int(data.get("max_content_length", 5000)),
        )
        await db[self.COLLECTION].insert_one(
            doc.model_dump(by_alias=True, exclude={"id"})
        )
        return doc.model_dump()

    async def publish(
        self,
        config_id: str,
        updated_by: str = "",
        change_reason: str = "",
    ) -> Dict[str, Any]:
        await self.initialize()
        db = get_mongo_db()
        target = await db[self.COLLECTION].find_one({"config_id": config_id})
        if not target:
            raise ValueError("online badcase config not found")
        validate_config(target)
        await db[self.COLLECTION].update_many(
            {
                "config_key": DEFAULT_CONFIG_KEY,
                "status": OnlineBadcaseConfigStatus.PUBLISHED.value,
                "config_id": {"$ne": config_id},
            },
            {"$set": {"status": OnlineBadcaseConfigStatus.ARCHIVED.value}},
        )
        await db[self.COLLECTION].update_one(
            {"config_id": config_id},
            {
                "$set": {
                    "status": OnlineBadcaseConfigStatus.PUBLISHED.value,
                    "source": "db",
                    "updated_by": updated_by or "admin",
                    "updated_at": now_tz(),
                    "change_reason": change_reason,
                }
            },
        )
        self.invalidate_cache()
        self._last_valid_config = None
        updated = await db[self.COLLECTION].find_one({"config_id": config_id})
        return OnlineBadcaseConfig(**updated).model_dump()

    async def rollback(
        self,
        config_id: str,
        updated_by: str = "",
        change_reason: str = "",
    ) -> Dict[str, Any]:
        await self.initialize()
        db = get_mongo_db()
        target = await db[self.COLLECTION].find_one({"config_id": config_id})
        if not target:
            raise ValueError("online badcase config not found")
        validate_config(target)
        current = await db[self.COLLECTION].find_one(
            {
                "config_key": DEFAULT_CONFIG_KEY,
                "status": OnlineBadcaseConfigStatus.PUBLISHED.value,
                "config_id": {"$ne": config_id},
            }
        )
        if current:
            await db[self.COLLECTION].update_one(
                {"config_id": current["config_id"]},
                {"$set": {"status": OnlineBadcaseConfigStatus.ARCHIVED.value}},
            )
        await db[self.COLLECTION].update_one(
            {"config_id": config_id},
            {
                "$set": {
                    "status": OnlineBadcaseConfigStatus.PUBLISHED.value,
                    "source": "db",
                    "updated_by": updated_by or "admin",
                    "updated_at": now_tz(),
                    "change_reason": change_reason
                    or f"rollback to {config_id}",
                }
            },
        )
        self.invalidate_cache()
        self._last_valid_config = None
        updated = await db[self.COLLECTION].find_one({"config_id": config_id})
        return OnlineBadcaseConfig(**updated).model_dump()


online_badcase_config_service = OnlineBadcaseConfigService()
