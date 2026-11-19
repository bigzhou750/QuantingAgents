"""
第一阶段策略历史模拟服务

基于 stock_daily_quotes 中的日线数据，按策略筛选条件构建股票池，
执行等权调仓模拟，生成累计收益、最大回撤等保守摘要指标。
"""

import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple

from app.core.config import get_settings
from app.core.database import get_mongo_db
from app.models.simulation import SimulationResultDoc
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)


@dataclass
class SimulationConfig:
    """模拟配置"""
    stock_pool: List[str] = field(default_factory=list)
    start_date: str = ""          # YYYY-MM-DD
    end_date: str = ""            # YYYY-MM-DD
    rebalance_frequency: str = "monthly"  # weekly / monthly / quarterly
    initial_capital: float = 1_000_000.0
    commission_rate: float = 0.0003   # 万三
    stamp_tax_rate: float = 0.001     # 千一（仅卖出）
    slippage_pct: float = 0.001       # 0.1%


@dataclass
class SimulationResult:
    """模拟结果"""
    cumulative_return: float = 0.0
    annualized_return: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: Optional[float] = None
    simulation_period: Dict[str, str] = field(default_factory=dict)
    sample_count: int = 0
    coverage_rate: float = 0.0
    data_as_of: Optional[datetime] = None
    data_sufficient: bool = True
    data_quality_note: Optional[str] = None
    rebalance_count: int = 0
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)


class SimulationService:
    """策略历史模拟服务"""

    COLLECTION = "simulation_results"

    def __init__(self):
        self._initialized = False

    async def initialize(self):
        """初始化服务和索引"""
        if self._initialized:
            return
        db = get_mongo_db()
        await db[self.COLLECTION].create_index("strategy_id")
        await db[self.COLLECTION].create_index("created_at")
        await db[self.COLLECTION].create_index([("strategy_id", 1), ("created_at", -1)])
        self._initialized = True
        logger.info("SimulationService initialized")

    async def run_simulation(
        self,
        strategy_id: str,
        config: SimulationConfig,
    ) -> SimulationResult:
        """运行策略模拟

        Args:
            strategy_id: 策略或模板 ID
            config: 模拟配置（stock_pool 必须已填充）

        Returns:
            SimulationResult
        """
        settings = get_settings()
        result = SimulationResult()
        result.simulation_period = {"start": config.start_date, "end": config.end_date}

        if not config.stock_pool:
            result.data_sufficient = False
            result.data_quality_note = "股票池为空，无法执行模拟"
            await self._save_result(strategy_id, config, result)
            return result

        # 1. 获取日线数据
        bars = await self._fetch_daily_bars(config.stock_pool, config.start_date, config.end_date)
        stocks_with_data = [code for code, df in bars.items() if len(df) > 0]
        coverage = len(stocks_with_data) / len(config.stock_pool) if config.stock_pool else 0.0
        result.sample_count = len(stocks_with_data)
        result.coverage_rate = round(coverage, 4)

        # 检查覆盖率
        if coverage < settings.SIMULATION_MIN_COVERAGE_RATE:
            result.data_sufficient = False
            result.data_quality_note = (
                f"数据覆盖率 {coverage:.1%} 低于最低要求 "
                f"{settings.SIMULATION_MIN_COVERAGE_RATE:.1%}，不生成模拟收益指标"
            )
            await self._save_result(strategy_id, config, result)
            return result

        # 2. 计算净值曲线
        equity = self._compute_equity_curve(bars, stocks_with_data, config)

        if len(equity) < 2:
            result.data_sufficient = False
            result.data_quality_note = "有效交易日不足，无法计算模拟指标"
            await self._save_result(strategy_id, config, result)
            return result

        # 3. 计算指标
        result.cumulative_return = round(self._compute_cumulative_return(equity), 6)
        result.max_drawdown = round(self._compute_max_drawdown(equity), 6)

        # 年化收益
        days = len(equity)
        if days > 1:
            years = days / 252.0
            if years > 0 and result.cumulative_return > -1:
                result.annualized_return = round(
                    (1 + result.cumulative_return) ** (1 / years) - 1, 6
                )

        # 夏普比率（简化版，假设无风险利率 3%）
        result.sharpe_ratio = self._compute_sharpe(equity, risk_free_rate=0.03)

        # data_as_of 取最后一个交易日
        result.data_as_of = now_tz()
        result.data_sufficient = True
        result.rebalance_count = self._count_rebalances(config)

        # 保存
        await self._save_result(strategy_id, config, result)
        logger.info(
            f"Simulation completed for {strategy_id}: "
            f"return={result.cumulative_return:.2%}, "
            f"max_dd={result.max_drawdown:.2%}, "
            f"coverage={coverage:.1%}"
        )
        return result

    async def get_latest_result(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """获取最新的模拟结果"""
        db = get_mongo_db()
        doc = await db[self.COLLECTION].find_one(
            {"strategy_id": strategy_id},
            sort=[("created_at", -1)],
        )
        if doc:
            doc.pop("_id", None)
        return doc

    async def update_template_metrics(
        self, template_id: str, sim_result: SimulationResult
    ) -> bool:
        """更新策略模板的模拟指标字段"""
        from app.services.personal_investment.marketplace_service import marketplace_service
        db = get_mongo_db()

        update_fields = {
            "simulation_cumulative_return": sim_result.cumulative_return if sim_result.data_sufficient else None,
            "simulation_max_drawdown": sim_result.max_drawdown if sim_result.data_sufficient else None,
            "simulation_period": (
                f"{sim_result.simulation_period.get('start', '')} ~ {sim_result.simulation_period.get('end', '')}"
                if sim_result.data_sufficient else None
            ),
            "simulation_data_as_of": sim_result.data_as_of,
            "simulation_data_sufficient": sim_result.data_sufficient,
            "data_preparation_status": "ready" if sim_result.data_sufficient else "insufficient",
            "updated_at": now_tz(),
        }

        result = await db[marketplace_service.COLLECTION_TEMPLATES].update_one(
            {"template_id": template_id},
            {"$set": update_fields},
        )
        return result.modified_count > 0

    # ==================== 内部方法 ====================

    async def _fetch_daily_bars(
        self, codes: List[str], start_date: str, end_date: str
    ) -> Dict[str, List[Dict]]:
        """从 MongoDB 获取日线数据"""
        db = get_mongo_db()
        bars = {}

        for code in codes:
            try:
                cursor = db["stock_daily_quotes"].find({
                    "symbol": code,
                    "trade_date": {"$gte": start_date.replace("-", ""), "$lte": end_date.replace("-", "")},
                }).sort("trade_date", 1)

                docs = []
                async for doc in cursor:
                    close = doc.get("close")
                    trade_date = doc.get("trade_date", "")
                    if close is not None and close > 0:
                        docs.append({"date": str(trade_date), "close": float(close)})

                bars[code] = docs
            except Exception as e:
                logger.warning(f"Failed to fetch bars for {code}: {e}")
                bars[code] = []

        return bars

    def _compute_equity_curve(
        self,
        bars: Dict[str, List[Dict]],
        valid_codes: List[str],
        config: SimulationConfig,
    ) -> List[float]:
        """计算等权调仓的净值曲线"""
        if not valid_codes:
            return []

        # 收集所有交易日
        all_dates = set()
        for code in valid_codes:
            for bar in bars.get(code, []):
                all_dates.add(bar["date"])
        sorted_dates = sorted(all_dates)

        if not sorted_dates:
            return []

        # 确定调仓日
        rebalance_dates = self._get_rebalance_dates(sorted_dates, config.rebalance_frequency)

        # 逐日计算净值
        capital = config.initial_capital
        holdings = {}  # {code: shares}
        equity = [capital]

        for i, date in enumerate(sorted_dates):
            if date in rebalance_dates and i > 0:
                # 调仓：先卖出再买入
                # 卖出
                sell_value = 0
                for code, shares in holdings.items():
                    price = self._get_price_on_date(bars.get(code, []), date)
                    if price:
                        sell_value += shares * price * (1 - config.commission_rate - config.stamp_tax_rate - config.slippage_pct)

                cash = sell_value if holdings else capital

                # 等权买入
                n_stocks = len(valid_codes)
                per_stock = cash / n_stocks if n_stocks > 0 else 0
                new_holdings = {}
                total_invested = 0
                for code in valid_codes:
                    price = self._get_price_on_date(bars.get(code, []), date)
                    if price and price > 0:
                        shares = per_stock / price * (1 - config.commission_rate - config.slippage_pct)
                        new_holdings[code] = shares
                        total_invested += shares * price
                holdings = new_holdings

            # 计算当日组合价值
            portfolio_value = 0
            for code, shares in holdings.items():
                price = self._get_price_on_date(bars.get(code, []), date)
                if price:
                    portfolio_value += shares * price

            if portfolio_value > 0:
                equity.append(portfolio_value)

        return equity

    @staticmethod
    def _get_price_on_date(bars: List[Dict], date: str) -> Optional[float]:
        """获取指定日期的收盘价"""
        for bar in bars:
            if bar["date"] == date:
                return bar["close"]
        return None

    @staticmethod
    def _get_rebalance_dates(sorted_dates: List[str], frequency: str) -> set:
        """根据频率确定调仓日期"""
        if not sorted_dates:
            return set()

        rebalance_dates = set()

        if frequency == "weekly":
            # 每周第一个交易日
            current_week = None
            for d in sorted_dates:
                try:
                    dt = datetime.strptime(d, "%Y%m%d")
                    week = dt.isocalendar()[1]
                    if week != current_week:
                        rebalance_dates.add(d)
                        current_week = week
                except ValueError:
                    continue
        elif frequency == "quarterly":
            # 每季度第一个交易日
            current_quarter = None
            for d in sorted_dates:
                try:
                    dt = datetime.strptime(d, "%Y%m%d")
                    quarter = (dt.month - 1) // 3
                    year_q = (dt.year, quarter)
                    if year_q != current_quarter:
                        rebalance_dates.add(d)
                        current_quarter = year_q
                except ValueError:
                    continue
        else:  # monthly (default)
            current_month = None
            for d in sorted_dates:
                try:
                    dt = datetime.strptime(d, "%Y%m%d")
                    month = (dt.year, dt.month)
                    if month != current_month:
                        rebalance_dates.add(d)
                        current_month = month
                except ValueError:
                    continue

        return rebalance_dates

    @staticmethod
    def _compute_cumulative_return(equity: List[float]) -> float:
        """计算累计收益率"""
        if len(equity) < 2 or equity[0] == 0:
            return 0.0
        return (equity[-1] - equity[0]) / equity[0]

    @staticmethod
    def _compute_max_drawdown(equity: List[float]) -> float:
        """计算最大回撤（返回负数）"""
        if len(equity) < 2:
            return 0.0

        peak = equity[0]
        max_dd = 0.0

        for value in equity:
            if value > peak:
                peak = value
            dd = (value - peak) / peak if peak > 0 else 0.0
            if dd < max_dd:
                max_dd = dd

        return max_dd

    @staticmethod
    def _compute_sharpe(equity: List[float], risk_free_rate: float = 0.03) -> Optional[float]:
        """计算年化夏普比率"""
        if len(equity) < 10:
            return None

        # 日收益率序列
        returns = []
        for i in range(1, len(equity)):
            if equity[i - 1] > 0:
                r = (equity[i] - equity[i - 1]) / equity[i - 1]
                returns.append(r)

        if not returns:
            return None

        mean_r = sum(returns) / len(returns)
        var_r = sum((r - mean_r) ** 2 for r in returns) / len(returns)
        std_r = math.sqrt(var_r) if var_r > 0 else 0

        if std_r == 0:
            return None

        daily_rf = risk_free_rate / 252
        sharpe = (mean_r - daily_rf) / std_r * math.sqrt(252)
        return round(sharpe, 4)

    def _count_rebalances(self, config: SimulationConfig) -> int:
        """估算调仓次数"""
        if not config.start_date or not config.end_date:
            return 0
        try:
            start = datetime.strptime(config.start_date, "%Y-%m-%d")
            end = datetime.strptime(config.end_date, "%Y-%m-%d")
            months = (end.year - start.year) * 12 + (end.month - start.month)
            if config.rebalance_frequency == "weekly":
                return max(int((end - start).days / 7), 0)
            elif config.rebalance_frequency == "quarterly":
                return max(months // 3, 0)
            else:
                return max(months, 0)
        except ValueError:
            return 0

    async def _save_result(
        self, strategy_id: str, config: SimulationConfig, result: SimulationResult
    ):
        """保存模拟结果到 MongoDB"""
        db = get_mongo_db()
        doc = SimulationResultDoc(
            result_id=f"sim_{uuid.uuid4().hex[:12]}",
            strategy_id=strategy_id,
            config={
                "stock_pool_size": len(config.stock_pool),
                "start_date": config.start_date,
                "end_date": config.end_date,
                "rebalance_frequency": config.rebalance_frequency,
                "initial_capital": config.initial_capital,
            },
            cumulative_return=result.cumulative_return,
            annualized_return=result.annualized_return,
            max_drawdown=result.max_drawdown,
            sharpe_ratio=result.sharpe_ratio,
            simulation_start=config.start_date,
            simulation_end=config.end_date,
            sample_count=result.sample_count,
            coverage_rate=result.coverage_rate,
            data_as_of=result.data_as_of,
            data_sufficient=result.data_sufficient,
            data_quality_note=result.data_quality_note,
            rebalance_count=result.rebalance_count,
        )
        await db[self.COLLECTION].insert_one(doc.model_dump(by_alias=True, exclude={"id"}))


# 模块级单例
_simulation_service: Optional[SimulationService] = None


async def get_simulation_service() -> SimulationService:
    """获取模拟服务单例"""
    global _simulation_service
    if _simulation_service is None:
        _simulation_service = SimulationService()
        await _simulation_service.initialize()
    return _simulation_service
