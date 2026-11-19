"""
统一术语过滤器

确保输出内容符合合规要求，不包含荐股式措辞。
"""

import re
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class TerminologyFilter:
    """术语过滤器"""

    # 禁止使用的词汇及其替换建议
    PROHIBITED_TERMS = {
        # 买卖类
        "买入": "关注",
        "卖出": "调整",
        "买进": "研究",
        "抛售": "优化",
        "建仓": "配置",
        "加仓": "增加观察",
        "减仓": "降低关注",
        "清仓": "重新评估",
        "抄底": "低位观察",
        "追涨": "趋势跟踪",

        # 推荐类
        "强烈推荐": "重点关注",
        "推荐": "列入观察",
        "力荐": "值得研究",
        "必买": "具有研究价值",
        "牛股": "表现活跃标的",
        "黑马": "潜在机会",
        "金股": "优选标的",

        # 目标价类
        "目标价": "参考估值区间",
        "上涨空间": "潜在变动幅度",
        "翻倍": "显著变化可能",
        "暴涨": "大幅波动",
        "涨停": "价格上限",
        "跌停": "价格下限",

        # 保证收益类
        "稳赚": "历史表现良好",
        "保本": "风险相对可控",
        "包赚": "过往业绩稳定",
        "无风险": "风险较低",
        "躺赢": "长期持有策略",
        "稳赢": "胜率较高",

        # 煽动性用语
        "赶紧": "适时",
        "马上": "近期",
        "立刻": "可考虑",
        "不要错过": "值得关注",
        "千载难逢": "较为罕见",
        "最后机会": "阶段性窗口",
    }

    # 正则表达式模式（用于更复杂的匹配）
    PATTERNS = [
        (r"预计.*?涨.*?到\s*[\d.]+", "存在不确定性，请关注后续走势"),
        (r"至少.*?翻.*?倍", "历史数据仅供参考"),
        (r"\d+%.*?收益", "过往表现不代表未来"),
        (r"(一定|肯定|必然).*?(涨|升|盈利)", "市场存在不确定性"),
    ]

    @staticmethod
    def filter_text(text: str) -> tuple[str, List[str]]:
        """
        过滤文本中的违规术语

        Args:
            text: 待过滤的文本

        Returns:
            (filtered_text, replacements): 过滤后的文本和替换记录列表
        """
        if not text:
            return text, []

        replacements = []
        filtered = text

        # 1. 直接词汇替换
        for prohibited, replacement in TerminologyFilter.PROHIBITED_TERMS.items():
            if prohibited in filtered:
                count = filtered.count(prohibited)
                filtered = filtered.replace(prohibited, replacement)
                replacements.append(f"'{prohibited}' → '{replacement}' ({count}次)")

        # 2. 正则模式替换
        for pattern, replacement in TerminologyFilter.PATTERNS:
            matches = re.findall(pattern, filtered)
            if matches:
                filtered = re.sub(pattern, replacement, filtered)
                replacements.append(f"模式 '{pattern}' → '{replacement}' ({len(matches)}次)")

        if replacements:
            logger.info(f"Applied {len(replacements)} terminology filters")

        return filtered, replacements

    @staticmethod
    def filter_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
        """
        过滤单个候选标的的描述

        Args:
            candidate: 候选标的字典

        Returns:
            过滤后的候选标的
        """
        filtered = candidate.copy()

        # 过滤 match_reasons
        if "match_reasons" in filtered:
            filtered["match_reasons"] = [
                TerminologyFilter.filter_text(reason)[0]
                for reason in filtered["match_reasons"]
            ]

        # 过滤 risk_warnings
        if "risk_warnings" in filtered:
            filtered["risk_warnings"] = [
                TerminologyFilter.filter_text(warning)[0]
                for warning in filtered["risk_warnings"]
            ]

        return filtered

    @staticmethod
    def filter_screening_result(result: Dict[str, Any]) -> Dict[str, Any]:
        """
        过滤整个选股结果

        Args:
            result: 选股结果字典

        Returns:
            过滤后的结果
        """
        filtered = result.copy()

        # 过滤候选列表
        if "candidates" in filtered:
            filtered["candidates"] = [
                TerminologyFilter.filter_candidate(c)
                for c in filtered["candidates"]
            ]

        # 过滤整体风险提示
        if "overall_risks" in filtered:
            filtered["overall_risks"] = [
                TerminologyFilter.filter_text(risk)[0]
                for risk in filtered["overall_risks"]
            ]

        # 标记为已合规检查
        filtered["terminology_compliant"] = True

        return filtered

    @staticmethod
    def filter_checkup_result(result: Dict[str, Any]) -> Dict[str, Any]:
        """
        过滤体检结果

        Args:
            result: 体检结果字典

        Returns:
            过滤后的结果
        """
        filtered = result.copy()

        # 过滤摘要
        if "fitness_summary" in filtered:
            filtered["fitness_summary"], _ = TerminologyFilter.filter_text(
                filtered["fitness_summary"]
            )

        # 过滤风险警告
        if "risk_warnings" in filtered:
            filtered["risk_warnings"] = [
                TerminologyFilter.filter_text(warning)[0]
                for warning in filtered["risk_warnings"]
            ]

        # 标记为已合规检查
        filtered["terminology_compliant"] = True

        return filtered

    @staticmethod
    def validate_compliance(text: str) -> Dict[str, Any]:
        """
        验证文本是否合规（不修改，仅检查）

        Args:
            text: 待验证的文本

        Returns:
            {"compliant": bool, "violations": [...]}
        """
        violations = []

        # 检查禁用词汇
        for term in TerminologyFilter.PROHIBITED_TERMS.keys():
            if term in text:
                violations.append({
                    "type": "prohibited_term",
                    "term": term,
                    "suggestion": TerminologyFilter.PROHIBITED_TERMS[term],
                })

        # 检查模式
        for pattern, suggestion in TerminologyFilter.PATTERNS:
            matches = re.findall(pattern, text)
            if matches:
                violations.append({
                    "type": "pattern_match",
                    "pattern": pattern,
                    "count": len(matches),
                    "suggestion": suggestion,
                })

        return {
            "compliant": len(violations) == 0,
            "violations": violations,
        }


# 单例实例
terminology_filter = TerminologyFilter()
