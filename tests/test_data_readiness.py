"""
数据可用性服务测试

覆盖:
- DataCategory / FreshnessLevel 枚举
- CategoryStatus / DataReadinessReport 序列化
- DataReadinessService 核心逻辑（mock Mongo）
- 正常、缺失、过期、数据源失败场景
- check_gate 通过/失败
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta, timezone

from app.services.data_readiness_service import (
    DataCategory,
    FreshnessLevel,
    CategoryStatus,
    DataReadinessReport,
    DataReadinessService,
)


# ==================== 枚举与数据类测试 ====================

class TestDataEnums:
    def test_data_category_values(self):
        assert DataCategory.STOCK_POOL.value == "stock_pool"
        assert DataCategory.QUOTES.value == "quotes"
        assert DataCategory.HISTORICAL_QUOTES.value == "historical_quotes"
        assert DataCategory.FINANCIAL_INDICATORS.value == "financial_indicators"
        assert DataCategory.INDEX_DATA.value == "index_data"

    def test_freshness_level_values(self):
        assert FreshnessLevel.FRESH.value == "fresh"
        assert FreshnessLevel.STALE.value == "stale"
        assert FreshnessLevel.MISSING.value == "missing"
        assert FreshnessLevel.ERROR.value == "error"


class TestDataClasses:
    def test_category_status_to_dict(self):
        status = CategoryStatus(
            category="stock_pool",
            freshness="fresh",
            source="tushare",
            updated_at=datetime(2026, 8, 31, 10, 0, 0),
            record_count=5000,
            coverage_rate=0.95,
        )
        d = status.to_dict()
        assert d["category"] == "stock_pool"
        assert d["freshness"] == "fresh"
        assert d["record_count"] == 5000
        assert isinstance(d["updated_at"], str)  # ISO format

    def test_report_to_dict(self):
        report = DataReadinessReport(
            overall_ready=True,
            checked_at=datetime(2026, 8, 31, 12, 0, 0),
            gate_passed=True,
            gate_failures=[],
        )
        d = report.to_dict()
        assert d["overall_ready"] is True
        assert d["gate_passed"] is True
        assert d["gate_failures"] == []
        assert isinstance(d["checked_at"], str)

    def test_report_with_failures(self):
        report = DataReadinessReport(
            overall_ready=False,
            gate_passed=False,
            gate_failures=["stock_pool: missing", "quotes: error"],
        )
        d = report.to_dict()
        assert len(d["gate_failures"]) == 2


# ==================== Service 测试（mock Mongo）====================

class TestDataReadinessService:
    @pytest.fixture
    def service(self):
        return DataReadinessService()

    def _make_mock_db(self, collections_data: dict):
        """构建 mock MongoDB 数据库

        Args:
            collections_data: {collection_name: {"count": int, "latest": dict|None, ...}}
        """
        mock_db = MagicMock()

        def getitem(name):
            coll = AsyncMock()
            data = collections_data.get(name, {})

            coll.count_documents = AsyncMock(return_value=data.get("count", 0))
            coll.find_one = AsyncMock(return_value=data.get("latest"))
            coll.distinct = AsyncMock(return_value=data.get("distinct_symbols", []))
            coll.insert_one = AsyncMock()

            return coll

        mock_db.__getitem__ = MagicMock(side_effect=getitem)
        return mock_db

    @pytest.mark.asyncio
    async def test_check_stock_pool_missing(self, service):
        """股票池为空时应返回 MISSING"""
        mock_db = self._make_mock_db({
            "stock_basic_info": {"count": 0},
            "sync_status": {"latest": None},
        })

        with patch("app.services.data_readiness_service.get_mongo_db", return_value=mock_db):
            settings = MagicMock()
            settings.DATA_READINESS_FRESHNESS_STOCK_POOL_HOURS = 48
            status = await service._check_stock_pool(settings)

        assert status.freshness == FreshnessLevel.MISSING.value
        assert status.record_count == 0

    @pytest.mark.asyncio
    async def test_check_stock_pool_fresh(self, service):
        """有近期数据时应返回 FRESH"""
        now = datetime.now(timezone.utc)
        mock_db = self._make_mock_db({
            "stock_basic_info": {
                "count": 4800,
                "latest": {"updated_at": now - timedelta(hours=1)},
            },
            "sync_status": {"latest": {"status": "success"}},
        })

        with patch("app.services.data_readiness_service.get_mongo_db", return_value=mock_db):
            settings = MagicMock()
            settings.DATA_READINESS_FRESHNESS_STOCK_POOL_HOURS = 48
            status = await service._check_stock_pool(settings)

        assert status.freshness == FreshnessLevel.FRESH.value
        assert status.record_count == 4800
        assert status.coverage_rate > 0

    @pytest.mark.asyncio
    async def test_check_stock_pool_stale(self, service):
        """超出阈值应返回 STALE"""
        old_time = datetime.now(timezone.utc) - timedelta(hours=72)
        mock_db = self._make_mock_db({
            "stock_basic_info": {
                "count": 4800,
                "latest": {"updated_at": old_time},
            },
            "sync_status": {"latest": {"status": "success"}},
        })

        with patch("app.services.data_readiness_service.get_mongo_db", return_value=mock_db):
            settings = MagicMock()
            settings.DATA_READINESS_FRESHNESS_STOCK_POOL_HOURS = 48
            status = await service._check_stock_pool(settings)

        assert status.freshness == FreshnessLevel.STALE.value

    @pytest.mark.asyncio
    async def test_check_stock_pool_sync_failed(self, service):
        """同步失败且有旧数据时应返回 ERROR"""
        old_time = datetime.now(timezone.utc) - timedelta(hours=72)
        mock_db = self._make_mock_db({
            "stock_basic_info": {
                "count": 4800,
                "latest": {"updated_at": old_time},
            },
            "sync_status": {
                "latest": {"status": "failed", "message": "Tushare API 限流"},
            },
        })

        with patch("app.services.data_readiness_service.get_mongo_db", return_value=mock_db):
            settings = MagicMock()
            settings.DATA_READINESS_FRESHNESS_STOCK_POOL_HOURS = 48
            status = await service._check_stock_pool(settings)

        assert status.freshness == FreshnessLevel.ERROR.value
        assert "限流" in status.error_summary

    @pytest.mark.asyncio
    async def test_check_quotes_missing(self, service):
        mock_db = self._make_mock_db({
            "market_quotes": {"count": 0},
            "quotes_ingestion_status": {"latest": None},
        })

        with patch("app.services.data_readiness_service.get_mongo_db", return_value=mock_db):
            settings = MagicMock()
            settings.DATA_READINESS_FRESHNESS_QUOTES_HOURS = 2
            status = await service._check_quotes(settings)

        assert status.freshness == FreshnessLevel.MISSING.value

    @pytest.mark.asyncio
    async def test_check_index_coverage(self, service):
        """指数覆盖率计算"""
        now = datetime.now(timezone.utc)
        mock_db = self._make_mock_db({
            "stock_daily_quotes": {
                "count": 300,
                "latest": {"trade_date": "20260830", "updated_at": now - timedelta(hours=1)},
                "distinct_symbols": ["000001", "399001"],  # 只有2个指数
            },
        })

        with patch("app.services.data_readiness_service.get_mongo_db", return_value=mock_db):
            settings = MagicMock()
            settings.DATA_READINESS_FRESHNESS_INDEX_HOURS = 26
            status = await service._check_index(settings)

        assert status.coverage_rate == pytest.approx(2 / 3, abs=0.01)
        assert status.data_as_of is not None

    @pytest.mark.asyncio
    async def test_check_gate_pass(self, service):
        """所有类别就绪时闸门通过"""
        now = datetime.now(timezone.utc)
        report = DataReadinessReport(
            overall_ready=True,
            checked_at=now,
            gate_passed=True,
            categories={
                "stock_pool": {"freshness": "fresh", "record_count": 5000},
                "quotes": {"freshness": "fresh", "record_count": 4500},
            },
        )
        service._last_report = report

        passed, failures = await service.check_gate([DataCategory.STOCK_POOL, DataCategory.QUOTES])
        assert passed is True
        assert len(failures) == 0

    @pytest.mark.asyncio
    async def test_check_gate_fail(self, service):
        """有类别缺失时闸门不通过"""
        report = DataReadinessReport(
            overall_ready=False,
            checked_at=datetime.now(timezone.utc),
            gate_passed=False,
            categories={
                "stock_pool": {"freshness": "missing", "record_count": 0},
                "quotes": {"freshness": "fresh", "record_count": 4500},
            },
        )
        service._last_report = report

        passed, failures = await service.check_gate([DataCategory.STOCK_POOL, DataCategory.QUOTES])
        assert passed is False
        assert len(failures) == 1
        assert "stock_pool" in failures[0]

    @pytest.mark.asyncio
    async def test_compute_freshness_none(self, service):
        result = DataReadinessService._compute_freshness(None, timedelta(hours=1))
        assert result == FreshnessLevel.MISSING

    @pytest.mark.asyncio
    async def test_compute_freshness_fresh(self, service):
        recent = datetime.now(timezone.utc) - timedelta(minutes=30)
        result = DataReadinessService._compute_freshness(recent, timedelta(hours=1))
        assert result == FreshnessLevel.FRESH

    @pytest.mark.asyncio
    async def test_compute_freshness_stale(self, service):
        old = datetime.now(timezone.utc) - timedelta(hours=3)
        result = DataReadinessService._compute_freshness(old, timedelta(hours=1))
        assert result == FreshnessLevel.STALE
