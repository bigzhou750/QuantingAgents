"""
规则评分器

基于确定性规则进行评分，包括：
- 输出 schema 检查
- 字段完整性检查
- token 使用检查
- 耗时检查
- 工具调用检查
- 权限拒绝检查
- 状态检查
"""

import logging
from typing import Optional, List, Dict, Any

from app.models.eval import ScoreSource, TrialStatus
from app.services.eval.scorers.base import BaseScorer, ScoreResult

logger = logging.getLogger(__name__)


class RuleBasedScorer(BaseScorer):
    """规则评分器"""

    @property
    def name(self) -> str:
        return "rule_based"

    @property
    def source(self) -> ScoreSource:
        return ScoreSource.RULE_BASED

    async def score(
        self,
        trial_data: Dict[str, Any],
        trace_events: List[Dict[str, Any]],
        case_config: Optional[Dict[str, Any]] = None,
    ) -> ScoreResult:
        """执行规则评分"""
        checks = []
        reasons = []

        # 1. 状态检查
        status = trial_data.get("status", "")
        if status == TrialStatus.COMPLETED.value:
            checks.append(True)
        else:
            checks.append(False)
            reasons.append(f"Trial 状态为 {status}，非 completed")

        # 2. 输出存在性检查
        output_data = trial_data.get("output_data")
        if output_data is not None and output_data != {}:
            checks.append(True)
        else:
            checks.append(False)
            reasons.append("缺少输出数据")

        # 3. 错误消息检查
        error_message = trial_data.get("error_message")
        if error_message:
            checks.append(False)
            reasons.append(f"存在错误: {error_message[:100]}")
        else:
            checks.append(True)

        # 4. 耗时检查（如果有配置）
        config = case_config or {}
        max_latency_ms = config.get("max_latency_ms")
        latency_ms = trial_data.get("latency_ms", 0)
        if max_latency_ms and latency_ms > max_latency_ms:
            checks.append(False)
            reasons.append(f"耗时 {latency_ms}ms 超过限制 {max_latency_ms}ms")
        elif max_latency_ms:
            checks.append(True)

        # 5. Token 使用检查（如果有配置）
        max_tokens = config.get("max_tokens")
        token_usage = trial_data.get("token_usage", {})
        total_tokens = sum(token_usage.values()) if isinstance(token_usage, dict) else 0
        if max_tokens and total_tokens > max_tokens:
            checks.append(False)
            reasons.append(f"Token 使用 {total_tokens} 超过限制 {max_tokens}")
        elif max_tokens:
            checks.append(True)

        # 6. Trace 事件存在性检查
        if len(trace_events) > 0:
            checks.append(True)
        else:
            checks.append(False)
            reasons.append("缺少 trace 事件")

        # 7. 权限拒绝检查（从 trace 事件中查找）
        permission_denied = False
        for event in trace_events:
            event_type = event.get("event_type", "")
            data = event.get("data", {})
            if event_type == "tool_call":
                result = data.get("result", {})
                if isinstance(result, dict) and result.get("permission_denied"):
                    permission_denied = True
                    break

        if permission_denied:
            checks.append(False)
            reasons.append("检测到权限拒绝")
        else:
            checks.append(True)

        # 计算分数
        passed_checks = sum(1 for c in checks if c)
        total_checks = len(checks)
        score = self._calculate_score(passed_checks, total_checks)

        reason_text = "; ".join(reasons) if reasons else f"通过 {passed_checks}/{total_checks} 项检查"

        return ScoreResult(
            score_name="rule_based",
            score=score,
            passed=score >= 0.8,  # 80% 以上视为通过
            reason=reason_text,
            confidence=1.0,
            source=self.source,
            version=self.version,
        )
