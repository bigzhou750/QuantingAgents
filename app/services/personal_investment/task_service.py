"""
策略任务服务

负责策略选股和策略体检任务的创建、执行和结果管理。
"""

import logging
import uuid
from typing import Optional, List, Dict, Any

from app.core.database import get_mongo_db
from app.models.personal_investment import (
    StrategyTask, TaskStatus, TaskType,
    ScreeningResult, CheckupResult,
)
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)


class TaskService:
    """策略任务服务"""

    COLLECTION_TASKS = "strategy_tasks"
    COLLECTION_SCREENING_RESULTS = "screening_results"
    COLLECTION_CHECKUP_RESULTS = "checkup_results"

    def __init__(self):
        self._initialized = False

    async def initialize(self):
        """初始化服务，创建索引"""
        if self._initialized:
            return

        logger.info("Initializing TaskService")
        db = get_mongo_db()

        # 任务索引
        await db[self.COLLECTION_TASKS].create_index("task_id", unique=True)
        await db[self.COLLECTION_TASKS].create_index([("user_id", 1), ("created_at", -1)])
        await db[self.COLLECTION_TASKS].create_index([("user_id", 1), ("task_type", 1)])
        await db[self.COLLECTION_TASKS].create_index("strategy_id")
        await db[self.COLLECTION_TASKS].create_index("status")

        # 选股结果索引
        await db[self.COLLECTION_SCREENING_RESULTS].create_index("result_id", unique=True)
        await db[self.COLLECTION_SCREENING_RESULTS].create_index("task_id", unique=True)

        # 体检结果索引
        await db[self.COLLECTION_CHECKUP_RESULTS].create_index("result_id", unique=True)
        await db[self.COLLECTION_CHECKUP_RESULTS].create_index("task_id", unique=True)

        self._initialized = True
        logger.info("TaskService initialized with indexes")

    async def create_task(
        self,
        user_id: str,
        task_type: TaskType,
        strategy_id: str,
        profile_id: Optional[str] = None,
        input_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """创建策略任务"""
        db = get_mongo_db()

        task_id = f"task_{uuid.uuid4().hex[:12]}"

        task = StrategyTask(
            task_id=task_id,
            user_id=user_id,
            task_type=task_type,
            strategy_id=strategy_id,
            profile_id=profile_id,
            status=TaskStatus.PENDING,
            input_params=input_params or {},
        )

        doc = task.model_dump(by_alias=True, exclude={"id"})
        await db[self.COLLECTION_TASKS].insert_one(doc)

        logger.info(f"Created {task_type.value} task {task_id} for user {user_id}")

        # 异步触发任务执行
        import asyncio
        asyncio.create_task(self._execute_task(task_id, user_id, task_type, strategy_id, profile_id, input_params or {}))

        return {"task_id": task_id, "task_type": task_type.value}

    async def _execute_task(
        self,
        task_id: str,
        user_id: str,
        task_type: TaskType,
        strategy_id: str,
        profile_id: Optional[str],
        input_params: Dict[str, Any],
    ) -> None:
        """异步执行任务"""
        try:
            if task_type == TaskType.STRATEGY_SCREENING:
                from app.services.personal_investment.screening_executor import screening_executor
                await screening_executor.execute(
                    task_id=task_id,
                    user_id=user_id,
                    strategy_id=strategy_id,
                    profile_id=profile_id,
                    input_params=input_params,
                )
            elif task_type == TaskType.STRATEGY_CHECKUP:
                from app.services.personal_investment.checkup_executor import checkup_executor
                await checkup_executor.execute(
                    task_id=task_id,
                    user_id=user_id,
                    strategy_id=strategy_id,
                    profile_id=profile_id,
                    input_params=input_params,
                )
            else:
                logger.warning(f"Unknown task type: {task_type}")
        except Exception as e:
            logger.error(f"Task execution failed for {task_id}: {e}", exc_info=True)
            # 状态已在 executor 中更新为 FAILED

    async def get_task(self, task_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """获取任务详情"""
        db = get_mongo_db()

        query = {"task_id": task_id}
        if user_id:
            query["user_id"] = user_id

        doc = await db[self.COLLECTION_TASKS].find_one(query)
        if doc:
            doc["id"] = str(doc.pop("_id"))
        return doc

    async def list_tasks(
        self,
        user_id: str,
        task_type: Optional[TaskType] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """列出用户的任务列表"""
        db = get_mongo_db()

        query = {"user_id": user_id}
        if task_type:
            query["task_type"] = task_type.value

        cursor = db[self.COLLECTION_TASKS].find(query).sort("created_at", -1).skip(skip).limit(limit)
        results = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            results.append(doc)
        return results

    async def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        error_message: Optional[str] = None,
    ) -> bool:
        """更新任务状态"""
        db = get_mongo_db()

        update_fields = {
            "status": status.value,
            "updated_at": now_tz(),
        }

        if status == TaskStatus.RUNNING:
            update_fields["started_at"] = now_tz()
        elif status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.DATA_INSUFFICIENT):
            update_fields["completed_at"] = now_tz()

        if error_message:
            update_fields["error_message"] = error_message

        result = await db[self.COLLECTION_TASKS].update_one(
            {"task_id": task_id},
            {"$set": update_fields}
        )
        return result.modified_count > 0

    async def save_screening_result(
        self,
        task_id: str,
        candidates: List[Dict[str, Any]],
        overall_risks: Optional[List[str]] = None,
        data_sources: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """保存选股结果"""
        db = get_mongo_db()

        result_id = f"scr_{uuid.uuid4().hex[:12]}"

        screening_result = ScreeningResult(
            result_id=result_id,
            task_id=task_id,
            candidates=candidates,
            total_candidates=len(candidates),
            overall_risks=overall_risks or [],
            terminology_compliant=True,  # 默认合规，后续可检查
        )

        doc = screening_result.model_dump(by_alias=True, exclude={"id"})
        await db[self.COLLECTION_SCREENING_RESULTS].insert_one(doc)

        # 更新任务的数据源信息
        if data_sources:
            await db[self.COLLECTION_TASKS].update_one(
                {"task_id": task_id},
                {"$set": {"data_sources": data_sources, "data_as_of": now_tz()}}
            )

        logger.info(f"Saved screening result {result_id} for task {task_id}")
        return {"result_id": result_id, "total_candidates": len(candidates)}

    async def get_screening_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取选股结果"""
        db = get_mongo_db()
        doc = await db[self.COLLECTION_SCREENING_RESULTS].find_one({"task_id": task_id})
        if doc:
            doc["id"] = str(doc.pop("_id"))
        return doc

    async def save_checkup_result(
        self,
        task_id: str,
        fitness_level: str,
        fitness_summary: str,
        key_metrics: List[Dict[str, Any]],
        risk_warnings: Optional[List[str]] = None,
        data_sufficient: bool = True,
        data_quality_note: Optional[str] = None,
        recent_performance: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """保存体检结果"""
        db = get_mongo_db()

        result_id = f"chk_{uuid.uuid4().hex[:12]}"

        checkup_result = CheckupResult(
            result_id=result_id,
            task_id=task_id,
            fitness_level=fitness_level,
            fitness_summary=fitness_summary,
            key_metrics=key_metrics,
            risk_warnings=risk_warnings or [],
            data_sufficient=data_sufficient,
            data_quality_note=data_quality_note,
            recent_performance=recent_performance or {},
        )

        doc = checkup_result.model_dump(by_alias=True, exclude={"id"})
        await db[self.COLLECTION_CHECKUP_RESULTS].insert_one(doc)

        logger.info(f"Saved checkup result {result_id} for task {task_id}")
        return {"result_id": result_id, "fitness_level": fitness_level}

    async def get_checkup_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取体检结果"""
        db = get_mongo_db()
        doc = await db[self.COLLECTION_CHECKUP_RESULTS].find_one({"task_id": task_id})
        if doc:
            doc["id"] = str(doc.pop("_id"))
        return doc


# 单例实例
task_service = TaskService()
