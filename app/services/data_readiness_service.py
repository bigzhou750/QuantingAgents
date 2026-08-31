"""
数据可用性服务

统一判断股票池、行情、历史行情、财务指标、指数数据的新鲜度和覆盖率，
为策略选股、体检和模拟提供数据质量闸门。
"""

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple

from app.core.config import get_settings
from app.core.database import get_mongo_db
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)


# ==================== 枚举与数据类 ====================

class DataCategory(str, Enum):
    """数据类别"""
    STOCK_POOL = "stock_pool"               # stock_basic_info
    QUOTES = "quotes"                       # market_quotes
    HISTORICAL_QUOTES = "historical_quotes" # stock_daily_quotes
    FINANCIAL_INDICATORS = "financial_indicators"  # stock_financial_data
    INDEX_DATA = "index_data"               # 指数日线数据


class FreshnessLevel(str, Enum):
    """新鲜度等级"""
    FRESH = "fresh"     # 在阈值内
    STALE = "stale"     # 超出阈值但有数据
    MISSING = "missing" # 无数据
    ERROR = "error"     # 上次同步失败


@dataclass
class CategoryStatus:
    """单个数据类别的状态"""
    category: str
    freshness: str
    source: Optional[str] = None
    updated_at: Optional[datetime] = None
    record_count: int = 0
    coverage_rate: float = 0.0
    error_summary: Optional[str] = None
    data_as_of: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # datetime → ISO string for JSON serialization
        for k in ("updated_at", "data_as_of"):
            if d.get(k) and isinstance(d[k], datetime):
                d[k] = d[k].isoformat()
        return d


@dataclass
class DataReadinessReport:
    """数据就绪报告"""
    overall_ready: bool = False
    categories: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    checked_at: Optional[datetime] = None
    gate_passed: bool = False
    gate_failures: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_ready": self.overall_ready,
            "categories": self.categories,
            "checked_at": self.checked_at.isoformat() if self.checked_at else None,
            "gate_passed": self.gate_passed,
            "gate_failures": self.gate_failures,
        }


# ==================== 服务 ====================

class DataReadinessService:
    """数据可用性服务"""

    COLLECTION = "data_readiness_status"

    # 各类别对应的 MongoDB 集合
    CATEGORY_COLLECTIONS = {
        DataCategory.STOCK_POOL: "stock_basic_info",
        DataCategory.QUOTES: "market_quotes",
        DataCategory.HISTORICAL_QUOTES: "stock_daily_quotes",
        DataCategory.FINANCIAL_INDICATORS: "stock_financial_data",
        DataCategory.INDEX_DATA: "stock_daily_quotes",  # 同集合，按 symbol 过滤
    }

    # 指数代码列表
    INDEX_CODES = ["000001", "399001", "399006"]

    def __init__(self):
        self._initialized = False
        self._last_report: Optional[DataReadinessReport] = None

    async def initialize(self):
        """初始化服务和索引"""
        if self._initialized:
            return
        db = get_mongo_db()
        await db[self.COLLECTION].create_index("checked_at", expireAfterSeconds=86400)
        self._initialized = True
        logger.info("DataReadinessService initialized")

    async def refresh(self) -> DataReadinessReport:
        """刷新所有数据类别状态并持久化"""
        settings = get_settings()
        report = DataReadinessReport(checked_at=now_tz())

        # 检查每个类别
        checkers = {
            DataCategory.STOCK_POOL: lambda: self._check_stock_pool(settings),
            DataCategory.QUOTES: lambda: self._check_quotes(settings),
            DataCategory.HISTORICAL_QUOTES: lambda: self._check_historical(settings),
            DataCategory.FINANCIAL_INDICATORS: lambda: self._check_financial(settings),
            DataCategory.INDEX_DATA: lambda: self._check_index(settings),
        }

        all_fresh = True
        for cat, checker in checkers.items():
            try:
                status = await checker()
            except Exception as e:
                logger.error(f"Error checking {cat.value}: {e}")
                status = CategoryStatus(
                    category=cat.value,
                    freshness=FreshnessLevel.ERROR.value,
                    error_summary=str(e)[:500],
                )
                all_fresh = False

            report.categories[cat.value] = status.to_dict()
            if status.freshness != FreshnessLevel.FRESH.value:
                all_fresh = False

        report.overall_ready = all_fresh
        report.gate_passed = all_fresh
        report.gate_failures = [
            f"{k}: {v['freshness']}"
            for k, v in report.categories.items()
            if v["freshness"] != FreshnessLevel.FRESH.value
        ]

        # 持久化
        await self._persist(report)
        self._last_report = report
        logger.info(
            f"Data readiness refreshed: ready={report.overall_ready}, "
            f"failures={report.gate_failures}"
        )
        return report

    async def get_report(self) -> DataReadinessReport:
        """获取最新的就绪报告（缓存或从DB读取）"""
        if self._last_report:
            return self._last_report

        db = get_mongo_db()
        doc = await db[self.COLLECTION].find_one(sort=[("checked_at", -1)])
        if not doc:
            # 从未刷新过，返回空报告
            return DataReadinessReport(checked_at=now_tz(), gate_failures=["尚未执行过数据就绪检查"])

        report = DataReadinessReport(
            overall_ready=doc.get("overall_ready", False),
            categories=doc.get("categories", {}),
            checked_at=doc.get("checked_at"),
            gate_passed=doc.get("gate_passed", False),
            gate_failures=doc.get("gate_failures", []),
        )
        self._last_report = report
        return report

    async def check_gate(
        self, required_categories: List[DataCategory]
    ) -> Tuple[bool, List[str]]:
        """检查指定类别是否满足数据闸门要求

        Returns:
            (passed, failure_reasons)
        """
        report = await self.get_report()
        failures = []
        for cat in required_categories:
            cat_status = report.categories.get(cat.value)
            if not cat_status:
                failures.append(f"{cat.value}: 无状态信息")
                continue
            freshness = cat_status.get("freshness", FreshnessLevel.MISSING.value)
            if freshness in (FreshnessLevel.MISSING.value, FreshnessLevel.ERROR.value):
                reason = cat_status.get("error_summary") or freshness
                failures.append(f"{cat.value}: {reason}")
            elif freshness == FreshnessLevel.STALE.value:
                # STALE 不算完全失败，但记录警告
                logger.warning(f"Data gate warning: {cat.value} is stale")

        return len(failures) == 0, failures

    # ==================== 内部检查方法 ====================

    async def _check_stock_pool(self, settings) -> CategoryStatus:
        """检查股票池新鲜度"""
        db = get_mongo_db()
        collection = db[self.CATEGORY_COLLECTIONS[DataCategory.STOCK_POOL]]

        count = await collection.count_documents({})
        if count == 0:
            return CategoryStatus(
                category=DataCategory.STOCK_POOL.value,
                freshness=FreshnessLevel.MISSING.value,
                record_count=0,
            )

        # 查最新更新时间
        latest = await collection.find_one(sort=[("updated_at", -1)], projection={"updated_at": 1})
        updated_at = latest.get("updated_at") if latest else None

        # 检查同步状态中的错误
        sync_doc = await db["sync_status"].find_one({"job": "stock_basics_multi_source"})
        source = None
        error_summary = None
        if sync_doc:
            source = sync_doc.get("data_sources_used", [None])[0] if sync_doc.get("data_sources_used") else None
            if sync_doc.get("status") == "failed":
                error_summary = sync_doc.get("message", "同步失败")[:200]

        # 判断新鲜度
        threshold = timedelta(hours=settings.DATA_READINESS_FRESHNESS_STOCK_POOL_HOURS)
        freshness = self._compute_freshness(updated_at, threshold)

        # 如果同步失败且数据已过期，标记为 ERROR 而非 STALE
        if error_summary and freshness == FreshnessLevel.STALE:
            freshness = FreshnessLevel.ERROR

        return CategoryStatus(
            category=DataCategory.STOCK_POOL.value,
            freshness=freshness.value,
            source=source,
            updated_at=updated_at,
            record_count=count,
            coverage_rate=min(count / 5000, 1.0),  # 以5000只A股为基准
            error_summary=error_summary,
        )

    async def _check_quotes(self, settings) -> CategoryStatus:
        """检查近实时行情新鲜度"""
        db = get_mongo_db()
        collection = db[self.CATEGORY_COLLECTIONS[DataCategory.QUOTES]]

        count = await collection.count_documents({})
        if count == 0:
            return CategoryStatus(
                category=DataCategory.QUOTES.value,
                freshness=FreshnessLevel.MISSING.value,
                record_count=0,
            )

        latest = await collection.find_one(sort=[("updated_at", -1)], projection={"updated_at": 1, "trade_date": 1})
        updated_at = latest.get("updated_at") if latest else None

        # 读取 quotes_ingestion_status 获取来源和错误
        ingestion_doc = await db["quotes_ingestion_status"].find_one({"job": "quotes_ingestion"})
        source = ingestion_doc.get("data_source") if ingestion_doc else None
        error_summary = None
        if ingestion_doc and not ingestion_doc.get("success", True):
            error_summary = ingestion_doc.get("error_message", "行情入库失败")[:200]

        threshold = timedelta(hours=settings.DATA_READINESS_FRESHNESS_QUOTES_HOURS)
        freshness = self._compute_freshness(updated_at, threshold)

        if error_summary and freshness != FreshnessLevel.FRESH:
            freshness = FreshnessLevel.ERROR

        return CategoryStatus(
            category=DataCategory.QUOTES.value,
            freshness=freshness.value,
            source=source,
            updated_at=updated_at,
            record_count=count,
            coverage_rate=min(count / 5000, 1.0),
            error_summary=error_summary,
        )

    async def _check_historical(self, settings) -> CategoryStatus:
        """检查历史行情新鲜度"""
        db = get_mongo_db()
        collection = db[self.CATEGORY_COLLECTIONS[DataCategory.HISTORICAL_QUOTES]]

        count = await collection.count_documents({})
        if count == 0:
            return CategoryStatus(
                category=DataCategory.HISTORICAL_QUOTES.value,
                freshness=FreshnessLevel.MISSING.value,
                record_count=0,
            )

        # 获取最近交易日期
        latest = await collection.find_one(
            sort=[("trade_date", -1)],
            projection={"trade_date": 1, "updated_at": 1},
        )
        trade_date_str = latest.get("trade_date") if latest else None
        updated_at = latest.get("updated_at") if latest else None

        # 尝试解析 trade_date 作为 data_as_of
        data_as_of = None
        if trade_date_str:
            try:
                data_as_of = datetime.strptime(str(trade_date_str), "%Y%m%d")
            except (ValueError, TypeError):
                try:
                    data_as_of = datetime.strptime(str(trade_date_str), "%Y-%m-%d")
                except (ValueError, TypeError):
                    pass

        # 计算覆盖率：有数据的 distinct symbol 数 / 股票池总数
        distinct_symbols = len(await collection.distinct("symbol"))
        pool_count = await db["stock_basic_info"].count_documents({})
        coverage = min(distinct_symbols / max(pool_count, 1), 1.0) if pool_count > 0 else 0.0

        threshold = timedelta(hours=settings.DATA_READINESS_FRESHNESS_HISTORICAL_HOURS)
        ref_time = data_as_of or updated_at
        freshness = self._compute_freshness(ref_time, threshold)

        return CategoryStatus(
            category=DataCategory.HISTORICAL_QUOTES.value,
            freshness=freshness.value,
            updated_at=updated_at,
            record_count=count,
            coverage_rate=coverage,
            data_as_of=data_as_of,
        )

    async def _check_financial(self, settings) -> CategoryStatus:
        """检查财务数据新鲜度"""
        db = get_mongo_db()
        collection = db[self.CATEGORY_COLLECTIONS[DataCategory.FINANCIAL_INDICATORS]]

        count = await collection.count_documents({})
        if count == 0:
            return CategoryStatus(
                category=DataCategory.FINANCIAL_INDICATORS.value,
                freshness=FreshnessLevel.MISSING.value,
                record_count=0,
            )

        latest = await collection.find_one(sort=[("updated_at", -1)], projection={"updated_at": 1})
        updated_at = latest.get("updated_at") if latest else None

        threshold = timedelta(hours=settings.DATA_READINESS_FRESHNESS_FINANCIAL_HOURS)
        freshness = self._compute_freshness(updated_at, threshold)

        return CategoryStatus(
            category=DataCategory.FINANCIAL_INDICATORS.value,
            freshness=freshness.value,
            updated_at=updated_at,
            record_count=count,
            coverage_rate=min(count / 5000, 1.0),
        )

    async def _check_index(self, settings) -> CategoryStatus:
        """检查指数数据新鲜度"""
        db = get_mongo_db()
        collection = db[self.CATEGORY_COLLECTIONS[DataCategory.INDEX_DATA]]

        # 只查指数代码
        query = {"symbol": {"$in": self.INDEX_CODES}}
        count = await collection.count_documents(query)

        if count == 0:
            return CategoryStatus(
                category=DataCategory.INDEX_DATA.value,
                freshness=FreshnessLevel.MISSING.value,
                record_count=0,
            )

        latest = await collection.find_one(
            query, sort=[("trade_date", -1)],
            projection={"trade_date": 1, "updated_at": 1},
        )
        trade_date_str = latest.get("trade_date") if latest else None
        updated_at = latest.get("updated_at") if latest else None

        data_as_of = None
        if trade_date_str:
            try:
                data_as_of = datetime.strptime(str(trade_date_str), "%Y%m%d")
            except (ValueError, TypeError):
                try:
                    data_as_of = datetime.strptime(str(trade_date_str), "%Y-%m-%d")
                except (ValueError, TypeError):
                    pass

        # 覆盖率：有数据的指数数 / 总指数数
        distinct_indices = len(await collection.distinct("symbol", query))
        coverage = distinct_indices / len(self.INDEX_CODES)

        threshold = timedelta(hours=settings.DATA_READINESS_FRESHNESS_INDEX_HOURS)
        ref_time = data_as_of or updated_at
        freshness = self._compute_freshness(ref_time, threshold)

        return CategoryStatus(
            category=DataCategory.INDEX_DATA.value,
            freshness=freshness.value,
            updated_at=updated_at,
            record_count=count,
            coverage_rate=coverage,
            data_as_of=data_as_of,
        )

    # ==================== 工具方法 ====================

    @staticmethod
    def _compute_freshness(updated_at: Optional[datetime], threshold: timedelta) -> FreshnessLevel:
        """根据更新时间和阈值判断新鲜度"""
        if updated_at is None:
            return FreshnessLevel.MISSING

        now = now_tz()
        # 处理 naive vs aware datetime
        if updated_at.tzinfo is None and now.tzinfo is not None:
            from datetime import timezone as tz_mod
            updated_at = updated_at.replace(tzinfo=tz_mod.utc)
        elif updated_at.tzinfo is not None and now.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=None)

        age = now - updated_at
        if age <= threshold:
            return FreshnessLevel.FRESH
        return FreshnessLevel.STALE

    async def _persist(self, report: DataReadinessReport):
        """持久化报告到 MongoDB"""
        db = get_mongo_db()
        doc = report.to_dict()
        doc["_id"] = None  # let MongoDB assign
        await db[self.COLLECTION].insert_one(doc)


# 模块级单例
_data_readiness_service: Optional[DataReadinessService] = None


async def get_data_readiness_service() -> DataReadinessService:
    """获取数据就绪服务单例"""
    global _data_readiness_service
    if _data_readiness_service is None:
        _data_readiness_service = DataReadinessService()
        await _data_readiness_service.initialize()
    return _data_readiness_service
