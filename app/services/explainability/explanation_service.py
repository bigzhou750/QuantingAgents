"""分层业务解释生成服务。

生成面向开发者、业务人员和终端用户的解释，用户层只使用决策记录和
证据摘要，不暴露原始模型推理内容。
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.models.decision import ExplanationLayer, LayeredExplanation
from app.utils.timezone import now_tz


def _as_dict(value: Any) -> Dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value or {}


class ExplanationService:
    """基于结构化决策记录生成三层解释。"""

    VERSION = "1.0.0"

    def generate(
        self,
        decision: Any,
        *,
        evidence_texts: Optional[List[str]] = None,
        output_text: str = "",
    ) -> LayeredExplanation:
        record = _as_dict(decision)
        business_id = record.get("business_id")
        task_id = record.get("task_id")
        session_id = record.get("session_id")
        decision_id = record.get("decision_id")
        scenario = str(record.get("scenario") or "Agent 决策")
        selected = str(record.get("selected_option") or "未记录")
        reason = str(record.get("selection_reason") or "")
        conclusion = str(record.get("conclusion") or output_text or "未生成结论")
        candidates = record.get("candidates") or []
        evidence_ids = record.get("evidence_ids") or []
        evidence_texts = evidence_texts or []

        if reason in {"candidates_unavailable", "reason_unavailable"}:
            user_text = (
                f"系统完成了“{scenario}”决策，但本次没有留存可解释的候选和选择依据；"
                f"当前结论为：{conclusion[:200]}。"
            )
        else:
            user_text = (
                f"系统在“{scenario}”中选择了“{selected}”，"
                f"依据是{reason}，最终结论为：{conclusion[:200]}。"
            )

        business_text = (
            f"本次“{scenario}”决策选择：{selected}。\n"
            f"选择依据：{reason or '未提供'}。\n"
            f"最终结论：{conclusion[:1000]}。\n"
            f"关联证据：{len(evidence_ids)} 条。"
        )

        candidate_detail = "；".join(
            f"{item.get('label') or item.get('option_id')}"
            f"{'（未选原因：' + str(item.get('rejected_reason')) + '）' if item.get('rejected_reason') else ''}"
            for item in candidates
        ) or "候选不可用"
        developer_text = (
            f"decision_id={decision_id}\n"
            f"decision_type={record.get('decision_type')}\n"
            f"sequence={record.get('sequence')}\n"
            f"scenario={scenario}\n"
            f"candidates={candidate_detail}\n"
            f"selected_option={selected}\n"
            f"selection_reason={reason}\n"
            f"conclusion={conclusion}\n"
            f"evidence_ids={evidence_ids}\n"
            f"risk_level={record.get('risk_level')}\n"
            f"model_version={record.get('model_version')}\n"
            f"strategy_version={record.get('strategy_version')}\n"
            f"evidence_count={len(evidence_texts)}"
        )

        return LayeredExplanation(
            explanation_id=f"exp_{uuid.uuid4().hex[:12]}",
            business_id=business_id,
            task_id=task_id,
            session_id=session_id,
            decision_id=decision_id,
            developer=ExplanationLayer(
                text=developer_text,
                source="explanation_service",
                generated_at=now_tz(),
            ),
            business=ExplanationLayer(
                text=business_text,
                source="explanation_service",
                generated_at=now_tz(),
            ),
            user=ExplanationLayer(
                text=user_text,
                source="explanation_service",
                generated_at=now_tz(),
            ),
            version=self.VERSION,
            source="explanation_service",
            created_at=now_tz(),
        )


explanation_service = ExplanationService()
