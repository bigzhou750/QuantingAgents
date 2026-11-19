"""Bad Case 去重指纹和来源标识工具。"""

import hashlib
import json
import re
from typing import Any, Dict, Optional


VOLATILE_KEYS = {
    "session_id",
    "task_id",
    "user_id",
    "created_at",
    "updated_at",
    "started_at",
    "finished_at",
    "id",
    "_id",
}


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def _canonicalize(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key in VOLATILE_KEYS or key.startswith("_"):
                continue
            cleaned = _canonicalize(item)
            if cleaned not in (None, "", [], {}):
                result[str(key)] = cleaned
        return result
    if isinstance(value, list):
        cleaned_items = [_canonicalize(item) for item in value]
        return [item for item in cleaned_items if item not in (None, "", [], {})]
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip()
    return value


def canonicalize_for_fingerprint(value: Any) -> str:
    """生成稳定、去时变字段的规范化 JSON。"""
    return _stable_json(_canonicalize(value))


def normalize_failure_signature(failure_reason: str, signal_types: Optional[list] = None) -> str:
    """将失败原因和信号类型压缩为稳定签名。"""
    normalized = re.sub(r"\s+", " ", str(failure_reason or "")).strip()[:160]
    signal_part = ",".join(sorted(signal_types or []))
    return f"{normalized}|{signal_part}".lower()


def compute_dedup_key(
    input_data: Dict[str, Any],
    failure_family: str,
    failure_reason: str,
    artifact_version: Optional[str] = None,
    data_window: Optional[Dict[str, Any]] = None,
    signal_types: Optional[list] = None,
) -> str:
    """基于输入、失败家族、失败特征、版本和数据窗口生成指纹。"""
    payload = {
        "input": canonicalize_for_fingerprint(input_data),
        "failure_family": str(failure_family or ""),
        "failure_signature": normalize_failure_signature(failure_reason, signal_types),
        "artifact_version": str(artifact_version or ""),
        "data_window": canonicalize_for_fingerprint(data_window or {}),
    }
    raw = _stable_json(payload)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def hash_user_id(user_id: str) -> str:
    """生成不包含原始用户 ID 的短哈希。"""
    return hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()[:16]
