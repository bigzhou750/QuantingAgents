"""
Agent 评测平台服务模块

提供 Vibe Agent runtime 的评测集管理、批量运行、trace 标准化、
分层评分、LLM-as-judge、人工复核、bad case 回流和评测报告能力。
"""

from app.services.eval.dataset_service import EvalDatasetService
from app.services.eval.runner_service import EvalRunnerService
from app.services.eval.trace_adapter import TraceAdapter
from app.services.eval.scorer_hub import ScorerHub

__all__ = [
    "EvalDatasetService",
    "EvalRunnerService",
    "TraceAdapter",
    "ScorerHub",
]
