"""
VibeAgent 上下文构造器

负责将用户画像和策略信息转换为受控的上下文摘要，
用于注入到 VibeAgent 的研究输入中。
"""

import logging
from typing import Optional, Dict, Any

from app.services.personal_investment.profile_service import profile_service
from app.services.personal_investment.strategy_service import strategy_service

logger = logging.getLogger(__name__)


class ContextBuilder:
    """上下文构造器"""

    @staticmethod
    async def build_context_summary(
        user_id: str,
        include_profile: bool = True,
        strategy_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        构建上下文摘要字符串

        Args:
            user_id: 用户 ID
            include_profile: 是否包含画像信息
            strategy_id: 可选的策略 ID

        Returns:
            格式化的上下文字符串，或 None（如果无可用上下文）
        """
        sections = []

        # 1. 添加画像摘要
        if include_profile:
            profile_summary = await profile_service.get_profile_summary(user_id)
            if profile_summary:
                profile_section = ContextBuilder._format_profile_summary(profile_summary)
                if profile_section:
                    sections.append(profile_section)

        # 2. 添加策略信息
        if strategy_id:
            strategy = await strategy_service.get_strategy(strategy_id, user_id)
            if strategy:
                strategy_section = ContextBuilder._format_strategy_info(strategy)
                if strategy_section:
                    sections.append(strategy_section)

        if not sections:
            return None

        return "\n\n".join(sections)

    @staticmethod
    def _format_profile_summary(summary: Dict[str, Any]) -> Optional[str]:
        """格式化画像摘要"""
        if not summary:
            return None

        lines = ["## 用户投资画像"]

        # 风险偏好
        risk_map = {
            "conservative": "保守型（偏好低风险、稳定收益）",
            "balanced": "平衡型（风险与收益均衡）",
            "aggressive": "进取型（可接受较高风险追求高收益）",
        }
        risk = summary.get("risk_preference", "")
        if risk in risk_map:
            lines.append(f"- 风险偏好：{risk_map[risk]}")

        # 交易风格
        style_map = {
            "value": "价值投资",
            "growth": "成长投资",
            "momentum": "趋势跟踪",
            "dividend": "红利投资",
            "contrarian": "逆向投资",
        }
        style = summary.get("trading_style", "")
        if style in style_map:
            lines.append(f"- 交易风格：{style_map[style]}")

        # 目标市场
        markets = summary.get("target_markets", [])
        if markets:
            lines.append(f"- 关注市场：{', '.join(markets)}")

        # 禁投规则
        excluded_sectors = summary.get("excluded_sectors", [])
        if excluded_sectors:
            lines.append(f"- 回避行业：{', '.join(excluded_sectors)}")

        excluded_stocks = summary.get("excluded_stocks", [])
        if excluded_stocks:
            lines.append(f"- 回避标的：{', '.join(excluded_stocks[:5])}")  # 最多显示5个

        if summary.get("exclude_st"):
            lines.append("- 排除 ST 股票：是")

        # 仓位约束
        max_pos = summary.get("max_position_per_stock", 0.2)
        if max_pos < 1.0:
            lines.append(f"- 单只最大仓位：{int(max_pos * 100)}%")

        holdings_count = summary.get("current_holdings_count", 0)
        if holdings_count > 0:
            lines.append(f"- 当前持仓数量：{holdings_count} 只")
            for holding in summary.get("current_holdings", []):
                code = holding.get("stock_code", "")
                name = holding.get("stock_name", "")
                quantity = holding.get("quantity", 0)
                cost_price = holding.get("cost_price", 0)
                label = f"{code} {name}".strip()
                lines.append(
                    f"- 持仓：{label}，数量 {quantity} 股，成本价 {cost_price}"
                )

        if len(lines) <= 1:
            return None

        return "\n".join(lines)

    @staticmethod
    def _format_strategy_info(strategy: Dict[str, Any]) -> Optional[str]:
        """格式化策略信息"""
        if not strategy:
            return None

        lines = ["## 当前研究策略"]
        lines.append(f"- 策略名称：{strategy.get('name', '未命名')}")

        description = strategy.get("description", "")
        if description:
            lines.append(f"- 策略说明：{description[:200]}")  # 限制长度

        markets = strategy.get("applicable_markets", [])
        if markets:
            lines.append(f"- 适用市场：{', '.join(markets)}")

        # 筛选条件摘要
        criteria = strategy.get("screening_criteria", {})
        if criteria:
            criteria_items = []
            if "pe_max" in criteria:
                criteria_items.append(f"PE≤{criteria['pe_max']}")
            if "roe_min" in criteria:
                criteria_items.append(f"ROE≥{criteria['roe_min']}%")
            if "dividend_yield_min" in criteria:
                criteria_items.append(f"股息率≥{criteria['dividend_yield_min']}%")
            if criteria_items:
                lines.append(f"- 核心条件：{', '.join(criteria_items)}")

        tags = strategy.get("tags", [])
        if tags:
            lines.append(f"- 标签：{', '.join(tags)}")

        if len(lines) <= 1:
            return None

        return "\n".join(lines)

    @staticmethod
    def check_profile_conflict(
        stock_code: str,
        stock_info: Dict[str, Any],
        profile: Dict[str, Any],
    ) -> Optional[str]:
        """
        检查标的是否与用户画像冲突

        Returns:
            冲突原因字符串，或 None（无冲突）
        """
        if not profile:
            return None

        # 检查是否在禁投标的中
        excluded_stocks = profile.get("excluded_stocks", [])
        if stock_code in excluded_stocks:
            return f"该标的在您的禁投列表中"

        # 检查是否是 ST 股票
        if profile.get("exclude_st", True):
            stock_name = stock_info.get("name", "")
            if "ST" in stock_name.upper():
                return "您设置了排除 ST 股票"

        # 检查行业是否在禁投行业中
        excluded_sectors = profile.get("excluded_sectors", [])
        stock_sector = stock_info.get("sector", "")
        if stock_sector and stock_sector in excluded_sectors:
            return f"该标的属于您回避的 {stock_sector} 行业"

        # 检查仓位约束冲突：候选标的已在当前持仓中
        # 注：由于缺少总资产/市值数据，无法精确计算持仓占比，因此不编造
        # 具体百分比，只提示用户结合自身设置的单只最大仓位比例审慎追加。
        current_holdings = profile.get("current_holdings", [])
        held_codes = {
            h.get("stock_code") for h in current_holdings if h.get("stock_code")
        }
        if stock_code in held_codes:
            max_position = profile.get("max_position_per_stock")
            if max_position is not None:
                return (
                    f"您已持有该标的，请结合您设置的单只最大仓位比例"
                    f"（{int(max_position * 100)}%）审慎评估是否继续追加"
                )
            return "您已持有该标的，请结合仓位约束审慎评估是否继续追加"

        return None


# 单例实例
context_builder = ContextBuilder()
