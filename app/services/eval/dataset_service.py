"""
评测集管理服务

负责评测集、评测用例的版本化管理和 CRUD 操作。
"""

import json
import logging
import os
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid

from bson import ObjectId

from app.core.database import get_mongo_db
from app.models.eval import EvalDataset, EvalCase, DatasetStatus
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


def _parse_semver(version: str) -> Optional[tuple[int, int, int]]:
    parts = version.split(".")
    if len(parts) != 3:
        return None
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None


def _version_lte(case_version: str, target_version: str) -> bool:
    """Return whether case_version is included in a target dataset version."""
    parsed_case = _parse_semver(case_version)
    parsed_target = _parse_semver(target_version)
    if not parsed_case or not parsed_target:
        return case_version == target_version
    return parsed_case <= parsed_target


class EvalDatasetService:
    """评测集管理服务"""

    COLLECTION_DATASETS = "eval_datasets"
    COLLECTION_CASES = "eval_cases"

    def __init__(self):
        self._initialized = False

    async def initialize(self):
        """初始化服务，创建索引"""
        if self._initialized:
            return

        logger.info("Initializing EvalDatasetService")
        db = get_mongo_db()

        # 创建索引
        await db[self.COLLECTION_DATASETS].create_index("dataset_id", unique=True)
        await db[self.COLLECTION_DATASETS].create_index("version")
        await db[self.COLLECTION_DATASETS].create_index("status")
        await db[self.COLLECTION_DATASETS].create_index("created_at")

        await db[self.COLLECTION_CASES].create_index("case_id")
        await db[self.COLLECTION_CASES].create_index([("case_id", 1), ("version", 1)], unique=True)
        await db[self.COLLECTION_CASES].create_index("tags")
        await db[self.COLLECTION_CASES].create_index("category")

        self._initialized = True
        logger.info("EvalDatasetService initialized with indexes")

    # ==================== Dataset CRUD ====================

    async def create_dataset(
        self,
        name: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        created_by: str = "",
    ) -> Dict[str, Any]:
        """创建评测集"""
        db = get_mongo_db()

        dataset_id = f"ds_{uuid.uuid4().hex[:12]}"
        dataset = EvalDataset(
            dataset_id=dataset_id,
            name=name,
            description=description,
            version="1.0.0",
            status=DatasetStatus.DRAFT,
            tags=tags or [],
            created_by=created_by,
        )

        doc = dataset.model_dump(by_alias=True, exclude={"id"})
        result = await db[self.COLLECTION_DATASETS].insert_one(doc)

        logger.info(f"Created dataset: {dataset_id}")
        return {"dataset_id": dataset_id, "_id": str(result.inserted_id)}

    async def get_dataset(self, dataset_id: str) -> Optional[Dict[str, Any]]:
        """获取评测集"""
        db = get_mongo_db()
        doc = await db[self.COLLECTION_DATASETS].find_one({"dataset_id": dataset_id})
        if doc:
            doc["id"] = str(doc.pop("_id"))
        return doc

    async def list_datasets(
        self,
        skip: int = 0,
        limit: int = 20,
        tags: Optional[List[str]] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """列出评测集"""
        db = get_mongo_db()

        query = {}
        if tags:
            query["tags"] = {"$in": tags}
        if status:
            query["status"] = status

        cursor = db[self.COLLECTION_DATASETS].find(query).sort("created_at", -1).skip(skip).limit(limit)
        results = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            results.append(doc)
        return results

    async def update_dataset(
        self,
        dataset_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        status: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """更新评测集"""
        db = get_mongo_db()

        update_fields = {"updated_at": now_tz()}
        if name is not None:
            update_fields["name"] = name
        if description is not None:
            update_fields["description"] = description
        if tags is not None:
            update_fields["tags"] = tags
        if status is not None:
            update_fields["status"] = status

        result = await db[self.COLLECTION_DATASETS].update_one(
            {"dataset_id": dataset_id},
            {"$set": update_fields}
        )

        if result.modified_count == 0:
            return None

        return await self.get_dataset(dataset_id)

    async def delete_dataset(self, dataset_id: str) -> bool:
        """删除评测集（软删除，标记为 archived）"""
        db = get_mongo_db()
        result = await db[self.COLLECTION_DATASETS].update_one(
            {"dataset_id": dataset_id},
            {"$set": {"status": DatasetStatus.ARCHIVED.value, "updated_at": now_tz()}}
        )
        return result.modified_count > 0

    # ==================== Case CRUD ====================

    async def add_case(
        self,
        dataset_id: str,
        name: str,
        input_data: Dict[str, Any],
        expected_output: Optional[Dict[str, Any]] = None,
        scoring_criteria: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        difficulty: str = "medium",
        category: str = "general",
        description: str = "",
    ) -> Dict[str, Any]:
        """向评测集添加用例"""
        db = get_mongo_db()

        # 检查数据集是否存在
        dataset = await self.get_dataset(dataset_id)
        if not dataset:
            raise ValueError(f"Dataset {dataset_id} not found")

        case_id = f"case_{uuid.uuid4().hex[:12]}"
        case = EvalCase(
            case_id=case_id,
            name=name,
            description=description,
            input=input_data,
            expected_output=expected_output,
            scoring_criteria=scoring_criteria or {},
            tags=tags or [],
            difficulty=difficulty,
            category=category,
        )

        doc = case.model_dump(by_alias=True, exclude={"id"})
        doc["dataset_id"] = dataset_id
        doc["version"] = dataset.get("version", "1.0.0")

        await db[self.COLLECTION_CASES].insert_one(doc)

        # 递增数据集版本并更新 cases 列表
        new_version = _bump_patch_version(dataset.get("version", "1.0.0"))
        await db[self.COLLECTION_DATASETS].update_one(
            {"dataset_id": dataset_id},
            {
                "$addToSet": {"cases": case_id},
                "$set": {"version": new_version, "updated_at": now_tz()},
            }
        )

        logger.info(f"Added case {case_id} to dataset {dataset_id} (v{new_version})")
        return {"case_id": case_id, "dataset_id": dataset_id, "dataset_version": new_version}

    async def get_case(self, case_id: str) -> Optional[Dict[str, Any]]:
        """获取用例"""
        db = get_mongo_db()
        doc = await db[self.COLLECTION_CASES].find_one({"case_id": case_id})
        if doc:
            doc["id"] = str(doc.pop("_id"))
        return doc

    async def list_cases(
        self,
        dataset_id: str,
        skip: int = 0,
        limit: int = 50,
        tags: Optional[List[str]] = None,
        category: Optional[str] = None,
        version: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """列出评测集中的用例

        Args:
            version: 可选，按数据集版本过滤。不传时返回当前最新版本的所有 case。
        """
        db = get_mongo_db()

        query = {"dataset_id": dataset_id}
        if tags:
            query["tags"] = {"$in": tags}
        if category:
            query["category"] = category

        cursor = db[self.COLLECTION_CASES].find(query).sort("created_at", -1)
        results = []
        async for doc in cursor:
            if version and not _version_lte(str(doc.get("version", "")), version):
                continue
            doc["id"] = str(doc.pop("_id"))
            results.append(doc)
        return results[skip:skip + limit]

    async def update_case(
        self,
        case_id: str,
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """更新用例

        更新成功后自动递增所属数据集的 patch 版本号，
        确保"按版本重放"能拿到更新前的快照。
        """
        db = get_mongo_db()

        # 先获取 case 以确认存在并拿到 dataset_id
        existing_case = await self.get_case(case_id)
        if not existing_case:
            return None

        allowed_fields = {"name", "description", "input", "expected_output", "scoring_criteria", "tags", "difficulty", "category"}
        update_fields = {"updated_at": now_tz()}
        for k, v in kwargs.items():
            if k in allowed_fields and v is not None:
                update_fields[k] = v

        result = await db[self.COLLECTION_CASES].update_one(
            {"case_id": case_id},
            {"$set": update_fields}
        )

        if result.modified_count == 0:
            return None

        # 递增数据集版本
        dataset_id = existing_case.get("dataset_id")
        if dataset_id:
            dataset = await self.get_dataset(dataset_id)
            if dataset:
                new_version = _bump_patch_version(dataset.get("version", "1.0.0"))
                await db[self.COLLECTION_DATASETS].update_one(
                    {"dataset_id": dataset_id},
                    {"$set": {"version": new_version, "updated_at": now_tz()}}
                )

        return await self.get_case(case_id)

    async def delete_case(self, case_id: str) -> bool:
        """删除用例"""
        db = get_mongo_db()

        # 获取 case 所属的 dataset
        case = await self.get_case(case_id)
        if not case:
            return False

        dataset_id = case.get("dataset_id")

        # 删除 case
        result = await db[self.COLLECTION_CASES].delete_one({"case_id": case_id})

        # 从数据集中移除引用并递增版本
        if dataset_id:
            dataset = await self.get_dataset(dataset_id)
            new_version = _bump_patch_version(dataset.get("version", "1.0.0")) if dataset else "1.0.0"
            await db[self.COLLECTION_DATASETS].update_one(
                {"dataset_id": dataset_id},
                {
                    "$pull": {"cases": case_id},
                    "$set": {"version": new_version, "updated_at": now_tz()},
                }
            )

        return result.deleted_count > 0

    async def get_dataset_with_cases(
        self,
        dataset_id: str,
        version: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """获取数据集及其所有用例

        Args:
            version: 可选，指定版本。不传时返回当前最新版本。
        """
        dataset = await self.get_dataset(dataset_id)
        if not dataset:
            return None

        cases = await self.list_cases(dataset_id, limit=1000, version=version)
        dataset["cases_detail"] = cases
        return dataset

    async def import_golden_cases(
        self,
        dataset_id: str,
    ) -> Dict[str, Any]:
        """导入内置 Golden Set 用例到指定评测集

        幂等操作：如果同名 case 已存在于数据集中则跳过，不创建重复记录。

        Returns:
            {"imported": N, "skipped": N, "total": N}
        """
        db = get_mongo_db()

        # 检查数据集是否存在
        dataset = await self.get_dataset(dataset_id)
        if not dataset:
            raise ValueError(f"Dataset {dataset_id} not found")

        # 加载 golden_cases.json
        golden_path = os.path.join(
            os.path.dirname(__file__), "data", "golden_cases.json"
        )
        with open(golden_path, "r", encoding="utf-8") as f:
            golden_data = json.load(f)

        cases_to_import = golden_data.get("cases", [])

        # 获取当前数据集中已有的 case name 集合，用于去重
        existing_cursor = db[self.COLLECTION_CASES].find(
            {"dataset_id": dataset_id}, {"name": 1}
        )
        existing_names = set()
        async for doc in existing_cursor:
            existing_names.add(doc.get("name"))

        imported = 0
        skipped = 0

        for case_data in cases_to_import:
            case_name = case_data.get("name", "")
            if case_name in existing_names:
                skipped += 1
                continue

            await self.add_case(
                dataset_id=dataset_id,
                name=case_name,
                input_data=case_data.get("input", {}),
                expected_output=case_data.get("expected_output"),
                scoring_criteria=case_data.get("scoring_criteria"),
                tags=case_data.get("tags", []),
                difficulty=case_data.get("difficulty", "medium"),
                category=case_data.get("category", "general"),
                description=case_data.get("description", ""),
            )
            imported += 1

        logger.info(
            f"Imported golden cases into dataset {dataset_id}: "
            f"{imported} imported, {skipped} skipped"
        )
        return {
            "imported": imported,
            "skipped": skipped,
            "total": len(cases_to_import),
        }

    async def batch_update_cases(
        self,
        case_ids: List[str],
        tags: Optional[List[str]] = None,
        category: Optional[str] = None,
        difficulty: Optional[str] = None,
        scoring_criteria: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """批量更新多个用例的公共字段

        Returns:
            {"updated": N}
        """
        db = get_mongo_db()

        update_fields = {"updated_at": now_tz()}
        if tags is not None:
            update_fields["tags"] = tags
        if category is not None:
            update_fields["category"] = category
        if difficulty is not None:
            update_fields["difficulty"] = difficulty
        if scoring_criteria is not None:
            update_fields["scoring_criteria"] = scoring_criteria

        if len(update_fields) <= 1:
            # 只有 updated_at，没有实际更新字段
            return {"updated": 0}

        result = await db[self.COLLECTION_CASES].update_many(
            {"case_id": {"$in": case_ids}},
            {"$set": update_fields},
        )

        # 收集受影响的 dataset_id 并递增版本
        affected_datasets = set()
        cursor = db[self.COLLECTION_CASES].find(
            {"case_id": {"$in": case_ids}}, {"dataset_id": 1}
        )
        async for doc in cursor:
            ds_id = doc.get("dataset_id")
            if ds_id:
                affected_datasets.add(ds_id)

        for ds_id in affected_datasets:
            dataset = await self.get_dataset(ds_id)
            if dataset:
                new_version = _bump_patch_version(dataset.get("version", "1.0.0"))
                await db[self.COLLECTION_DATASETS].update_one(
                    {"dataset_id": ds_id},
                    {"$set": {"version": new_version, "updated_at": now_tz()}},
                )

        logger.info(f"Batch updated {result.modified_count} cases")
        return {"updated": result.modified_count}

    async def publish_version(
        self,
        dataset_id: str,
        version: str,
    ) -> Optional[Dict[str, Any]]:
        """手动发布语义化版本

        将数据集版本号设置为用户指定的值（如 "2.0.0"），
        用于标记一个稳定的评测基准。不会修改任何 case 内容。
        """
        db = get_mongo_db()

        # 简单校验版本号格式
        parts = version.split(".")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            raise ValueError(f"Invalid version format: {version}, expected x.y.z")

        result = await db[self.COLLECTION_DATASETS].update_one(
            {"dataset_id": dataset_id},
            {"$set": {"version": version, "updated_at": now_tz()}}
        )

        if result.modified_count == 0:
            return None

        logger.info(f"Published dataset {dataset_id} as v{version}")
        return await self.get_dataset(dataset_id)


# 单例实例
dataset_service = EvalDatasetService()
