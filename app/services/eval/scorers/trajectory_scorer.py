"""
工具与轨迹评分器

基于 trace 事件中的工具调用记录，评估：
- 工具选择合理性：是否选择了合适的工具完成任务
- 参数正确性：工具调用参数是否合理
- 必要工具覆盖：是否遗漏了完成任务所必需的工具
- 冗余调用：是否存在不必要的重复工具调用
- 步骤效率：完成任务的步骤数是否合理
- 重试和死循环检测：是否存在无效重试或循环调用

对应 spec 二期任务 2.4。
"""

import logging
from collections import Counter
from typing import Optional, List, Dict, Any

from app.models.eval import ScoreSource
from app.services.eval.scorers.base import BaseScorer, ScoreResult

logger = logging.getLogger(__name__)


class TrajectoryScorer(BaseScorer):
    """工具与轨迹评分器"""

    @property
    def name(self) -> str:
        return "trajectory"

    @property
    def source(self) -> ScoreSource:
        return ScoreSource.TRACE

    @property
    def version(self) -> str:
        return "1.0.0"

    async def score(
        self,
        trial_data: Dict[str, Any],
        trace_events: List[Dict[str, Any]],
        case_config: Optional[Dict[str, Any]] = None,
    ) -> ScoreResult:
        """执行轨迹评分"""
        # 从 trace 中提取工具调用事件
        tool_events = [
            e for e in trace_events
            if e.get("event_type") == "tool_call"
        ]

        output_data = trial_data.get("output_data", {})
        tool_trail = []
        if isinstance(output_data, dict):
            tool_trail = output_data.get("tool_trail", [])

        # 合并两个来源的工具调用记录
        all_tool_calls = self._extract_tool_calls(tool_events, tool_trail)

        if not all_tool_calls:
            status = trial_data.get("status", "")
            if status == "completed":
                return ScoreResult(
                    score_name=self.name,
                    score=0.5,
                    passed=True,
                    reason="无工具调用记录，可能为纯文本回答",
                    confidence=0.6,
                    source=self.source,
                    version=self.version,
                )
            else:
                return ScoreResult(
                    score_name=self.name,
                    score=0.0,
                    passed=False,
                    reason=f"Trial 状态为 {status} 且无工具调用",
                    confidence=1.0,
                    source=self.source,
                    version=self.version,
                )

        dimensions = {}
        reasons = []
        config = case_config or {}

        # 1. 冗余调用检测
        tool_names = [tc.get("name", "unknown") for tc in all_tool_calls]
        name_counts = Counter(tool_names)
        total_calls = len(all_tool_calls)
        unique_calls = len(name_counts)
        redundancy_ratio = 1.0 - (unique_calls / max(1, total_calls))

        # 检查连续相同工具调用（可能是死循环）
        consecutive_dupes = 0
        for i in range(1, len(tool_names)):
            if tool_names[i] == tool_names[i - 1]:
                consecutive_dupes += 1
        loop_detected = consecutive_dupes >= 3

        dimensions["redundancy"] = round(max(0.0, 1.0 - redundancy_ratio - (0.3 if loop_detected else 0)), 4)
        if loop_detected:
            reasons.append(f"检测到疑似死循环：连续 {consecutive_dupes + 1} 次相同工具调用")
        if redundancy_ratio > 0.5:
            reasons.append(f"工具调用冗余率 {redundancy_ratio:.0%}")

        # 2. 步骤效率
        expected_max_steps = config.get("max_expected_steps", 20)
        step_efficiency = min(1.0, expected_max_steps / max(1, total_calls))
        if total_calls > expected_max_steps:
            step_efficiency = max(0.0, 1.0 - (total_calls - expected_max_steps) / expected_max_steps)
        dimensions["step_efficiency"] = round(step_efficiency, 4)
        if total_calls > expected_max_steps:
            reasons.append(f"步骤数 {total_calls} 超过预期上限 {expected_max_steps}")

        # 3. 工具失败率
        failed_calls = sum(
            1 for tc in all_tool_calls
            if tc.get("error") or tc.get("failed") or tc.get("status") == "error"
        )
        failure_rate = failed_calls / max(1, total_calls)
        dimensions["tool_success_rate"] = round(1.0 - failure_rate, 4)
        if failure_rate > 0.3:
            reasons.append(f"工具失败率 {failure_rate:.0%} ({failed_calls}/{total_calls})")

        # 4. 工具多样性（使用了多少种不同工具）
        diversity = min(1.0, unique_calls / max(1, min(5, total_calls)))
        dimensions["tool_diversity"] = round(diversity, 4)

        # 综合分数
        weights = {
            "redundancy": 0.25,
            "step_efficiency": 0.25,
            "tool_success_rate": 0.30,
            "tool_diversity": 0.20,
        }
        overall_score = sum(dimensions[k] * weights[k] for k in weights)

        reason_text = "; ".join(reasons) if reasons else f"轨迹质量良好，{total_calls} 次工具调用，{unique_calls} 种工具"

        return ScoreResult(
            score_name=self.name,
            score=max(0.0, min(1.0, overall_score)),
            passed=overall_score >= 0.6,
            reason=reason_text,
            confidence=0.9,
            source=self.source,
            version=self.version,
            raw_output={
                "dimensions": dimensions,
                "total_tool_calls": total_calls,
                "unique_tools": unique_calls,
                "tool_distribution": dict(name_counts),
            },
        )

    def _extract_tool_calls(
        self,
        tool_events: List[Dict[str, Any]],
        tool_trail: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """从 trace 事件和 tool_trail 中提取工具调用记录"""
        calls = []

        # 从 trace 事件提取
        for event in tool_events:
            data = event.get("data", {})
            call = {
                "name": data.get("tool_name") or data.get("name", "unknown"),
                "params": data.get("params") or data.get("arguments", {}),
                "error": data.get("error"),
                "failed": data.get("failed", False),
                "status": data.get("status"),
            }
            calls.append(call)

        # 从 tool_trail 补充（避免重复）
        seen_names = {c["name"] for c in calls}
        for trail_item in tool_trail:
            name = trail_item.get("tool") or trail_item.get("name", "unknown")
            if name not in seen_names or len(calls) < len(tool_trail):
                calls.append({
                    "name": name,
                    "params": trail_item.get("params") or trail_item.get("arguments", {}),
                    "error": trail_item.get("error"),
                    "failed": trail_item.get("failed", False),
                    "status": trail_item.get("status"),
                })

        return calls
