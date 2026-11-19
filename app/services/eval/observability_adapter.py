"""
观测平台适配器

支持将 trace 事件、评分结果导出到 Langfuse / Phoenix 等外部观测平台。
通过配置开关控制启停，关闭时不影响本地评测功能。

对应 spec 三期任务 3.1 + 3.2。
"""

import re
import json
import hashlib
import logging
from typing import Optional, List, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)


class ObservabilityBackend(str, Enum):
    """观测后端类型"""
    NONE = "none"
    LANGFUSE = "langfuse"
    PHOENIX = "phoenix"


# ==================== 脱敏规则 ====================

# 需要脱敏的模式
SENSITIVE_PATTERNS = [
    (re.compile(r'(?<!\d)\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}(?!\d)'), '[CARD_REDACTED]'),  # 银行卡号
    (re.compile(r'(?<!\d)\d{17}[\dXx](?!\d)'), '[ID_REDACTED]'),  # 身份证号
    (re.compile(r'(?<!\d)1[3-9]\d{9}(?!\d)'), '[PHONE_REDACTED]'),  # 手机号
    (re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}'), '[EMAIL_REDACTED]'),  # 邮箱
    (re.compile(r'(?:api[_\-]?key|token|secret|password)\s*[:=]\s*\S+', re.I), '[CREDENTIAL_REDACTED]'),  # API key
]

# 大文本阈值（字符数），超过此长度的内容将被摘要化存储
LARGE_TEXT_THRESHOLD = 5000


def redact_sensitive_data(text: str) -> str:
    """对文本执行脱敏处理"""
    if not isinstance(text, str):
        return text
    result = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def truncate_large_text(text: str, threshold: int = LARGE_TEXT_THRESHOLD) -> Dict[str, Any]:
    """大文本外存策略：超过阈值时返回摘要+引用标记"""
    if not isinstance(text, str):
        return {"content": text, "truncated": False}

    if len(text) <= threshold:
        return {"content": text, "truncated": False}

    content_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
    return {
        "content": f"[TRUNCATED: {len(text)} chars, hash={content_hash}]",
        "truncated": True,
        "original_length": len(text),
        "hash": content_hash,
    }


def sanitize_trace_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """递归清理 trace 数据：脱敏 + 大文本截断"""
    if not isinstance(data, dict):
        return data

    result = {}
    for key, value in data.items():
        if isinstance(value, str):
            # 先脱敏再截断
            cleaned = redact_sensitive_data(value)
            truncated = truncate_large_text(cleaned)
            result[key] = truncated["content"] if truncated["truncated"] else cleaned
        elif isinstance(value, dict):
            result[key] = sanitize_trace_data(value)
        elif isinstance(value, list):
            result[key] = [
                sanitize_trace_data(item) if isinstance(item, dict) else
                redact_sensitive_data(item) if isinstance(item, str) else item
                for item in value
            ]
        else:
            result[key] = value

    return result


# ==================== 观测适配器 ====================

class ObservabilityAdapter:
    """观测平台适配器"""

    def __init__(self):
        self._backend = ObservabilityBackend.NONE
        self._client = None
        self._enabled = False

    def configure(
        self,
        backend: str = "none",
        api_key: Optional[str] = None,
        host: Optional[str] = None,
        project: Optional[str] = None,
    ):
        """配置观测后端"""
        self._backend = ObservabilityBackend(backend)

        if self._backend == ObservabilityBackend.NONE:
            self._enabled = False
            logger.info("Observability adapter disabled")
            return

        try:
            if self._backend == ObservabilityBackend.LANGFUSE:
                self._init_langfuse(api_key, host, project)
            elif self._backend == ObservabilityBackend.PHOENIX:
                self._init_phoenix(api_key, host)
            self._enabled = True
            logger.info(f"Observability adapter enabled: {backend}")
        except Exception as e:
            logger.warning(f"Failed to init observability backend {backend}: {e}")
            self._enabled = False

    def _init_langfuse(self, api_key, host, project):
        try:
            from langfuse import Langfuse
            self._client = Langfuse(
                public_key=api_key,
                secret_key="",  # 简化配置
                host=host or "https://cloud.langfuse.com",
            )
        except ImportError:
            raise RuntimeError("langfuse package not installed")

    def _init_phoenix(self, api_key, host):
        try:
            import phoenix  # noqa: F401
            logger.info("Phoenix SDK available")
        except ImportError:
            raise RuntimeError("arize-phoenix package not installed")

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def export_trial(
        self,
        trial_id: str,
        trial_data: Dict[str, Any],
        trace_events: List[Dict[str, Any]],
        scores: List[Dict[str, Any]],
    ) -> bool:
        """将 trial 数据导出到观测平台"""
        if not self._enabled:
            return False

        try:
            # 脱敏处理
            sanitized_input = sanitize_trace_data(trial_data.get("input_data", {}))
            sanitized_output = sanitize_trace_data(trial_data.get("output_data", {}))
            sanitized_events = [sanitize_trace_data(e.get("data", {})) for e in trace_events]

            if self._backend == ObservabilityBackend.LANGFUSE and self._client:
                await self._export_to_langfuse(
                    trial_id, sanitized_input, sanitized_output,
                    sanitized_events, scores
                )

            logger.debug(f"Exported trial {trial_id} to {self._backend.value}")
            return True

        except Exception as e:
            logger.error(f"Failed to export trial {trial_id}: {e}")
            return False

    async def _export_to_langfuse(
        self,
        trial_id: str,
        input_data: Dict[str, Any],
        output_data: Dict[str, Any],
        events: List[Dict[str, Any]],
        scores: List[Dict[str, Any]],
    ):
        """导出到 Langfuse"""
        trace = self._client.trace(
            id=trial_id,
            name=f"eval_trial_{trial_id}",
            input=input_data,
            output=output_data,
            metadata={"source": "eval_platform", "event_count": len(events)},
        )

        # 添加评分
        for score in scores:
            trace.score(
                name=score.get("score_name", "unknown"),
                value=score.get("score", 0),
                comment=score.get("reason", ""),
            )

        self._client.flush()

    async def export_summary(
        self,
        run_id: str,
        metrics: Dict[str, Any],
    ) -> bool:
        """将 run 级别的汇总指标导出"""
        if not self._enabled:
            return False

        try:
            if self._backend == ObservabilityBackend.LANGFUSE and self._client:
                self._client.trace(
                    id=f"run_summary_{run_id}",
                    name=f"eval_run_{run_id}",
                    metadata=metrics,
                )
                self._client.flush()
            return True
        except Exception as e:
            logger.error(f"Failed to export run summary: {e}")
            return False


# 单例实例
observability_adapter = ObservabilityAdapter()
