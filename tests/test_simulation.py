"""
策略历史模拟服务测试

覆盖:
- 累计收益率计算
- 最大回撤计算
- 夏普比率计算
- 覆盖率与数据不足判定
- 调仓日期生成
- 空股票池处理
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.simulation_service import (
    SimulationConfig,
    SimulationResult,
    SimulationService,
)


# ==================== 纯数学函数测试（无需DB）====================

class TestSimulationMath:
    """测试纯数学计算函数"""

    def test_cumulative_return_simple(self):
        equity = [100.0, 110.0, 105.0, 115.0]
        result = SimulationService._compute_cumulative_return(equity)
        assert abs(result - 0.15) < 1e-6

    def test_cumulative_return_no_change(self):
        equity = [100.0, 100.0, 100.0]
        result = SimulationService._compute_cumulative_return(equity)
        assert result == 0.0

    def test_cumulative_return_negative(self):
        equity = [100.0, 90.0, 80.0]
        result = SimulationService._compute_cumulative_return(equity)
        assert abs(result - (-0.20)) < 1e-6

    def test_cumulative_return_empty(self):
        assert SimulationService._compute_cumulative_return([]) == 0.0
        assert SimulationService._compute_cumulative_return([100.0]) == 0.0

    def test_max_drawdown_simple(self):
        equity = [100.0, 110.0, 90.0, 95.0]
        result = SimulationService._compute_max_drawdown(equity)
        # Peak was 110, trough was 90 → dd = (90-110)/110 = -0.1818...
        assert abs(result - (-0.18181818)) < 1e-4

    def test_max_drawdown_no_drawdown(self):
        equity = [100.0, 105.0, 110.0, 115.0]
        result = SimulationService._compute_max_drawdown(equity)
        assert result == 0.0

    def test_max_drawdown_full_loss(self):
        equity = [100.0, 50.0, 25.0, 10.0]
        result = SimulationService._compute_max_drawdown(equity)
        assert abs(result - (-0.90)) < 1e-6

    def test_max_drawdown_empty(self):
        assert SimulationService._compute_max_drawdown([]) == 0.0
        assert SimulationService._compute_max_drawdown([100.0]) == 0.0

    def test_sharpe_ratio_positive(self):
        # Steady upward curve
        equity = [100 + i * 0.5 for i in range(50)]
        sharpe = SimulationService._compute_sharpe(equity, risk_free_rate=0.03)
        assert sharpe is not None
        assert sharpe > 0

    def test_sharpe_ratio_insufficient_data(self):
        equity = [100.0, 101.0, 102.0]
        sharpe = SimulationService._compute_sharpe(equity)
        assert sharpe is None  # Less than 10 data points


class TestRebalanceDates:
    """测试调仓日期生成"""

    def test_monthly_rebalance(self):
        dates = ["20240102", "20240115", "20240201", "20240215", "20240301"]
        result = SimulationService._get_rebalance_dates(dates, "monthly")
        assert "20240102" in result  # Jan first
        assert "20240201" in result  # Feb first
        assert "20240301" in result  # Mar first
        assert len(result) == 3

    def test_weekly_rebalance(self):
        dates = ["20240101", "20240102", "20240108", "20240109", "20240115"]
        result = SimulationService._get_rebalance_dates(dates, "weekly")
        assert len(result) >= 2  # At least 2 weeks

    def test_quarterly_rebalance(self):
        dates = ["20240102", "20240201", "20240301", "20240401", "20240701"]
        result = SimulationService._get_rebalance_dates(dates, "quarterly")
        assert "20240102" in result  # Q1
        assert "20240401" in result  # Q2
        assert "20240701" in result  # Q3

    def test_empty_dates(self):
        result = SimulationService._get_rebalance_dates([], "monthly")
        assert result == set()


# ==================== Service 集成测试（mock DB）====================

class TestSimulationService:
    @pytest.fixture
    def service(self):
        return SimulationService()

    @pytest.mark.asyncio
    async def test_empty_stock_pool(self, service):
        """空股票池应返回 data_sufficient=False"""
        config = SimulationConfig(stock_pool=[], start_date="2024-01-01", end_date="2024-12-31")

        mock_db = MagicMock()
        mock_coll = AsyncMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_coll)
        mock_coll.insert_one = AsyncMock()

        with patch("app.services.simulation_service.get_mongo_db", return_value=mock_db):
            result = await service.run_simulation("test_strategy", config)

        assert result.data_sufficient is False
        assert "股票池为空" in result.data_quality_note

    @pytest.mark.asyncio
    async def test_coverage_below_threshold(self, service):
        """覆盖率低于阈值时应标记数据不足"""
        config = SimulationConfig(
            stock_pool=["000001", "000002", "000003", "000004", "000005"],
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        mock_db = MagicMock()
        mock_coll_sim = AsyncMock()
        mock_coll_quotes = AsyncMock()

        def getitem(name):
            if name == "simulation_results":
                return mock_coll_sim
            return mock_coll_quotes

        mock_db.__getitem__ = MagicMock(side_effect=getitem)
        mock_coll_sim.insert_one = AsyncMock()

        # Only 1 out of 5 stocks has data → coverage = 0.2
        async def fake_find(query):
            symbol = query.get("symbol", "")
            if symbol == "000001":
                return _make_async_cursor([{"trade_date": "20240102", "close": 10.0}])
            return _make_async_cursor([])

        mock_coll_quotes.find = MagicMock(side_effect=fake_find)

        with patch("app.services.simulation_service.get_mongo_db", return_value=mock_db):
            with patch("app.services.simulation_service.get_settings") as mock_settings:
                mock_settings.return_value.SIMULATION_MIN_COVERAGE_RATE = 0.5
                result = await service.run_simulation("test_strategy", config)

        assert result.data_sufficient is False
        assert result.coverage_rate < 0.5
        assert "覆盖率" in result.data_quality_note

    @pytest.mark.asyncio
    async def test_get_latest_result(self, service):
        mock_db = MagicMock()
        mock_coll = AsyncMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_coll)

        fake_doc = {
            "_id": "oid",
            "strategy_id": "tpl_test",
            "cumulative_return": 0.12,
            "max_drawdown": -0.08,
        }
        mock_coll.find_one = AsyncMock(return_value=fake_doc)

        with patch("app.services.simulation_service.get_mongo_db", return_value=mock_db):
            result = await service.get_latest_result("tpl_test")

        assert result is not None
        assert result["cumulative_return"] == 0.12
        assert "_id" not in result

    @pytest.mark.asyncio
    async def test_get_latest_result_not_found(self, service):
        mock_db = MagicMock()
        mock_coll = AsyncMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_coll)
        mock_coll.find_one = AsyncMock(return_value=None)

        with patch("app.services.simulation_service.get_mongo_db", return_value=mock_db):
            result = await service.get_latest_result("nonexistent")

        assert result is None


def _make_async_cursor(docs):
    """Helper to create an async iterable cursor mock"""
    cursor = AsyncMock()
    cursor.__aiter__ = AsyncMock(return_value=iter(docs))

    async def _iterate():
        for doc in docs:
            yield doc

    cursor.__aiter__ = lambda self: _iterate().__aiter__()
    cursor.__anext__ = lambda self: _iterate().__anext__()
    return cursor
