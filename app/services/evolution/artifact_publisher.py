"""Artifact 发布 materialization 服务。

版本内容以 MongoDB 为权威来源；文件系统只承担当前环境的可运行 materialization。
Skill 写入可配置 runtime root，非 Skill 写入按 artifact 类型隔离的配置目录。
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, Any, List

from app.core.config import settings
from app.models.evolution import ArtifactType, ArtifactVersion

logger = logging.getLogger(__name__)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def evolution_artifact_runtime_root() -> Path:
    configured = getattr(
        settings,
        "EVOLUTION_ARTIFACT_RUNTIME_ROOT",
        "~/.quantingagents/runtime/evolution-artifacts",
    )
    root = Path(str(configured)).expanduser().resolve()
    project_root = _project_root()
    if root == project_root or project_root in root.parents:
        raise ValueError("EVOLUTION_ARTIFACT_RUNTIME_ROOT must be outside the source tree")
    return root


def legacy_user_skills_dir() -> Path:
    return Path.home() / ".zhitouagent" / "skills" / "user"


def _safe_component(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
    cleaned = cleaned.strip("._")
    if not cleaned:
        raise ValueError(f"unsafe artifact path component: {value!r}")
    return cleaned


def _artifact_type_dir(
    artifact_type: ArtifactType,
    artifact_id: str,
    version: str,
    environment: str = "default",
) -> Path:
    return (
        evolution_artifact_runtime_root()
        / _safe_component(environment)
        / "artifacts"
        / _safe_component(artifact_type.value)
        / _safe_component(artifact_id)
        / _safe_component(version)
    )


def skill_user_dir(environment: str = "default") -> Path:
    return evolution_artifact_runtime_root() / _safe_component(environment) / "skills" / "user"


class ArtifactPublisher:
    """按 artifact 类型 materialize 不可变版本。"""

    async def materialize(self, version: ArtifactVersion, environment: str = "default") -> Dict[str, Any]:
        if version.artifact_type == ArtifactType.SKILL:
            return await self._materialize_skill(version, environment)
        return await self._materialize_config(version, environment)

    async def _materialize_skill(self, version: ArtifactVersion, environment: str) -> Dict[str, Any]:
        skill_name = version.artifact_id.replace("art_skill_", "")
        skill_name = _safe_component(skill_name)
        content = (version.content_snapshot or {}).get("content", "")
        if not content:
            raise ValueError(f"Skill version {version.version} has no content snapshot")
        target = skill_user_dir(environment) / skill_name / "SKILL.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        logger.info("Materialized skill %s v%s -> %s", version.artifact_id, version.version, target)
        return {
            "environment": environment,
            "artifact_id": version.artifact_id,
            "artifact_type": version.artifact_type.value,
            "version": version.version,
            "root": str(target.parent),
            "files": [str(target)],
            "materialized_at": self._now_iso(),
        }

    async def _materialize_config(self, version: ArtifactVersion, environment: str) -> Dict[str, Any]:
        target_dir = _artifact_type_dir(
            version.artifact_type,
            version.artifact_id,
            version.version,
            environment,
        )
        target = target_dir / "artifact.json"
        target_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "artifact_id": version.artifact_id,
            "artifact_type": version.artifact_type.value,
            "version": version.version,
            "content_snapshot": version.content_snapshot,
            "materialized_at": self._now_iso(),
        }
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(
            "Materialized %s %s v%s -> %s",
            version.artifact_type.value,
            version.artifact_id,
            version.version,
            target,
        )
        return {
            "environment": environment,
            "artifact_id": version.artifact_id,
            "artifact_type": version.artifact_type.value,
            "version": version.version,
            "root": str(target_dir),
            "files": [str(target)],
            "materialized_at": self._now_iso(),
        }

    def runtime_skill_paths(self, artifact_id: str, environment: str = "default") -> List[Path]:
        skill_name = _safe_component(artifact_id.replace("art_skill_", ""))
        return [
            skill_user_dir(environment) / skill_name / "SKILL.md",
            legacy_user_skills_dir() / skill_name / "SKILL.md",
        ]

    @staticmethod
    def _now_iso() -> str:
        from app.utils.timezone import now_tz
        return now_tz().isoformat()


artifact_publisher = ArtifactPublisher()
