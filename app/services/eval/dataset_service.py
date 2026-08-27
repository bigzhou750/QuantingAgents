"""
评测集管理服务

负责评测集、评测用例的版本化管理和 CRUD 操作。
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid

from bson import ObjectId

from app.core.database import get_mongo_db
from app.models.eval import EvalDataset, EvalCase, DatasetStatus
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)


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

        # 更新数据集的 cases 列表
        await db[self.COLLECTION_DATASETS].update_one(
            {"dataset_id": dataset_id},
            {"$addToSet": {"cases": case_id}, "$set": {"updated_at": now_tz()}}
        )

        logger.info(f"Added case {case_id} to dataset {dataset_id}")
        return {"case_id": case_id, "dataset_id": dataset_id}

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
    ) -> List[Dict[str, Any]]:
        """列出评测集中的用例"""
        db = get_mongo_db()

        query = {"dataset_id": dataset_id}
        if tags:
            query["tags"] = {"$in": tags}
        if category:
            query["category"] = category

        cursor = db[self.COLLECTION_CASES].find(query).sort("created_at", -1).skip(skip).limit(limit)
        results = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            results.append(doc)
        return results

    async def update_case(
        self,
        case_id: str,
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """更新用例"""
        db = get_mongo_db()

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

        # 从数据集中移除引用
        if dataset_id:
            await db[self.COLLECTION_DATASETS].update_one(
                {"dataset_id": dataset_id},
                {"$pull": {"cases": case_id}, "$set": {"updated_at": now_tz()}}
            )

        return result.deleted_count > 0

    async def get_dataset_with_cases(
        self,
        dataset_id: str,
    ) -> Optional[Dict[str, Any]]:
        """获取数据集及其所有用例"""
        dataset = await self.get_dataset(dataset_id)
        if not dataset:
            return None

        cases = await self.list_cases(dataset_id, limit=1000)
        dataset["cases_detail"] = cases
        return dataset


# 单例实例
dataset_service = EvalDatasetService()
