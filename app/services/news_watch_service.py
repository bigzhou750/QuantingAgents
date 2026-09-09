"""
新闻关注工作台服务
提供关注收集、持仓影响分析和模拟告警能力
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from bson import ObjectId

from app.core.database import get_mongo_db
from app.models.news_intelligence import HoldingImpactCard

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
IMPACT_CACHE_COLLECTION = "news_holdings_impact_cache"
IMPACT_CACHE_HOURS = 4


class NewsWatchService:
    """新闻关注工作台服务"""

    def __init__(self):
        self._db = None
        self._background_tasks: set = set()

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

    async def ignore_item(
        self,
        user_id: str,
        symbol: Optional[str] = None,
        news_id: Optional[str] = None,
        title: str = "",
        reason: str = "news_watch_ignore",
    ) -> Dict[str, Any]:
        """记录用户主动忽略的新闻，用于后续去重与噪声分析。"""
        db = await self._get_db()
        doc = {
            "user_id": user_id,
            "symbol": symbol,
            "news_id": news_id,
            "title": title,
            "reason": reason,
            "created_at": datetime.utcnow(),
        }
        result = await db["news_ignored_items"].insert_one(doc)
        doc["_id"] = str(result.inserted_id)
        logger.info("News ignored: user=%s, symbol=%s", user_id, symbol)
        return doc

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

        total_value = sum(
            float(h.get("position_value") or h.get("market_value") or 0)
            for h in holdings
        )

        for holding in holdings:
            impact = await self._analyze_holding_impact(
                user_id, holding, total_value, hours_back
            )
            if impact:
                impacts.append(impact)

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
        impact = await self._analyze_holding_impact(
            user_id, holding, 0, hours_back
        )

        return {
            "has_holdings": True,
            "holdings_count": 1,
            "hours_back": hours_back,
            "symbol": stock_code,
            "impacts": [impact] if impact else [],
            "data_sufficient": bool(impact and impact.get("news_count", 0) >= 3),
            "boundary_note": (
                "分析基于近期新闻的规则匹配，并结合你的投资画像上下文，不构成交易建议。"
                + (
                    "新闻覆盖不足，结论仅供参考。"
                    if not impact or impact.get("news_count", 0) < 3
                    else ""
                )
            ),
        }

    async def get_auto_holdings_impact(
        self,
        user_id: str,
        hours_back: int = 72,
    ) -> Dict[str, Any]:
        """读取缓存；缺失时当场分析，过期时返回旧结果并后台刷新。"""
        db = await self._get_db()
        cache = db[IMPACT_CACHE_COLLECTION]
        latest = await cache.find_one(
            {"user_id": user_id}, sort=[("created_at", -1)]
        )
        now = datetime.utcnow()

        if latest and latest.get("created_at"):
            age = now - latest["created_at"]
            if age.total_seconds() <= IMPACT_CACHE_HOURS * 3600:
                result = latest.get("result") or {}
                result.update({
                    "cached": True,
                    "refresh_state": "current",
                    "cached_at": latest["created_at"].isoformat(),
                })
                return result

            stale_result = dict(latest.get("result") or {})
            stale_result.update({
                "cached": True,
                "refresh_state": "refreshing",
                "cached_at": latest["created_at"].isoformat(),
            })
            self._schedule_background_refresh(user_id, hours_back)
            return stale_result

        result = await self.analyze_holdings_impact(
            user_id=user_id, hours_back=hours_back
        )
        result.update({"cached": False, "refresh_state": "current"})
        await self._persist_holdings_impact(user_id, result)
        return result

    async def _analyze_holding_impact(
        self,
        user_id: str,
        holding: Dict[str, Any],
        total_value: float,
        hours_back: int,
    ) -> Optional[Dict[str, Any]]:
        """为单个持仓生成多维影响评分卡，并保留直接/间接覆盖信息。"""
        stock_code = holding.get("stock_code") or holding.get("symbol", "")
        stock_name = holding.get("stock_name", stock_code)
        if not stock_code:
            return None

        news_list, direct_count, indirect_count, failure_summary = (
            await self._fetch_holding_news(user_id, stock_code, hours_back)
        )
        impact_level, evidence_note = self._evaluate_impact(news_list, holding)
        direction = self._infer_direction(news_list)
        holding_value = float(holding.get("position_value") or holding.get("market_value") or 0)
        exposure = round(holding_value / total_value, 4) if total_value > 0 else 0.0
        evidence_quality = (
            "weak"
            if len(news_list) < 3
            else "moderate" if len(news_list) < 5 else "strong"
        )
        impact_paths = [
            n.get("_via") for n in news_list if n.get("_via")
        ][:5]

        card = HoldingImpactCard(
            stock_code=stock_code,
            stock_name=stock_name,
            direction=direction,
            strength=int(impact_level == IMPACT_HIGH) * 4 + int(impact_level == IMPACT_MEDIUM) * 3,
            exposure=exposure,
            news_count=len(news_list),
            freshness=news_list[0].get("publish_time") if news_list else None,
            evidence_quality=evidence_quality,
            market_confirmation="未确认",
            risk_category=holding.get("risk_category", "general"),
            watch_indicators=["成交量", "公告", "行业指数"],
            is_direct=direct_count > 0,
            impact_paths=impact_paths,
            refresh_state=(
                "source_failure"
                if failure_summary and not news_list
                else "insufficient" if not news_list else "current"
            ),
            analysis_id=holding.get("analysis_id"),
        ).to_dict()
        card.update({
            "impact_level": impact_level,
            "evidence_note": evidence_note,
            "latest_news_time": (
                str(
                    news_list[0].get("publish_time")
                    or news_list[0].get("published_at")
                    or ""
                ).strip()
                if news_list else ""
            ),
            "sample_headlines": [
                n.get("title", "")[:80] for n in news_list[:3]
            ],
            "direct_count": direct_count,
            "indirect_count": indirect_count,
            "failure_summary": failure_summary,
        })
        return card

    async def _fetch_holding_news(
        self, user_id: str, stock_code: str, hours_back: int
    ) -> tuple:
        """先查直接新闻，不足时用聚合服务补充行业/概念/自选/热门兜底。"""
        direct_news = []
        try:
            from app.services.news_data_service import (
                get_news_data_service,
                NewsQueryParams,
            )
            news_service = await get_news_data_service()
            params = NewsQueryParams(
                symbol=stock_code,
                start_time=datetime.utcnow() - timedelta(hours=hours_back),
                limit=20,
                sort_by="publish_time",
                sort_order=-1,
            )
            direct_news = await news_service.query_news(params) or []
        except Exception as exc:
            logger.warning(f"Direct news fetch failed for {stock_code}: {exc}")

        if len(direct_news) >= 3:
            return direct_news, len(direct_news), 0, None

        try:
            from app.services.news_aggregator_service import get_news_aggregator_service
            aggregator = await get_news_aggregator_service()
            aggregated = await aggregator.aggregate(stock_code, user_id)
            news_list = aggregated.news_list or []
            if len(news_list) > len(direct_news):
                return (
                    news_list,
                    aggregated.direct_count,
                    aggregated.indirect_count,
                    aggregated.failure_summary,
                )
        except Exception as exc:
            logger.warning(f"Aggregated news fallback failed for {stock_code}: {exc}")

        return direct_news, len(direct_news), 0, None

    @staticmethod
    def _infer_direction(news_list: List[Dict[str, Any]]) -> str:
        positive = sum(1 for n in news_list if n.get("sentiment") == "positive")
        negative = sum(1 for n in news_list if n.get("sentiment") == "negative")
        if positive > negative:
            return "positive"
        if negative > positive:
            return "negative"
        return "neutral"

    def _schedule_background_refresh(self, user_id: str, hours_back: int) -> None:
        async def runner():
            try:
                await self._refresh_holdings_impact(user_id, hours_back)
            except Exception as exc:
                logger.warning("Background holdings impact refresh failed: %s", exc)

        task = asyncio.create_task(runner())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _refresh_holdings_impact(
        self, user_id: str, hours_back: int
    ) -> None:
        result = await self.analyze_holdings_impact(
            user_id=user_id, hours_back=hours_back
        )
        result.update({"cached": False, "refresh_state": "current"})
        await self._persist_holdings_impact(user_id, result)

    async def _persist_holdings_impact(
        self, user_id: str, result: Dict[str, Any]
    ) -> None:
        db = await self._get_db()
        await db[IMPACT_CACHE_COLLECTION].update_one(
            {"user_id": user_id},
            {"$set": {
                "user_id": user_id,
                "result": result,
                "created_at": datetime.utcnow(),
            }},
            upsert=True,
        )

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
