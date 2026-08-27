"""
策略管理服务

负责策略定义的 CRUD 操作，确保用户隔离。
"""

import logging
import uuid
from typing import Optional, List, Dict, Any

from app.core.database import get_mongo_db
from app.models.personal_investment import StrategyDefinition, StrategyStatus
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)


class StrategyService:
    """策略管理服务"""

    COLLECTION = "strategy_definitions"

    def __init__(self):
        self._initialized = False

    async def initialize(self):
        """初始化服务，创建索引"""
        if self._initialized:
            return

        logger.info("Initializing StrategyService")
        db = get_mongo_db()

        # 创建索引
        await db[self.COLLECTION].create_index("strategy_id", unique=True)
        await db[self.COLLECTION].create_index([("user_id", 1), ("status", 1)])
        await db[self.COLLECTION].create_index("tags")
        await db[self.COLLECTION].create_index("created_at")

        self._initialized = True
        logger.info("StrategyService initialized with indexes")

    async def create_strategy(
        self,
        user_id: str,
        name: str,
        description: str = "",
        applicable_markets: Optional[List[str]] = None,
        screening_criteria: Optional[Dict[str, Any]] = None,
        parameters: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """创建策略"""
        db = get_mongo_db()

        strategy_id = f"strat_{uuid.uuid4().hex[:12]}"

        strategy = StrategyDefinition(
            strategy_id=strategy_id,
            user_id=user_id,
            name=name,
            description=description,
            status=StrategyStatus.ACTIVE,
            applicable_markets=applicable_markets or ["A股"],
            screening_criteria=screening_criteria or {},
            parameters=parameters or {},
            tags=tags or [],
        )

        doc = strategy.model_dump(by_alias=True, exclude={"id"})
        await db[self.COLLECTION].insert_one(doc)

        logger.info(f"Created strategy {strategy_id} for user {user_id}")
        return {"strategy_id": strategy_id, "name": name}

    async def get_strategy(self, strategy_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """获取策略详情"""
        db = get_mongo_db()

        query = {"strategy_id": strategy_id}
        if user_id:
            query["user_id"] = user_id  # 用户隔离

        doc = await db[self.COLLECTION].find_one(query)
        if doc:
            doc["id"] = str(doc.pop("_id"))
        return doc

    async def list_strategies(
        self,
        user_id: str,
        include_disabled: bool = False,
        skip: int = 0,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """列出用户的策略列表"""
        db = get_mongo_db()

        query = {"user_id": user_id}
        if not include_disabled:
            query["status"] = {"$ne": StrategyStatus.DISABLED.value}

        cursor = db[self.COLLECTION].find(query).sort("created_at", -1).skip(skip).limit(limit)
        results = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            results.append(doc)
        return results

    async def update_strategy(
        self,
        strategy_id: str,
        user_id: str,
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """更新策略"""
        db = get_mongo_db()

        allowed_fields = {"name", "description", "applicable_markets", "screening_criteria", "parameters", "tags"}
        update_fields = {"updated_at": now_tz()}
        for k, v in kwargs.items():
            if k in allowed_fields and v is not None:
                update_fields[k] = v

        result = await db[self.COLLECTION].update_one(
            {"strategy_id": strategy_id, "user_id": user_id},
            {"$set": update_fields}
        )

        if result.modified_count == 0:
            return None

        return await self.get_strategy(strategy_id, user_id)

    async def disable_strategy(self, strategy_id: str, user_id: str) -> bool:
        """停用策略"""
        db = get_mongo_db()
        result = await db[self.COLLECTION].update_one(
            {"strategy_id": strategy_id, "user_id": user_id},
            {"$set": {"status": StrategyStatus.DISABLED.value, "updated_at": now_tz()}}
        )
        return result.modified_count > 0

    async def enable_strategy(self, strategy_id: str, user_id: str) -> bool:
        """启用策略"""
        db = get_mongo_db()
        result = await db[self.COLLECTION].update_one(
            {"strategy_id": strategy_id, "user_id": user_id},
            {"$set": {"status": StrategyStatus.ACTIVE.value, "updated_at": now_tz()}}
        )
        return result.modified_count > 0

    async def delete_strategy(self, strategy_id: str, user_id: str) -> bool:
        """删除策略（软删除，标记为归档）"""
        db = get_mongo_db()
        result = await db[self.COLLECTION].update_one(
            {"strategy_id": strategy_id, "user_id": user_id},
            {"$set": {"status": StrategyStatus.ARCHIVED.value, "updated_at": now_tz()}}
        )
        return result.modified_count > 0


# 单例实例
strategy_service = StrategyService()
