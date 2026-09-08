"""
Token 计费服务层 — 综合单元测试。

测试策略说明：
- 使用 asyncio.run(_run()) 在同步测试函数中运行异步代码，避免 @pytest.mark.asyncio 插件依赖。
- 通过手写 _FakeColl / _FakeDB / _FakeRedis 替代真实 MongoDB 和 Redis，
  经 monkeypatch.setattr 注入到被测模块的命名空间（而非全局），确保隔离性。
- 每个测试独立构建 fake 实例，不使用共享 fixture，避免测试间状态污染。
- 每个测试开始前调用 _reset_cache() 清除模块级计费配置缓存，防止缓存命中掩盖加载逻辑缺陷。
"""

import asyncio
import copy
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock


# ---------------------------------------------------------------------------
# Fake infrastructure
# ---------------------------------------------------------------------------

def _eval_expr(expr, doc):
    """
    递归求值 MongoDB 聚合管道表达式（$max/$cond/$subtract/$add/$gte 等）。
    用于在 _FakeColl.find_one_and_update 中模拟聚合管道更新，
    使测试无需真实 MongoDB 即可验证服务层的条件扣减逻辑。
    """
    if isinstance(expr, str) and expr.startswith("$"):
        field = expr[1:]
        return doc.get(field, 0)
    if isinstance(expr, dict):
        if "$max" in expr:
            args = [_eval_expr(a, doc) for a in expr["$max"]]
            return max(args)
        if "$cond" in expr:
            cond_args = expr["$cond"]
            condition = _eval_expr(cond_args[0], doc)
            then_val = _eval_expr(cond_args[1], doc)
            else_val = _eval_expr(cond_args[2], doc)
            return then_val if condition else else_val
        if "$subtract" in expr:
            a = _eval_expr(expr["$subtract"][0], doc)
            b = _eval_expr(expr["$subtract"][1], doc)
            return a - b
        if "$add" in expr:
            a = _eval_expr(expr["$add"][0], doc)
            b = _eval_expr(expr["$add"][1], doc)
            return a + b
        if "$gte" in expr:
            a = _eval_expr(expr["$gte"][0], doc)
            b = _eval_expr(expr["$gte"][1], doc)
            return a >= b
        # Unknown operator — return as-is
        return expr
    # Literal value
    return expr


def _match_filter(doc: dict, filt: dict) -> bool:
    """Very small subset of MongoDB query matching used by the tests."""
    for key, val in filt.items():
        doc_val = doc.get(key)
        if isinstance(val, dict):
            for op, operand in val.items():
                if op == "$gte":
                    if not (doc_val is not None and doc_val >= operand):
                        return False
                elif op == "$gt":
                    if not (doc_val is not None and doc_val > operand):
                        return False
                elif op == "$lt":
                    if not (doc_val is not None and doc_val < operand):
                        return False
                elif op == "$lte":
                    if not (doc_val is not None and doc_val <= operand):
                        return False
                else:
                    return False
        else:
            if doc_val != val:
                return False
    return True


class _FakeCursor:
    """Chainable async cursor returned by _FakeColl.find()."""

    def __init__(self, docs: List[dict]):
        self._docs = list(docs)

    def sort(self, key, direction=-1):
        self._docs.sort(key=lambda d: d.get(key, ""), reverse=(direction == -1))
        return self

    def skip(self, n):
        self._docs = self._docs[n:]
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    async def to_list(self, length=None):
        if length is None:
            return list(self._docs)
        return self._docs[:length]

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._docs:
            raise StopAsyncIteration
        return self._docs.pop(0)


class _UpdateResult:
    def __init__(self, modified_count: int):
        self.modified_count = modified_count


class _FakeColl:
    """In-memory collection supporting the subset of pymongo API used by the service."""

    def __init__(self, name: str):
        self.name = name
        self.docs: List[dict] = []

    # -- find_one -----------------------------------------------------------
    async def find_one(self, filt: dict, projection=None, sort=None):
        for doc in self.docs:
            if _match_filter(doc, filt):
                result = dict(doc)
                if projection:
                    result = {k: v for k, v in result.items() if k in projection or k == "_id"}
                    # Include projected fields explicitly set to 1
                    included = {k for k, v in projection.items() if v == 1}
                    if included:
                        result = {k: doc[k] for k in included if k in doc}
                if sort:
                    pass  # single-doc, sort irrelevant
                return result
        return None

    # -- find_one_and_update ------------------------------------------------
    async def find_one_and_update(self, filt, update, upsert=False, return_document=None):
        from pymongo import ReturnDocument

        target = None
        for doc in self.docs:
            if _match_filter(doc, filt):
                target = doc
                break

        if target is None:
            if upsert:
                new_doc = {}
                # Apply $setOnInsert
                if isinstance(update, dict) and "$setOnInsert" in update:
                    new_doc.update(update["$setOnInsert"])
                if isinstance(update, dict) and "$set" in update:
                    new_doc.update(update["$set"])
                self.docs.append(new_doc)
                target = new_doc
            else:
                return None

        # Capture BEFORE state for conditional evaluation
        before_doc = dict(target)

        if isinstance(update, list):
            # Aggregation pipeline update
            for stage in update:
                if "$set" in stage:
                    for field, expr in stage["$set"].items():
                        target[field] = _eval_expr(expr, before_doc)
        elif isinstance(update, dict):
            if "$inc" in update:
                for field, delta in update["$inc"].items():
                    target[field] = target.get(field, 0) + delta
            if "$set" in update:
                for field, val in update["$set"].items():
                    target[field] = val
            # $setOnInsert only applies on insert (already handled above)

        if return_document == ReturnDocument.AFTER:
            return dict(target)
        else:
            return dict(before_doc)

    # -- insert_one ---------------------------------------------------------
    async def insert_one(self, doc: dict):
        self.docs.append(dict(doc))

    # -- update_many --------------------------------------------------------
    async def update_many(self, filt: dict, update: dict):
        count = 0
        for doc in self.docs:
            if _match_filter(doc, filt):
                if "$set" in update:
                    for k, v in update["$set"].items():
                        doc[k] = v
                count += 1
        return _UpdateResult(count)

    # -- count_documents ----------------------------------------------------
    async def count_documents(self, filt: dict):
        return sum(1 for doc in self.docs if _match_filter(doc, filt))

    # -- find (returns chainable cursor) ------------------------------------
    def find(self, filt: dict, projection=None):
        matched = [dict(d) for d in self.docs if _match_filter(d, filt)]
        if projection:
            included = {k for k, v in projection.items() if v == 1}
            if included:
                matched = [{k: d[k] for k in included if k in d} for d in matched]
        return _FakeCursor(matched)


class _FakeDB:
    """Dict-like database returning _FakeColl instances by collection name."""

    def __init__(self):
        self._colls: Dict[str, _FakeColl] = {}

    def __getitem__(self, name: str) -> _FakeColl:
        if name not in self._colls:
            self._colls[name] = _FakeColl(name)
        return self._colls[name]


class _FakeRedis:
    """Minimal async Redis stub backed by a plain dict."""

    def __init__(self):
        self._store: Dict[str, Any] = {}

    async def get(self, key: str):
        return self._store.get(key)

    async def setex(self, key: str, ttl: int, value: Any):
        self._store[key] = value

    async def delete(self, key: str):
        self._store.pop(key, None)


def _reset_cache():
    """Reset the module-level billing config cache."""
    import app.services.token_billing_service as tbs
    tbs._billing_cache = {}
    tbs._billing_cache_ts = 0


def _default_config():
    """Return default billing config matching service defaults."""
    return {
        "consumption_ratio": 1.2,
        "input_price": 1.0,
        "output_price": 2.0,
        "exchange_rate": 1.1,
        "preoccupy_ratio": 1.2,
        "warn_threshold_mq": 5000,
        "order_expire_minutes": 30,
    }


def _mock_config_service(monkeypatch, config_dict=None):
    """Patch config_service.get_system_config so _get_billing_config works."""
    if config_dict is None:
        config_dict = {
            "token_consumption_ratio": 1.2,
            "token_input_price_per_1m": 1.0,
            "token_output_price_per_1m": 2.0,
            "token_exchange_rate": 1.1,
            "token_preoccupy_ratio": 1.2,
            "token_balance_warn_threshold": 5.0,
            "token_order_expire_minutes": 30,
        }

    fake_config = MagicMock()
    fake_config.system_settings = config_dict

    mock_svc = AsyncMock()
    mock_svc.get_system_config = AsyncMock(return_value=fake_config)

    import app.services.config_service as cs_mod
    monkeypatch.setattr(cs_mod, "config_service", mock_svc)
    return mock_svc


# ===========================================================================
# 账户管理：测试 get_or_create_account 的首次创建和已有用户返回逻辑
# ===========================================================================

def test_get_or_create_account_new_user(monkeypatch):
    import app.services.token_billing_service as tbs
    _reset_cache()

    fake_db = _FakeDB()
    monkeypatch.setattr(tbs, "get_mongo_db", lambda: fake_db)

    async def _run():
        svc = tbs.TokenBillingService()
        account = await svc.get_or_create_account("user1")
        assert account["user_id"] == "user1"
        assert account["balance_mq"] == 0
        assert account["frozen_mq"] == 0
        assert account["total_recharged_mq"] == 0
        assert account["total_consumed_mq"] == 0
        assert account["total_gifted_mq"] == 0
        assert "created_at" in account
        assert "updated_at" in account

    asyncio.run(_run())


def test_get_or_create_account_existing_user(monkeypatch):
    import app.services.token_billing_service as tbs
    _reset_cache()

    fake_db = _FakeDB()
    monkeypatch.setattr(tbs, "get_mongo_db", lambda: fake_db)

    async def _run():
        svc = tbs.TokenBillingService()
        first = await svc.get_or_create_account("user1")
        # Manually adjust balance to simulate prior activity
        fake_db["token_accounts"].docs[0]["balance_mq"] = 5000
        second = await svc.get_or_create_account("user1")
        # Should return existing doc without resetting counters
        assert second["balance_mq"] == 5000
        assert len(fake_db["token_accounts"].docs) == 1

    asyncio.run(_run())


# ===========================================================================
# 余额预占：测试 Agent 任务开始时的额度冻结，包括正常预占、余额不足、Redis 耗尽标记等场景
# ===========================================================================

def test_preoccupy_balance_success(monkeypatch):
    import app.services.token_billing_service as tbs
    _reset_cache()
    _mock_config_service(monkeypatch)

    fake_db = _FakeDB()
    fake_redis = _FakeRedis()
    monkeypatch.setattr(tbs, "get_mongo_db", lambda: fake_db)
    import app.core.database as db_mod
    monkeypatch.setattr(db_mod, "get_redis_client", lambda: fake_redis)

    async def _run():
        svc = tbs.TokenBillingService()
        # Create account with 100000 mq balance
        await svc.get_or_create_account("user1")
        fake_db["token_accounts"].docs[0]["balance_mq"] = 100000

        txn_id, preoccupy_mq = await svc.preoccupy_balance("user1", estimated_round_tokens=4096)
        assert txn_id.startswith("PRE_")
        # preoccupy_mq = round(4096 * 2.0 / 1e6 * 1.2 * 1.2 * 1000) = round(11.796...) = 12
        assert preoccupy_mq == 12
        account = fake_db["token_accounts"].docs[0]
        assert account["balance_mq"] == 100000 - 12
        assert account["frozen_mq"] == 12

        # Verify transaction recorded
        txns = fake_db["token_transactions"].docs
        assert len(txns) == 1
        assert txns[0]["type"] == "preoccupy"
        assert txns[0]["amount_mq"] == 12

    asyncio.run(_run())


def test_preoccupy_balance_insufficient_raises(monkeypatch):
    import app.services.token_billing_service as tbs
    _reset_cache()
    _mock_config_service(monkeypatch)

    fake_db = _FakeDB()
    fake_redis = _FakeRedis()
    monkeypatch.setattr(tbs, "get_mongo_db", lambda: fake_db)
    import app.core.database as db_mod
    monkeypatch.setattr(db_mod, "get_redis_client", lambda: fake_redis)

    async def _run():
        svc = tbs.TokenBillingService()
        await svc.get_or_create_account("user1")
        fake_db["token_accounts"].docs[0]["balance_mq"] = 5  # 5 mq

        try:
            await svc.preoccupy_balance("user1", estimated_round_tokens=4096)
            assert False, "Should have raised InsufficientBalanceError"
        except tbs.InsufficientBalanceError as e:
            assert e.required_mq == 12
            assert e.available_mq == 5

    asyncio.run(_run())


def test_preoccupy_balance_redis_exhausted_flag(monkeypatch):
    import app.services.token_billing_service as tbs
    _reset_cache()
    _mock_config_service(monkeypatch)

    fake_db = _FakeDB()
    fake_redis = _FakeRedis()
    monkeypatch.setattr(tbs, "get_mongo_db", lambda: fake_db)
    import app.core.database as db_mod
    monkeypatch.setattr(db_mod, "get_redis_client", lambda: fake_redis)

    async def _run():
        svc = tbs.TokenBillingService()
        await svc.get_or_create_account("user1")
        fake_db["token_accounts"].docs[0]["balance_mq"] = 100000

        # Set exhausted flag
        await fake_redis.setex("token_balance_exhausted:user1", 300, "1")

        try:
            await svc.preoccupy_balance("user1", estimated_round_tokens=4096)
            assert False, "Should have raised InsufficientBalanceError"
        except tbs.InsufficientBalanceError as e:
            assert e.required_mq == 1
            assert e.available_mq == 0

    asyncio.run(_run())


def test_preoccupy_balance_exact_boundary(monkeypatch):
    import app.services.token_billing_service as tbs
    _reset_cache()
    _mock_config_service(monkeypatch)

    fake_db = _FakeDB()
    fake_redis = _FakeRedis()
    monkeypatch.setattr(tbs, "get_mongo_db", lambda: fake_db)
    import app.core.database as db_mod
    monkeypatch.setattr(db_mod, "get_redis_client", lambda: fake_redis)

    async def _run():
        svc = tbs.TokenBillingService()
        await svc.get_or_create_account("user1")
        # Balance exactly equal to preoccupy amount (12 mq for 4096 tokens)
        fake_db["token_accounts"].docs[0]["balance_mq"] = 12

        txn_id, preoccupy_mq = await svc.preoccupy_balance("user1", estimated_round_tokens=4096)
        assert preoccupy_mq == 12
        account = fake_db["token_accounts"].docs[0]
        assert account["balance_mq"] == 0
        assert account["frozen_mq"] == 12

    asyncio.run(_run())


def test_preoccupy_balance_minimum_1mq(monkeypatch):
    import app.services.token_billing_service as tbs
    _reset_cache()
    _mock_config_service(monkeypatch)

    fake_db = _FakeDB()
    fake_redis = _FakeRedis()
    monkeypatch.setattr(tbs, "get_mongo_db", lambda: fake_db)
    import app.core.database as db_mod
    monkeypatch.setattr(db_mod, "get_redis_client", lambda: fake_redis)

    async def _run():
        svc = tbs.TokenBillingService()
        await svc.get_or_create_account("user1")
        fake_db["token_accounts"].docs[0]["balance_mq"] = 100

        # 0 tokens → computed mq would be 0, clamped to 1
        txn_id, preoccupy_mq = await svc.preoccupy_balance("user1", estimated_round_tokens=0)
        assert preoccupy_mq == 1
        account = fake_db["token_accounts"].docs[0]
        assert account["balance_mq"] == 99
        assert account["frozen_mq"] == 1

    asyncio.run(_run())


# ===========================================================================
# LLM 用量结算：测试 settle_llm_usage 的扣费逻辑，包括冻结覆盖、超额扣减、零消耗边界等
# ===========================================================================

def test_settle_llm_usage_frozen_only(monkeypatch):
    """frozen covers full deduction → balance unchanged."""
    import app.services.token_billing_service as tbs
    _reset_cache()
    _mock_config_service(monkeypatch)

    fake_db = _FakeDB()
    monkeypatch.setattr(tbs, "get_mongo_db", lambda: fake_db)

    async def _run():
        svc = tbs.TokenBillingService()
        await svc.get_or_create_account("user1")
        acct = fake_db["token_accounts"].docs[0]
        acct["balance_mq"] = 1000
        acct["frozen_mq"] = 100
        acct["total_consumed_mq"] = 0

        # prompt=1000, completion=1000
        # real_cost_yuan = 1000*1.0/1e6 + 1000*2.0/1e6 = 0.003
        # deduction_mq = round(0.003 * 1.2 * 1000) = round(3.6) = 4
        result = await svc.settle_llm_usage(
            "user1", task_id="t1", session_id="s1",
            prompt_tokens=1000, completion_tokens=1000,
        )
        assert result["deduction_mq"] == 4
        # frozen was 100, deduct 4 → frozen=96, balance stays 1000
        acct = fake_db["token_accounts"].docs[0]
        assert acct["frozen_mq"] == 96
        assert acct["balance_mq"] == 1000

    asyncio.run(_run())


def test_settle_llm_usage_overspend(monkeypatch):
    """frozen insufficient → remainder deducted from balance."""
    import app.services.token_billing_service as tbs
    _reset_cache()
    _mock_config_service(monkeypatch)

    fake_db = _FakeDB()
    monkeypatch.setattr(tbs, "get_mongo_db", lambda: fake_db)

    async def _run():
        svc = tbs.TokenBillingService()
        await svc.get_or_create_account("user1")
        acct = fake_db["token_accounts"].docs[0]
        acct["balance_mq"] = 100
        acct["frozen_mq"] = 10
        acct["total_consumed_mq"] = 0

        # Use large tokens to produce deduction > frozen
        # prompt=10000, completion=10000
        # real_cost_yuan = 10000*1.0/1e6 + 10000*2.0/1e6 = 0.03
        # deduction_mq = round(0.03 * 1.2 * 1000) = round(36) = 36
        result = await svc.settle_llm_usage(
            "user1", task_id="t1", session_id="s1",
            prompt_tokens=10000, completion_tokens=10000,
        )
        assert result["deduction_mq"] == 36
        acct = fake_db["token_accounts"].docs[0]
        # frozen was 10, deduct 36 → frozen=max(10-36,0)=0
        assert acct["frozen_mq"] == 0
        # overspend = 36-10 = 26 → balance = 100-26 = 74
        assert acct["balance_mq"] == 74

    asyncio.run(_run())


def test_settle_llm_usage_zero_cost_returns_actual_balance(monkeypatch):
    """Bug B5 verification: 0 tokens returns actual balance, NOT 0."""
    import app.services.token_billing_service as tbs
    _reset_cache()
    _mock_config_service(monkeypatch)

    fake_db = _FakeDB()
    monkeypatch.setattr(tbs, "get_mongo_db", lambda: fake_db)

    async def _run():
        svc = tbs.TokenBillingService()
        await svc.get_or_create_account("user1")
        fake_db["token_accounts"].docs[0]["balance_mq"] = 9999

        result = await svc.settle_llm_usage(
            "user1", task_id="t1", session_id="s1",
            prompt_tokens=0, completion_tokens=0,
        )
        assert result["deduction_mq"] == 0
        assert result["new_balance_mq"] == 9999  # actual balance, not 0
        assert result["txn_id"] is None

    asyncio.run(_run())


def test_settle_llm_usage_negative_balance(monkeypatch):
    """Balance can go negative when frozen=0 and deduction exceeds balance."""
    import app.services.token_billing_service as tbs
    _reset_cache()
    _mock_config_service(monkeypatch)

    fake_db = _FakeDB()
    monkeypatch.setattr(tbs, "get_mongo_db", lambda: fake_db)

    async def _run():
        svc = tbs.TokenBillingService()
        await svc.get_or_create_account("user1")
        acct = fake_db["token_accounts"].docs[0]
        acct["balance_mq"] = 10
        acct["frozen_mq"] = 0
        acct["total_consumed_mq"] = 0

        # Large tokens: deduction_mq = 36 (same calc as overspend test)
        result = await svc.settle_llm_usage(
            "user1", task_id="t1", session_id="s1",
            prompt_tokens=10000, completion_tokens=10000,
        )
        assert result["deduction_mq"] == 36
        acct = fake_db["token_accounts"].docs[0]
        assert acct["frozen_mq"] == 0
        assert acct["balance_mq"] == 10 - 36  # = -26

    asyncio.run(_run())


def test_settle_llm_usage_creates_consume_txn(monkeypatch):
    """Verify consume transaction inserted with correct fields."""
    import app.services.token_billing_service as tbs
    _reset_cache()
    _mock_config_service(monkeypatch)

    fake_db = _FakeDB()
    monkeypatch.setattr(tbs, "get_mongo_db", lambda: fake_db)

    async def _run():
        svc = tbs.TokenBillingService()
        await svc.get_or_create_account("user1")
        acct = fake_db["token_accounts"].docs[0]
        acct["balance_mq"] = 1000
        acct["frozen_mq"] = 50
        acct["total_consumed_mq"] = 0

        result = await svc.settle_llm_usage(
            "user1", task_id="task_abc", session_id="sess_xyz",
            prompt_tokens=1000, completion_tokens=1000,
            model="gpt-4", preoccupy_txn_id="PRE_001",
        )
        assert result["txn_id"] is not None
        assert result["txn_id"].startswith("CON_")

        txns = fake_db["token_transactions"].docs
        assert len(txns) == 1
        txn = txns[0]
        assert txn["type"] == "consume"
        assert txn["direction"] == "out"
        assert txn["user_id"] == "user1"
        assert txn["related_txn_id"] == "PRE_001"
        assert txn["metadata"]["session_id"] == "sess_xyz"
        assert txn["metadata"]["task_id"] == "task_abc"
        assert txn["metadata"]["model"] == "gpt-4"
        assert txn["status"] == "success"

    asyncio.run(_run())


# ===========================================================================
# 冻结释放：测试 release_frozen 将剩余冻结额度归还余额，以及零冻结时的空操作优化
# ===========================================================================

def test_release_frozen_all_remaining(monkeypatch):
    """Bug B2: release_frozen(user, 0) releases ALL remaining frozen."""
    import app.services.token_billing_service as tbs
    _reset_cache()
    _mock_config_service(monkeypatch)

    fake_db = _FakeDB()
    monkeypatch.setattr(tbs, "get_mongo_db", lambda: fake_db)

    async def _run():
        svc = tbs.TokenBillingService()
        await svc.get_or_create_account("user1")
        acct = fake_db["token_accounts"].docs[0]
        acct["balance_mq"] = 500
        acct["frozen_mq"] = 50

        await svc.release_frozen("user1", 0)

        acct = fake_db["token_accounts"].docs[0]
        assert acct["frozen_mq"] == 0
        assert acct["balance_mq"] == 550  # 500 + 50

    asyncio.run(_run())


def test_release_frozen_noop_when_zero(monkeypatch):
    """When frozen=0, release_frozen does nothing (no DB write)."""
    import app.services.token_billing_service as tbs
    _reset_cache()
    _mock_config_service(monkeypatch)

    fake_db = _FakeDB()
    monkeypatch.setattr(tbs, "get_mongo_db", lambda: fake_db)

    async def _run():
        svc = tbs.TokenBillingService()
        await svc.get_or_create_account("user1")
        acct = fake_db["token_accounts"].docs[0]
        acct["balance_mq"] = 500
        acct["frozen_mq"] = 0

        await svc.release_frozen("user1", 0)

        # No transaction should be created
        assert len(fake_db["token_transactions"].docs) == 0
        # Balance unchanged
        assert fake_db["token_accounts"].docs[0]["balance_mq"] == 500

    asyncio.run(_run())


def test_release_frozen_creates_settle_refund_txn(monkeypatch):
    """Verify settle_refund transaction is created."""
    import app.services.token_billing_service as tbs
    _reset_cache()
    _mock_config_service(monkeypatch)

    fake_db = _FakeDB()
    monkeypatch.setattr(tbs, "get_mongo_db", lambda: fake_db)

    async def _run():
        svc = tbs.TokenBillingService()
        await svc.get_or_create_account("user1")
        acct = fake_db["token_accounts"].docs[0]
        acct["balance_mq"] = 200
        acct["frozen_mq"] = 30

        await svc.release_frozen("user1", 0, reason="task_complete")

        txns = fake_db["token_transactions"].docs
        assert len(txns) == 1
        txn = txns[0]
        assert txn["type"] == "settle_refund"
        assert txn["direction"] == "in"
        assert txn["amount_mq"] == 30
        assert txn["balance_before_mq"] == 200
        assert txn["balance_after_mq"] == 230
        assert txn["metadata"]["reason"] == "task_complete"
        assert txn["txn_id"].startswith("REL_")

    asyncio.run(_run())


# ===========================================================================
# 充值入账：测试 credit_quota 的本金+赠送拆分、Redis 耗尽标记清除等
# ===========================================================================

def test_credit_quota_with_gift(monkeypatch):
    """Credit with gift creates both recharge and gift transactions."""
    import app.services.token_billing_service as tbs
    _reset_cache()
    _mock_config_service(monkeypatch)

    fake_db = _FakeDB()
    fake_redis = _FakeRedis()
    monkeypatch.setattr(tbs, "get_mongo_db", lambda: fake_db)
    import app.core.database as db_mod
    monkeypatch.setattr(db_mod, "get_redis_client", lambda: fake_redis)

    async def _run():
        svc = tbs.TokenBillingService()
        result = await svc.credit_quota(
            user_id="user1",
            quota_mq=11000,   # total credits
            gift_mq=1000,     # gift portion
            order_id="ORD001",
            amount_cny_mq=10000,  # paid 10 yuan
        )
        assert result is True

        acct = fake_db["token_accounts"].docs[0]
        assert acct["balance_mq"] == 11000
        assert acct["total_recharged_mq"] == 10000
        assert acct["total_gifted_mq"] == 1000

        txns = fake_db["token_transactions"].docs
        assert len(txns) == 2
        types = {t["type"] for t in txns}
        assert types == {"recharge", "gift"}

        recharge_txn = [t for t in txns if t["type"] == "recharge"][0]
        assert recharge_txn["amount_mq"] == 10000  # principal = quota - gift
        assert recharge_txn["direction"] == "in"

        gift_txn = [t for t in txns if t["type"] == "gift"][0]
        assert gift_txn["amount_mq"] == 1000
        assert gift_txn["related_txn_id"] == recharge_txn["txn_id"]

    asyncio.run(_run())


def test_credit_quota_without_gift(monkeypatch):
    """gift_mq=0 → only recharge transaction, no gift."""
    import app.services.token_billing_service as tbs
    _reset_cache()
    _mock_config_service(monkeypatch)

    fake_db = _FakeDB()
    fake_redis = _FakeRedis()
    monkeypatch.setattr(tbs, "get_mongo_db", lambda: fake_db)
    import app.core.database as db_mod
    monkeypatch.setattr(db_mod, "get_redis_client", lambda: fake_redis)

    async def _run():
        svc = tbs.TokenBillingService()
        result = await svc.credit_quota(
            user_id="user1",
            quota_mq=10000,
            gift_mq=0,
            order_id="ORD002",
            amount_cny_mq=10000,
        )
        assert result is True

        txns = fake_db["token_transactions"].docs
        assert len(txns) == 1
        assert txns[0]["type"] == "recharge"
        assert txns[0]["amount_mq"] == 10000

    asyncio.run(_run())


def test_credit_quota_clears_redis_exhausted(monkeypatch):
    """After credit, redis.delete called for exhausted flag."""
    import app.services.token_billing_service as tbs
    _reset_cache()
    _mock_config_service(monkeypatch)

    fake_db = _FakeDB()
    fake_redis = _FakeRedis()
    monkeypatch.setattr(tbs, "get_mongo_db", lambda: fake_db)
    import app.core.database as db_mod
    monkeypatch.setattr(db_mod, "get_redis_client", lambda: fake_redis)

    async def _run():
        # Pre-set exhausted flag
        await fake_redis.setex("token_balance_exhausted:user1", 300, "1")
        assert await fake_redis.get("token_balance_exhausted:user1") == "1"

        svc = tbs.TokenBillingService()
        await svc.credit_quota(
            user_id="user1",
            quota_mq=5000,
            gift_mq=0,
            order_id="ORD003",
            amount_cny_mq=5000,
        )

        # Flag should be cleared
        assert await fake_redis.get("token_balance_exhausted:user1") is None

    asyncio.run(_run())


# ===========================================================================
# 订单管理：测试创建订单、幂等去重、状态流转（pending→credited/expired）等
# ===========================================================================

def test_create_order_with_package(monkeypatch):
    """Valid package_id → order created successfully."""
    import app.services.token_billing_service as tbs
    _reset_cache()
    _mock_config_service(monkeypatch)

    fake_db = _FakeDB()
    monkeypatch.setattr(tbs, "get_mongo_db", lambda: fake_db)

    async def _run():
        # Seed a package
        fake_db["token_packages"].docs.append({
            "package_id": "pkg_100",
            "name": "100元套餐",
            "amount_cny": 100.0,
            "sort_order": 1,
            "enabled": True,
            "tags": [],
        })

        svc = tbs.TokenBillingService()
        order = await svc.create_order(
            user_id="user1",
            package_id="pkg_100",
            custom_amount_mq=None,
            idempotency_key="idem_001",
            pay_type="NATIVE",
        )
        assert order["order_id"].startswith("RC")
        assert order["user_id"] == "user1"
        assert order["status"] == "pending"
        assert order["package_id"] == "pkg_100"
        # amount_mq = yuan_to_mq(100.0) = 100000
        assert order["amount_mq"] == 100000
        # quota = round(100000 * 1.1) = 110000
        assert order["quota_to_credit_mq"] == 110000
        # gift = 110000 - 100000 = 10000
        assert order["gift_amount_mq"] == 10000

    asyncio.run(_run())


def test_create_order_invalid_package_raises(monkeypatch):
    """Nonexistent package → ValueError."""
    import app.services.token_billing_service as tbs
    _reset_cache()
    _mock_config_service(monkeypatch)

    fake_db = _FakeDB()
    monkeypatch.setattr(tbs, "get_mongo_db", lambda: fake_db)

    async def _run():
        svc = tbs.TokenBillingService()
        try:
            await svc.create_order(
                user_id="user1",
                package_id="nonexistent_pkg",
                custom_amount_mq=None,
                idempotency_key="idem_002",
                pay_type="NATIVE",
            )
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "无效的套餐ID" in str(e)

    asyncio.run(_run())


def test_create_order_idempotency_duplicate(monkeypatch):
    """Same idempotency_key → DuplicateOrderError."""
    import app.services.token_billing_service as tbs
    _reset_cache()
    _mock_config_service(monkeypatch)

    fake_db = _FakeDB()
    monkeypatch.setattr(tbs, "get_mongo_db", lambda: fake_db)

    async def _run():
        # Seed a package
        fake_db["token_packages"].docs.append({
            "package_id": "pkg_50",
            "name": "50元套餐",
            "amount_cny": 50.0,
            "sort_order": 1,
            "enabled": True,
            "tags": [],
        })

        svc = tbs.TokenBillingService()
        first_order = await svc.create_order(
            user_id="user1",
            package_id="pkg_50",
            custom_amount_mq=None,
            idempotency_key="idem_dup",
            pay_type="NATIVE",
        )

        try:
            await svc.create_order(
                user_id="user1",
                package_id="pkg_50",
                custom_amount_mq=None,
                idempotency_key="idem_dup",
                pay_type="NATIVE",
            )
            assert False, "Should have raised DuplicateOrderError"
        except tbs.DuplicateOrderError as e:
            assert e.existing_order_id == first_order["order_id"]

    asyncio.run(_run())


def test_mark_order_credited_success(monkeypatch):
    """pending → credited transition succeeds."""
    import app.services.token_billing_service as tbs
    _reset_cache()
    _mock_config_service(monkeypatch)

    fake_db = _FakeDB()
    monkeypatch.setattr(tbs, "get_mongo_db", lambda: fake_db)

    async def _run():
        # Insert a pending order directly
        fake_db["token_recharge_orders"].docs.append({
            "order_id": "ORD_CRED",
            "user_id": "user1",
            "status": "pending",
            "wx_transaction_id": None,
            "callback_raw": None,
            "credited_at": None,
            "updated_at": "2025-01-01T00:00:00",
        })

        svc = tbs.TokenBillingService()
        result = await svc.mark_order_credited(
            order_id="ORD_CRED",
            wx_transaction_id="WX_TXN_001",
            callback_raw={"event": "SUCCESS"},
        )
        assert result is True

        order = fake_db["token_recharge_orders"].docs[0]
        assert order["status"] == "credited"
        assert order["wx_transaction_id"] == "WX_TXN_001"
        assert order["callback_raw"] == {"event": "SUCCESS"}
        assert order["credited_at"] is not None

    asyncio.run(_run())


def test_mark_order_credited_already_credited_returns_false(monkeypatch):
    """Bug B3: Already credited → returns False (no double credit)."""
    import app.services.token_billing_service as tbs
    _reset_cache()
    _mock_config_service(monkeypatch)

    fake_db = _FakeDB()
    monkeypatch.setattr(tbs, "get_mongo_db", lambda: fake_db)

    async def _run():
        fake_db["token_recharge_orders"].docs.append({
            "order_id": "ORD_DUP",
            "user_id": "user1",
            "status": "credited",
            "wx_transaction_id": "WX_OLD",
            "callback_raw": {},
            "credited_at": "2025-01-01T00:00:00",
            "updated_at": "2025-01-01T00:00:00",
        })

        svc = tbs.TokenBillingService()
        result = await svc.mark_order_credited(
            order_id="ORD_DUP",
            wx_transaction_id="WX_NEW",
            callback_raw={"event": "SUCCESS"},
        )
        assert result is False

        # Status should remain credited with original data
        order = fake_db["token_recharge_orders"].docs[0]
        assert order["status"] == "credited"
        assert order["wx_transaction_id"] == "WX_OLD"

    asyncio.run(_run())


def test_expire_stale_orders(monkeypatch):
    """Pending orders past expire_at → marked expired."""
    import app.services.token_billing_service as tbs
    _reset_cache()
    _mock_config_service(monkeypatch)

    fake_db = _FakeDB()
    monkeypatch.setattr(tbs, "get_mongo_db", lambda: fake_db)

    async def _run():
        from app.utils.timezone import now_tz
        from datetime import timedelta

        past = (now_tz() - timedelta(hours=1)).isoformat()
        future = (now_tz() + timedelta(hours=1)).isoformat()

        fake_db["token_recharge_orders"].docs.extend([
            {"order_id": "EXP1", "status": "pending", "expire_at": past, "updated_at": past},
            {"order_id": "EXP2", "status": "pending", "expire_at": past, "updated_at": past},
            {"order_id": "VALID", "status": "pending", "expire_at": future, "updated_at": past},
            {"order_id": "CRED", "status": "credited", "expire_at": past, "updated_at": past},
        ])

        svc = tbs.TokenBillingService()
        count = await svc.expire_stale_orders()
        assert count == 2

        statuses = {d["order_id"]: d["status"] for d in fake_db["token_recharge_orders"].docs}
        assert statuses["EXP1"] == "expired"
        assert statuses["EXP2"] == "expired"
        assert statuses["VALID"] == "pending"
        assert statuses["CRED"] == "credited"

    asyncio.run(_run())


# ===========================================================================
# 对账清理：测试 reconcile_stale_frozen 释放超时冻结的账户
# ===========================================================================

def test_reconcile_stale_frozen(monkeypatch):
    """Accounts with frozen>0 and updated_at > 10min ago → released."""
    import app.services.token_billing_service as tbs
    _reset_cache()
    _mock_config_service(monkeypatch)

    fake_db = _FakeDB()
    monkeypatch.setattr(tbs, "get_mongo_db", lambda: fake_db)

    async def _run():
        from app.utils.timezone import now_tz
        from datetime import timedelta

        stale_time = (now_tz() - timedelta(minutes=15)).isoformat()
        recent_time = now_tz().isoformat()

        fake_db["token_accounts"].docs.extend([
            {
                "user_id": "stale_user",
                "balance_mq": 1000,
                "frozen_mq": 50,
                "total_consumed_mq": 0,
                "total_recharged_mq": 0,
                "total_gifted_mq": 0,
                "updated_at": stale_time,
                "created_at": stale_time,
            },
            {
                "user_id": "recent_user",
                "balance_mq": 2000,
                "frozen_mq": 30,
                "total_consumed_mq": 0,
                "total_recharged_mq": 0,
                "total_gifted_mq": 0,
                "updated_at": recent_time,
                "created_at": recent_time,
            },
        ])

        svc = tbs.TokenBillingService()
        count = await svc.reconcile_stale_frozen()
        assert count == 1

        # Stale user's frozen should be released
        stale_acct = [a for a in fake_db["token_accounts"].docs if a["user_id"] == "stale_user"][0]
        assert stale_acct["frozen_mq"] == 0
        assert stale_acct["balance_mq"] == 1050  # 1000 + 50

        # Recent user untouched
        recent_acct = [a for a in fake_db["token_accounts"].docs if a["user_id"] == "recent_user"][0]
        assert recent_acct["frozen_mq"] == 30
        assert recent_acct["balance_mq"] == 2000

    asyncio.run(_run())


# ===========================================================================
# 配置缓存：测试 _get_billing_config 的缓存命中/未命中及手动失效逻辑
# ===========================================================================

def test_get_billing_config_cache_miss(monkeypatch):
    """First call loads from config_service."""
    import app.services.token_billing_service as tbs
    _reset_cache()

    mock_svc = _mock_config_service(monkeypatch)

    async def _run():
        config = await tbs._get_billing_config()
        assert config["consumption_ratio"] == 1.2
        assert config["input_price"] == 1.0
        assert config["output_price"] == 2.0
        # config_service should have been called once
        mock_svc.get_system_config.assert_called_once()

    asyncio.run(_run())


def test_get_billing_config_cache_hit(monkeypatch):
    """Within TTL → config_service NOT called again."""
    import app.services.token_billing_service as tbs
    _reset_cache()

    mock_svc = _mock_config_service(monkeypatch)

    async def _run():
        # First call populates cache
        await tbs._get_billing_config()
        assert mock_svc.get_system_config.call_count == 1

        # Second call within TTL should use cache
        config = await tbs._get_billing_config()
        assert config["consumption_ratio"] == 1.2
        # Still only called once
        assert mock_svc.get_system_config.call_count == 1

    asyncio.run(_run())


def test_invalidate_billing_cache(monkeypatch):
    """After invalidate → next call refetches."""
    import app.services.token_billing_service as tbs
    _reset_cache()

    mock_svc = _mock_config_service(monkeypatch)

    async def _run():
        await tbs._get_billing_config()
        assert mock_svc.get_system_config.call_count == 1

        tbs.invalidate_billing_cache()

        await tbs._get_billing_config()
        assert mock_svc.get_system_config.call_count == 2

    asyncio.run(_run())


# ===========================================================================
# 账本不变量：验证 balance + frozen == sum(入) - sum(出)，确保扣费链路无资金泄漏
# ===========================================================================

def test_ledger_invariant(monkeypatch):
    """
    For a user: balance + frozen == sum(in txns) - sum(out txns).

    Note: The preoccupy/settle_refund pair acts as an internal transfer
    (balance→frozen→balance). To keep the invariant clean we verify it
    on a lifecycle that uses credit + direct consume (no preoccupy),
    then separately verify that a full preoccupy→settle→release cycle
    preserves total value (balance+frozen unchanged by the round-trip).
    """
    import app.services.token_billing_service as tbs
    _reset_cache()
    _mock_config_service(monkeypatch)

    fake_db = _FakeDB()
    fake_redis = _FakeRedis()
    monkeypatch.setattr(tbs, "get_mongo_db", lambda: fake_db)
    import app.core.database as db_mod
    monkeypatch.setattr(db_mod, "get_redis_client", lambda: fake_redis)

    async def _run():
        svc = tbs.TokenBillingService()

        # --- Part A: clean invariant with credit + consume (no frozen ops) ---
        await svc.get_or_create_account("userA")
        acct_a = fake_db["token_accounts"].docs[0]
        acct_a["balance_mq"] = 0
        acct_a["frozen_mq"] = 0

        # Credit 10000 mq
        await svc.credit_quota("userA", quota_mq=10000, gift_mq=0,
                               order_id="O_A", amount_cny_mq=10000)

        # Consume 4 mq (frozen=0, so entire deduction comes from balance)
        await svc.settle_llm_usage("userA", task_id="t1", session_id="s1",
                                    prompt_tokens=1000, completion_tokens=1000)

        acct_a = fake_db["token_accounts"].docs[0]
        # Only recharge (in) and consume (out) transactions for userA
        txns_a = [t for t in fake_db["token_transactions"].docs if t["user_id"] == "userA"]
        sum_in_a = sum(t["amount_mq"] for t in txns_a if t["direction"] == "in")
        sum_out_a = sum(t["amount_mq"] for t in txns_a if t["direction"] == "out")
        total_a = acct_a["balance_mq"] + acct_a["frozen_mq"]
        assert total_a == sum_in_a - sum_out_a, (
            f"Part A invariant failed: balance+frozen={total_a}, "
            f"in={sum_in_a}, out={sum_out_a}"
        )

        # --- Part B: full preoccupy→settle→release preserves total value ---
        await svc.get_or_create_account("userB")
        acct_b = [a for a in fake_db["token_accounts"].docs if a["user_id"] == "userB"][0]
        acct_b["balance_mq"] = 5000
        acct_b["frozen_mq"] = 0

        total_before = acct_b["balance_mq"] + acct_b["frozen_mq"]  # 5000

        # Preoccupy
        _, preoccupy_mq = await svc.preoccupy_balance("userB", estimated_round_tokens=4096)
        # Settle
        settle_result = await svc.settle_llm_usage(
            "userB", task_id="t2", session_id="s2",
            prompt_tokens=1000, completion_tokens=1000,
        )
        # Release remaining frozen
        await svc.release_frozen("userB", 0)

        acct_b = [a for a in fake_db["token_accounts"].docs if a["user_id"] == "userB"][0]
        total_after = acct_b["balance_mq"] + acct_b["frozen_mq"]
        consumed = settle_result["deduction_mq"]

        # Total should decrease by exactly the consumed amount
        assert total_before - total_after == consumed, (
            f"Part B value conservation failed: before={total_before}, "
            f"after={total_after}, consumed={consumed}"
        )
        assert acct_b["frozen_mq"] == 0

    asyncio.run(_run())
