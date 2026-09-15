"""
算力充值计费核心服务

职责：
- 账户管理（创建/查询）
- 预占与结算（原子操作）
- 充值入账（幂等）
- 交易流水记录
- 计费配置缓存
- 对账补偿

金额规范：所有内部运算使用整数毫额度(mq)，1 mq = 0.001元
"""

import time
import logging
import re
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta

from pymongo import ReturnDocument
from bson import ObjectId

from app.core.database import get_mongo_db
from app.utils.timezone import now_tz
from app.models.token_billing import (
    TokenAccountResponse,
    TransactionResponse,
    TransactionListResponse,
    PackageInfo,
    TokenBillingSettings,
    generate_order_id,
    generate_txn_id,
    yuan_to_mq,
    mq_to_yuan,
)

logger = logging.getLogger(__name__)

# ==================== 集合名称常量 ====================
COL_ACCOUNTS = "token_accounts"
COL_ORDERS = "token_recharge_orders"
COL_TRANSACTIONS = "token_transactions"
COL_PACKAGES = "token_packages"
REGISTRATION_BONUS_MQ = 5000

# ==================== 计费配置缓存 ====================
_billing_cache: Dict[str, Any] = {}
_billing_cache_ts: float = 0
_CACHE_TTL = 30  # 秒


async def _get_billing_config() -> Dict[str, Any]:
    """获取计费配置（30秒TTL进程内缓存）"""
    global _billing_cache, _billing_cache_ts
    now = time.time()
    if now - _billing_cache_ts > _CACHE_TTL:
        try:
            from app.services.config_service import config_service
            config = await config_service.get_system_config()
            ss = config.system_settings if config and hasattr(config, 'system_settings') else {}
            if isinstance(ss, dict):
                _billing_cache = {
                    "consumption_ratio": ss.get("token_consumption_ratio", 1.2),
                    "input_price": ss.get("token_input_price_per_1m", 1.0),
                    "output_price": ss.get("token_output_price_per_1m", 2.0),
                    "exchange_rate": ss.get("token_exchange_rate", 1.1),
                    "preoccupy_ratio": ss.get("token_preoccupy_ratio", 1.2),
                    "warn_threshold_mq": yuan_to_mq(ss.get("token_balance_warn_threshold", 5.0)),
                    "order_expire_minutes": ss.get("token_order_expire_minutes", 30),
                }
            _billing_cache_ts = now
        except Exception as e:
            logger.warning("⚠️ 获取计费配置失败，使用默认值: %s", e)
            if not _billing_cache:
                _billing_cache = {
                    "consumption_ratio": 1.2,
                    "input_price": 1.0,
                    "output_price": 2.0,
                    "exchange_rate": 1.1,
                    "preoccupy_ratio": 1.2,
                    "warn_threshold_mq": 5000,
                    "order_expire_minutes": 30,
                }
    return _billing_cache


def invalidate_billing_cache():
    """手动失效计费配置缓存（配置更新后调用）"""
    global _billing_cache_ts
    _billing_cache_ts = 0


# ==================== 账户管理 ====================

class TokenBillingService:
    """Token 计费核心服务"""

    async def get_or_create_account(self, user_id: str) -> dict:
        """获取或创建用户额度账户（原子upsert）"""
        db = get_mongo_db()
        now_iso = now_tz().isoformat()
        result = await db[COL_ACCOUNTS].find_one_and_update(
            {"user_id": user_id},
            {
                "$setOnInsert": {
                    "user_id": user_id,
                    "balance_mq": 0,
                    "frozen_mq": 0,
                    "total_recharged_mq": 0,
                    "total_consumed_mq": 0,
                    "total_gifted_mq": 0,
                    "registration_bonus_granted": False,
                    "created_at": now_iso,
                },
                "$set": {"updated_at": now_iso},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return result

    async def get_account_response(self, user_id: str) -> TokenAccountResponse:
        """获取账户响应（金额转为元）"""
        account = await self.get_or_create_account(user_id)
        return TokenAccountResponse.from_account(account)

    async def grant_quota(
        self,
        user_id: str,
        amount_mq: int,
        *,
        txn_type: str,
        source: str,
        reason: str = "",
        username: Optional[str] = None,
        email: Optional[str] = None,
        operator_user_id: Optional[str] = None,
        operator_username: Optional[str] = None,
    ) -> Optional[dict]:
        """
        统一额度发放入口：注册赠送、管理员充值等收入型运营操作。

        Returns:
            入账结果字典；注册赠送已存在时返回 None。
        """
        if amount_mq <= 0:
            raise ValueError("发放额度必须大于0")
        if txn_type not in ("gift", "admin_recharge"):
            raise ValueError(f"不支持的额度发放类型: {txn_type}")

        db = get_mongo_db()
        now_iso = now_tz().isoformat()
        await self.get_or_create_account(user_id)

        account_filter: Dict[str, Any] = {"user_id": user_id}
        if source == "registration_bonus":
            account_filter["registration_bonus_granted"] = {"$ne": True}

        if txn_type == "admin_recharge":
            inc = {"balance_mq": amount_mq, "total_recharged_mq": amount_mq}
            txn_prefix = "ADM"
        else:
            inc = {"balance_mq": amount_mq, "total_gifted_mq": amount_mq}
            txn_prefix = "GFT"

        update: Dict[str, Any] = {
            "$inc": inc,
            "$set": {"updated_at": now_iso},
        }
        if source == "registration_bonus":
            update["$set"]["registration_bonus_granted"] = True

        result = await db[COL_ACCOUNTS].find_one_and_update(
            account_filter,
            update,
            return_document=ReturnDocument.AFTER,
        )

        if result is None:
            if source == "registration_bonus":
                logger.info("注册赠送已存在，跳过: user=%s", user_id)
                return None
            logger.error("额度发放失败: 账户不存在 user=%s", user_id)
            return None

        balance_before = result["balance_mq"] - amount_mq
        txn_id = generate_txn_id(txn_prefix)
        metadata: Dict[str, Any] = {
            "source": source,
            "reason": reason,
        }
        if username:
            metadata["username"] = username
        if email:
            metadata["email"] = email
        if operator_user_id:
            metadata["operator_user_id"] = operator_user_id
        if operator_username:
            metadata["operator_username"] = operator_username

        await db[COL_TRANSACTIONS].insert_one({
            "txn_id": txn_id,
            "user_id": user_id,
            "order_id": None,
            "type": txn_type,
            "direction": "in",
            "amount_mq": amount_mq,
            "balance_before_mq": balance_before,
            "balance_after_mq": result["balance_mq"],
            "metadata": metadata,
            "status": "success",
            "related_txn_id": None,
            "created_at": now_iso,
        })

        # 发放成功后清除余额耗尽标记
        try:
            from app.core.database import get_redis_client
            redis = get_redis_client()
            await redis.delete(f"token_balance_exhausted:{user_id}")
        except Exception:
            pass

        logger.info(
            "额度发放成功: user=%s, type=%s, amount=%d mq (%.3f元), txn=%s",
            user_id, txn_type, amount_mq, mq_to_yuan(amount_mq), txn_id
        )
        return {
            "txn_id": txn_id,
            "amount_mq": amount_mq,
            "balance_after_mq": result["balance_mq"],
        }

    async def grant_registration_bonus(self, user_id: str, username: str) -> Optional[dict]:
        """新用户注册赠送 5 元算力（幂等）。"""
        return await self.grant_quota(
            user_id=user_id,
            amount_mq=REGISTRATION_BONUS_MQ,
            txn_type="gift",
            source="registration_bonus",
            reason="新用户注册赠送5元算力",
            username=username,
            operator_user_id="system",
            operator_username="system",
        )

    async def admin_recharge(
        self,
        user_id: str,
        amount_mq: int,
        *,
        username: str,
        email: str,
        operator_user_id: str,
        operator_username: str,
        reason: str,
    ) -> Optional[dict]:
        """管理员后台充值算力。"""
        return await self.grant_quota(
            user_id=user_id,
            amount_mq=amount_mq,
            txn_type="admin_recharge",
            source="admin_recharge",
            reason=reason,
            username=username,
            email=email,
            operator_user_id=operator_user_id,
            operator_username=operator_username,
        )

    # ==================== 预占与结算 ====================

    async def preoccupy_balance(
        self, user_id: str, estimated_round_tokens: int = 4096
    ) -> Tuple[str, int]:
        """
        预占余额（发消息前调用）

        Returns:
            (preoccupy_txn_id, preoccupy_mq)

        Raises:
            InsufficientBalanceError: 余额不足时
        """
        # 检查Redis余额耗尽标记（熔断后5分钟内拒绝新请求）
        try:
            from app.core.database import get_redis_client
            redis = get_redis_client()
            exhausted = await redis.get(f"token_balance_exhausted:{user_id}")
            if exhausted:
                raise InsufficientBalanceError(required_mq=1, available_mq=0)
        except InsufficientBalanceError:
            raise
        except Exception:
            pass  # Redis异常不阻塞

        config = await _get_billing_config()

        # 预占毫额度 = estimated_tokens × output_price / 1e6 × consumption_ratio × preoccupy_ratio × 1000
        preoccupy_mq = int(round(
            estimated_round_tokens
            * config["output_price"] / 1_000_000
            * config["consumption_ratio"]
            * config["preoccupy_ratio"]
            * 1000
        ))

        if preoccupy_mq <= 0:
            preoccupy_mq = 1  # 最少预占1毫额度

        db = get_mongo_db()
        now_iso = now_tz().isoformat()

        # 原子操作：余额 >= 预占额才扣减
        result = await db[COL_ACCOUNTS].find_one_and_update(
            {"user_id": user_id, "balance_mq": {"$gte": preoccupy_mq}},
            {
                "$inc": {"balance_mq": -preoccupy_mq, "frozen_mq": preoccupy_mq},
                "$set": {"updated_at": now_iso},
            },
            return_document=ReturnDocument.AFTER,
        )

        if result is None:
            # 余额不足，查询当前余额用于提示
            account = await db[COL_ACCOUNTS].find_one({"user_id": user_id})
            current_balance = account.get("balance_mq", 0) if account else 0
            raise InsufficientBalanceError(
                required_mq=preoccupy_mq,
                available_mq=current_balance,
            )

        # 记录预占交易流水
        txn_id = generate_txn_id("PRE")
        balance_after = result["balance_mq"]
        balance_before = balance_after + preoccupy_mq

        await db[COL_TRANSACTIONS].insert_one({
            "txn_id": txn_id,
            "user_id": user_id,
            "order_id": None,
            "type": "preoccupy",
            "direction": "out",
            "amount_mq": preoccupy_mq,
            "balance_before_mq": balance_before,
            "balance_after_mq": balance_after,
            "metadata": {"estimated_round_tokens": estimated_round_tokens},
            "status": "success",
            "related_txn_id": None,
            "created_at": now_iso,
        })

        logger.info(
            "预占成功: user=%s, amount=%d mq (%.3f元), txn=%s",
            user_id, preoccupy_mq, mq_to_yuan(preoccupy_mq), txn_id
        )
        return txn_id, preoccupy_mq

    async def settle_llm_usage(
        self,
        user_id: str,
        task_id: str,
        session_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        model: str = "",
        preoccupy_txn_id: Optional[str] = None,
    ) -> dict:
        """
        结算单轮LLM调用的token消耗

        采用"frozen优先扣减 + balance追扣"策略处理超支。

        Returns:
            结算结果字典 {deduction_mq, new_balance_mq, txn_id}
        """
        config = await _get_billing_config()

        # 计算本轮实际消耗（毫额度）
        real_cost_yuan = (
            prompt_tokens * config["input_price"] / 1_000_000
            + completion_tokens * config["output_price"] / 1_000_000
        )
        deduction_mq = int(round(real_cost_yuan * config["consumption_ratio"] * 1000))

        if deduction_mq <= 0:
            # 零消耗时查询实际余额，避免误触发余额耗尽熔断
            db = get_mongo_db()
            account = await db[COL_ACCOUNTS].find_one({"user_id": user_id}, {"balance_mq": 1})
            actual_balance = account["balance_mq"] if account else 0
            return {"deduction_mq": 0, "new_balance_mq": actual_balance, "txn_id": None}

        db = get_mongo_db()
        now_iso = now_tz().isoformat()

        # 原子操作：frozen优先扣减，不够则从balance追扣
        # 使用aggregation pipeline实现条件逻辑
        result = await db[COL_ACCOUNTS].find_one_and_update(
            {"user_id": user_id},
            [
                {"$set": {
                    "frozen_mq": {
                        "$max": [{"$subtract": ["$frozen_mq", deduction_mq]}, 0]
                    },
                    "balance_mq": {
                        "$cond": [
                            {"$gte": ["$frozen_mq", deduction_mq]},
                            "$balance_mq",  # frozen够扣，balance不变
                            {"$subtract": [
                                "$balance_mq",
                                {"$subtract": [deduction_mq, "$frozen_mq"]}
                            ]}  # frozen不够，差额从balance追扣
                        ]
                    },
                    "total_consumed_mq": {"$add": ["$total_consumed_mq", deduction_mq]},
                    "updated_at": now_iso,
                }}
            ],
            return_document=ReturnDocument.AFTER,
        )

        if result is None:
            logger.error("结算失败: 账户不存在 user=%s", user_id)
            return {"deduction_mq": deduction_mq, "new_balance_mq": 0, "txn_id": None}

        new_balance_mq = result["balance_mq"]

        # 插入consume交易流水
        txn_id = generate_txn_id("CON")
        await db[COL_TRANSACTIONS].insert_one({
            "txn_id": txn_id,
            "user_id": user_id,
            "order_id": None,
            "type": "consume",
            "direction": "out",
            "amount_mq": deduction_mq,
            "balance_before_mq": new_balance_mq + deduction_mq,  # 近似值
            "balance_after_mq": new_balance_mq,
            "metadata": {
                "session_id": session_id,
                "task_id": task_id,
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "real_cost_mq": int(round(real_cost_yuan * 1000)),
                "consumption_ratio": config["consumption_ratio"],
            },
            "status": "success",
            "related_txn_id": preoccupy_txn_id,
            "created_at": now_iso,
        })

        logger.debug(
            "结算完成: user=%s, deduct=%d mq, balance=%d mq, tokens=%d/%d",
            user_id, deduction_mq, new_balance_mq, prompt_tokens, completion_tokens
        )

        return {
            "deduction_mq": deduction_mq,
            "new_balance_mq": new_balance_mq,
            "txn_id": txn_id,
        }

    async def release_frozen(
        self, user_id: str, frozen_mq: int = 0, reason: str = "task_terminal"
    ) -> None:
        """
        释放frozen回balance（任务终态时调用）

        Args:
            user_id: 用户ID
            frozen_mq: 要释放的毫额度。传0表示释放全部剩余frozen。
            reason: 释放原因
        """
        db = get_mongo_db()
        now_iso = now_tz().isoformat()

        if frozen_mq <= 0:
            # 释放全部剩余frozen：使用聚合管道原子操作
            # 先用 BEFORE 视图获取当前frozen量
            before = await db[COL_ACCOUNTS].find_one(
                {"user_id": user_id, "frozen_mq": {"$gt": 0}},
                {"frozen_mq": 1, "balance_mq": 1},
            )
            if before is None:
                return  # 没有frozen可释放
            actual_released = before["frozen_mq"]

            result = await db[COL_ACCOUNTS].find_one_and_update(
                {"user_id": user_id, "frozen_mq": {"$gt": 0}},
                [
                    {"$set": {
                        "balance_mq": {"$add": ["$balance_mq", "$frozen_mq"]},
                        "frozen_mq": 0,
                        "updated_at": now_iso,
                    }}
                ],
                return_document=ReturnDocument.AFTER,
            )
            if result is None:
                return  # 并发竞争导致frozen已被其他操作清零
        else:
            # 指定金额释放（向后兼容）
            result = await db[COL_ACCOUNTS].find_one_and_update(
                {"user_id": user_id, "frozen_mq": {"$gte": frozen_mq}},
                {
                    "$inc": {"balance_mq": frozen_mq, "frozen_mq": -frozen_mq},
                    "$set": {"updated_at": now_iso},
                },
                return_document=ReturnDocument.AFTER,
            )
            if result is None:
                logger.warning(
                    "释放frozen失败: user=%s, requested=%d mq", user_id, frozen_mq
                )
                return
            actual_released = frozen_mq

        # 记录settle_refund流水
        balance_before = result["balance_mq"] - actual_released
        txn_id = generate_txn_id("REL")
        await db[COL_TRANSACTIONS].insert_one({
            "txn_id": txn_id,
            "user_id": user_id,
            "order_id": None,
            "type": "settle_refund",
            "direction": "in",
            "amount_mq": actual_released,
            "balance_before_mq": balance_before,
            "balance_after_mq": result["balance_mq"],
            "metadata": {"reason": reason},
            "status": "success",
            "related_txn_id": None,
            "created_at": now_iso,
        })

        logger.info(
            "释放frozen: user=%s, amount=%d mq (%.3f元), reason=%s",
            user_id, actual_released, mq_to_yuan(actual_released), reason
        )

    # ==================== 充值入账 ====================

    async def credit_quota(
        self,
        user_id: str,
        quota_mq: int,
        gift_mq: int,
        order_id: str,
        amount_cny_mq: int,
    ) -> bool:
        """
        充值入账（幂等）

        Args:
            user_id: 用户ID
            quota_mq: 总到账额度（毫额度）
            gift_mq: 赠送部分（毫额度）
            order_id: 关联订单号
            amount_cny_mq: 实付金额（毫额度）

        Returns:
            是否成功入账
        """
        db = get_mongo_db()
        now_iso = now_tz().isoformat()

        # 确保账户存在
        await self.get_or_create_account(user_id)

        # 原子增加余额
        result = await db[COL_ACCOUNTS].find_one_and_update(
            {"user_id": user_id},
            {
                "$inc": {
                    "balance_mq": quota_mq,
                    "total_recharged_mq": amount_cny_mq,
                    "total_gifted_mq": gift_mq,
                },
                "$set": {"updated_at": now_iso},
            },
            return_document=ReturnDocument.AFTER,
        )

        if result is None:
            logger.error("充值入账失败: 账户不存在 user=%s", user_id)
            return False

        balance_before = result["balance_mq"] - quota_mq

        # 插入充值交易流水
        recharge_txn_id = generate_txn_id("RCH")
        principal_mq = quota_mq - gift_mq

        await db[COL_TRANSACTIONS].insert_one({
            "txn_id": recharge_txn_id,
            "user_id": user_id,
            "order_id": order_id,
            "type": "recharge",
            "direction": "in",
            "amount_mq": principal_mq,
            "balance_before_mq": balance_before,
            "balance_after_mq": balance_before + principal_mq,
            "metadata": {"package_amount_mq": amount_cny_mq},
            "status": "success",
            "related_txn_id": None,
            "created_at": now_iso,
        })

        # 如果有赠送部分，单独记一笔
        if gift_mq > 0:
            gift_txn_id = generate_txn_id("GFT")
            await db[COL_TRANSACTIONS].insert_one({
                "txn_id": gift_txn_id,
                "user_id": user_id,
                "order_id": order_id,
                "type": "gift",
                "direction": "in",
                "amount_mq": gift_mq,
                "balance_before_mq": balance_before + principal_mq,
                "balance_after_mq": balance_before + quota_mq,
                "metadata": {"gift_split": True},
                "status": "success",
                "related_txn_id": recharge_txn_id,
                "created_at": now_iso,
            })

        # 充值成功后清除余额耗尽标记
        try:
            from app.core.database import get_redis_client
            redis = get_redis_client()
            await redis.delete(f"token_balance_exhausted:{user_id}")
        except Exception:
            pass

        logger.info(
            "充值入账成功: user=%s, quota=%d mq (%.3f元), gift=%d mq, order=%s",
            user_id, quota_mq, mq_to_yuan(quota_mq), gift_mq, order_id
        )
        return True

    # ==================== 交易流水查询 ====================

    async def get_transactions(
        self,
        user_id: str,
        type_filter: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> TransactionListResponse:
        """分页查询交易流水"""
        db = get_mongo_db()

        query: Dict[str, Any] = {"user_id": user_id}
        if type_filter and type_filter != "all":
            query["type"] = type_filter
        if start_date or end_date:
            date_query: Dict[str, str] = {}
            if start_date:
                date_query["$gte"] = start_date
            if end_date:
                date_query["$lte"] = end_date
            query["created_at"] = date_query

        total = await db[COL_TRANSACTIONS].count_documents(query)
        skip = (page - 1) * page_size

        cursor = (
            db[COL_TRANSACTIONS]
            .find(query)
            .sort("created_at", -1)
            .skip(skip)
            .limit(page_size)
        )

        items = []
        async for doc in cursor:
            items.append(TransactionResponse.from_record(doc))

        return TransactionListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_admin_transactions(
        self,
        *,
        user_id: Optional[str] = None,
        type_filter: Optional[str] = None,
        keyword: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> TransactionListResponse:
        """管理员分页查询充值/赠送交易记录，支持关键字、类型和日期过滤。"""
        db = get_mongo_db()

        query: Dict[str, Any] = {}
        if user_id:
            query["user_id"] = user_id
        if type_filter and type_filter != "all":
            query["type"] = type_filter
        if start_date or end_date:
            date_query: Dict[str, str] = {}
            if start_date:
                date_query["$gte"] = start_date
            if end_date:
                date_query["$lte"] = end_date
            query["created_at"] = date_query

        if keyword and keyword.strip():
            pattern = re.escape(keyword.strip())
            or_conditions: List[Dict[str, Any]] = []
            matched_user_ids: List[str] = []

            user_cursor = db["users"].find({"$or": [
                {"username": {"$regex": pattern, "$options": "i"}},
                {"email": {"$regex": pattern, "$options": "i"}},
            ]})
            async for user_doc in user_cursor:
                matched_user_ids.append(str(user_doc.get("_id")))

            if ObjectId.is_valid(keyword.strip()):
                matched_user_ids.append(keyword.strip())

            if matched_user_ids:
                or_conditions.append({"user_id": {"$in": matched_user_ids}})
            or_conditions.extend([
                {"txn_id": {"$regex": pattern, "$options": "i"}},
                {"order_id": {"$regex": pattern, "$options": "i"}},
                {"metadata.username": {"$regex": pattern, "$options": "i"}},
                {"metadata.email": {"$regex": pattern, "$options": "i"}},
                {"metadata.operator_username": {"$regex": pattern, "$options": "i"}},
            ])
            query["$or"] = or_conditions

        total = await db[COL_TRANSACTIONS].count_documents(query)
        skip = (page - 1) * page_size
        cursor = (
            db[COL_TRANSACTIONS]
            .find(query)
            .sort("created_at", -1)
            .skip(skip)
            .limit(page_size)
        )
        page_docs = []
        async for doc in cursor:
            page_docs.append(doc)

        # 用 user_id 回查用户身份，兼容缺少 username/email 元数据的历史流水。
        user_ids = {doc.get("user_id") for doc in page_docs if doc.get("user_id")}
        user_map: Dict[str, Dict[str, str]] = {}
        if user_ids:
            id_conditions: List[Any] = []
            for uid in user_ids:
                if ObjectId.is_valid(uid):
                    id_conditions.append(ObjectId(uid))
                else:
                    id_conditions.append(uid)
            user_cursor = db["users"].find({"_id": {"$in": id_conditions}})
            async for user_doc in user_cursor:
                user_map[str(user_doc.get("_id"))] = {
                    "username": user_doc.get("username", ""),
                    "email": user_doc.get("email", ""),
                }

        items = []
        for doc in page_docs:
            record = dict(doc)
            metadata = dict(record.get("metadata") or {})
            info = user_map.get(record.get("user_id"))
            if info:
                metadata.setdefault("username", info["username"])
                metadata.setdefault("email", info["email"])
            record["metadata"] = metadata
            items.append(TransactionResponse.from_record(record))

        return TransactionListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )

    # ==================== 套餐管理 ====================

    async def get_packages(self) -> List[PackageInfo]:
        """获取启用的充值套餐列表"""
        db = get_mongo_db()
        cursor = db[COL_PACKAGES].find({"enabled": True}).sort("sort_order", 1)
        packages = []
        async for doc in cursor:
            packages.append(PackageInfo.from_doc(doc))
        return packages

    async def get_package_by_id(self, package_id: str) -> Optional[PackageInfo]:
        """根据ID获取套餐"""
        db = get_mongo_db()
        doc = await db[COL_PACKAGES].find_one({"package_id": package_id, "enabled": True})
        return PackageInfo.from_doc(doc) if doc else None

    # ==================== 订单管理 ====================

    async def create_order(
        self,
        user_id: str,
        package_id: Optional[str],
        custom_amount_mq: Optional[int],
        idempotency_key: str,
        pay_type: str,
    ) -> dict:
        """
        创建充值订单

        Returns:
            订单文档dict

        Raises:
            ValueError: 参数无效
            DuplicateOrderError: 幂等键重复
        """
        db = get_mongo_db()
        config = await _get_billing_config()

        # 确定金额
        if package_id:
            pkg = await self.get_package_by_id(package_id)
            if not pkg:
                raise ValueError(f"无效的套餐ID: {package_id}")
            amount_mq = yuan_to_mq(pkg.amount_cny)
        elif custom_amount_mq and custom_amount_mq > 0:
            amount_mq = custom_amount_mq
        else:
            raise ValueError("必须指定package_id或custom_amount")

        # 计算到账额度
        exchange_rate = config["exchange_rate"]
        quota_mq = int(round(amount_mq * exchange_rate))
        gift_mq = quota_mq - amount_mq  # 赠送 = 总额度 - 本金

        # 幂等检查
        existing = await db[COL_ORDERS].find_one({"idempotency_key": idempotency_key})
        if existing:
            raise DuplicateOrderError(existing["order_id"])

        now_iso = now_tz().isoformat()
        expire_minutes = config.get("order_expire_minutes", 30)
        expire_at = (now_tz() + timedelta(minutes=expire_minutes)).isoformat()

        order_id = generate_order_id()
        order_doc = {
            "order_id": order_id,
            "user_id": user_id,
            "package_id": package_id or "custom",
            "amount_mq": amount_mq,
            "exchange_rate": exchange_rate,
            "quota_to_credit_mq": quota_mq,
            "gift_amount_mq": max(gift_mq, 0),
            "pay_type": pay_type,
            "wx_out_trade_no": order_id,
            "wx_transaction_id": None,
            "wx_prepay_id": None,
            "wx_code_url": None,
            "wx_mweb_url": None,
            "status": "pending",
            "callback_raw": None,
            "credited_at": None,
            "expire_at": expire_at,
            "ab_group": None,
            "idempotency_key": idempotency_key,
            "created_at": now_iso,
            "updated_at": now_iso,
        }

        await db[COL_ORDERS].insert_one(order_doc)
        logger.info(
            "创建订单: order=%s, user=%s, amount=%d mq, pay_type=%s",
            order_id, user_id, amount_mq, pay_type
        )
        return order_doc

    async def get_order(self, user_id: str, order_id: str) -> Optional[dict]:
        """查询订单"""
        db = get_mongo_db()
        return await db[COL_ORDERS].find_one({
            "order_id": order_id,
            "user_id": user_id,
        })

    async def mark_order_credited(
        self, order_id: str, wx_transaction_id: str, callback_raw: dict
    ) -> bool:
        """
        标记订单为已入账（幂等）

        Returns:
            是否成功更新（False表示已处理过）
        """
        db = get_mongo_db()
        now_iso = now_tz().isoformat()

        result = await db[COL_ORDERS].find_one_and_update(
            {"order_id": order_id, "status": "pending"},
            {
                "$set": {
                    "status": "credited",
                    "wx_transaction_id": wx_transaction_id,
                    "callback_raw": callback_raw,
                    "credited_at": now_iso,
                    "updated_at": now_iso,
                }
            },
            return_document=ReturnDocument.AFTER,
        )

        if result is None:
            # 可能已经credited了（幂等）
            existing = await db[COL_ORDERS].find_one({"order_id": order_id})
            if existing and existing.get("status") == "credited":
                logger.info("订单已入账（幂等跳过，不再重复入账）: %s", order_id)
                return False  # 防止并发回调双重入账
            logger.warning("标记入账失败: order=%s, status=%s",
                          order_id, existing.get("status") if existing else "not_found")
            return False

        return True

    async def get_pending_order(self, user_id: str) -> Optional[dict]:
        """获取用户最近的pending订单（中断恢复用）"""
        db = get_mongo_db()
        return await db[COL_ORDERS].find_one(
            {"user_id": user_id, "status": "pending"},
            sort=[("created_at", -1)],
        )

    # ==================== 对账补偿 ====================

    async def reconcile_stale_frozen(self) -> int:
        """
        对账：释放僵死frozen

        查找 frozen_mq > 0 且 updated_at 超过10分钟的账户，
        释放其frozen回balance。

        Returns:
            处理的账户数
        """
        db = get_mongo_db()
        cutoff = (now_tz() - timedelta(minutes=10)).isoformat()

        stale_accounts = await db[COL_ACCOUNTS].find({
            "frozen_mq": {"$gt": 0},
            "updated_at": {"$lt": cutoff},
        }).to_list(None)

        count = 0
        for account in stale_accounts:
            user_id = account["user_id"]
            frozen_mq = account["frozen_mq"]
            await self.release_frozen(user_id, frozen_mq, reason="reconcile_stale")
            count += 1
            logger.warning(
                "对账释放僵死frozen: user=%s, frozen=%d mq", user_id, frozen_mq
            )

        if count > 0:
            logger.info("对账完成: 释放 %d 个僵死账户的frozen", count)
        return count

    async def expire_stale_orders(self) -> int:
        """
        标记过期 pending 订单为 expired

        查找 status=pending 且 expire_at < now 的订单，
        原子更新为 expired 状态。

        Returns:
            过期的订单数
        """
        db = get_mongo_db()
        now_iso = now_tz().isoformat()

        result = await db[COL_ORDERS].update_many(
            {
                "status": "pending",
                "expire_at": {"$lt": now_iso},
            },
            {
                "$set": {
                    "status": "expired",
                    "updated_at": now_iso,
                },
            },
        )

        count = result.modified_count
        if count > 0:
            logger.info("订单过期清理: 标记 %d 个订单为 expired", count)
        return count


# ==================== 自定义异常 ====================

class InsufficientBalanceError(Exception):
    """余额不足异常"""
    def __init__(self, required_mq: int, available_mq: int):
        self.required_mq = required_mq
        self.available_mq = available_mq
        super().__init__(
            f"额度不足: 需要 {mq_to_yuan(required_mq):.3f}元, "
            f"可用 {mq_to_yuan(available_mq):.3f}元"
        )


class DuplicateOrderError(Exception):
    """重复订单异常（幂等命中）"""
    def __init__(self, existing_order_id: str):
        self.existing_order_id = existing_order_id
        super().__init__(f"重复订单: {existing_order_id}")


# ==================== 初始化函数（启动时调用） ====================

async def init_token_billing():
    """
    初始化Token计费模块：
    1. 种子充值套餐数据
    2. 默认计费配置写入system_settings
    """
    db = get_mongo_db()

    # 后台充值记录查询常用索引
    try:
        await db[COL_TRANSACTIONS].create_index([("user_id", 1), ("created_at", -1)])
        await db[COL_TRANSACTIONS].create_index([("type", 1), ("created_at", -1)])
        await db[COL_TRANSACTIONS].create_index([("order_id", 1)])
    except Exception as exc:
        logger.warning("⚠️ 创建交易流水索引失败: %s", exc)

    # ---- 种子套餐数据 ----
    default_packages = [
        {"package_id": "pkg_20", "name": "20元套餐", "amount_cny": 20.0, "sort_order": 1, "enabled": True, "tags": []},
        {"package_id": "pkg_50", "name": "50元套餐", "amount_cny": 50.0, "sort_order": 2, "enabled": True, "tags": []},
        {"package_id": "pkg_100", "name": "100元套餐", "amount_cny": 100.0, "sort_order": 3, "enabled": True, "tags": ["hot"]},
        {"package_id": "pkg_200", "name": "200元套餐", "amount_cny": 200.0, "sort_order": 4, "enabled": True, "tags": []},
        {"package_id": "pkg_500", "name": "500元套餐", "amount_cny": 500.0, "sort_order": 5, "enabled": True, "tags": ["recommended"]},
    ]

    for pkg in default_packages:
        existing = await db[COL_PACKAGES].find_one({"package_id": pkg["package_id"]})
        if not existing:
            await db[COL_PACKAGES].insert_one(pkg)
            logger.info("种子套餐: %s", pkg["package_id"])

    # ---- 默认计费配置 ----
    default_billing_config = {
        "token_exchange_rate": 1.1,
        "token_consumption_ratio": 1.2,
        "token_input_price_per_1m": 1.0,
        "token_output_price_per_1m": 2.0,
        "token_preoccupy_ratio": 1.2,
        "token_balance_warn_threshold": 5.0,
        "token_order_expire_minutes": 30,
    }

    try:
        from app.services.config_service import config_service
        config = await config_service.get_system_config()
        ss = config.system_settings if config and hasattr(config, 'system_settings') else {}
        if isinstance(ss, dict):
            updates = {}
            for key, default_val in default_billing_config.items():
                if key not in ss:
                    updates[key] = default_val
            if updates:
                await config_service.update_system_settings(updates)
                logger.info("写入默认计费配置: %s", list(updates.keys()))
                invalidate_billing_cache()
    except Exception as e:
        logger.warning("⚠️ 写入默认计费配置失败（首次启动可能正常）: %s", e)

    logger.info("✅ Token计费模块初始化完成")


# ==================== 模块级单例 ====================
token_billing_service = TokenBillingService()
