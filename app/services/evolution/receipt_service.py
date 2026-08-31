"""
自进化回执服务

管理 EvolutionReceipt 的 CRUD 操作，记录完整的自进化生命周期。
"""

import logging
from typing import Optional, List, Dict, Any

from app.core.database import get_mongo_db
from app.models.evolution import EvolutionReceipt

logger = logging.getLogger(__name__)


class ReceiptService:
    """回执服务"""

    COLLECTION = "evolution_receipts"

    def __init__(self):
        self._initialized = False

    async def initialize(self):
        """初始化服务和索引"""
        if self._initialized:
            return
        db = get_mongo_db()
        await db[self.COLLECTION].create_index("receipt_id", unique=True)
        await db[self.COLLECTION].create_index("proposal_id")
        await db[self.COLLECTION].create_index("final_action")
        await db[self.COLLECTION].create_index("created_at")
        self._initialized = True
        logger.info("ReceiptService initialized")

    async def create(self, receipt: EvolutionReceipt) -> EvolutionReceipt:
        """创建回执"""
        db = get_mongo_db()
        await db[self.COLLECTION].insert_one(receipt.model_dump(by_alias=True, exclude={"id"}))
        logger.info(f"[Evolution] Created receipt {receipt.receipt_id} for proposal {receipt.proposal_id}")
        return receipt

    async def get(self, receipt_id: str) -> Optional[EvolutionReceipt]:
        """获取回执"""
        db = get_mongo_db()
        doc = await db[self.COLLECTION].find_one({"receipt_id": receipt_id})
        if not doc:
            return None
        return EvolutionReceipt(**doc)

    async def list_receipts(self, skip: int = 0, limit: int = 50) -> List[EvolutionReceipt]:
        """列出回执"""
        db = get_mongo_db()
        cursor = db[self.COLLECTION].find().skip(skip).limit(limit).sort("created_at", -1)
        results = []
        async for doc in cursor:
            results.append(EvolutionReceipt(**doc))
        return results

    async def get_stats(self) -> Dict[str, Any]:
        """获取回执统计"""
        db = get_mongo_db()
        total = await db[self.COLLECTION].count_documents({})
        pipeline = [{"$group": {"_id": "$final_action", "count": {"$sum": 1}}}]
        by_action = {}
        async for doc in db[self.COLLECTION].aggregate(pipeline):
            by_action[doc["_id"]] = doc["count"]
        return {"total": total, "by_action": by_action}


# 模块级单例
receipt_service = ReceiptService()
