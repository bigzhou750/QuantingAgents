"""自进化生产治理策略：状态机、allowlist、预算、去重和门禁。"""

import hashlib
import json
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.core.config import get_settings
from app.core.database import get_mongo_db
from app.models.evolution import ProposalStatus, StopReason
from app.utils.timezone import now_tz


class EvolutionGovernanceService:
    """所有自进化入口共享的生产安全策略。"""

    PROPOSAL_COLLECTION = "evolution_proposals"
    VERIFICATION_COLLECTION = "evolution_verifications"
    EVENT_COLLECTION = "evolution_governance_events"
    CONFIG_COLLECTION = "evolution_governance_config"
    LOCK_COLLECTION = "evolution_trigger_locks"
    NOTIFICATION_COLLECTION = "evolution_notification_deliveries"
    FOLLOW_UP_COLLECTION = "evolution_follow_up_actions"

    TRANSITIONS = {
        ProposalStatus.DRAFT.value: {ProposalStatus.PENDING_VERIFY.value, ProposalStatus.STOPPED.value},
        ProposalStatus.PENDING_VERIFY.value: {ProposalStatus.VERIFYING.value, ProposalStatus.STOPPED.value},
        ProposalStatus.VERIFYING.value: {ProposalStatus.VERIFIED.value, ProposalStatus.DRAFT.value, ProposalStatus.STOPPED.value},
        ProposalStatus.VERIFIED.value: {ProposalStatus.APPROVED.value, ProposalStatus.REJECTED.value, ProposalStatus.STOPPED.value},
        ProposalStatus.APPROVED.value: {ProposalStatus.PROMOTED.value, ProposalStatus.STOPPED.value},
        ProposalStatus.REJECTED.value: set(),
        ProposalStatus.PROMOTED.value: {ProposalStatus.ROLLBACK.value},
        ProposalStatus.ROLLBACK.value: set(),
        ProposalStatus.STOPPED.value: set(),
    }

    async def initialize(self) -> None:
        db = get_mongo_db()
        await db[self.PROPOSAL_COLLECTION].create_index("fingerprint")
        await db[self.PROPOSAL_COLLECTION].create_index("idempotency_key", sparse=True)
        await db[self.PROPOSAL_COLLECTION].create_index([("target_artifact_id", 1), ("status", 1)])
        await db[self.EVENT_COLLECTION].create_index("created_at")
        await db[self.CONFIG_COLLECTION].create_index("config_id", unique=True)
        await db[self.LOCK_COLLECTION].create_index("lock_key", unique=True)
        await db[self.LOCK_COLLECTION].create_index("expires_at", expireAfterSeconds=0)
        await db[self.NOTIFICATION_COLLECTION].create_index("created_at")
        await db[self.FOLLOW_UP_COLLECTION].create_index("action_id", unique=True)
        await db[self.FOLLOW_UP_COLLECTION].create_index("artifact_id")
        await db[self.FOLLOW_UP_COLLECTION].create_index([("artifact_id", 1), ("created_at", -1)])
        await db[self.FOLLOW_UP_COLLECTION].create_index("status")

    async def notify(self, event: str, detail: Dict[str, Any]) -> Dict[str, Any]:
        """写入通知投递记录，并尽力复用现有站内通知服务。"""
        db = get_mongo_db()
        doc = {
            "event": event,
            "detail": detail,
            "status": "pending",
            "attempts": 0,
            "created_at": now_tz(),
        }
        result = await db[self.NOTIFICATION_COLLECTION].insert_one(doc)
        delivery_id = str(result.inserted_id)
        status, error = await self._deliver_notification(event, detail, delivery_id)
        await db[self.NOTIFICATION_COLLECTION].update_one(
            {"_id": result.inserted_id},
            {"$set": {"status": status, "attempts": 1, "error": error, "updated_at": now_tz()}},
        )
        doc.update({"_id": delivery_id, "status": status, "attempts": 1, "error": error})
        return doc

    async def _deliver_notification(self, event: str, detail: Dict[str, Any], delivery_id: str) -> tuple[str, Optional[str]]:
        try:
            db = get_mongo_db()
            admin = await db["users"].find_one({"is_admin": True}, {"_id": 1})
            if not admin:
                raise RuntimeError("no admin recipient")
            from app.models.notification import NotificationCreate
            from app.services.notifications_service import get_notifications_service
            await get_notifications_service().create_and_publish(NotificationCreate(
                user_id=str(admin["_id"]),
                type="alert",
                title=f"自进化事件：{event}",
                content=json.dumps(detail, ensure_ascii=False, default=str)[:2000],
                source="evolution",
                severity="warning" if "failed" in event or "stop" in event else "info",
                metadata={"delivery_id": delivery_id, "event": event},
            ))
            return "sent", None
        except Exception as exc:
            return "failed", str(exc)[:500]

    async def retry_failed_notifications(self, limit: int = 20) -> Dict[str, Any]:
        """重试最近失败的自进化通知，最多重试 3 次。"""
        db = get_mongo_db()
        cursor = db[self.NOTIFICATION_COLLECTION].find(
            {"status": "failed", "attempts": {"$lt": 3}}
        ).sort("created_at", -1).limit(limit)
        retried = 0
        for doc in await cursor.to_list(length=limit):
            delivery_id = str(doc["_id"])
            status, error = await self._deliver_notification(
                doc.get("event", "retry"), doc.get("detail", {}), delivery_id
            )
            attempts = int(doc.get("attempts", 0) or 0) + 1
            await db[self.NOTIFICATION_COLLECTION].update_one(
                {"_id": doc["_id"]},
                {"$set": {"status": status, "attempts": attempts, "error": error, "updated_at": now_tz()}},
            )
            retried += 1
        return {"retried": retried}

    def evaluate_post_release(
        self,
        metrics: Dict[str, Any],
        thresholds: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """判断发布后指标是否退化，并返回 rollback 建议。"""
        thresholds = thresholds or {
            "success_rate": 0.8,
            "safety_score": 0.8,
            "grounding_score": 0.6,
            "max_latency_ms": 30000,
            "max_cost_usd": 5.0,
        }
        checks = []
        success_rate = float(metrics.get("success_rate", 0) or 0)
        checks.append({"name": "success_rate", "passed": success_rate >= thresholds["success_rate"]})
        scores = metrics.get("score_aggregation", {}) or {}
        if "safety" in scores:
            checks.append({"name": "safety", "passed": float(scores["safety"].get("avg_score", 0) or 0) >= thresholds["safety_score"]})
        if "evidence_quality" in scores:
            checks.append({"name": "grounding", "passed": float(scores["evidence_quality"].get("avg_score", 0) or 0) >= thresholds["grounding_score"]})
        latency = metrics.get("latency", {}) or {}
        if latency.get("mean_ms"):
            checks.append({"name": "latency", "passed": float(latency["mean_ms"]) <= thresholds["max_latency_ms"]})
        cost = metrics.get("cost", {}) or {}
        if cost.get("total_usd") is not None:
            checks.append({"name": "cost", "passed": float(cost["total_usd"] or 0) <= thresholds["max_cost_usd"]})
        failed = [c for c in checks if not c["passed"]]
        return {
            "passed": not failed,
            "checks": checks,
            "failures": [c["name"] for c in failed],
            "rollback_suggestion": bool(failed),
        }

    async def get_config(self) -> Dict[str, Any]:
        """读取持久化治理配置；不存在时返回当前安全默认值。"""
        settings = get_settings()
        db = get_mongo_db()
        doc = await db[self.CONFIG_COLLECTION].find_one({"config_id": "default"})
        if doc:
            doc.pop("_id", None)
            return doc
        return {
            "config_id": "default",
            "cooldown_minutes": settings.EVOLUTION_COOLDOWN_MINUTES,
            "change_budget_chars": settings.EVOLUTION_CHANGE_BUDGET_CHARS,
            "daily_cost_budget_usd": settings.EVOLUTION_DAILY_COST_BUDGET_USD,
            "require_smoke_test": settings.EVOLUTION_REQUIRE_SMOKE_TEST,
            "updated_at": None,
        }

    async def update_config(self, values: Dict[str, Any]) -> Dict[str, Any]:
        """持久化治理配置并同步当前进程 settings。"""
        settings = get_settings()
        allowed = {
            "cooldown_minutes": "EVOLUTION_COOLDOWN_MINUTES",
            "change_budget_chars": "EVOLUTION_CHANGE_BUDGET_CHARS",
            "daily_cost_budget_usd": "EVOLUTION_DAILY_COST_BUDGET_USD",
            "require_smoke_test": "EVOLUTION_REQUIRE_SMOKE_TEST",
        }
        doc = {"config_id": "default"}
        for key, setting_name in allowed.items():
            if key in values and values[key] is not None:
                setattr(settings, setting_name, values[key])
                doc[key] = values[key]
        doc["updated_at"] = now_tz()
        db = get_mongo_db()
        await db[self.CONFIG_COLLECTION].update_one(
            {"config_id": "default"}, {"$set": doc}, upsert=True
        )
        result = await self.get_config()
        if isinstance(result.get("updated_at"), datetime):
            result["updated_at"] = result["updated_at"].isoformat()
        return result

    @staticmethod
    def fingerprint(trigger_info: Dict[str, Any], artifact_id: str) -> str:
        payload = {"artifact_id": artifact_id, "trigger": trigger_info}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()

    async def find_active_duplicate(self, fingerprint: str) -> Optional[Dict[str, Any]]:
        db = get_mongo_db()
        return await db[self.PROPOSAL_COLLECTION].find_one({
            "fingerprint": fingerprint,
            "status": {"$in": [ProposalStatus.DRAFT.value, ProposalStatus.PENDING_VERIFY.value, ProposalStatus.VERIFYING.value, ProposalStatus.VERIFIED.value, ProposalStatus.APPROVED.value]},
        })

    async def check_cooldown(self, target_artifact_id: str, fingerprint: str) -> Optional[Dict[str, Any]]:
        """检查同一目标是否仍在冷却窗口内。"""
        settings = get_settings()
        minutes = int(settings.EVOLUTION_COOLDOWN_MINUTES or 0)
        if minutes <= 0:
            return None
        db = get_mongo_db()
        cutoff = now_tz() - timedelta(minutes=minutes)
        recent = await db[self.PROPOSAL_COLLECTION].find_one(
            {
                "target_artifact_id": target_artifact_id,
                "created_at": {"$gte": cutoff},
            },
            sort=[("created_at", -1)],
        )
        if not recent:
            return None
        return {
            "blocked": True,
            "target_artifact_id": target_artifact_id,
            "fingerprint": fingerprint,
            "cooldown_minutes": minutes,
            "latest_proposal_id": recent.get("proposal_id", ""),
            "latest_created_at": recent.get("created_at"),
        }

    async def create_follow_up_action(
        self,
        action_type: str,
        source: str,
        artifact_id: str,
        receipt_id: str = "",
        proposal_id: str = "",
        detail: Optional[Dict[str, Any]] = None,
        severity: str = "warning",
    ) -> Dict[str, Any]:
        """创建可追踪的后续自动动作候选，并记录事件链路。"""
        db = get_mongo_db()
        settings = get_settings()
        window_minutes = int(settings.EVOLUTION_FOLLOW_UP_WINDOW_MINUTES or 60)
        cutoff = now_tz() - timedelta(minutes=window_minutes)
        recent_count = await db[self.FOLLOW_UP_COLLECTION].count_documents({
            "artifact_id": artifact_id,
            "created_at": {"$gte": cutoff},
        })
        escalation_level = int(recent_count) + 1
        action_id = f"evact_{uuid.uuid4().hex[:12]}"
        doc = {
            "action_id": action_id,
            "action_type": action_type,
            "source": source,
            "artifact_id": artifact_id,
            "receipt_id": receipt_id,
            "proposal_id": proposal_id,
            "severity": severity,
            "escalation_level": escalation_level,
            "status": "pending",
            "detail": detail or {},
            "created_at": now_tz(),
        }
        await db[self.FOLLOW_UP_COLLECTION].insert_one(doc)
        await db[self.EVENT_COLLECTION].insert_one({
            "event": f"follow_up_{action_type}",
            "artifact_id": artifact_id,
            "proposal_id": proposal_id,
            "receipt_id": receipt_id,
            "detail": {
                "action_id": action_id,
                "source": source,
                "escalation_level": escalation_level,
                "severity": severity,
            },
            "created_at": now_tz(),
        })
        await db["evolution_event_log"].insert_one({
            "event_type": "follow_up_action_created",
            "proposal_id": proposal_id,
            "artifact_id": artifact_id,
            "actor": "system",
            "detail": {
                "action_id": action_id,
                "action_type": action_type,
                "source": source,
                "escalation_level": escalation_level,
            },
            "created_at": now_tz(),
        })
        return doc

    async def route_post_release_observation(
        self,
        receipt,
        metrics: Dict[str, Any],
    ) -> Dict[str, Any]:
        """把发布后观测结果自动写入后续动作候选，并支持升级为 stop。"""
        result = self.evaluate_post_release(metrics)
        actions = []
        failures = result.get("failures", [])
        artifact_id = receipt.artifact_id or ""
        severity = "critical" if "safety" in failures or len(failures) >= 3 else "warning"

        if result.get("rollback_suggestion"):
            actions.append(await self.create_follow_up_action(
                action_type="rollback",
                source="post_release_observe",
                artifact_id=artifact_id,
                receipt_id=receipt.receipt_id,
                proposal_id=receipt.proposal_id,
                detail={
                    "rollback_target_version": receipt.baseline_artifact_version,
                    "failures": failures,
                    "metrics": {key: metrics.get(key) for key in list(metrics)[:12]},
                },
                severity=severity,
            ))

        if failures and len(actions) == 0:
            actions.append(await self.create_follow_up_action(
                action_type="bad_case",
                source="post_release_observe",
                artifact_id=artifact_id,
                receipt_id=receipt.receipt_id,
                proposal_id=receipt.proposal_id,
                detail={
                    "failures": failures,
                    "metrics": {key: metrics.get(key) for key in list(metrics)[:12]},
                },
                severity=severity,
            ))

        latest_action = actions[-1] if actions else {}
        if latest_action.get("escalation_level", 0) >= 3:
            actions.append(await self.create_follow_up_action(
                action_type="stop",
                source="post_release_observe_escalation",
                artifact_id=artifact_id,
                receipt_id=receipt.receipt_id,
                proposal_id=receipt.proposal_id,
                detail={
                    "auto_stop_candidate": True,
                    "failures": failures,
                    "escalation_level": latest_action["escalation_level"],
                },
                severity="critical",
            ))

        result["follow_up_actions"] = actions
        result["event_chain"] = [
            {"event": "post_release_observed", "rollback_suggestion": result.get("rollback_suggestion")},
        ] + [{"event": "follow_up_action_created", "action_id": action.get("action_id")} for action in actions]
        return result

    async def list_follow_up_actions(
        self,
        artifact_id: Optional[str] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        db = get_mongo_db()
        query: Dict[str, Any] = {}
        if artifact_id:
            query["artifact_id"] = artifact_id
        if status:
            query["status"] = status
        cursor = db[self.FOLLOW_UP_COLLECTION].find(query).skip(skip).limit(limit).sort("created_at", -1)
        results = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            results.append(doc)
        return results

    async def acquire_window_lock(self, lock_key: str, ttl_seconds: int = 300) -> bool:
        """为定时 trigger 获取短期窗口锁，重复执行时直接跳过。"""
        from pymongo.errors import DuplicateKeyError
        db = get_mongo_db()
        try:
            await db[self.LOCK_COLLECTION].insert_one({
                "lock_key": lock_key,
                "expires_at": datetime.utcnow() + timedelta(seconds=ttl_seconds),
                "created_at": now_tz(),
            })
            return True
        except DuplicateKeyError:
            return False

    async def acquire_proposal_lock(self, proposal_id: str, ttl_seconds: int = 300) -> str:
        """为 promote/rollback 获取 proposal 级互斥锁。"""
        import uuid
        db = get_mongo_db()
        lock_id = f"lock_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()
        result = await db[self.PROPOSAL_COLLECTION].update_one(
            {
                "proposal_id": proposal_id,
                "$or": [
                    {"lock_expires_at": {"$exists": False}},
                    {"lock_expires_at": {"$lte": now}},
                ],
            },
            {"$set": {
                "lock_id": lock_id,
                "lock_expires_at": now + timedelta(seconds=ttl_seconds),
                "updated_at": now_tz(),
            }},
        )
        if result.modified_count != 1:
            raise ValueError("proposal is locked by another operation")
        return lock_id

    async def validate_target(self, artifact_id: str, artifact_type: str, path: str = "", sections: Optional[list] = None) -> None:
        settings = get_settings()
        allowed = {x.strip() for x in settings.EVOLUTION_ALLOWED_ARTIFACT_TYPES.split(",") if x.strip()}
        if artifact_type not in allowed:
            raise ValueError(f"artifact type not allowed: {artifact_type}")
        db = get_mongo_db()
        entry = await db["evolution_artifact_registry"].find_one({"artifact_id": artifact_id})
        if not entry:
            raise ValueError(f"artifact not registered: {artifact_id}")
        patterns = entry.get("allowlist_patterns") or []
        if patterns and (not path or not any(p in path for p in patterns)):
            raise ValueError(f"artifact path is outside allowlist: {path}")
        for section in sections or []:
            if patterns and not any(p in section for p in patterns):
                raise ValueError(f"artifact section is outside allowlist: {section}")

    def validate_change_budget(self, diff: Dict[str, Any]) -> None:
        settings = get_settings()
        size = len(json.dumps(diff, ensure_ascii=False, default=str))
        if size > settings.EVOLUTION_CHANGE_BUDGET_CHARS:
            raise ValueError(f"change budget exceeded: {size} > {settings.EVOLUTION_CHANGE_BUDGET_CHARS}")

    async def assert_verification_budget(self) -> None:
        """验证前检查每日验证次数和累计候选成本。"""
        settings = get_settings()
        start_of_day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        db = get_mongo_db()
        cursor = db[self.VERIFICATION_COLLECTION].find(
            {"created_at": {"$gte": start_of_day}},
            {"comparison_result": 1},
        )
        run_count = 0
        total_cost = 0.0
        async for doc in cursor:
            run_count += 1
            comparison = doc.get("comparison_result") or {}
            candidate = comparison.get("candidate") or {}
            total_cost += float((candidate.get("cost") or {}).get("total_usd", 0) or 0)

        if run_count >= settings.EVOLUTION_BUDGET_MAX_RUNS_PER_DAY:
            raise ValueError(
                f"daily evolution verification budget exceeded: {run_count} >= "
                f"{settings.EVOLUTION_BUDGET_MAX_RUNS_PER_DAY}"
            )
        if total_cost >= settings.EVOLUTION_DAILY_COST_BUDGET_USD:
            raise ValueError(
                f"daily evolution cost budget exceeded: {total_cost:.4f} >= "
                f"{settings.EVOLUTION_DAILY_COST_BUDGET_USD:.4f}"
            )

    async def assert_no_repeated_failure(self, fingerprint: str, artifact_id: str, proposal_id: str) -> None:
        """连续同类失败达到阈值时停止闭环。"""
        settings = get_settings()
        db = get_mongo_db()
        count = await db[self.PROPOSAL_COLLECTION].count_documents({
            "fingerprint": fingerprint,
            "target_artifact_id": artifact_id,
        })
        if count >= 3:
            await self.stop(
                proposal_id,
                StopReason.REPEATED_FAILURES,
                {"fingerprint": fingerprint, "artifact_id": artifact_id, "count": count},
            )
            raise ValueError("repeated failure threshold exceeded")

    async def transition(self, proposal_id: str, target: ProposalStatus) -> Dict[str, Any]:
        db = get_mongo_db()
        current = await db[self.PROPOSAL_COLLECTION].find_one({"proposal_id": proposal_id})
        if not current:
            raise ValueError(f"Proposal {proposal_id} not found")
        current_status = current.get("status", ProposalStatus.DRAFT.value)
        if target.value not in self.TRANSITIONS.get(current_status, set()):
            raise ValueError(f"invalid proposal transition: {current_status} -> {target.value}")
        result = await db[self.PROPOSAL_COLLECTION].update_one(
            {"proposal_id": proposal_id, "status": current_status},
            {"$set": {"status": target.value, "updated_at": now_tz()}},
        )
        if result.modified_count != 1:
            raise ValueError("proposal changed concurrently; retry")
        return {"from": current_status, "to": target.value}

    async def stop(self, proposal_id: str, reason: StopReason, detail: Optional[Dict[str, Any]] = None) -> None:
        db = get_mongo_db()
        await db[self.PROPOSAL_COLLECTION].update_one(
            {"proposal_id": proposal_id, "status": {"$nin": [ProposalStatus.PROMOTED.value, ProposalStatus.ROLLBACK.value]}},
            {"$set": {"status": ProposalStatus.STOPPED.value, "stop_reason": reason.value, "updated_at": now_tz(), "gate_result": detail or {}}},
        )
        await db[self.EVENT_COLLECTION].insert_one({"event": "stop", "proposal_id": proposal_id, "reason": reason.value, "detail": detail or {}, "created_at": now_tz()})
        await self.notify("proposal_stop", {"proposal_id": proposal_id, "reason": reason.value})


governance_service = EvolutionGovernanceService()
