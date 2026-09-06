"""
评测运行服务

负责评测运行的创建、执行、trial 管理和状态跟踪。
对接 Vibe Agent runtime，支持多 trial、超时、取消和预算限制。
"""

import asyncio
import logging
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime

from app.core.database import get_mongo_db
from app.core.config import settings
from app.models.eval import (
    EvalRun, EvalTrial, RunStatus, TrialStatus, EvalRunConfig, RunSnapshot,
)
from app.services.eval.dataset_service import dataset_service
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)


def _make_trace_sink(trial_id: str):
    """
    构造一个绑定到指定 trial 的事件回调，将 embedded_agent_runtime 推送的
    (event_type, payload) 事件对接到 trace_adapter，归一化并落盘为标准
    trace 事件（对应 spec: MUST 记录与该 trial 关联的结构化事件序列）。

    embedded_agent_runtime 调用 sink 时传入的是两个独立参数
    (event_type: str, payload: dict)，而 TraceAdapter.adapt_vibe_event()
    期望的是一个组合字典，字段名为 "type"/"data"（而不是
    "event_type"/"payload"），因此这里需要做一次字段名转换，而不能直接
    转发原始参数。

    必须是异步函数：embedded_agent_runtime 内部通过
    asyncio.run_coroutine_threadsafe 调度 sink 回调，要求返回协程对象。
    """
    sequence_counter = {"n": 0}

    async def _sink(event_type: str, payload: Dict[str, Any]) -> None:
        try:
            from app.services.eval.trace_adapter import trace_adapter

            sequence_counter["n"] += 1
            vibe_event = {
                "type": event_type,
                "data": payload if isinstance(payload, dict) else {"raw": payload},
            }
            trace_event = trace_adapter.adapt_vibe_event(
                vibe_event, trial_id=trial_id, sequence=sequence_counter["n"]
            )
            if trace_event:
                await trace_adapter.save_single_event(trace_event)
        except Exception:
            # trace 记录失败不应该影响 trial 本身的执行
            logger.warning(f"Failed to record trace event for trial {trial_id}", exc_info=True)

    return _sink


class EvalRunnerService:
    """评测运行服务"""

    COLLECTION_RUNS = "eval_runs"
    COLLECTION_TRIALS = "eval_trials"

    def __init__(self):
        self._initialized = False
        self._running_tasks: Dict[str, asyncio.Task] = {}

    async def initialize(self):
        """初始化服务，创建索引"""
        if self._initialized:
            return

        logger.info("Initializing EvalRunnerService")
        db = get_mongo_db()

        # 创建索引
        await db[self.COLLECTION_RUNS].create_index("run_id", unique=True)
        await db[self.COLLECTION_RUNS].create_index("dataset_id")
        await db[self.COLLECTION_RUNS].create_index("status")
        await db[self.COLLECTION_RUNS].create_index("created_at")

        await db[self.COLLECTION_TRIALS].create_index("trial_id", unique=True)
        await db[self.COLLECTION_TRIALS].create_index("run_id")
        await db[self.COLLECTION_TRIALS].create_index([("run_id", 1), ("case_id", 1)])
        await db[self.COLLECTION_TRIALS].create_index("status")

        try:
            from app.services.eval.observability_adapter import observability_adapter

            observability_adapter.configure(
                backend=settings.EVAL_OBSERVABILITY_BACKEND,
                api_key=settings.EVAL_OBSERVABILITY_API_KEY or None,
                host=settings.EVAL_OBSERVABILITY_HOST or None,
                project=settings.EVAL_OBSERVABILITY_PROJECT,
            )
        except Exception:
            logger.warning("Failed to configure eval observability adapter", exc_info=True)

        self._initialized = True
        logger.info("EvalRunnerService initialized with indexes")

    async def create_run(
        self,
        dataset_id: str,
        dataset_version: Optional[str] = None,
        num_trials: int = 1,
        config: Optional[Dict[str, Any]] = None,
        created_by: str = "",
    ) -> Dict[str, Any]:
        """创建评测运行"""
        db = get_mongo_db()

        if num_trials < 1:
            raise ValueError("num_trials must be >= 1")
        if num_trials > settings.EVAL_MAX_TRIALS_PER_CASE:
            raise ValueError(
                f"num_trials {num_trials} exceeds EVAL_MAX_TRIALS_PER_CASE "
                f"{settings.EVAL_MAX_TRIALS_PER_CASE}"
            )

        # 验证数据集存在
        dataset = await dataset_service.get_dataset(dataset_id)
        if not dataset:
            raise ValueError(f"Dataset {dataset_id} not found")

        # 使用指定版本或当前版本
        version = dataset_version or dataset.get("version", "1.0.0")

        # 获取数据集下指定版本的所有 case
        cases = await dataset_service.list_cases(dataset_id, limit=1000, version=version)
        if not cases:
            raise ValueError(f"Dataset {dataset_id} v{version} has no cases")

        run_id = f"run_{uuid.uuid4().hex[:12]}"
        run_config = EvalRunConfig(**(config or {}))
        if run_config.timeout_seconds > settings.EVAL_TRIAL_TIMEOUT_SECONDS:
            raise ValueError(
                f"timeout_seconds {run_config.timeout_seconds} exceeds "
                f"EVAL_TRIAL_TIMEOUT_SECONDS {settings.EVAL_TRIAL_TIMEOUT_SECONDS}"
            )

        # 构建运行快照：固化 case 内容、scorer/judge 配置和数据窗口
        case_contents = {}
        for c in cases:
            case_contents[c["case_id"]] = {
                "name": c.get("name", ""),
                "input": c.get("input", {}),
                "expected_output": c.get("expected_output"),
                "scoring_criteria": c.get("scoring_criteria", {}),
                "tags": c.get("tags", []),
                "difficulty": c.get("difficulty", "medium"),
                "category": c.get("category", "general"),
            }

        # 获取 scorer 配置快照
        scorer_config_snapshot = []
        try:
            from app.services.eval.scorer_hub import scorer_hub
            all_scorers = scorer_hub.list_scorers()
            selected_names = run_config.scorer_names or [s["name"] for s in all_scorers]
            scorer_config_snapshot = [
                {"name": s["name"], "source": s["source"], "version": s["version"], "status": s.get("status", "available")}
                for s in all_scorers
                if s["name"] in selected_names
            ]
        except Exception:
            logger.warning("Failed to snapshot scorer config", exc_info=True)

        # Judge 配置快照
        judge_config_snapshot = {}
        if run_config.judge_model:
            judge_config_snapshot = {
                "model": run_config.judge_model,
                "rubric_version": run_config.rubric_version,
                "low_confidence_threshold": run_config.low_confidence_threshold,
                "review_strategy": run_config.review_strategy,
            }

        snapshot = RunSnapshot(
            dataset_version=version,
            case_contents=case_contents,
            scorer_config=scorer_config_snapshot,
            judge_config=judge_config_snapshot,
            data_window=run_config.data_window,
        )

        run = EvalRun(
            run_id=run_id,
            dataset_id=dataset_id,
            dataset_version=version,
            status=RunStatus.PENDING,
            config=run_config,
            num_trials_per_case=num_trials,
            total_cases=len(cases),
            snapshot=snapshot,
            created_by=created_by,
        )

        doc = run.model_dump(by_alias=True, exclude={"id"})
        await db[self.COLLECTION_RUNS].insert_one(doc)

        logger.info(f"Created eval run {run_id} for dataset {dataset_id} v{version} with snapshot")
        return {"run_id": run_id, "total_cases": len(cases), "num_trials_per_case": num_trials}

    async def start_run(self, run_id: str) -> bool:
        """启动评测运行"""
        db = get_mongo_db()

        run_doc = await db[self.COLLECTION_RUNS].find_one({"run_id": run_id})
        if not run_doc:
            raise ValueError(f"Run {run_id} not found")

        if run_doc["status"] != RunStatus.PENDING.value:
            raise ValueError(f"Run {run_id} is already {run_doc['status']}")

        # 更新状态为 running
        await db[self.COLLECTION_RUNS].update_one(
            {"run_id": run_id},
            {"$set": {"status": RunStatus.RUNNING.value, "started_at": now_tz()}}
        )

        # 异步启动运行任务
        task = asyncio.create_task(self._execute_run(run_id))
        self._running_tasks[run_id] = task

        logger.info(f"Started eval run {run_id}")
        return True

    async def _execute_run(self, run_id: str):
        """执行评测运行（内部方法）"""
        db = get_mongo_db()

        try:
            run_doc = await db[self.COLLECTION_RUNS].find_one({"run_id": run_id})
            if not run_doc:
                logger.error(f"Run {run_id} not found during execution")
                return

            dataset_id = run_doc["dataset_id"]
            dataset_version = run_doc.get("dataset_version")
            num_trials = run_doc["num_trials_per_case"]
            timeout_seconds = run_doc["config"]["timeout_seconds"]

            evolution_config = run_doc.get("config") or {}

            cases = await self._resolve_run_cases(run_doc, dataset_id, dataset_version)
            self._validate_evolution_scope(evolution_config, cases, dataset_version)

            # 为每个 case 创建并执行 trial
            for case in cases:
                case_id = case["case_id"]

                for trial_idx in range(num_trials):
                    trial_id = f"{run_id}_{case_id}_t{trial_idx}"

                    # 创建 trial，附带 case 内容快照
                    case_snap = {
                        "name": case.get("name", ""),
                        "input": case.get("input", {}),
                        "expected_output": case.get("expected_output"),
                        "scoring_criteria": case.get("scoring_criteria", {}),
                        "tags": case.get("tags", []),
                        "difficulty": case.get("difficulty", "medium"),
                        "category": case.get("category", "general"),
                        "dataset_version": dataset_version,
                    }
                    trial = EvalTrial(
                        trial_id=trial_id,
                        run_id=run_id,
                        case_id=case_id,
                        trial_index=trial_idx,
                        status=TrialStatus.PENDING,
                        input_data=case.get("input", {}),
                        case_snapshot=case_snap,
                        snapshot_version=dataset_version,
                    )

                    trial_doc = trial.model_dump(by_alias=True, exclude={"id"})
                    await db[self.COLLECTION_TRIALS].insert_one(trial_doc)

                    # 执行 trial
                    await self._execute_trial(
                        run_id,
                        trial_id,
                        case,
                        timeout_seconds,
                        dataset_version,
                    )

            # 完成运行
            completed_count = await db[self.COLLECTION_TRIALS].count_documents({
                "run_id": run_id,
                "status": TrialStatus.COMPLETED.value
            })
            failed_count = await db[self.COLLECTION_TRIALS].count_documents({
                "run_id": run_id,
                "status": {"$in": [TrialStatus.FAILED.value, TrialStatus.TIMEOUT.value]}
            })

            await db[self.COLLECTION_RUNS].update_one(
                {"run_id": run_id},
                {
                    "$set": {
                        "status": RunStatus.COMPLETED.value,
                        "completed_at": now_tz(),
                        "completed_trials": completed_count,
                        "failed_trials": failed_count,
                    }
                }
            )

            logger.info(f"Eval run {run_id} completed: {completed_count} succeeded, {failed_count} failed")

            # 自进化触发 hook：通知 trigger_service 检查是否需要创建候选提案
            try:
                from app.core.config import settings as _settings
                if _settings.EVOLUTION_ENABLED:
                    from app.services.evolution.trigger_service import trigger_service
                    await trigger_service.on_run_completed(run_id)
            except Exception as evo_err:
                logger.warning(f"[Evolution] Trigger hook error for run {run_id}: {evo_err}")

        except asyncio.CancelledError:
            logger.info(f"Eval run {run_id} was cancelled")
            await db[self.COLLECTION_RUNS].update_one(
                {"run_id": run_id},
                {"$set": {"status": RunStatus.CANCELLED.value, "completed_at": now_tz()}}
            )
        except Exception as e:
            logger.exception(f"Eval run {run_id} failed: {e}")
            await db[self.COLLECTION_RUNS].update_one(
                {"run_id": run_id},
                {"$set": {"status": RunStatus.FAILED.value, "error_message": str(e), "completed_at": now_tz()}}
            )
        finally:
            self._running_tasks.pop(run_id, None)

    @staticmethod
    def _validate_evolution_scope(
        run_config: Dict[str, Any],
        cases: List[Dict[str, Any]],
        dataset_version: str,
    ) -> None:
        """验证候选验证只能访问固定版本的 validation 样本。"""
        if not run_config.get("evolution_proposal_id"):
            return
        split = str(run_config.get("split", "validation")).lower()
        if split in {"test", "holdout", "production"}:
            raise ValueError(f"candidate verification split is not allowed: {split}")
        overlay_version = run_config.get("overlay_dataset_version")
        if overlay_version and overlay_version != dataset_version:
            raise ValueError("candidate overlay dataset version does not match run snapshot")
        forbidden_cases = [
            case for case in cases
            if str(case.get("split", "")).lower() in {"test", "holdout", "production"}
        ]
        if forbidden_cases:
            raise ValueError("candidate verification cannot access test/holdout cases")

    async def _execute_trial(
        self,
        run_id: str,
        trial_id: str,
        case: Dict[str, Any],
        timeout_seconds: int,
        dataset_version: Optional[str] = None,
    ):
        """执行单个 trial"""
        db = get_mongo_db()
        case_id = case.get("case_id", "")

        try:
            # 更新 trial 状态为 running
            await db[self.COLLECTION_TRIALS].update_one(
                {"trial_id": trial_id},
                {"$set": {"status": TrialStatus.RUNNING.value, "started_at": now_tz()}}
            )

            # 对接 Vibe Agent runtime
            try:
                from vibe_agent_runtime import embedded_agent_runtime

                start_time = now_tz()

                # 创建临时的 session 和 task 用于评测
                eval_session_id = f"eval_{run_id}_{case_id}"
                eval_task_id = f"task_{trial_id}"

                prompt = case.get("input", {}).get("prompt", "")
                run_doc = await self.get_run(run_id)
                run_config = (run_doc or {}).get("config") or {}
                overlay = None
                if run_config.get("sandbox_path") and run_config.get("evolution_proposal_id"):
                    overlay = {
                        "sandbox_path": run_config["sandbox_path"],
                        "proposal_id": run_config["evolution_proposal_id"],
                        "artifact_id": run_config.get("artifact_override", ""),
                        "overlay_id": run_config.get("overlay_id", ""),
                        "baseline_version": run_config.get("baseline_artifact_version", ""),
                        "candidate_version": run_config.get("candidate_version", "candidate"),
                    }

                result = await asyncio.wait_for(
                    embedded_agent_runtime.run(
                        session_id=eval_session_id,
                        task_id=eval_task_id,
                        prompt=prompt,
                        title=f"Eval: {case.get('name', 'Unknown')}",
                        user_id="eval_system",
                        username="Evaluation System",
                        sink=_make_trace_sink(trial_id),  # 归一化事件并落盘为标准 trace
                        session_config={"overlay": overlay} if overlay else None,
                    ),
                    timeout=timeout_seconds,
                )

                if result is None:
                    raise RuntimeError(
                        "embedded_agent_runtime.run() returned None "
                        "(Vibe Agent runtime 执行内部失败，未返回结果)"
                    )

                end_time = now_tz()
                latency_ms = int((end_time - start_time).total_seconds() * 1000)

                # 注意：result 中的 "metrics" 键即使存在也可能显式为 None
                # （而不是缺失该键），此时 dict.get(key, default) 的默认值
                # 不会生效，必须用 `or {}` 兜底，否则链式 .get() 调用会在
                # None 上报 AttributeError。
                metrics = result.get("metrics") or {}
                output_data = {
                    "content": result.get("content", ""),
                    "status": result.get("status"),
                    "tool_trail": result.get("tool_trail", []),
                    "metrics": metrics,
                }

                # runtime 可能不抛异常、正常返回字典，但字典内部
                # status="failed" 并携带 reason —— 必须显式检查，否则会把
                # 真实失败的 trial 误标记为 COMPLETED（对应 spec: trial 失败
                # MUST 保留失败原因，不能被静默吞掉）。
                runtime_status = result.get("status")
                if runtime_status not in ("completed", "success", "ok"):
                    error_message = result.get("reason") or f"Agent runtime status={runtime_status!r}"
                    await db[self.COLLECTION_TRIALS].update_one(
                        {"trial_id": trial_id},
                        {
                            "$set": {
                                "status": TrialStatus.FAILED.value,
                                "completed_at": end_time,
                                "output_data": output_data,
                                "latency_ms": latency_ms,
                                "error_message": error_message,
                            }
                        }
                    )
                    logger.warning(f"Trial {trial_id} runtime returned non-success status: {error_message}")
                else:
                    await db[self.COLLECTION_TRIALS].update_one(
                        {"trial_id": trial_id},
                        {
                            "$set": {
                                "status": TrialStatus.COMPLETED.value,
                                "completed_at": end_time,
                                "output_data": output_data,
                                "latency_ms": latency_ms,
                                "token_usage": metrics.get("token_usage", {}),
                            }
                        }
                    )

            except ImportError:
                # Vibe Agent runtime 未安装，使用模拟模式
                logger.warning("vibe_agent_runtime not available, using simulation mode")
                await asyncio.sleep(0.1)

                await db[self.COLLECTION_TRIALS].update_one(
                    {"trial_id": trial_id},
                    {
                        "$set": {
                            "status": TrialStatus.COMPLETED.value,
                            "completed_at": now_tz(),
                            "output_data": {"result": "simulated_output", "mode": "simulation"},
                            "latency_ms": 100,
                        }
                    }
                )

            logger.debug(f"Trial {trial_id} completed")

        except asyncio.TimeoutError:
            logger.warning(f"Trial {trial_id} timed out after {timeout_seconds}s")
            await db[self.COLLECTION_TRIALS].update_one(
                {"trial_id": trial_id},
                {
                    "$set": {
                        "status": TrialStatus.TIMEOUT.value,
                        "completed_at": now_tz(),
                        "error_message": f"Timeout after {timeout_seconds}s",
                    }
                }
            )
        except Exception as e:
            logger.exception(f"Trial {trial_id} failed: {e}")
            await db[self.COLLECTION_TRIALS].update_one(
                {"trial_id": trial_id},
                {
                    "$set": {
                        "status": TrialStatus.FAILED.value,
                        "completed_at": now_tz(),
                        "error_message": str(e),
                    }
                }
            )
        finally:
            await self._score_and_export_trial(trial_id, case)

    async def _score_and_export_trial(self, trial_id: str, case: Dict[str, Any]) -> None:
        """Run scorers and optional observability export for every terminal trial."""
        try:
            from app.services.eval.scorer_hub import scorer_hub

            trial_data = await self.get_trial(trial_id)
            if not trial_data:
                return

            # Trace persistence is diagnostic data. It must not prevent the
            # authoritative scorer pipeline from running for candidate runs.
            trace_events: List[Dict[str, Any]] = []
            try:
                from app.services.eval.trace_adapter import trace_adapter

                trace_events = await trace_adapter.get_trace_events(trial_id, limit=1000)
            except Exception:
                logger.warning(f"Failed to load trace for trial {trial_id}; scoring without trace", exc_info=True)

            case_config = dict(case.get("scoring_criteria", {}) or {})
            if case.get("expected_output") is not None:
                case_config["expected_output"] = case["expected_output"]
            if case.get("input") is not None:
                case_config["case_input"] = case["input"]
            run_id = trial_data.get("run_id", "")
            run_doc = await self.get_run(run_id) if run_id else None
            run_config = (run_doc or {}).get("config") or {}
            scorer_names = run_config.get("scorer_names")

            scores = await scorer_hub.score_trial(
                trial_id=trial_id,
                trial_data=trial_data,
                trace_events=trace_events,
                scorer_names=scorer_names or None,
                case_config=case_config,
                run_config=run_config,
            )

            # Observability export is best-effort after score persistence.
            try:
                from app.services.eval.observability_adapter import observability_adapter

                await observability_adapter.export_trial(
                    trial_id=trial_id,
                    trial_data=trial_data,
                    trace_events=trace_events,
                    scores=scores,
                )
            except Exception:
                logger.warning(f"Failed to export scored trial {trial_id}", exc_info=True)
        except Exception:
            logger.warning(f"Failed to score/export trial {trial_id}", exc_info=True)

    async def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """获取评测运行"""
        db = get_mongo_db()
        doc = await db[self.COLLECTION_RUNS].find_one({"run_id": run_id})
        if doc:
            doc["id"] = str(doc.pop("_id"))
        return doc

    @staticmethod
    async def _resolve_run_cases(
        run_doc: Dict[str, Any],
        dataset_id: str,
        dataset_version: str,
    ) -> List[Dict[str, Any]]:
        """优先使用创建时锁定的 snapshot，确保 case 后续修改/删除不影响该 run。"""
        snapshot_case_contents = (run_doc.get("snapshot") or {}).get("case_contents") or {}
        if snapshot_case_contents:
            return list(snapshot_case_contents.values())
        return await dataset_service.list_cases(
            dataset_id, limit=1000, version=dataset_version
        )

    async def list_runs(
        self,
        dataset_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """列出评测运行"""
        db = get_mongo_db()

        query = {}
        if dataset_id:
            query["dataset_id"] = dataset_id

        cursor = db[self.COLLECTION_RUNS].find(query).sort("created_at", -1).skip(skip).limit(limit)
        results = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            results.append(doc)
        return results

    async def cancel_run(self, run_id: str, cancelled_by: str = "") -> bool:
        """取消评测运行"""
        db = get_mongo_db()

        # 检查是否有正在运行的任务
        task = self._running_tasks.get(run_id)
        if task and not task.done():
            task.cancel()

        # 更新运行状态
        result = await db[self.COLLECTION_RUNS].update_one(
            {"run_id": run_id, "status": {"$in": [RunStatus.PENDING.value, RunStatus.RUNNING.value]}},
            {"$set": {"status": RunStatus.CANCELLED.value, "completed_at": now_tz()}}
        )

        # 更新未完成的 trial 状态
        await db[self.COLLECTION_TRIALS].update_many(
            {"run_id": run_id, "status": {"$in": [TrialStatus.PENDING.value, TrialStatus.RUNNING.value]}},
            {"$set": {"status": TrialStatus.CANCELLED.value, "completed_at": now_tz()}}
        )

        return result.modified_count > 0

    async def get_trial(self, trial_id: str) -> Optional[Dict[str, Any]]:
        """获取 trial 详情"""
        db = get_mongo_db()
        doc = await db[self.COLLECTION_TRIALS].find_one({"trial_id": trial_id})
        if doc:
            doc["id"] = str(doc.pop("_id"))
        return doc

    async def list_trials(
        self,
        run_id: str,
        case_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """列出某个运行的所有 trial"""
        db = get_mongo_db()

        query = {"run_id": run_id}
        if case_id:
            query["case_id"] = case_id

        cursor = db[self.COLLECTION_TRIALS].find(query).sort("trial_index", 1)
        results = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            results.append(doc)
        return results


# 单例实例
runner_service = EvalRunnerService()
