"""
新闻聚合服务

统一调用多源新闻接口，提供确定性降级链、来源状态追踪、去重和轻量事件聚类。
解决"新闻源失败被吞成0条"的核心问题。
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from difflib import SequenceMatcher

from app.core.database import get_mongo_db
from app.models.news_intelligence import (
    NewsSourceStatus,
    SourceStatusEntry,
    AggregatedNewsResult,
)
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)


class NewsAggregatorService:
    """新闻聚合服务"""

    HEALTH_COLLECTION = "news_source_health_log"

    # 降级时间窗口
    FALLBACK_WINDOWS = [
        ("72h", timedelta(hours=72)),
        ("7d", timedelta(days=7)),
        ("30d", timedelta(days=30)),
    ]

    async def initialize(self):
        db = get_mongo_db()
        await db[self.HEALTH_COLLECTION].create_index("checked_at", expireAfterSeconds=86400)
        logger.info("NewsAggregatorService initialized")

    async def aggregate(
        self,
        symbol: str,
        user_id: Optional[str] = None,
    ) -> AggregatedNewsResult:
        """聚合新闻，带完整降级链"""
        result = AggregatedNewsResult()
        all_news: List[Dict[str, Any]] = []

        # Step 1-3: 直接查询，逐步扩大时间窗口
        for window_name, window_delta in self.FALLBACK_WINDOWS:
            step_name = f"direct_{symbol}_{window_name}"
            news, status = await self._fetch_news(symbol, window_delta)
            result.source_statuses.append(status.__dict__ if hasattr(status, '__dict__') else {
                "source_name": f"stock_news_{window_name}",
                "status": status.status if isinstance(status, SourceStatusEntry) else str(status),
                "count": len(news),
            })
            result.fallback_steps.append(step_name)

            if news:
                all_news.extend(news)
                result.direct_count += len(news)
                # 如果72h内有足够新闻，不再继续扩大窗口
                if window_name == "72h" and len(news) >= 3:
                    break

        # Step 4: 行业/概念新闻（间接）
        if len(all_news) < 3:
            industry_news = await self._fetch_industry_news(symbol)
            if industry_news:
                all_news.extend(industry_news)
                result.indirect_count += len(industry_news)
                result.fallback_steps.append(f"industry_{symbol}")

        # Step 5: 用户自选/持仓相关新闻（间接）
        if user_id and len(all_news) < 3:
            user_news = await self._fetch_user_related_news(user_id, symbol)
            if user_news:
                all_news.extend(user_news)
                result.indirect_count += len(user_news)
                result.fallback_steps.append("user_related")

        # Step 6: 热门标的兜底
        if len(all_news) < 2:
            hot_news = await self._fetch_hot_news()
            if hot_news:
                all_news.extend(hot_news)
                result.indirect_count += len(hot_news)
                result.fallback_steps.append("hot_symbols_fallback")

        # 去重 + 事件聚类
        deduped = self._deduplicate(all_news)
        result.news_list = deduped
        result.event_clusters = self.cluster_news_items(deduped)

        # 新鲜度
        if deduped:
            newest = max(
                (n.get("published_at") or n.get("pub_date") or "")
                for n in deduped
            )
            result.freshness = str(newest) if newest else None

        # 失败摘要
        failed_sources = [
            s for s in result.source_statuses
            if s.get("status") in (NewsSourceStatus.FAILED.value, NewsSourceStatus.RATE_LIMITED.value)
        ]
        if failed_sources:
            names = [s.get("source_name", "?") for s in failed_sources]
            result.failure_summary = f"以下来源异常: {', '.join(names)}"

        # 持久化健康日志
        await self._log_health(symbol, result)

        return result

    async def get_source_coverage(self) -> Dict[str, Any]:
        """获取来源覆盖调试信息"""
        db = get_mongo_db()
        latest = await db[self.HEALTH_COLLECTION].find_one(sort=[("checked_at", -1)])
        if not latest:
            return {"message": "尚无覆盖记录", "sources": []}
        latest.pop("_id", None)
        return latest

    # ==================== 内部方法 ====================

    async def _fetch_news(
        self, symbol: str, window: timedelta
    ) -> Tuple[List[Dict[str, Any]], SourceStatusEntry]:
        """从 news_data_service 获取新闻，显式区分 empty vs failed"""
        source_name = f"stock_news_{symbol}"
        start_time = time.monotonic()

        try:
            from app.services.news_data_service import NewsDataService
            service = NewsDataService()

            end_date = now_tz()
            start_date = end_date - window

            params = {
                "symbol": symbol,
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d"),
                "limit": 50,
            }
            news_list = await service.query_news(params)
            elapsed = int((time.monotonic() - start_time) * 1000)

            if news_list:
                return news_list, SourceStatusEntry(
                    source_name=source_name,
                    status=NewsSourceStatus.SUCCESS.value,
                    count=len(news_list),
                    response_time_ms=elapsed,
                )
            else:
                return [], SourceStatusEntry(
                    source_name=source_name,
                    status=NewsSourceStatus.EMPTY.value,
                    count=0,
                    response_time_ms=elapsed,
                )

        except Exception as e:
            elapsed = int((time.monotonic() - start_time) * 1000)
            error_msg = str(e)[:200]
            logger.warning(f"News fetch failed for {symbol}: {error_msg}")

            # 区分限流/鉴权/其他
            status = NewsSourceStatus.FAILED
            if "rate" in error_msg.lower() or "429" in error_msg:
                status = NewsSourceStatus.RATE_LIMITED
            elif "auth" in error_msg.lower() or "401" in error_msg or "403" in error_msg:
                status = NewsSourceStatus.AUTH_FAILED

            return [], SourceStatusEntry(
                source_name=source_name,
                status=status.value,
                count=0,
                error_message=error_msg,
                response_time_ms=elapsed,
            )

    async def _fetch_industry_news(self, symbol: str) -> List[Dict[str, Any]]:
        """通过行业获取间接新闻"""
        try:
            db = get_mongo_db()
            stock_info = await db["stock_basic_info"].find_one({"symbol": symbol})
            if not stock_info:
                return []
            industry = stock_info.get("industry", "")
            if not industry:
                return []
            # 用行业关键词搜索新闻
            from app.services.news_data_service import NewsDataService
            service = NewsDataService()
            results = await service.search_news(industry, limit=10)
            # 标记为间接
            for item in results:
                item["_indirect"] = True
                item["_via"] = f"industry:{industry}"
            return results
        except Exception as e:
            logger.warning(f"Industry news fetch failed for {symbol}: {e}")
            return []

    async def _fetch_user_related_news(
        self, user_id: str, exclude_symbol: str
    ) -> List[Dict[str, Any]]:
        """获取用户自选/持仓相关新闻"""
        try:
            db = get_mongo_db()
            # 查自选股
            user_doc = await db["users"].find_one({"_id": user_id}, projection={"favorites": 1})
            symbols = []
            if user_doc and user_doc.get("favorites"):
                for fav in user_doc["favorites"]:
                    code = fav.get("stock_code", "")
                    if code and code != exclude_symbol:
                        symbols.append(code)

            # 查模拟持仓
            positions = db["paper_positions"].find(
                {"user_id": user_id, "quantity": {"$gt": 0}},
                projection={"code": 1},
            ).limit(5)
            async for pos in positions:
                code = pos.get("code", "")
                if code and code != exclude_symbol and code not in symbols:
                    symbols.append(code)

            if not symbols:
                return []

            # 取前3个相关标的的新闻
            all_news = []
            for sym in symbols[:3]:
                news, _ = await self._fetch_news(sym, timedelta(hours=72))
                for item in news:
                    item["_indirect"] = True
                    item["_via"] = f"user_related:{sym}"
                all_news.extend(news)

            return all_news[:15]
        except Exception as e:
            logger.warning(f"User related news fetch failed: {e}")
            return []

    async def _fetch_hot_news(self) -> List[Dict[str, Any]]:
        """获取热门标的兜底新闻"""
        try:
            hot_symbols = ["000001", "600519", "300750"]
            all_news = []
            for sym in hot_symbols:
                news, _ = await self._fetch_news(sym, timedelta(hours=72))
                for item in news:
                    item["_fallback"] = True
                    item["_via"] = f"hot:{sym}"
                all_news.extend(news)
            return all_news[:10]
        except Exception as e:
            logger.warning(f"Hot news fetch failed: {e}")
            return []

    def _deduplicate(self, news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """去重：URL精确匹配 + 标题相似度 > 0.8"""
        seen_urls = set()
        seen_titles = []
        result = []

        for item in news_list:
            url = item.get("url", "")
            title = item.get("title", "")

            # URL 精确去重
            if url and url in seen_urls:
                continue

            # 标题相似度去重
            is_dup = False
            for prev_title in seen_titles:
                ratio = SequenceMatcher(None, title, prev_title).ratio()
                if ratio > 0.8:
                    is_dup = True
                    break

            if is_dup:
                continue

            if url:
                seen_urls.add(url)
            if title:
                seen_titles.append(title)
            result.append(item)

        return result

    @staticmethod
    def _event_time(value: Any) -> Optional[datetime]:
        """把新闻常见时间格式转成可比较时间。"""
        if not value:
            return None
        text = str(value).strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            pass
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(text[:19], fmt)
            except ValueError:
                continue
        try:
            return datetime.strptime(text[:8], "%Y%m%d")
        except ValueError:
            return None

    @classmethod
    def cluster_news_items(
        cls,
        news_items: List[Dict[str, Any]],
        window_hours: int = 24,
        similarity_threshold: float = 0.6,
    ) -> List[Dict[str, Any]]:
        """轻量事件聚类：URL/标题相似度 + 同一发布时间窗口。"""
        clusters: List[Dict[str, Any]] = []

        for item in news_items:
            title = item.get("title", "")
            url = item.get("url", "")
            pub_time = cls._event_time(
                item.get("published_at") or item.get("publish_time")
                or item.get("pub_date") or item.get("time")
            )

            target_cluster = None
            for cluster in clusters:
                representative = cluster["items"][0]
                rep_time = cls._event_time(
                    representative.get("published_at")
                    or representative.get("publish_time")
                    or representative.get("pub_date") or representative.get("time")
                )
                same_url = url and url == representative.get("url")
                same_title = title and title == representative.get("title")
                same_window = (
                    pub_time
                    and rep_time
                    and abs((pub_time - rep_time).total_seconds()) <= window_hours * 3600
                )
                if same_url or (
                    same_title
                    and (same_window or not pub_time or not rep_time)
                ):
                    target_cluster = cluster
                    break

                similar_title = (
                    title
                    and representative.get("title")
                    and SequenceMatcher(None, title, representative["title"]).ratio()
                    >= similarity_threshold
                )
                if similar_title and (same_window or not pub_time or not rep_time):
                    target_cluster = cluster
                    break

            if target_cluster is None:
                target_cluster = {
                    "cluster_id": f"event_{len(clusters) + 1}",
                    "title": title,
                    "count": 0,
                    "published_at_min": None,
                    "published_at_max": None,
                    "symbols": [],
                    "urls": [],
                    "items": [],
                }
                clusters.append(target_cluster)

            target_cluster["count"] += 1
            target_cluster.setdefault("title", title or target_cluster.get("title", ""))
            if pub_time:
                current_min = target_cluster.get("published_at_min")
                current_max = target_cluster.get("published_at_max")
                target_cluster["published_at_min"] = min(pub_time, current_min) if current_min else pub_time
                target_cluster["published_at_max"] = max(pub_time, current_max) if current_max else pub_time
            if item.get("symbol"):
                target_cluster["symbols"].append(item["symbol"])
            if url:
                target_cluster["urls"].append(url)
            target_cluster["items"].append({
                "_id": item.get("_id", ""),
                "news_id": item.get("news_id", ""),
                "title": title,
                "symbol": item.get("symbol", item.get("stock_code", "")),
                "url": url,
                "published_at": (
                    item.get("published_at")
                    or item.get("publish_time")
                    or item.get("pub_date") or item.get("time")
                ),
            })

        for cluster in clusters:
            if cluster.get("published_at_min"):
                cluster["published_at_min"] = cluster["published_at_min"].isoformat()
            if cluster.get("published_at_max"):
                cluster["published_at_max"] = cluster["published_at_max"].isoformat()

        return clusters

    async def _log_health(self, symbol: str, result: AggregatedNewsResult):
        """持久化来源健康日志"""
        try:
            db = get_mongo_db()
            doc = {
                "symbol": symbol,
                "checked_at": now_tz(),
                "total_count": len(result.news_list),
                "direct_count": result.direct_count,
                "indirect_count": result.indirect_count,
                "source_statuses": result.source_statuses,
                "fallback_steps": result.fallback_steps,
                "failure_summary": result.failure_summary,
                "freshness": result.freshness,
            }
            await db[self.HEALTH_COLLECTION].insert_one(doc)
        except Exception as e:
            logger.warning(f"Failed to log health: {e}")


# 模块级单例
_news_aggregator: Optional[NewsAggregatorService] = None


async def get_news_aggregator_service() -> NewsAggregatorService:
    global _news_aggregator
    if _news_aggregator is None:
        _news_aggregator = NewsAggregatorService()
        await _news_aggregator.initialize()
    return _news_aggregator
