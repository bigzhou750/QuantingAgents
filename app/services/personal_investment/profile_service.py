"""
投资画像服务

负责用户投资画像的 CRUD 操作，确保用户隔离和数据校验。
"""

import logging
from typing import Optional, Dict, Any

from app.core.database import get_mongo_db
from app.models.personal_investment import InvestmentProfile, RiskPreference, TradingStyle
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)


class ProfileService:
    """投资画像服务"""

    COLLECTION = "investment_profiles"

    def __init__(self):
        self._initialized = False

    async def initialize(self):
        """初始化服务，创建索引"""
        if self._initialized:
            return

        logger.info("Initializing ProfileService")
        db = get_mongo_db()

        # 创建索引：每个用户只能有一个画像
        await db[self.COLLECTION].create_index("user_id", unique=True)
        await db[self.COLLECTION].create_index("updated_at")

        self._initialized = True
        logger.info("ProfileService initialized with indexes")

    async def get_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户的投资画像"""
        db = get_mongo_db()
        doc = await db[self.COLLECTION].find_one({"user_id": user_id})
        if doc:
            doc["id"] = str(doc.pop("_id"))
        return doc

    async def create_or_update_profile(
        self,
        user_id: str,
        profile_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """创建或更新用户画像"""
        db = get_mongo_db()

        # 验证数据
        try:
            profile = InvestmentProfile(user_id=user_id, **profile_data)
        except Exception as e:
            raise ValueError(f"Invalid profile data: {e}")

        doc = profile.model_dump(by_alias=True, exclude={"id"})
        doc["updated_at"] = now_tz()

        # upsert: 如果存在则更新，不存在则插入
        result = await db[self.COLLECTION].update_one(
            {"user_id": user_id},
            {"$set": doc},
            upsert=True,
        )

        logger.info(f"Profile saved for user {user_id}")
        return await self.get_profile(user_id)

    async def delete_profile(self, user_id: str) -> bool:
        """删除用户画像"""
        db = get_mongo_db()
        result = await db[self.COLLECTION].delete_one({"user_id": user_id})
        return result.deleted_count > 0

    async def get_profile_summary(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取画像摘要（用于 VibeAgent 上下文注入）"""
        profile = await self.get_profile(user_id)
        if not profile:
            return None

        # 返回归一化的摘要字段。持仓只暴露研究所需字段，不把原始画像文档直接交给 runtime。
        holdings = []
        for holding in profile.get("current_holdings", [])[:20]:
            if not isinstance(holding, dict) or not holding.get("stock_code"):
                continue
            holdings.append({
                "stock_code": str(holding["stock_code"]),
                "stock_name": str(holding.get("stock_name", "")),
                "quantity": holding.get("quantity", 0),
                "cost_price": holding.get("cost_price", 0),
            })

        return {
            "risk_preference": profile.get("risk_preference"),
            "trading_style": profile.get("trading_style"),
            "target_markets": profile.get("target_markets", []),
            "excluded_sectors": profile.get("excluded_sectors", []),
            "excluded_stocks": profile.get("excluded_stocks", []),
            "exclude_st": profile.get("exclude_st", True),
            "max_position_per_stock": profile.get("max_position_per_stock", 0.2),
            "current_holdings_count": len(holdings),
            "current_holdings": holdings,
        }


# 单例实例
profile_service = ProfileService()
