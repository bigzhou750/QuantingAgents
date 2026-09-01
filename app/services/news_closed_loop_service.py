"""
新闻闭环管理服务

告警状态机、观察任务桥接、复盘验证和闭环指标计算。
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from app.core.database import get_mongo_db
from app.models.news_intelligence import (
    AlertStatus,
    AlertAction,
    ReviewVerdict,
    ClosedLoopMetrics,
)
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)


class NewsClosedLoopService:
    """新闻闭环管理服务"""

    REVIEW_COLLECTION = "news_review_records"

    # 合法状态转换
    VALID_TRANSITIONS = {
        AlertStatus.PENDING.value: [
            AlertStatus.CONFIRMED.value,
            AlertStatus.IGNORED.value,
            AlertStatus.CONVERTED.value,
        ],
        AlertStatus.CONFIRMED.value: [AlertStatus.REVIEWED.value],
        AlertStatus.CONVERTED.value: [AlertStatus.REVIEWED.value],
        AlertStatus.IGNORED.value: [],
        AlertStatus.REVIEWED.value: [],
    }

    async def initialize(self):
        db = get_mongo_db()
        await db[self.REVIEW_COLLECTION].create_index(
            [("user_id", 1), ("observation_id", 1)]
        )
        logger.info("NewsClosedLoopService initialized")

    # ==================== 告警状态管理 ====================

    async def update_alert_status(
        self,
        alert_id: str,
        user_id: str,
        action: str,
        note: str = "",
    ) -> Dict[str, Any]:
        """更新告警状态"""
        db = get_mongo_db()
        coll = db["news_alert_records"]

        # 查找告警
        from bson import ObjectId
        try:
            oid = ObjectId(alert_id)
        except Exception:
            return {"error": "Invalid alert ID"}

        alert = await coll.find_one({"_id": oid, "user_id": user_id})
        if not alert:
            return {"error": "Alert not found"}

        current_status = alert.get("status", AlertStatus.PENDING.value)

        # 兼容旧的 "simulated" 状态
        if current_status == "simulated":
            current_status = AlertStatus.PENDING.value

        # 验证状态转换
        target_status = action  # action 即目标状态
        valid_targets = self.VALID_TRANSITIONS.get(current_status, [])
        if target_status not in valid_targets:
            return {
                "error": f"Cannot transition from {current_status} to {target_status}",
                "valid_actions": valid_targets,
            }

        # 执行转换
        update_data = {
            "status": target_status,
            "user_action": action,
            "action_time": now_tz(),
            "action_note": note,
        }
        await coll.update_one({"_id": oid}, {"$set": update_data})

        updated = await coll.find_one({"_id": oid})
        updated["_id"] = str(updated["_id"])
        if isinstance(updated.get("created_at"), datetime):
            updated["created_at"] = updated["created_at"].isoformat()
        if isinstance(updated.get("action_time"), datetime):
            updated["action_time"] = updated["action_time"].isoformat()

        logger.info(f"Alert {alert_id} status: {current_status} → {target_status}")
        return updated

    # ==================== 观察任务桥接 ====================

    async def create_observation_from_news(
        self,
        user_id: str,
        stock_code: str,
        stock_name: str = "",
        news_event_id: Optional[str] = None,
        analysis_id: Optional[str] = None,
        verification_indicators: Optional[List[str]] = None,
        user_notes: str = "",
    ) -> Dict[str, Any]:
        """从新闻分析创建观察任务（桥接到 observation_service）"""
        from app.services.personal_investment.observation_service import observation_service
        from app.models.observation import ObservationRecord, ObservationSource

        record = ObservationRecord(
            user_id=user_id,
            stock_code=stock_code,
            stock_name=stock_name,
            source_type=ObservationSource.NEWS.value,
            user_notes=user_notes,
            news_event_id=news_event_id,
            analysis_id=analysis_id,
            verification_indicators=verification_indicators or [],
        )

        result = await observation_service.add_observation(user_id, record)
        logger.info(f"Observation created from news: stock={stock_code}, event={news_event_id}")
        return result

    # ==================== 复盘 ====================

    async def trigger_review(
        self,
        observation_id: str,
        user_id: str,
        window_days: int = 7,
    ) -> Dict[str, Any]:
        """触发复盘验证"""
        from app.services.personal_investment.observation_service import observation_service

        obs = await observation_service.get_observation(observation_id, user_id)
        if not obs:
            return {"error": "Observation not found"}

        stock_code = obs.get("stock_code", "")

        # 获取分析时的预测方向
        analysis_result = {}
        db = get_mongo_db()
        analysis_id = obs.get("analysis_id") or obs.get("news_event_id")
        if analysis_id:
            analysis_doc = await db["news_analysis_results"].find_one(
                {"analysis_id": analysis_id},
            )
            if analysis_doc:
                analysis_result = analysis_doc.get("result", {})
            elif obs.get("news_event_id"):
                analysis_doc = await db["news_analysis_results"].find_one(
                    {"news_ids": obs["news_event_id"]},
                )
                if analysis_doc:
                    analysis_result = analysis_doc.get("result", {})

        predicted_direction = analysis_result.get("impact_direction", "neutral")

        # 查询价格、成交量和公告变化
        price_change = await self._get_price_change(stock_code, window_days)
        volume_change = await self._get_volume_change(stock_code, window_days)
        announcement_count = await self._get_announcement_count(
            stock_code, window_days
        )
        industry_change = await self._get_industry_change(stock_code, window_days)

        # 判定
        verdict = self._compute_verdict(predicted_direction, price_change)

        # 保存复盘记录
        review_doc = {
            "user_id": user_id,
            "observation_id": observation_id,
            "stock_code": stock_code,
            "window_days": window_days,
            "predicted_direction": predicted_direction,
            "actual_change_pct": price_change,
            "volume_change_pct": volume_change,
            "announcement_count": announcement_count,
            "industry_change_pct": industry_change,
            "verdict": verdict,
            "analysis_summary": analysis_result.get("event_summary", ""),
            "analysis_id": analysis_id,
            "created_at": now_tz(),
        }

        await db[self.REVIEW_COLLECTION].insert_one(review_doc)

        # 添加复盘备注到观察记录
        await observation_service.add_review_note(
            user_id=user_id,
            target_id=observation_id,
            content=f"复盘({window_days}日): 预测{predicted_direction}, 实际涨跌{price_change:+.2f}%, 判定: {verdict}",
        )

        review_doc.pop("_id", None)
        return review_doc

    async def get_review_summary(
        self, user_id: str
    ) -> Dict[str, Any]:
        """获取复盘汇总"""
        db = get_mongo_db()
        total = await db[self.REVIEW_COLLECTION].count_documents({"user_id": user_id})

        verified = await db[self.REVIEW_COLLECTION].count_documents({
            "user_id": user_id, "verdict": ReviewVerdict.VERIFIED.value,
        })
        contradicted = await db[self.REVIEW_COLLECTION].count_documents({
            "user_id": user_id, "verdict": ReviewVerdict.CONTRADICTED.value,
        })

        recent_cursor = db[self.REVIEW_COLLECTION].find(
            {"user_id": user_id}
        ).sort("created_at", -1).limit(5)
        recent = []
        async for doc in recent_cursor:
            doc.pop("_id", None)
            if isinstance(doc.get("created_at"), datetime):
                doc["created_at"] = doc["created_at"].isoformat()
            recent.append(doc)

        return {
            "total_reviews": total,
            "verified_count": verified,
            "contradicted_count": contradicted,
            "verification_rate": verified / max(total, 1),
            "recent": recent,
        }

    # ==================== 闭环指标 ====================

    async def get_metrics(self, user_id: str) -> ClosedLoopMetrics:
        """计算闭环指标"""
        db = get_mongo_db()

        # 新闻总数
        total_news = await db["stock_news"].count_documents({})

        # 分析总数 & 成功率
        total_analyses = await db["news_analysis_results"].count_documents({})
        degraded = await db["news_analysis_results"].count_documents({"degraded": True})
        analysis_success_rate = (total_analyses - degraded) / max(total_analyses, 1)

        # 告警总数 & 命中率(确认+转观察 / 总告警)
        total_alerts = await db["news_alert_records"].count_documents({"user_id": user_id})
        confirmed_alerts = await db["news_alert_records"].count_documents({
            "user_id": user_id,
            "status": {"$in": [AlertStatus.CONFIRMED.value, AlertStatus.CONVERTED.value]},
        })
        ignored_alerts = await db["news_alert_records"].count_documents({
            "user_id": user_id,
            "status": AlertStatus.IGNORED.value,
        })
        alert_hit_rate = confirmed_alerts / max(total_alerts, 1)
        noise_rate = ignored_alerts / max(total_alerts, 1)

        # 观察任务
        total_tasks = await db["investment_observations"].count_documents({
            "user_id": user_id, "source_type": "news",
        })
        completed_tasks = await db["investment_observations"].count_documents({
            "user_id": user_id, "source_type": "news",
            "status": {"$in": ["reviewed"]},
        })
        task_completion_rate = completed_tasks / max(total_tasks, 1)

        # 复盘验证率
        total_reviews = await db[self.REVIEW_COLLECTION].count_documents({"user_id": user_id})
        verified_reviews = await db[self.REVIEW_COLLECTION].count_documents({
            "user_id": user_id, "verdict": ReviewVerdict.VERIFIED.value,
        })
        review_verification_rate = verified_reviews / max(total_reviews, 1)

        # 覆盖率（有新闻的标的数 / 总关注标的数）
        watched_symbols = await db["investment_observations"].distinct(
            "stock_code", {"user_id": user_id, "status": "active"}
        )
        covered = 0
        for sym in watched_symbols:
            count = await db["stock_news"].count_documents({"symbol": sym})
            if count > 0:
                covered += 1
        coverage_rate = covered / max(len(watched_symbols), 1)

        return ClosedLoopMetrics(
            coverage_rate=coverage_rate,
            analysis_success_rate=analysis_success_rate,
            alert_hit_rate=alert_hit_rate,
            task_completion_rate=task_completion_rate,
            review_verification_rate=review_verification_rate,
            noise_rate=noise_rate,
            total_news=total_news,
            total_analyses=total_analyses,
            total_alerts=total_alerts,
            total_tasks=total_tasks,
            total_reviews=total_reviews,
        )

    # ==================== 内部方法 ====================

    async def _get_price_change(self, stock_code: str, days: int) -> float:
        """获取近N日价格变化百分比"""
        try:
            db = get_mongo_db()
            end = now_tz()
            start = end - timedelta(days=days)

            cursor = db["stock_daily_quotes"].find({
                "symbol": stock_code,
            }).sort("trade_date", -1).limit(days + 5)

            prices = []
            async for doc in cursor:
                close = doc.get("close")
                if close:
                    prices.append(float(close))

            if len(prices) >= 2:
                return (prices[0] - prices[-1]) / prices[-1] * 100
            return 0.0
        except Exception as e:
            logger.warning(f"Price change calc failed for {stock_code}: {e}")
            return 0.0

    async def _get_volume_change(self, stock_code: str, days: int) -> float:
        """获取复盘窗口成交量变化百分比"""
        try:
            db = get_mongo_db()
            cursor = db["stock_daily_quotes"].find({
                "symbol": stock_code,
                "volume": {"$gt": 0},
            }).sort("trade_date", -1).limit(days + 5)
            volumes = []
            async for doc in cursor:
                volume = doc.get("volume") or doc.get("vol")
                if volume:
                    volumes.append(float(volume))
            if len(volumes) >= 2 and volumes[-1] > 0:
                return round((volumes[0] - volumes[-1]) / volumes[-1] * 100, 4)
            return 0.0
        except Exception as exc:
            logger.warning("Volume change calc failed: %s", exc)
            return 0.0

    async def _get_announcement_count(
        self, stock_code: str, days: int
    ) -> int:
        """统计复盘窗口内公告/公司新闻条数"""
        try:
            db = get_mongo_db()
            since = now_tz() - timedelta(days=days)
            return await db["stock_news"].count_documents({
                "symbol": stock_code,
                "$or": [
                    {"category": {"$in": ["公告", "announcement"]}},
                    {"news_type": "announcement"},
                ],
            })
        except Exception as exc:
            logger.warning("Announcement count failed: %s", exc)
            return 0

    async def _get_industry_change(
        self, stock_code: str, days: int
    ) -> Optional[float]:
        """若行业指数未接入，返回 None 避免伪造行业表现。"""
        try:
            db = get_mongo_db()
            stock = await db["stock_basic_info"].find_one({
                "$or": [{"code": stock_code}, {"symbol": stock_code}],
            })
            industry = (stock or {}).get("industry", "")
            if not industry:
                return None
            return None
        except Exception as exc:
            logger.warning("Industry change calc failed: %s", exc)
            return None

    def _compute_verdict(
        self, predicted_direction: str, actual_change_pct: float
    ) -> str:
        """根据预测方向和实际涨跌计算复盘判定"""
        threshold = 1.0  # 1%以上才算明确方向

        if abs(actual_change_pct) < threshold:
            return ReviewVerdict.UNVERIFIED.value

        actual_positive = actual_change_pct > 0

        if predicted_direction == "positive" and actual_positive:
            return ReviewVerdict.VERIFIED.value
        elif predicted_direction == "negative" and not actual_positive:
            return ReviewVerdict.VERIFIED.value
        elif predicted_direction == "neutral":
            return ReviewVerdict.UNVERIFIED.value
        else:
            return ReviewVerdict.CONTRADICTED.value


# 模块级单例
_closed_loop: Optional[NewsClosedLoopService] = None


async def get_news_closed_loop_service() -> NewsClosedLoopService:
    global _closed_loop
    if _closed_loop is None:
        _closed_loop = NewsClosedLoopService()
        await _closed_loop.initialize()
    return _closed_loop
