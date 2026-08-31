"""
策略体检执行器

负责评估策略与当前市场环境的适配度，输出体检报告。
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

from app.services.personal_investment.task_service import task_service
from app.models.personal_investment import TaskStatus

logger = logging.getLogger(__name__)


class CheckupExecutor:
    """策略体检执行器"""

    async def execute(
        self,
        task_id: str,
        user_id: str,
        strategy_id: str,
        profile_id: Optional[str] = None,
        input_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        执行策略体检任务

        Args:
            task_id: 任务 ID
            user_id: 用户 ID
            strategy_id: 策略 ID
            profile_id: 可选的画像 ID
            input_params: 额外参数

        Returns:
            体检结果摘要
        """
        try:
            # 1. 更新任务状态为运行中
            await task_service.update_task_status(task_id, TaskStatus.RUNNING)

            # 2. 获取策略定义
            from app.services.personal_investment.strategy_service import strategy_service
            strategy = await strategy_service.get_strategy(strategy_id, user_id)
            if not strategy:
                raise ValueError(f"Strategy {strategy_id} not found")

            # 3. 获取用户画像（如果提供）
            profile = None
            if profile_id:
                from app.services.personal_investment.profile_service import profile_service
                profile = await profile_service.get_profile(user_id)

            # 4. 收集市场数据
            market_data = await self._collect_market_data(strategy)

            # 5. 评估策略适配度
            fitness_assessment = self._assess_fitness(strategy, profile, market_data)

            # 6. 生成关键指标
            key_metrics = self._generate_key_metrics(strategy, market_data)

            # 7. 识别风险警告
            risk_warnings = self._identify_risks(strategy, profile, market_data)

            # 8. 检查数据充分性
            data_sufficient, data_quality_note = self._check_data_sufficiency(market_data)

            # 9. 保存结果
            result_summary = await task_service.save_checkup_result(
                task_id=task_id,
                fitness_level=fitness_assessment["level"],
                fitness_summary=fitness_assessment["summary"],
                key_metrics=key_metrics,
                risk_warnings=risk_warnings,
                data_sufficient=data_sufficient,
                data_quality_note=data_quality_note,
                recent_performance=fitness_assessment.get("performance", {}),
            )

            # 10. 更新任务状态
            if data_sufficient:
                await task_service.update_task_status(task_id, TaskStatus.COMPLETED)
            else:
                await task_service.update_task_status(task_id, TaskStatus.DATA_INSUFFICIENT)

            logger.info(f"Checkup task {task_id} completed with fitness level: {fitness_assessment['level']}")
            return result_summary

        except Exception as e:
            logger.error(f"Checkup task {task_id} failed: {e}", exc_info=True)
            await task_service.update_task_status(
                task_id,
                TaskStatus.FAILED,
                error_message=str(e),
            )
            raise

    async def _collect_market_data(self, strategy: Dict[str, Any]) -> Dict[str, Any]:
        """
        收集市场数据用于体检

        返回的数据包括：
        - 近期市场趋势
        - 波动率指标
        - 行业轮动情况
        - 流动性状况
        """
        try:
            # 这里应该调用实际的市场数据服务
            # 暂时使用模拟数据作为占位

            from tradingagents.dataflows.data_source_manager import get_data_source_manager

            manager = get_data_source_manager()

            # 获取主要指数的近期表现
            indices = ["000001", "399001", "399006"]  # 上证指数、深证成指、创业板指
            index_data = {}

            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)

            for idx_code in indices:
                try:
                    df = manager.get_stock_dataframe(
                        idx_code,
                        start_date.strftime("%Y-%m-%d"),
                        end_date.strftime("%Y-%m-%d"),
                    )
                    if df is not None and not df.empty:
                        close_col = "Close" if "Close" in df.columns else "close"
                        if close_col in df.columns:
                            prices = df[close_col].values
                            if len(prices) > 1:
                                change_pct = (prices[-1] - prices[0]) / prices[0] * 100
                                volatility = float(prices.std() / prices.mean() * 100) if prices.mean() > 0 else 0
                                index_data[idx_code] = {
                                    "latest_price": float(prices[-1]),
                                    "period_change_pct": round(change_pct, 2),
                                    "volatility": round(volatility, 2),
                                }
                except Exception as e:
                    logger.warning(f"Failed to fetch index {idx_code}: {e}")

            return {
                "indices": index_data,
                "data_timestamp": datetime.now().isoformat(),
                "market_phase": self._determine_market_phase(index_data),
            }

        except Exception as e:
            logger.error(f"Failed to collect market data: {e}")
            return {
                "indices": {},
                "data_timestamp": datetime.now().isoformat(),
                "market_phase": "unknown",
                "error": str(e),
            }

    def _determine_market_phase(self, index_data: Dict[str, Any]) -> str:
        """判断市场阶段"""
        if not index_data:
            return "unknown"

        sh_index = index_data.get("000001", {})
        change = sh_index.get("period_change_pct", 0)

        if change > 5:
            return "bullish"
        elif change < -5:
            return "bearish"
        else:
            return "sideways"

    def _assess_fitness(
        self,
        strategy: Dict[str, Any],
        profile: Optional[Dict[str, Any]],
        market_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        评估策略与市场的适配度

        返回：
        - level: high/medium/low
        - summary: 文字说明
        - performance: 近期表现摘要
        """
        market_phase = market_data.get("market_phase", "unknown")
        criteria = strategy.get("screening_criteria", {})
        tags = strategy.get("tags", [])

        score = 50  # 基础分

        # 根据市场阶段调整分数
        if market_phase == "bullish":
            # 牛市环境下，成长型策略更适配
            if "growth" in tags or "momentum" in tags:
                score += 20
            elif "value" in tags or "dividend" in tags:
                score += 10
        elif market_phase == "bearish":
            # 熊市环境下，防御型策略更适配
            if "value" in tags or "dividend" in tags:
                score += 20
            elif "conservative" in tags:
                score += 15
        elif market_phase == "sideways":
            # 震荡市，均衡型策略较适配
            if "balanced" in tags or "contrarian" in tags:
                score += 15

        # 检查策略条件是否过于严格
        strict_conditions = 0
        if criteria.get("pe_max") and criteria["pe_max"] < 15:
            strict_conditions += 1
        if criteria.get("roe_min") and criteria["roe_min"] > 15:
            strict_conditions += 1
        if criteria.get("rsi_min") and criteria.get("rsi_max"):
            rsi_range = criteria["rsi_max"] - criteria["rsi_min"]
            if rsi_range < 20:
                strict_conditions += 1

        if strict_conditions >= 2:
            score -= 10

        # 确定等级
        if score >= 70:
            level = "high"
            summary = f"当前市场{self._translate_phase(market_phase)}，您的策略与该环境较为契合。建议保持关注，定期复盘。"
        elif score >= 40:
            level = "medium"
            summary = f"当前市场{self._translate_phase(market_phase)}，您的策略适配度中等。可适当调整参数或增加观察频次。"
        else:
            level = "low"
            summary = f"当前市场{self._translate_phase(market_phase)}，您的策略可能与该环境存在一定偏差。建议审慎评估是否需要调整策略。"

        # 添加合规声明
        summary += "\n\n注：以上分析仅基于历史数据和规则匹配，不构成任何投资建议。投资有风险，决策需谨慎。"

        return {
            "level": level,
            "summary": summary,
            "score": score,
            "performance": {
                "market_phase": market_phase,
                "strict_conditions_count": strict_conditions,
            },
        }

    def _translate_phase(self, phase: str) -> str:
        """翻译市场阶段"""
        mapping = {
            "bullish": "处于上升趋势",
            "bearish": "处于下行趋势",
            "sideways": "处于震荡整理阶段",
            "unknown": "数据不足，趋势不明确",
        }
        return mapping.get(phase, "状态未知")

    def _generate_key_metrics(
        self,
        strategy: Dict[str, Any],
        market_data: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """生成关键指标"""
        metrics = []

        # 策略条件数量
        criteria = strategy.get("screening_criteria", {})
        metrics.append({
            "name": "筛选条件数",
            "value": len(criteria),
            "unit": "项",
            "interpretation": "策略包含的筛选条件数量",
        })

        # 市场波动率（如果有数据）
        sh_index = market_data.get("indices", {}).get("000001", {})
        if sh_index.get("volatility"):
            metrics.append({
                "name": "近30日波动率",
                "value": sh_index["volatility"],
                "unit": "%",
                "interpretation": "上证指数的价格波动程度",
            })

        # 市场涨跌幅
        if sh_index.get("period_change_pct"):
            metrics.append({
                "name": "近30日涨跌",
                "value": sh_index["period_change_pct"],
                "unit": "%",
                "interpretation": "上证指数的区间涨跌幅",
            })

        return metrics

    def _identify_risks(
        self,
        strategy: Dict[str, Any],
        profile: Optional[Dict[str, Any]],
        market_data: Dict[str, Any],
    ) -> List[str]:
        """识别风险提示"""
        warnings = []

        market_phase = market_data.get("market_phase", "unknown")

        # 市场风险提示
        if market_phase == "bearish":
            warnings.append("当前市场处于下行趋势，请注意控制仓位和风险")
        elif market_phase == "bullish":
            warnings.append("市场短期涨幅较大，注意追高风险")

        # 策略风险提示
        criteria = strategy.get("screening_criteria", {})
        if criteria.get("pe_max") and criteria["pe_max"] > 30:
            warnings.append("策略允许较高估值标的，需关注估值回归风险")

        if criteria.get("rsi_min") and criteria["rsi_min"] < 20:
            warnings.append("策略可能在超跌时介入，需注意左侧交易风险")

        # 画像匹配风险
        if profile:
            risk_pref = profile.get("risk_preference", "balanced")
            if risk_pref == "conservative" and "aggressive" in strategy.get("tags", []):
                warnings.append("该策略风格偏激进，与您的保守型偏好可能存在差异")

        # 通用风险提示
        warnings.append("历史表现不代表未来收益，请结合自身情况审慎决策")

        return warnings

    def _check_data_sufficiency(self, market_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """检查数据充分性"""
        indices = market_data.get("indices", {})

        if not indices:
            return False, "未能获取到市场指数数据，体检结果可能不完整"

        # 检查是否有足够的指数数据
        valid_indices = sum(1 for idx in indices.values() if idx.get("latest_price"))

        if valid_indices < 2:
            return False, f"仅获取到 {valid_indices} 个有效指数数据，建议稍后重试"

        if market_data.get("error"):
            return True, f"部分数据获取异常：{market_data['error']}"

        return True, None


# 单例实例
checkup_executor = CheckupExecutor()
