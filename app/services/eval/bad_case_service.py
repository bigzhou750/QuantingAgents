"""
Bad Case 池服务

管理失败样本的收集、标注和回流为正式评测用例。
支持从失败 trial、人工复核、安全拦截和用户反馈等来源回流。

对应 spec 二期任务 2.9。
"""

import logging
import uuid
from typing import Optional, List, Dict, Any

from app.core.database import get_mongo_db
from app.models.eval import EvalBadCase, BadCaseSource
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)


class BadCaseService:
    """Bad Case 池服务"""

    COLLECTION = "eval_bad_cases"

    def __init__(self):
        self._initialized = False

    async def initialize(self):
        if self._initialized:
            return
        db = get_mongo_db()
        await db[self.COLLECTION].create_index("bad_case_id", unique=True)
        await db[self.COLLECTION].create_index("source")
        await db[self.COLLECTION].create_index("risk_level")
        await db[self.COLLECTION].create_index("created_at")
        self._initialized = True

    async def create_bad_case(
        self,
        source: str,
        input_data: Dict[str, Any],
        output_data: Optional[Dict[str, Any]] = None,
        failure_reason: str = "",
        risk_level: str = "medium",
        tags: Optional[List[str]] = None,
        source_trial_id: Optional[str] = None,
        source_run_id: Optional[str] = None,
        created_by: str = "",
    ) -> Dict[str, Any]:
        """创建 bad case"""
        db = get_mongo_db()

        bad_case_id = f"bc_{uuid.uuid4().hex[:12]}"
        doc = EvalBadCase(
            bad_case_id=bad_case_id,
            source=BadCaseSource(source),
            source_trial_id=source_trial_id,
            source_run_id=source_run_id,
            input_data=input_data,
            output_data=output_data,
            failure_reason=failure_reason,
            risk_level=risk_level,
            tags=tags or [],
            created_by=created_by,
        )

        await db[self.COLLECTION].insert_one(doc.model_dump(by_alias=True, exclude={"id"}))
        logger.info(f"Created bad case {bad_case_id} from {source}")
        return {"bad_case_id": bad_case_id}

    async def create_from_failed_trial(
        self,
        trial_id: str,
        created_by: str = "",
    ) -> Optional[Dict[str, Any]]:
        """从失败的 trial 自动创建 bad case"""
        db = get_mongo_db()

        trial = await db["eval_trials"].find_one({"trial_id": trial_id})
        if not trial:
            return None

        return await self.create_bad_case(
            source=BadCaseSource.TRIAL_FAILURE.value,
            input_data=trial.get("input_data", {}),
            output_data=trial.get("output_data"),
            failure_reason=trial.get("error_message", "Trial failed"),
            risk_level="medium",
            source_trial_id=trial_id,
            source_run_id=trial.get("run_id"),
            created_by=created_by,
        )

    async def list_bad_cases(
        self,
        source: Optional[str] = None,
        risk_level: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """列出 bad cases"""
        db = get_mongo_db()

        query = {}
        if source:
            query["source"] = source
        if risk_level:
            query["risk_level"] = risk_level

        cursor = db[self.COLLECTION].find(query).sort("created_at", -1).skip(skip).limit(limit)
        results = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            results.append(doc)
        return results

    async def get_bad_case(self, bad_case_id: str) -> Optional[Dict[str, Any]]:
        db = get_mongo_db()
        doc = await db[self.COLLECTION].find_one({"bad_case_id": bad_case_id})
        if doc:
            doc["id"] = str(doc.pop("_id"))
        return doc

    async def convert_to_case(
        self,
        bad_case_id: str,
        dataset_id: str,
        created_by: str = "",
    ) -> Optional[Dict[str, Any]]:
        """将 bad case 转换为正式评测用例并加入指定数据集"""
        from app.services.eval.dataset_service import dataset_service

        bad_case = await self.get_bad_case(bad_case_id)
        if not bad_case:
            return None

        # 创建新 case
        result = await dataset_service.add_case(
            dataset_id=dataset_id,
            name=f"[BadCase] {bad_case.get('failure_reason', '')[:50]}",
            input_data=bad_case.get("input_data", {}),
            expected_output=bad_case.get("output_data"),
            tags=bad_case.get("tags", []) + ["bad_case_reflow"],
            description=f"From bad case {bad_case_id}, source: {bad_case.get('source')}",
        )

        # 标记已转换
        db = get_mongo_db()
        await db[self.COLLECTION].update_one(
            {"bad_case_id": bad_case_id},
            {"$set": {"converted_to_case_id": result.get("case_id"), "updated_at": now_tz()}}
        )

        logger.info(f"Converted bad case {bad_case_id} to case {result.get('case_id')}")
        return result

    async def delete_bad_case(self, bad_case_id: str) -> bool:
        db = get_mongo_db()
        result = await db[self.COLLECTION].delete_one({"bad_case_id": bad_case_id})
        return result.deleted_count > 0

    async def get_stats(self) -> Dict[str, Any]:
        """获取 bad case 池统计"""
        db = get_mongo_db()

        total = await db[self.COLLECTION].count_documents({})
        by_source = {}
        async for doc in db[self.COLLECTION].aggregate([
            {"$group": {"_id": "$source", "count": {"$sum": 1}}},
        ]):
            by_source[doc["_id"]] = doc["count"]

        by_risk = {}
        async for doc in db[self.COLLECTION].aggregate([
            {"$group": {"_id": "$risk_level", "count": {"$sum": 1}}},
        ]):
            by_risk[doc["_id"]] = doc["count"]

        converted = await db[self.COLLECTION].count_documents({
            "converted_to_case_id": {"$ne": None}
        })

        return {
            "total": total,
            "by_source": by_source,
            "by_risk_level": by_risk,
            "converted_count": converted,
            "pending_count": total - converted,
        }


# 单例实例
bad_case_service = BadCaseService()
