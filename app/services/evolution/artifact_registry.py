"""
Artifact 注册与版本管理服务

管理自进化闭环中可修改的受控资产（Skill、Prompt、Policy、Rubric、Case）的注册、
版本创建、查询和回滚。所有 artifact 内容以快照形式存储在 MongoDB 中，
Skill 类型额外支持文件系统写回。
"""

import hashlib
import json
import logging
from typing import Optional, List, Dict, Any

from bson import ObjectId

from app.core.database import get_mongo_db
from app.models.evolution import (
    ArtifactVersion,
    ArtifactRegistryEntry,
    ArtifactType,
    ArtifactVersionStatus,
)
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)


def _bump_patch_version(version: str) -> str:
    """递增 patch 版本号（如 1.0.0 -> 1.0.1）"""
    parts = version.split(".")
    if len(parts) != 3:
        return version
    try:
        parts[2] = str(int(parts[2]) + 1)
        return ".".join(parts)
    except ValueError:
        return version


def _parse_semver(version: str) -> Optional[tuple]:
    """解析语义化版本号为元组"""
    parts = version.split(".")
    if len(parts) != 3:
        return None
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None


def _compute_content_hash(content: Dict[str, Any]) -> str:
    """计算内容快照的 SHA256 哈希"""
    canonical = json.dumps(content, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ArtifactRegistryService:
    """Artifact 注册与版本管理服务"""

    COLLECTION_REGISTRY = "evolution_artifact_registry"
    COLLECTION_VERSIONS = "evolution_artifact_versions"

    def __init__(self):
        self._initialized = False

    async def initialize(self):
        """初始化服务，创建集合索引"""
        if self._initialized:
            return

        logger.info("Initializing ArtifactRegistryService")
        db = get_mongo_db()

        # Registry 索引
        await db[self.COLLECTION_REGISTRY].create_index("artifact_id", unique=True)
        await db[self.COLLECTION_REGISTRY].create_index("artifact_type")

        # Versions 索引
        await db[self.COLLECTION_VERSIONS].create_index("artifact_id")
        await db[self.COLLECTION_VERSIONS].create_index([("artifact_id", 1), ("version", 1)], unique=True)
        await db[self.COLLECTION_VERSIONS].create_index("status")
        await db[self.COLLECTION_VERSIONS].create_index("artifact_type")

        # 首次启用自进化时登记受控默认资产，避免 proposal 生成因没有 registry
        # 条目而无法进入验证。真实用户资产仍必须显式登记。
        defaults = [
            (ArtifactType.SKILL, "general", "vibe_agent_runtime/vendor/src/skills/general/SKILL.md"),
            (ArtifactType.PROMPT, "system_default", "runtime/system_prompt"),
            (ArtifactType.POLICY, "grounding", "policy/grounding"),
            (ArtifactType.POLICY, "safety", "policy/safety"),
            (ArtifactType.POLICY, "routing_default", "policy/routing"),
            (ArtifactType.RUBRIC, "financial_default", "rubric/financial"),
        ]
        for artifact_type, name, path in defaults:
            artifact_id = f"art_{artifact_type.value}_{name}"
            if not await db[self.COLLECTION_REGISTRY].find_one({"artifact_id": artifact_id}):
                await self.register(
                    artifact_type=artifact_type,
                    name=name,
                    path=path,
                    owner="system",
                    content_snapshot={"content": "", "managed": True},
                    allowlist_patterns=[
                        path.rsplit("/", 1)[-1],
                        artifact_type.value,
                        "tool_selection",
                        "output_format",
                        "system_prompt",
                        "output_instructions",
                        "rules",
                        "thresholds",
                    ],
                )

        self._initialized = True
        logger.info("ArtifactRegistryService initialized")

    # ==================== Registry CRUD ====================

    async def register(
        self,
        artifact_type: ArtifactType,
        name: str,
        path: str = "",
        owner: str = "system",
        content_snapshot: Optional[Dict[str, Any]] = None,
        rollback_strategy: str = "previous_stable",
        allowlist_patterns: Optional[List[str]] = None,
    ) -> ArtifactRegistryEntry:
        """注册新 artifact 并创建初始版本 v1.0.0"""
        db = get_mongo_db()
        artifact_id = f"art_{artifact_type.value}_{name.replace(' ', '_').lower()}"

        # 检查是否已注册
        existing = await db[self.COLLECTION_REGISTRY].find_one({"artifact_id": artifact_id})
        if existing:
            raise ValueError(f"Artifact '{artifact_id}' already registered")

        entry = ArtifactRegistryEntry(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            name=name,
            path=path,
            current_version="1.0.0",
            owner=owner,
            rollback_strategy=rollback_strategy,
            allowlist_patterns=allowlist_patterns or [],
        )
        await db[self.COLLECTION_REGISTRY].insert_one(entry.model_dump(by_alias=True, exclude={"id"}))

        # 创建初始版本
        if content_snapshot is not None:
            await self.create_version(artifact_id, content_snapshot, created_by=owner)

        logger.info(f"Registered artifact: {artifact_id} ({artifact_type.value})")
        return entry

    async def get_registry_entry(self, artifact_id: str) -> Optional[ArtifactRegistryEntry]:
        """获取 artifact 注册信息"""
        db = get_mongo_db()
        doc = await db[self.COLLECTION_REGISTRY].find_one({"artifact_id": artifact_id})
        if not doc:
            return None
        return ArtifactRegistryEntry(**doc)

    async def list_artifacts(
        self,
        artifact_type: Optional[ArtifactType] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[ArtifactRegistryEntry]:
        """列出已注册的 artifact"""
        db = get_mongo_db()
        query: Dict[str, Any] = {}
        if artifact_type:
            query["artifact_type"] = artifact_type.value
        cursor = db[self.COLLECTION_REGISTRY].find(query).skip(skip).limit(limit).sort("created_at", -1)
        results = []
        async for doc in cursor:
            results.append(ArtifactRegistryEntry(**doc))
        return results

    async def is_registered(self, artifact_id: str) -> bool:
        """检查 artifact 是否已注册"""
        db = get_mongo_db()
        count = await db[self.COLLECTION_REGISTRY].count_documents({"artifact_id": artifact_id})
        return count > 0

    # ==================== Version Management ====================

    async def create_version(
        self,
        artifact_id: str,
        content_snapshot: Dict[str, Any],
        created_by: str = "system",
    ) -> ArtifactVersion:
        """为 artifact 创建新版本"""
        db = get_mongo_db()

        # 获取当前最新版本
        latest = await db[self.COLLECTION_VERSIONS].find_one(
            {"artifact_id": artifact_id},
            sort=[("created_at", -1)],
        )
        if latest:
            new_version = _bump_patch_version(latest.get("version", "1.0.0"))
        else:
            new_version = "1.0.0"

        # 获取 registry 信息
        registry = await db[self.COLLECTION_REGISTRY].find_one({"artifact_id": artifact_id})
        if not registry:
            raise ValueError(f"Artifact '{artifact_id}' not registered")

        content_hash = _compute_content_hash(content_snapshot)

        version_doc = ArtifactVersion(
            artifact_id=artifact_id,
            artifact_type=ArtifactType(registry["artifact_type"]),
            name=registry["name"],
            path=registry.get("path", ""),
            version=new_version,
            content_hash=content_hash,
            content_snapshot=content_snapshot,
            owner=created_by,
            status=ArtifactVersionStatus.ACTIVE,
        )
        await db[self.COLLECTION_VERSIONS].insert_one(version_doc.model_dump(by_alias=True, exclude={"id"}))

        # 将旧 active 版本标记为 superseded
        await db[self.COLLECTION_VERSIONS].update_many(
            {
                "artifact_id": artifact_id,
                "version": {"$ne": new_version},
                "status": ArtifactVersionStatus.ACTIVE.value,
            },
            {"$set": {"status": ArtifactVersionStatus.SUPERSEDED.value, "superseded_by": new_version}},
        )

        # 更新 registry 当前版本
        await db[self.COLLECTION_REGISTRY].update_one(
            {"artifact_id": artifact_id},
            {"$set": {"current_version": new_version, "updated_at": now_tz()}},
        )

        logger.info(f"Created version {new_version} for artifact {artifact_id}")
        return version_doc

    async def get_current_version(self, artifact_id: str) -> Optional[ArtifactVersion]:
        """获取 artifact 当前生效版本"""
        db = get_mongo_db()
        doc = await db[self.COLLECTION_VERSIONS].find_one(
            {"artifact_id": artifact_id, "status": ArtifactVersionStatus.ACTIVE.value},
        )
        if not doc:
            return None
        return ArtifactVersion(**doc)

    async def get_version(self, artifact_id: str, version: str) -> Optional[ArtifactVersion]:
        """获取指定版本"""
        db = get_mongo_db()
        doc = await db[self.COLLECTION_VERSIONS].find_one(
            {"artifact_id": artifact_id, "version": version},
        )
        if not doc:
            return None
        return ArtifactVersion(**doc)

    async def list_versions(
        self,
        artifact_id: str,
        skip: int = 0,
        limit: int = 50,
    ) -> List[ArtifactVersion]:
        """列出 artifact 的所有版本"""
        db = get_mongo_db()
        cursor = (
            db[self.COLLECTION_VERSIONS]
            .find({"artifact_id": artifact_id})
            .skip(skip)
            .limit(limit)
            .sort("created_at", -1)
        )
        results = []
        async for doc in cursor:
            results.append(ArtifactVersion(**doc))
        return results

    async def rollback(self, artifact_id: str, target_version: str, rolled_back_by: str = "system") -> ArtifactVersion:
        """回滚到指定版本"""
        db = get_mongo_db()

        # 验证目标版本存在
        target = await db[self.COLLECTION_VERSIONS].find_one(
            {"artifact_id": artifact_id, "version": target_version},
        )
        if not target:
            raise ValueError(f"Version {target_version} not found for artifact {artifact_id}")

        expected_hash = target.get("content_hash", "")
        actual_hash = _compute_content_hash(target.get("content_snapshot", {}))
        if expected_hash and expected_hash != actual_hash:
            raise ValueError(f"Version {target_version} content hash mismatch")
        if target.get("status") == ArtifactVersionStatus.ACTIVE.value:
            return ArtifactVersion(**target)

        # 将当前 active 版本标记为 rolled_back
        await db[self.COLLECTION_VERSIONS].update_many(
            {"artifact_id": artifact_id, "status": ArtifactVersionStatus.ACTIVE.value},
            {"$set": {"status": ArtifactVersionStatus.ROLLED_BACK.value}},
        )

        # 将目标版本恢复为 active
        await db[self.COLLECTION_VERSIONS].update_one(
            {"artifact_id": artifact_id, "version": target_version},
            {"$set": {"status": ArtifactVersionStatus.ACTIVE.value, "superseded_by": None}},
        )

        # 更新 registry
        await db[self.COLLECTION_REGISTRY].update_one(
            {"artifact_id": artifact_id},
            {"$set": {"current_version": target_version, "updated_at": now_tz()}},
        )

        logger.info(f"Rolled back artifact {artifact_id} to version {target_version} by {rolled_back_by}")
        return ArtifactVersion(**{**target, "status": ArtifactVersionStatus.ACTIVE.value})


# 模块级单例
artifact_registry = ArtifactRegistryService()
