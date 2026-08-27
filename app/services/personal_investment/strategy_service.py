"""
策略管理服务

负责策略定义的 CRUD 操作，确保用户隔离。
"""

import logging
import uuid
from typing import Optional, List, Dict, Any

from app.core.database import get_mongo_db
from app.models.personal_investment import StrategyDefinition, StrategyStatus
from app.services.personal_investment.terminology_filter import TerminologyFilter
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)


class StrategyService:
    """策略管理服务"""

    COLLECTION = "strategy_definitions"

    def __init__(self):
        self._initialized = False

    @staticmethod
    def _check_terminology(name: str, description: str) -> None:
        """
        校验策略名称/描述是否包含买入、卖出、目标价、稳赚等荐股式措辞。

        策略名称和描述是用户主动填写的文本，会被直接展示在候选池、体检
        报告和上下文注入摘要中，因此必须在源头拒绝，而不是等到结果落盘
        时才悄悄替换（那样会让用户困惑"我填的内容为什么变了"）。
        对应 spec: 结果 MUST NOT 直接输出买入、卖出或目标价指令。
        """
        for field_label, text in (("策略名称", name), ("策略说明", description)):
            if not text:
                continue
            check = TerminologyFilter.validate_compliance(text)
            if not check["compliant"]:
                terms = "、".join(v["term"] for v in check["violations"] if v.get("term"))
                raise ValueError(
                    f"{field_label}包含不合规措辞（{terms}），"
                    f"请使用研究、观察、筛选等中性表述，避免买入/卖出/目标价/稳赚等荐股式用语"
                )

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
        self._check_terminology(name, description)
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
        if kwargs.get("name") is not None or kwargs.get("description") is not None:
            existing = await self.get_strategy(strategy_id, user_id)
            name = kwargs.get("name", existing.get("name", "") if existing else "")
            description = kwargs.get("description", existing.get("description", "") if existing else "")
            self._check_terminology(name, description)

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
