"""
新闻关注工作台服务
提供关注收集、持仓影响分析和模拟告警能力
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from bson import ObjectId

from app.core.database import get_mongo_db

logger = logging.getLogger("webapi")

# ── 影响等级常量 ──────────────────────────────────────────────
IMPACT_LOW = "low"
IMPACT_MEDIUM = "medium"
IMPACT_HIGH = "high"
IMPACT_LEVELS = [IMPACT_LOW, IMPACT_MEDIUM, IMPACT_HIGH]

# ── 告警阈值常量 ──────────────────────────────────────────────
ALERT_THRESHOLD_LOW = "low"       # 低/中/高都告警
ALERT_THRESHOLD_MEDIUM = "medium" # 中/高告警
ALERT_THRESHOLD_HIGH = "high"     # 仅高告警


class NewsWatchService:
    """新闻关注工作台服务"""

    def __init__(self):
        self._db = None

    async def _get_db(self):
        if self._db is None:
            self._db = get_mongo_db()
        return self._db

    # ════════════════════════════════════════════════════════════
    # 1. 关注收集
    # ════════════════════════════════════════════════════════════

    async def collect_item(
        self,
        user_id: str,
        item_type: str,
        symbol: Optional[str] = None,
        news_id: Optional[str] = None,
        source_page: str = "",
        title: str = "",
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        收集一条股票或新闻到关注工作台。
        item_type: 'stock' | 'news'
        """
        db = await self._get_db()
        collection = db["news_watch_collected"]

        doc = {
            "user_id": user_id,
            "item_type": item_type,
            "symbol": symbol,
            "news_id": news_id,
            "source_page": source_page,
            "title": title,
            "extra": extra or {},
            "collected_at": datetime.utcnow(),
        }

        result = await collection.insert_one(doc)
        doc["_id"] = str(result.inserted_id)
        logger.info(f"✅ 收集记录已保存: user={user_id}, type={item_type}, symbol={symbol}")
        return doc

    async def get_collected_items(
        self,
        user_id: str,
        limit: int = 50,
        skip: int = 0,
        item_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """获取用户最近收集的记录"""
        db = await self._get_db()
        collection = db["news_watch_collected"]

        query: Dict[str, Any] = {"user_id": user_id}
        if item_type:
            query["item_type"] = item_type

        cursor = collection.find(query).sort("collected_at", -1).skip(skip).limit(limit)
        items = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            if isinstance(doc.get("collected_at"), datetime):
                doc["collected_at"] = doc["collected_at"].isoformat()
            items.append(doc)
        return items

    async def remove_collected_item(self, user_id: str, item_id: str) -> bool:
        """移除一条收集记录"""
        db = await self._get_db()
        collection = db["news_watch_collected"]
        result = await collection.delete_one({
            "_id": ObjectId(item_id),
            "user_id": user_id,
        })
        return result.deleted_count > 0

    # ════════════════════════════════════════════════════════════
    # 2. 持仓新闻影响分析
    # ════════════════════════════════════════════════════════════

    async def analyze_holdings_impact(
        self,
        user_id: str,
        hours_back: int = 72,
    ) -> Dict[str, Any]:
        """
        基于用户当前持仓，分析近期新闻的影响。
        返回：受影响持仓列表、每条的影响等级、证据充分性标记。
        """
        db = await self._get_db()

        # 1) 获取用户持仓（从投资画像）
        profile_doc = await db["investment_profiles"].find_one({"user_id": user_id})
        holdings: List[Dict[str, Any]] = []
        if profile_doc and profile_doc.get("current_holdings"):
            holdings = profile_doc["current_holdings"]

        if not holdings:
            return {
                "has_holdings": False,
                "holdings_count": 0,
                "impacts": [],
                "data_sufficient": False,
                "boundary_note": "当前没有持仓数据，无法进行持仓影响分析。你可以先在投资画像中设置当前持仓。",
            }

        # 2) 对每只持仓查询近期新闻并评估影响
        impacts = []
        from app.services.news_data_service import get_news_data_service, NewsQueryParams

        news_service = await get_news_data_service()
        start_time = datetime.utcnow() - timedelta(hours=hours_back)

        for holding in holdings:
            stock_code = holding.get("stock_code") or holding.get("symbol", "")
            stock_name = holding.get("stock_name", stock_code)

            if not stock_code:
                continue

            params = NewsQueryParams(
                symbol=stock_code,
                start_time=start_time,
                limit=20,
                sort_by="publish_time",
                sort_order=-1,
            )
            news_list = await news_service.query_news(params)

            # 简单规则评估影响等级
            impact_level, evidence_note = self._evaluate_impact(news_list, holding)

            impacts.append({
                "stock_code": stock_code,
                "stock_name": stock_name,
                "news_count": len(news_list),
                "impact_level": impact_level,
                "evidence_note": evidence_note,
                "latest_news_time": (
                    news_list[0].get("publish_time", "") if news_list else ""
                ),
                "sample_headlines": [
                    n.get("title", "")[:80] for n in news_list[:3]
                ],
            })

        data_sufficient = any(i["news_count"] >= 3 for i in impacts)

        return {
            "has_holdings": True,
            "holdings_count": len(holdings),
            "hours_back": hours_back,
            "impacts": impacts,
            "data_sufficient": data_sufficient,
            "boundary_note": (
                "分析基于近期新闻的规则匹配，不是回测结果，也不构成交易建议。"
                + ("部分持仓新闻覆盖不足，结论仅供参考。" if not data_sufficient else "")
            ),
        }

    async def analyze_stock_impact(
        self,
        user_id: str,
        stock_code: str,
        hours_back: int = 72,
    ) -> Dict[str, Any]:
        """分析单个观察标的的新闻影响，并保留用户画像上下文。"""
        db = await self._get_db()
        profile_doc = await db["investment_profiles"].find_one({"user_id": user_id})
        stock_doc = await db["stock_basic_info"].find_one({
            "$or": [{"code": stock_code}, {"symbol": stock_code}]
        })

        holding = {
            "stock_code": stock_code,
            "stock_name": (stock_doc or {}).get("name") or stock_code,
            "profile_risk_preference": (profile_doc or {}).get("risk_preference"),
        }

        from app.services.news_data_service import get_news_data_service, NewsQueryParams
        news_service = await get_news_data_service()
        start_time = datetime.utcnow() - timedelta(hours=hours_back)
        params = NewsQueryParams(
            symbol=stock_code,
            start_time=start_time,
            limit=20,
            sort_by="publish_time",
            sort_order=-1,
        )
        news_list = await news_service.query_news(params)
        impact_level, evidence_note = self._evaluate_impact(news_list, holding)

        return {
            "has_holdings": True,
            "holdings_count": 1,
            "hours_back": hours_back,
            "symbol": stock_code,
            "impacts": [{
                "stock_code": stock_code,
                "stock_name": holding["stock_name"],
                "news_count": len(news_list),
                "impact_level": impact_level,
                "evidence_note": evidence_note,
                "latest_news_time": news_list[0].get("publish_time", "") if news_list else "",
                "sample_headlines": [n.get("title", "")[:80] for n in news_list[:3]],
            }],
            "data_sufficient": len(news_list) >= 3,
            "boundary_note": (
                "分析基于近期新闻的规则匹配，并结合你的投资画像上下文，不构成交易建议。"
                + ("新闻覆盖不足，结论仅供参考。" if len(news_list) < 3 else "")
            ),
        }

    @staticmethod
    def _evaluate_impact(
        news_list: List[Dict[str, Any]],
        holding: Dict[str, Any],
    ) -> tuple:
        """
        简单规则评估新闻对持仓的影响等级。
        返回 (impact_level, evidence_note)
        """
        if not news_list:
            return IMPACT_LOW, "无近期新闻覆盖，证据不足"

        count = len(news_list)

        # 统计情绪分布
        positive = sum(1 for n in news_list if n.get("sentiment") == "positive")
        negative = sum(1 for n in news_list if n.get("sentiment") == "negative")

        # 检查重要性
        high_importance = sum(
            1 for n in news_list if n.get("importance") == "high"
        )

        # 分级规则
        if high_importance >= 2 or (count >= 5 and abs(positive - negative) >= 3):
            level = IMPACT_HIGH
            note = f"近期有 {high_importance} 条高重要性新闻，情绪偏向{'正面' if positive > negative else '负面'}"
        elif high_importance >= 1 or count >= 3:
            level = IMPACT_MEDIUM
            note = f"近期 {count} 条新闻，{high_importance} 条高重要性"
        else:
            level = IMPACT_LOW
            note = f"近期仅 {count} 条新闻，影响有限"

        return level, note

    # ════════════════════════════════════════════════════════════
    # 3. 告警配置与模拟投递
    # ════════════════════════════════════════════════════════════

    async def get_alert_config(self, user_id: str) -> Dict[str, Any]:
        """获取用户的告警阈值配置"""
        db = await self._get_db()
        doc = await db["news_alert_configs"].find_one({"user_id": user_id})
        if doc:
            doc["_id"] = str(doc["_id"])
            return doc
        # 默认配置
        return {
            "user_id": user_id,
            "threshold": ALERT_THRESHOLD_MEDIUM,
            "updated_at": None,
        }

    async def update_alert_config(
        self, user_id: str, threshold: str
    ) -> Dict[str, Any]:
        """更新告警阈值配置"""
        if threshold not in (ALERT_THRESHOLD_LOW, ALERT_THRESHOLD_MEDIUM, ALERT_THRESHOLD_HIGH):
            raise ValueError(f"无效的告警阈值: {threshold}")

        db = await self._get_db()
        doc = {
            "user_id": user_id,
            "threshold": threshold,
            "updated_at": datetime.utcnow(),
        }
        await db["news_alert_configs"].update_one(
            {"user_id": user_id},
            {"$set": doc},
            upsert=True,
        )
        doc["updated_at"] = doc["updated_at"].isoformat()
        return doc

    async def simulate_alerts(
        self,
        user_id: str,
        impacts: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        根据持仓影响分析结果和用户告警阈值，生成模拟告警记录。
        包含去重逻辑：同一标的 24 小时内不重复告警。
        """
        config = await self.get_alert_config(user_id)
        threshold = config.get("threshold", ALERT_THRESHOLD_MEDIUM)

        # 确定哪些等级需要告警
        if threshold == ALERT_THRESHOLD_LOW:
            trigger_levels = {IMPACT_LOW, IMPACT_MEDIUM, IMPACT_HIGH}
        elif threshold == ALERT_THRESHOLD_MEDIUM:
            trigger_levels = {IMPACT_MEDIUM, IMPACT_HIGH}
        else:
            trigger_levels = {IMPACT_HIGH}

        db = await self._get_db()
        alerts_collection = db["news_alert_records"]
        now = datetime.utcnow()
        dedup_window = now - timedelta(hours=24)

        generated = []
        for impact in impacts:
            level = impact.get("impact_level", IMPACT_LOW)
            if level not in trigger_levels:
                continue

            stock_code = impact.get("stock_code", "")

            # 去重：24h 内同标的同等级不重复
            existing = await alerts_collection.find_one({
                "user_id": user_id,
                "stock_code": stock_code,
                "impact_level": level,
                "created_at": {"$gte": dedup_window},
            })
            if existing:
                continue

            alert_doc = {
                "user_id": user_id,
                "stock_code": stock_code,
                "stock_name": impact.get("stock_name", stock_code),
                "impact_level": level,
                "evidence_note": impact.get("evidence_note", ""),
                "channel": "simulated",  # 明确标记为模拟
                "status": "simulated",
                "trigger_reason": f"持仓新闻影响达到{level}等级",
                "created_at": now,
            }
            result = await alerts_collection.insert_one(alert_doc)
            alert_doc["_id"] = str(result.inserted_id)
            alert_doc["created_at"] = now.isoformat()
            generated.append(alert_doc)

        logger.info(f"📢 模拟告警生成 {len(generated)} 条 (threshold={threshold})")
        return generated

    async def get_alert_records(
        self,
        user_id: str,
        limit: int = 50,
        skip: int = 0,
    ) -> List[Dict[str, Any]]:
        """获取用户的告警记录列表"""
        db = await self._get_db()
        cursor = (
            db["news_alert_records"]
            .find({"user_id": user_id})
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        records = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            if isinstance(doc.get("created_at"), datetime):
                doc["created_at"] = doc["created_at"].isoformat()
            records.append(doc)
        return records


# ── 单例 ──────────────────────────────────────────────────────
_news_watch_service: Optional[NewsWatchService] = None


async def get_news_watch_service() -> NewsWatchService:
    global _news_watch_service
    if _news_watch_service is None:
        _news_watch_service = NewsWatchService()
    return _news_watch_service
