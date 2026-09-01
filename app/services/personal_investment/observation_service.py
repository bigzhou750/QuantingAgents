"""
投资观察标的服务

提供观察标的的 CRUD 操作、复盘备注管理和待复盘汇总。
观察标的是选股结果与自选股之间的中间层，保留来源链路用于学习闭环。
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from app.core.database import get_mongo_db
from app.models.observation import (
    ObservationRecord,
    ObservationStatus,
    ReviewNote,
    ReviewTargetType,
)
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)


class ObservationService:
    """投资观察标的服务"""

    OBSERVATIONS_COLLECTION = "investment_observations"
    REVIEW_NOTES_COLLECTION = "review_notes"

    async def initialize(self):
        """初始化索引"""
        db = get_mongo_db()
        # 用户+股票代码唯一约束（仅对 ACTIVE 状态有效，REMOVED 允许重新添加）
        await db[self.OBSERVATIONS_COLLECTION].create_index(
            [("user_id", 1), ("stock_code", 1), ("status", 1)],
            unique=True,
        )
        await db[self.OBSERVATIONS_COLLECTION].create_index(
            [("user_id", 1), ("status", 1)]
        )
        await db[self.REVIEW_NOTES_COLLECTION].create_index(
            [("user_id", 1), ("target_type", 1), ("target_id", 1)]
        )
        logger.info("ObservationService initialized")

    # ==================== 观察标的 CRUD ====================

    async def add_observation(
        self,
        user_id: str,
        record: ObservationRecord,
    ) -> Dict[str, Any]:
        """添加观察标的

        如果同一用户+股票已存在 ACTIVE 记录，返回已有记录而非重复创建。
        如果之前是 REMOVED 状态，则重新激活。
        """
        db = get_mongo_db()
        coll = db[self.OBSERVATIONS_COLLECTION]

        # 检查是否已存在
        existing = await coll.find_one({
            "user_id": user_id,
            "stock_code": record.stock_code,
            "status": {"$in": [ObservationStatus.ACTIVE.value, ObservationStatus.REVIEWED.value]},
        })

        if existing:
            if existing.get("status") == ObservationStatus.ACTIVE.value:
                # 已存在且活跃，直接返回
                existing.pop("_id", None)
                return existing

            # 之前被移除，重新激活并更新来源信息
            update_data = {
                "status": ObservationStatus.ACTIVE.value,
                "source_type": record.source_type,
                "source_strategy_id": record.source_strategy_id,
                "source_task_id": record.source_task_id,
                "match_reasons": record.match_reasons,
                "risk_warnings": record.risk_warnings,
                "data_as_of": record.data_as_of,
                "review_interval_days": record.review_interval_days,
                "next_review_at": now_tz() + timedelta(days=record.review_interval_days),
                "updated_at": now_tz(),
            }
            if record.user_notes:
                update_data["user_notes"] = record.user_notes

            await coll.update_one(
                {"_id": existing["_id"]},
                {"$set": update_data},
            )
            updated = await coll.find_one({"_id": existing["_id"]})
            updated.pop("_id", None)
            return updated

        # 新建记录
        doc = record.to_doc()
        doc["user_id"] = user_id
        if not doc.get("next_review_at"):
            doc["next_review_at"] = now_tz() + timedelta(days=record.review_interval_days)
        result = await coll.insert_one(doc)
        doc["_id"] = result.inserted_id
        doc.pop("_id", None)
        logger.info(f"Observation added: user={user_id}, stock={record.stock_code}")
        return doc

    async def list_observations(
        self,
        user_id: str,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """列出观察标的"""
        db = get_mongo_db()
        coll = db[self.OBSERVATIONS_COLLECTION]

        query: Dict[str, Any] = {"user_id": user_id}
        if status:
            query["status"] = status
        else:
            # 默认只返回 ACTIVE
            query["status"] = ObservationStatus.ACTIVE.value

        total = await coll.count_documents(query)
        cursor = coll.find(query).sort("created_at", -1).skip(skip).limit(limit)
        items = []
        async for doc in cursor:
            doc.pop("_id", None)
            items.append(doc)

        return {"items": items, "total": total}

    async def get_observation(
        self,
        observation_id: str,
        user_id: str,
    ) -> Optional[Dict[str, Any]]:
        """获取单个观察标的详情"""
        db = get_mongo_db()
        doc = await db[self.OBSERVATIONS_COLLECTION].find_one({
            "observation_id": observation_id,
            "user_id": user_id,
        })
        if doc:
            doc.pop("_id", None)
        return doc

    async def update_observation(
        self,
        observation_id: str,
        user_id: str,
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """更新观察标的（备注等）"""
        db = get_mongo_db()
        coll = db[self.OBSERVATIONS_COLLECTION]

        update_fields = {k: v for k, v in kwargs.items() if v is not None}
        if "review_interval_days" in update_fields:
            update_fields["next_review_at"] = now_tz() + timedelta(days=update_fields["review_interval_days"])
        if not update_fields:
            return await self.get_observation(observation_id, user_id)

        update_fields["updated_at"] = now_tz()

        result = await coll.update_one(
            {"observation_id": observation_id, "user_id": user_id},
            {"$set": update_fields},
        )

        if result.modified_count == 0:
            return None

        return await self.get_observation(observation_id, user_id)

    async def remove_observation(
        self,
        observation_id: str,
        user_id: str,
    ) -> bool:
        """移出观察标的（状态更新为 REMOVED，不删除）"""
        db = get_mongo_db()
        result = await db[self.OBSERVATIONS_COLLECTION].update_one(
            {"observation_id": observation_id, "user_id": user_id},
            {"$set": {
                "status": ObservationStatus.REMOVED.value,
                "updated_at": now_tz(),
            }},
        )
        if result.modified_count > 0:
            logger.info(f"Observation removed: id={observation_id}, user={user_id}")
            return True
        return False

    async def is_observing(self, user_id: str, stock_code: str) -> bool:
        """检查某只股票是否正在被观察"""
        db = get_mongo_db()
        doc = await db[self.OBSERVATIONS_COLLECTION].find_one({
            "user_id": user_id,
            "stock_code": stock_code,
            "status": ObservationStatus.ACTIVE.value,
        })
        return doc is not None

    # ==================== 复盘备注 ====================

    async def add_review_note(
        self,
        user_id: str,
        target_id: str,
        content: str,
        target_type: str = ReviewTargetType.OBSERVATION.value,
    ) -> Dict[str, Any]:
        """添加复盘备注"""
        db = get_mongo_db()
        note = ReviewNote(
            user_id=user_id,
            target_type=target_type,
            target_id=target_id,
            content=content,
        )
        doc = note.to_doc()
        result = await db[self.REVIEW_NOTES_COLLECTION].insert_one(doc)
        doc["_id"] = result.inserted_id
        doc.pop("_id", None)

        # 如果是观察标的的复盘，更新状态为 REVIEWED
        if target_type == ReviewTargetType.OBSERVATION.value:
            await db[self.OBSERVATIONS_COLLECTION].update_one(
                {"observation_id": target_id, "user_id": user_id},
                {"$set": {
                    "status": ObservationStatus.REVIEWED.value,
                    "updated_at": now_tz(),
                }},
            )

        logger.info(f"Review note added: target={target_id}, user={user_id}")
        return doc

    async def list_review_notes(
        self,
        user_id: str,
        target_id: Optional[str] = None,
        target_type: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """列出复盘备注"""
        db = get_mongo_db()
        query: Dict[str, Any] = {"user_id": user_id}
        if target_id:
            query["target_id"] = target_id
        if target_type:
            query["target_type"] = target_type

        cursor = db[self.REVIEW_NOTES_COLLECTION].find(query).sort("created_at", -1).skip(skip).limit(limit)
        items = []
        async for doc in cursor:
            doc.pop("_id", None)
            items.append(doc)
        return items

    async def get_pending_reviews(self, user_id: str) -> Dict[str, Any]:
        """获取达到复盘周期且尚未复盘的观察标的。"""
        db = get_mongo_db()

        # 获取所有 ACTIVE 观察
        active_cursor = db[self.OBSERVATIONS_COLLECTION].find({
            "user_id": user_id,
            "status": ObservationStatus.ACTIVE.value,
        })
        active_ids = []
        async for doc in active_cursor:
            active_ids.append(doc.get("observation_id"))

        if not active_ids:
            return {"count": 0, "items": []}

        # 找出已有复盘备注的 observation_id
        reviewed_cursor = db[self.REVIEW_NOTES_COLLECTION].find({
            "user_id": user_id,
            "target_type": ReviewTargetType.OBSERVATION.value,
            "target_id": {"$in": active_ids},
        }).distinct("target_id")
        reviewed_ids = set(await reviewed_cursor)

        now = now_tz()
        due_cursor = db[self.OBSERVATIONS_COLLECTION].find({
            "user_id": user_id,
            "status": ObservationStatus.ACTIVE.value,
            "$or": [
                {"next_review_at": {"$lte": now}},
                {
                    "next_review_at": {"$exists": False},
                    "created_at": {"$lte": now - timedelta(days=7)},
                },
            ],
        })
        due_ids = []
        async for doc in due_cursor:
            due_ids.append(doc.get("observation_id"))
        pending_ids = [oid for oid in due_ids if oid not in reviewed_ids]

        # 获取待复盘的详细信息
        items = []
        if pending_ids:
            cursor = db[self.OBSERVATIONS_COLLECTION].find({
                "user_id": user_id,
                "observation_id": {"$in": pending_ids},
            }).sort("created_at", 1).limit(10)
            async for doc in cursor:
                doc.pop("_id", None)
                items.append(doc)

        return {"count": len(pending_ids), "items": items}


# 模块级单例
observation_service = ObservationService()
