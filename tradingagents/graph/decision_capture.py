"""zhitouagent graph 节点级决策采集。"""

import uuid
from typing import Any, Callable, Dict, List, Optional


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)[:4000]


class DecisionCapture:
    """轻量决策链采集器，不依赖 Mongo 或 app 模块。"""

    NODE_SCENARIOS = {
        "Market Analyst": "市场分析",
        "Fundamentals Analyst": "基本面分析",
        "News Analyst": "新闻分析",
        "Social Analyst": "社交媒体分析",
        "Bull Researcher": "看涨研究",
        "Bear Researcher": "看跌研究",
        "Research Manager": "研究经理仲裁",
        "Trader": "交易员决策",
        "Risky Analyst": "激进风险评估",
        "Safe Analyst": "保守风险评估",
        "Neutral Analyst": "中性风险评估",
        "Risk Judge": "风险经理决策",
    }

    def __init__(self) -> None:
        self.records: List[Dict[str, Any]] = []
        self._last_by_node: Dict[str, str] = {}

    def record(
        self,
        node_name: str,
        state_update: Dict[str, Any],
        *,
        parent_decision_id: Optional[str] = None,
        sink: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        node_name = str(node_name or "")
        scenario = self.NODE_SCENARIOS.get(node_name, f"{node_name} 节点")
        conclusion_keys = [
            "market_report",
            "fundamentals_report",
            "news_report",
            "sentiment_report",
            "bull_case",
            "bear_case",
            "manager_report",
            "trader_investment_plan",
            "final_trade_decision",
            "investment_plan",
            "risky_report",
            "safe_report",
            "neutral_report",
            "judge_decision",
            "final_decision",
        ]
        conclusion = ""
        for key in conclusion_keys:
            if state_update.get(key):
                conclusion = _text(state_update[key])
                break
        if not conclusion:
            conclusion = _text(
                state_update.get("reasoning")
                or state_update.get("summary")
                or state_update.get("report")
                or state_update.get("response")
            )

        record = {
            "decision_id": f"graph_{uuid.uuid4().hex[:12]}",
            "sequence": len(self.records),
            "decision_type": "graph",
            "node_name": node_name,
            "scenario": scenario,
            "selected_option": node_name,
            "selection_reason": "graph 节点执行后被选中",
            "conclusion": conclusion,
            "candidates": [],
            "evidence_ids": list(state_update.get("evidence_ids") or []),
            "parent_decision_id": parent_decision_id,
            "status": "confirmed" if conclusion else "unverified",
            "confidence": float(state_update.get("confidence") or 0.5),
            "risk_level": str(state_update.get("risk_level") or "medium"),
            "model_version": state_update.get("model_version"),
            "strategy_version": state_update.get("strategy_version"),
        }
        if parent_decision_id is None and self.records:
            record["parent_decision_id"] = self.records[-1]["decision_id"]
        self.records.append(record)
        self._last_by_node[node_name] = record["decision_id"]
        if sink is not None:
            sink(record)
        return record

    def snapshot(self) -> List[Dict[str, Any]]:
        return list(self.records)
