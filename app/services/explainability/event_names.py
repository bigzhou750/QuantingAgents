"""运行事件中文名称映射。"""

from typing import Any, Dict


EVENT_NAME_MAP = {
    "session_created": "创建会话",
    "task_created": "创建任务",
    "task_queued": "任务排队",
    "task_started": "开始任务",
    "task_status": "任务状态变更",
    "message_created": "生成消息",
    "message.received": "接收消息",
    "tool_call": "调用工具",
    "tool_result": "工具返回",
    "decision": "形成决策",
    "evidence": "获取证据",
    "retrieval": "检索信息",
    "citation": "添加引用",
    "message": "生成消息",
    "skill_route": "路由技能",
    "skill_execute": "执行技能",
    "react_summary": "生成分析总结",
    "swarm_status": "协同分析状态",
    "attempt.created": "创建执行尝试",
    "attempt.started": "开始执行尝试",
    "attempt.completed": "完成执行尝试",
    "attempt.failed": "执行尝试失败",
    "attempt.cancelled": "取消执行尝试",
    "llm_call": "调用模型",
    "llm_usage": "模型用量",
    "error": "执行异常",
}


def event_display_name(event: Dict[str, Any]) -> str:
    """返回事件中文名称；未知事件保留原始名称。"""
    event_type = str(event.get("event_type") or event.get("type") or "")
    payload = event.get("payload") or event.get("data") or {}
    if not isinstance(payload, dict):
        payload = {}
    phase = str(payload.get("phase") or "")
    original_type = str((payload.get("_meta") or {}).get("original_type") or "")
    if event_type == "worker_status":
        event_type = original_type or phase or event_type
    if event_type == "tool_call" and str(payload.get("phase") or "") == "tool_result":
        return "工具返回"
    if phase in {"tool_result", "attempt.completed", "attempt.failed", "attempt.started"}:
        return EVENT_NAME_MAP.get(phase, "运行状态变更")
    return EVENT_NAME_MAP.get(event_type, "运行事件")
