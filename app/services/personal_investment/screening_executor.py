"""
策略筛选执行器

负责执行策略选股任务，生成候选池并进行风险检查。
"""

import logging
from typing import Dict, List, Any, Optional

from app.services.screening_service import ScreeningService, ScreeningParams
from app.services.personal_investment.context_builder import ContextBuilder
from app.services.personal_investment.task_service import task_service
from app.models.personal_investment import TaskStatus

logger = logging.getLogger(__name__)


class ScreeningExecutor:
    """策略筛选执行器"""

    def __init__(self):
        self.screening_service = ScreeningService()

    async def execute(
        self,
        task_id: str,
        user_id: str,
        strategy_id: str,
        profile_id: Optional[str] = None,
        input_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        执行策略选股任务

        Args:
            task_id: 任务 ID
            user_id: 用户 ID
            strategy_id: 策略 ID
            profile_id: 可选的画像 ID
            input_params: 额外参数

        Returns:
            选股结果摘要
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

            # 4. 构建筛选条件
            conditions = self._build_screening_conditions(strategy, input_params or {})

            # 5. 执行筛选
            params = ScreeningParams(
                market=strategy.get("applicable_markets", ["A股"])[0] if strategy.get("applicable_markets") else "CN",
                limit=50,
            )

            # 5.5 数据质量闸门检查
            from app.services.data_readiness_service import get_data_readiness_service, DataCategory
            try:
                dr = await get_data_readiness_service()
                gate_passed, gate_failures = await dr.check_gate([DataCategory.STOCK_POOL])
            except Exception as e:
                logger.warning(f"Data readiness check failed (non-blocking): {e}")
                gate_passed = True  # 不阻塞正常流程
                gate_failures = []

            logger.info(f"Executing screening for task {task_id} with conditions: {conditions}")
            screening_result = self.screening_service.run(conditions, params)

            # 检查股票池是否为空（禁止演示标的冒充真实结果）
            universe_size = screening_result.get("universe_size", 0)
            coverage_rate = screening_result.get("coverage_rate", 0.0)

            if universe_size == 0 or not gate_passed:
                logger.warning(
                    f"Screening task {task_id}: data insufficient "
                    f"(universe={universe_size}, gate_passed={gate_passed})"
                )
                await task_service.save_screening_result(
                    task_id=task_id,
                    user_id=user_id,
                    candidates=[],
                    overall_risks=gate_failures or ["股票池为空或数据不足"],
                    data_sources=["stock_basic_info"],
                    data_sufficient=False,
                    coverage_rate=0.0,
                )
                await task_service.update_task_status(task_id, TaskStatus.DATA_INSUFFICIENT)
                return {"status": "data_insufficient", "failures": gate_failures}

            # 6. 应用风险闸门和画像冲突检查
            candidates = await self._apply_risk_gates(
                screening_result["items"],
                profile,
                strategy,
            )

            # 7. 保存结果（含真实数据质量信息）
            result_summary = await task_service.save_screening_result(
                task_id=task_id,
                user_id=user_id,
                candidates=candidates,
                overall_risks=self._collect_overall_risks(candidates),
                data_sources=["stock_basic_info", "kline_data"],
                coverage_rate=coverage_rate,
                data_sufficient=True,
            )

            # 8. 更新任务状态为完成
            await task_service.update_task_status(task_id, TaskStatus.COMPLETED)

            logger.info(f"Screening task {task_id} completed with {len(candidates)} candidates")
            return result_summary

        except Exception as e:
            logger.error(f"Screening task {task_id} failed: {e}", exc_info=True)
            await task_service.update_task_status(
                task_id,
                TaskStatus.FAILED,
                error_message=str(e),
            )
            raise

    def _build_screening_conditions(
        self,
        strategy: Dict[str, Any],
        input_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        根据策略定义构建筛选条件 DSL

        策略的 screening_criteria 格式示例：
        {
            "pe_max": 20,
            "roe_min": 10,
            "dividend_yield_min": 3,
            "ma_trend": "up"
        }
        """
        criteria = strategy.get("screening_criteria", {})
        conditions = {"op": "and", "conditions": []}

        # PE 上限
        if "pe_max" in criteria:
            conditions["conditions"].append({
                "field": "pe",
                "op": "<=",
                "value": criteria["pe_max"],
            })

        # ROE 下限
        if "roe_min" in criteria:
            conditions["conditions"].append({
                "field": "roe",
                "op": ">=",
                "value": criteria["roe_min"],
            })

        # 股息率下限
        if "dividend_yield_min" in criteria:
            # 注意：当前 screening_service 可能不支持 dividend_yield，这里作为占位
            logger.warning("dividend_yield screening not yet supported in base service")

        # MA 趋势（简单实现：收盘价 > MA20）
        if criteria.get("ma_trend") == "up":
            conditions["conditions"].append({
                "field": "close",
                "op": ">",
                "value_field": "ma20",
            })

        # RSI 范围
        if "rsi_min" in criteria:
            conditions["conditions"].append({
                "field": "rsi14",
                "op": ">=",
                "value": criteria["rsi_min"],
            })
        if "rsi_max" in criteria:
            conditions["conditions"].append({
                "field": "rsi14",
                "op": "<=",
                "value": criteria["rsi_max"],
            })

        # 合并额外输入参数中的条件
        if "extra_conditions" in input_params:
            conditions["conditions"].extend(input_params["extra_conditions"])

        # 如果没有条件，返回空条件（匹配所有）
        if not conditions["conditions"]:
            return {"op": "and", "conditions": []}

        return conditions

    async def _apply_risk_gates(
        self,
        raw_candidates: List[Dict[str, Any]],
        profile: Optional[Dict[str, Any]],
        strategy: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        应用风险闸门规则

        检查项：
        1. ST 股票标记
        2. 数据缺失标记
        3. 禁投标的检查
        4. 行业禁投检查
        5. 仓位冲突检查（简化版）
        """
        processed = []

        for item in raw_candidates:
            stock_code = item.get("code", "")
            candidate = {
                "stock_code": stock_code,
                "stock_name": item.get("name", ""),  # 需要从其他地方获取名称
                "match_reasons": [],
                "risk_warnings": [],
                "conflict_with_profile": False,
                "score": 0.5,  # 默认分数，后续可优化
                "data": item,
            }

            # 1. 检查 ST 股票
            stock_name = candidate["stock_name"]
            if "ST" in stock_name.upper():
                candidate["risk_warnings"].append("该标的为 ST 股票，风险较高")
                candidate["score"] -= 0.3

                # 如果画像要求排除 ST，标记为冲突
                if profile and profile.get("exclude_st", True):
                    candidate["conflict_with_profile"] = True
                    candidate["risk_warnings"].append("根据您的画像设置，已排除 ST 股票")

            # 2. 检查数据完整性
            if not item.get("close"):
                candidate["risk_warnings"].append("最新行情数据缺失")
                candidate["score"] -= 0.2

            # 3. 检查禁投标的
            if profile:
                conflict_reason = ContextBuilder.check_profile_conflict(
                    stock_code=stock_code,
                    stock_info={"name": stock_name},
                    profile=profile,
                )
                if conflict_reason:
                    candidate["conflict_with_profile"] = True
                    candidate["risk_warnings"].append(conflict_reason)
                    candidate["score"] -= 0.4

            # 4. 添加命中原因
            if item.get("close") and item.get("ma20"):
                if item["close"] > item["ma20"]:
                    candidate["match_reasons"].append("价格站上20日均线")
            if item.get("rsi14"):
                if 30 <= item["rsi14"] <= 70:
                    candidate["match_reasons"].append(f"RSI处于合理区间 ({item['rsi14']:.1f})")

            # 确保分数在合理范围
            candidate["score"] = max(0.0, min(1.0, candidate["score"]))

            processed.append(candidate)

        # 按分数降序排序
        processed.sort(key=lambda x: x["score"], reverse=True)

        return processed

    def _collect_overall_risks(self, candidates: List[Dict[str, Any]]) -> List[str]:
        """收集整体风险提示"""
        risks = []

        conflict_count = sum(1 for c in candidates if c.get("conflict_with_profile"))
        if conflict_count > 0:
            risks.append(f"有 {conflict_count} 只标的与您的投资画像存在冲突，请注意风险")

        st_count = sum(1 for c in candidates if any("ST" in w for w in c.get("risk_warnings", [])))
        if st_count > 0:
            risks.append(f"候选池中包含 {st_count} 只 ST 股票，风险较高")

        if len(candidates) < 5:
            risks.append("符合条件的标的较少，建议适当放宽筛选条件")

        if not risks:
            risks.append("当前市场环境下，请结合自身风险承受能力审慎决策")

        return risks


# 单例实例
screening_executor = ScreeningExecutor()
