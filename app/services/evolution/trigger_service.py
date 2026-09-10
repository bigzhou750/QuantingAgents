"""
自进化触发器服务

监听评测运行完成、趋势回退、Bad Case 阈值和定时任务事件，
判断是否需要创建自进化候选提案。
"""

import logging
from typing import Optional, Dict, Any, List

from app.core.config import settings
from app.core.database import get_mongo_db
from app.models.evolution import TriggerType
from app.services.evolution.clustering import cluster_failed_trials, identify_primary_failure_surface
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)


class TriggerService:
    """自进化触发器服务"""

    COLLECTION_EVENTS = "evolution_trigger_events"

    def __init__(self):
        self._initialized = False

    async def initialize(self):
        """初始化服务"""
        if self._initialized:
            return
        db = get_mongo_db()
        await db[self.COLLECTION_EVENTS].create_index("event_type")
        await db[self.COLLECTION_EVENTS].create_index("run_id")
        await db[self.COLLECTION_EVENTS].create_index("created_at")
        self._initialized = True
        logger.info("TriggerService initialized")

    async def on_run_completed(self, run_id: str) -> Optional[Dict[str, Any]]:
        """评测运行完成后的触发检查入口

        由 runner_service._execute_run 在 run 完成后调用。
        返回触发的提案信息或 None。
        """
        mode = settings.EVOLUTION_AUTOMATION_MODE
        if mode == "manual":
            # manual 模式只记录事件，不自动创建提案
            await self._log_event("run_completed", run_id, {"mode": "manual", "action": "logged_only"})
            logger.info(f"[Evolution] Run {run_id} completed (manual mode, logged only)")
            return None

        db = get_mongo_db()
        run_doc = await db["eval_runs"].find_one({"run_id": run_id})
        if not run_doc:
            return None

        dataset_id = run_doc.get("dataset_id", "")

        # 检查是否应触发
        trigger_info = await self._evaluate_triggers(run_id, dataset_id, run_doc)
        if not trigger_info:
            return None

        # 记录触发事件
        await self._log_event(
            trigger_info["trigger_type"],
            run_id,
            trigger_info,
        )

        logger.info(
            f"[Evolution] Trigger fired for run {run_id}: "
            f"type={trigger_info['trigger_type']}, surface={trigger_info.get('target_surface')}"
        )
        return trigger_info

    async def on_bad_case_event(self, bad_case: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """处理线上 Bad Case 事件。

        Bad Case 收集与自进化提案生成解耦：即使没有可用的 baseline run，
        样本仍会被保存，只记录触发被抑制的原因。
        """
        bad_case_id = str(bad_case.get("bad_case_id") or "")

        risk_level = str(bad_case.get("risk_level") or "medium")
        if risk_level in {"high", "critical"}:
            await self._log_event(
                "bad_case_high_risk",
                "",
                {
                    "bad_case_id": bad_case_id,
                    "risk_level": risk_level,
                    "failure_family": bad_case.get("failure_family"),
                    "action": "review_escalation",
                },
            )

        trigger = await self.check_bad_case_threshold("")
        if not trigger:
            return None

        db = get_mongo_db()
        latest_run = await db["eval_runs"].find_one(
            {"status": "completed"},
            sort=[("completed_at", -1)],
        )
        if not latest_run:
            await self._log_event(
                "bad_case_trigger_suppressed",
                "",
                {"bad_case_id": bad_case_id, "reason": "no_completed_baseline_run"},
            )
            return None

        trigger_info = {
            "trigger_type": TriggerType.BAD_CASE_THRESHOLD.value,
            "trigger_run_id": latest_run.get("run_id", ""),
            "dataset_id": latest_run.get("dataset_id", ""),
            "bad_case_detail": trigger,
            "target_surface": "case",
            "sample_failure_ids": trigger.get("sample_bad_case_ids", []),
        }
        if settings.EVOLUTION_AUTOMATION_MODE == "manual":
            trigger_info["action"] = "logged_only"
            await self._log_event("bad_case_threshold", latest_run.get("run_id", ""), trigger_info)
            return trigger_info

        from app.services.evolution.proposal_service import proposal_service

        proposal = await proposal_service.create_from_trigger(trigger_info)
        await self._log_event("bad_case_threshold", latest_run.get("run_id", ""), trigger_info)
        if proposal:
            trigger_info["proposal_id"] = proposal.proposal_id
        return trigger_info

    async def _evaluate_triggers(
        self, run_id: str, dataset_id: str, run_doc: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """评估所有触发条件，返回第一个命中的触发信息"""

        # 1. 检查趋势回退
        regression = await self.check_regression_trend(dataset_id)
        if regression:
            return {
                "trigger_type": TriggerType.REGRESSION.value,
                "trigger_run_id": run_id,
                "dataset_id": dataset_id,
                "regression_detail": regression,
                "target_surface": regression.get("target_surface", "unknown"),
                "sample_failure_ids": regression.get("sample_trial_ids", []),
            }

        # 2. 检查 Bad Case 阈值
        bad_case_trigger = await self.check_bad_case_threshold(dataset_id)
        if bad_case_trigger:
            return {
                "trigger_type": TriggerType.BAD_CASE_THRESHOLD.value,
                "trigger_run_id": run_id,
                "dataset_id": dataset_id,
                "bad_case_detail": bad_case_trigger,
                "target_surface": bad_case_trigger.get("target_surface", "unknown"),
                "sample_failure_ids": bad_case_trigger.get("sample_bad_case_ids", []),
            }

        # 3. 检查当前 run 的失败聚类是否有显著问题
        clustering = await cluster_failed_trials([run_id])
        failed_count = len(clustering.get("all_failed_trial_ids", []))
        total_trials = run_doc.get("completed_trials", 0) + run_doc.get("failed_trials", 0)
        if total_trials > 0 and failed_count / max(total_trials, 1) > 0.3:
            surface = identify_primary_failure_surface(clustering)
            return {
                "trigger_type": TriggerType.RUN_COMPLETED.value,
                "trigger_run_id": run_id,
                "dataset_id": dataset_id,
                "failure_rate": failed_count / max(total_trials, 1),
                "clustering": clustering,
                "target_surface": surface,
                "sample_failure_ids": clustering["all_failed_trial_ids"][:10],
            }

        return None

    async def check_regression_trend(self, dataset_id: str, window_size: int = 5) -> Optional[Dict[str, Any]]:
        """检查最近 N 次 run 的成功率是否出现显著回退"""
        db = get_mongo_db()
        threshold = settings.EVOLUTION_TRIGGER_REGRESSION_THRESHOLD

        cursor = (
            db["eval_runs"]
            .find({"dataset_id": dataset_id, "status": "completed"})
            .sort("completed_at", -1)
            .limit(window_size)
        )
        runs = []
        async for doc in cursor:
            runs.append(doc)

        if len(runs) < 2:
            return None

        # 比较最近一次与之前平均
        latest = runs[0]
        previous = runs[1:]

        latest_total = latest.get("completed_trials", 0) + latest.get("failed_trials", 0)
        latest_success_rate = latest.get("completed_trials", 0) / max(latest_total, 1)

        prev_rates = []
        for r in previous:
            t = r.get("completed_trials", 0) + r.get("failed_trials", 0)
            prev_rates.append(r.get("completed_trials", 0) / max(t, 1))

        avg_prev_rate = sum(prev_rates) / len(prev_rates) if prev_rates else 0

        drop = avg_prev_rate - latest_success_rate
        if drop >= threshold:
            # 对最新 run 做失败聚类以确定目标面
            clustering = await cluster_failed_trials([latest.get("run_id", "")])
            surface = identify_primary_failure_surface(clustering)
            return {
                "drop": round(drop, 4),
                "latest_success_rate": round(latest_success_rate, 4),
                "avg_previous_rate": round(avg_prev_rate, 4),
                "threshold": threshold,
                "target_surface": surface,
                "sample_trial_ids": clustering["all_failed_trial_ids"][:10],
            }

        return None

    async def check_bad_case_threshold(self, dataset_id: str) -> Optional[Dict[str, Any]]:
        """检查未处理的 Bad Case 数量是否超过阈值"""
        db = get_mongo_db()
        threshold = settings.EVOLUTION_TRIGGER_BAD_CASE_COUNT

        count = await db["eval_bad_cases"].count_documents({
            "converted_to_case_id": {"$exists": False},
            "detection_status": {"$ne": "rejected"},
        })

        if count >= threshold:
            # 获取最近的 bad case IDs
            cursor = (
                db["eval_bad_cases"]
                .find({
                    "converted_to_case_id": {"$exists": False},
                    "detection_status": {"$ne": "rejected"},
                })
                .sort("created_at", -1)
                .limit(20)
            )
            bad_case_ids = []
            async for doc in cursor:
                bad_case_ids.append(doc.get("bad_case_id", ""))

            return {
                "count": count,
                "threshold": threshold,
                "target_surface": "case",
                "sample_bad_case_ids": bad_case_ids,
            }

        return None

    async def scheduled_check(self) -> Optional[Dict[str, Any]]:
        """定时触发检查（由外部调度器调用）"""
        if not settings.EVOLUTION_SCHEDULE_CRON:
            return None

        from app.services.evolution.governance_service import governance_service
        window_key = f"scheduled:{now_tz().strftime('%Y%m%d%H%M')}"
        if not await governance_service.acquire_window_lock(window_key):
            return None

        # 查找最近完成的 run 作为基准
        db = get_mongo_db()
        latest_run = await db["eval_runs"].find_one(
            {"status": "completed"},
            sort=[("completed_at", -1)],
        )
        if not latest_run:
            return None

        run_id = latest_run.get("run_id", "")
        dataset_id = latest_run.get("dataset_id", "")

        try:
            trigger_info = await self._evaluate_triggers(run_id, dataset_id, latest_run)
        except Exception as exc:
            db = get_mongo_db()
            await db["evolution_trigger_failures"].insert_one({
                "window_key": window_key,
                "run_id": run_id,
                "error": str(exc)[:500],
                "created_at": now_tz(),
            })
            return None
        if trigger_info:
            trigger_info["trigger_type"] = TriggerType.SCHEDULED.value
            await self._log_event(TriggerType.SCHEDULED.value, run_id, trigger_info)

        return trigger_info

    async def _log_event(self, event_type: str, run_id: str, detail: Dict[str, Any]):
        """记录触发事件到 MongoDB"""
        db = get_mongo_db()
        await db[self.COLLECTION_EVENTS].insert_one({
            "event_type": event_type,
            "run_id": run_id,
            "detail": detail,
            "created_at": now_tz(),
        })

    async def get_recent_events(self, skip: int = 0, limit: int = 20) -> List[Dict[str, Any]]:
        """获取最近的触发事件"""
        db = get_mongo_db()
        cursor = db[self.COLLECTION_EVENTS].find().skip(skip).limit(limit).sort("created_at", -1)
        results = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            results.append(doc)
        return results


# 模块级单例
trigger_service = TriggerService()
