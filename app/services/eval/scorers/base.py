"""
评分器基类

定义评分器的通用接口和数据结构。
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from app.models.eval import ScoreSource


@dataclass
class ScoreResult:
    """评分结果"""
    score_name: str
    score: float  # 0.0 - 1.0
    passed: bool
    reason: str
    confidence: float = 1.0  # 0.0 - 1.0
    source: ScoreSource = ScoreSource.RULE_BASED
    version: str = "1.0.0"
    evidence_refs: List[str] = field(default_factory=list)
    raw_output: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score_name": self.score_name,
            "score": round(self.score, 4),
            "passed": self.passed,
            "reason": self.reason,
            "confidence": round(self.confidence, 4),
            "source": self.source.value,
            "version": self.version,
            "evidence_refs": self.evidence_refs,
            "raw_output": self.raw_output,
        }


class BaseScorer(ABC):
    """评分器基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """评分器名称"""
        pass

    @property
    @abstractmethod
    def source(self) -> ScoreSource:
        """评分来源"""
        pass

    @property
    def version(self) -> str:
        """评分器版本"""
        return "1.0.0"

    @abstractmethod
    async def score(
        self,
        trial_data: Dict[str, Any],
        trace_events: List[Dict[str, Any]],
        case_config: Optional[Dict[str, Any]] = None,
    ) -> ScoreResult:
        """
        执行评分

        Args:
            trial_data: trial 数据，包含 input_data、output_data、status 等
            trace_events: trace 事件列表
            case_config: case 级别的评分配置

        Returns:
            ScoreResult: 评分结果
        """
        pass

    def _calculate_score(self, passed_checks: int, total_checks: int) -> float:
        """计算分数（通过检查数 / 总检查数）"""
        if total_checks == 0:
            return 1.0
        return passed_checks / total_checks
