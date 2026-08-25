import json
from typing import Any, Dict

from .models import VibeCommand

COMMAND_STREAM_KEY = "vibe_agent:commands"
WORKER_HEARTBEAT_KEY = "vibe_agent:worker:heartbeat"
WORKER_STATUS_KEY = "vibe_agent:worker:status"
WORKER_CONFIG_KEY = "vibe_agent:worker:config"


def session_event_channel(session_id: str) -> str:
    return f"vibe_agent:events:{session_id}"


def task_event_channel(task_id: str) -> str:
    return f"vibe_agent:tasks:{task_id}"


def encode_command(command: VibeCommand) -> Dict[str, str]:
    return {"data": command.model_dump_json()}


def encode_event_payload(event: Dict[str, Any]) -> str:
    return json.dumps(event, ensure_ascii=False, default=str)
