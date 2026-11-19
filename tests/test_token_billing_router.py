"""
Token 计费路由 — API 集成测试。

测试策略说明：
- 使用 FastAPI TestClient 发送 HTTP 请求，验证路由层的参数校验、状态码和响应结构。
- 通过 app.dependency_overrides[get_current_user] 注入模拟用户身份，
  无需真实 JWT 即可测试认证/鉴权逻辑（NORMAL_USER / ADMIN_USER）。
- 复用 test_token_billing_service.py 中的 _FakeDB/_FakeRedis 基础设施，
  经 monkeypatch 注入到被测模块命名空间，避免连接真实数据库。
- 每个测试通过 _make_client() 构建独立的 TestClient 实例，确保隔离性。
"""

import asyncio
import json
import re
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fake infrastructure (copied from test_token_billing_service.py)
# ---------------------------------------------------------------------------

def _eval_expr(expr, doc):
    """Recursively evaluate an aggregation pipeline expression against *doc*."""
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
        return expr
    return expr


def _match_filter(doc: dict, filt: dict) -> bool:
    """Very small subset of MongoDB query matching used by the tests."""
    def _get_value(key: str):
        if "." not in key:
            return doc.get(key)
        current = doc
        for part in key.split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current

    if "$or" in filt:
        or_filters = filt["$or"]
        if not any(_match_filter(doc, sub_filter) for sub_filter in or_filters):
            return False
        filt = {k: v for k, v in filt.items() if k != "$or"}

    for key, val in filt.items():
        doc_val = _get_value(key)
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
                elif op == "$ne":
                    if doc_val == operand:
                        return False
                elif op == "$in":
                    if doc_val not in operand:
                        return False
                elif op == "$regex":
                    options = str(val.get("$options", ""))
                    flags = re.IGNORECASE if "i" in options else 0
                    if not re.search(operand, str(doc_val or ""), flags=flags):
                        return False
                elif op == "$options":
                    continue
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

    async def find_one(self, filt: dict, projection=None, sort=None):
        for doc in self.docs:
            if _match_filter(doc, filt):
                result = dict(doc)
                if projection:
                    included = {k for k, v in projection.items() if v == 1}
                    if included:
                        result = {k: doc[k] for k in included if k in doc}
                return result
        return None

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
                if isinstance(update, dict) and "$setOnInsert" in update:
                    new_doc.update(update["$setOnInsert"])
                if isinstance(update, dict) and "$set" in update:
                    new_doc.update(update["$set"])
                self.docs.append(new_doc)
                target = new_doc
            else:
                return None

        before_doc = dict(target)

        if isinstance(update, list):
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

        if return_document == ReturnDocument.AFTER:
            return dict(target)
        else:
            return dict(before_doc)

    async def insert_one(self, doc: dict):
        self.docs.append(dict(doc))

    async def update_many(self, filt: dict, update: dict):
        count = 0
        for doc in self.docs:
            if _match_filter(doc, filt):
                if "$set" in update:
                    for k, v in update["$set"].items():
                        doc[k] = v
                count += 1
        return _UpdateResult(count)

    async def count_documents(self, filt: dict):
        return sum(1 for doc in self.docs if _match_filter(doc, filt))

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NORMAL_USER = {"id": "user1", "username": "testuser", "is_admin": False}
ADMIN_USER = {"id": "admin1", "username": "admin", "is_admin": True}


def _reset_cache():
    """Reset the module-level billing config cache."""
    import app.services.token_billing_service as tbs
    tbs._billing_cache = {}
    tbs._billing_cache_ts = 0


def _mock_config_service():
    """Return a mock config_service object."""
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
    mock_svc.update_system_settings = AsyncMock(return_value=True)
    return mock_svc


def _make_client(user=None, fake_db=None):
    """Build a TestClient with optional auth override and fake DB."""
    _reset_cache()

    app = FastAPI()
    from app.routers.token_billing import router
    app.include_router(router, prefix="/api")

    if user:
        from app.routers.auth_db import get_current_user
        app.dependency_overrides[get_current_user] = lambda: user

    if fake_db:
        import app.services.token_billing_service as tbs
        import app.routers.token_billing as rtb
        tbs.get_mongo_db = lambda: fake_db
        # The wxpay_notify endpoint imports get_mongo_db locally
        import app.core.database as db_mod
        db_mod.get_mongo_db = lambda: fake_db

    return TestClient(app)


def _seed_package(fake_db, package_id="pkg_100", amount_cny=100.0):
    """Seed a package document into the fake DB."""
    fake_db["token_packages"].docs.append({
        "package_id": package_id,
        "name": f"{int(amount_cny)}元套餐",
        "amount_cny": amount_cny,
        "sort_order": 1,
        "enabled": True,
        "tags": [],
    })


def _seed_order(fake_db, order_id="RC20250101000001", user_id="user1",
                 status="pending", amount_mq=100000, quota_mq=110000,
                 gift_mq=10000):
    """Seed an order document into the fake DB."""
    from app.utils.timezone import now_tz
    now_iso = now_tz().isoformat()
    fake_db["token_recharge_orders"].docs.append({
        "order_id": order_id,
        "user_id": user_id,
        "package_id": "pkg_100",
        "amount_mq": amount_mq,
        "exchange_rate": 1.1,
        "quota_to_credit_mq": quota_mq,
        "gift_amount_mq": gift_mq,
        "pay_type": "NATIVE",
        "wx_out_trade_no": order_id,
        "wx_transaction_id": None,
        "wx_prepay_id": None,
        "wx_code_url": None,
        "wx_mweb_url": None,
        "status": status,
        "callback_raw": None,
        "credited_at": None,
        "expire_at": now_iso,
        "ab_group": None,
        "idempotency_key": f"idem_{order_id}",
        "created_at": now_iso,
        "updated_at": now_iso,
    })


# ===========================================================================
# 认证矩阵：验证未登录返回 401、非管理员访问管理接口返回 403
# ===========================================================================

def test_get_account_unauthorized():
    """No auth header → 401."""
    client = _make_client(user=None, fake_db=_FakeDB())
    resp = client.get("/api/token-billing/account")
    assert resp.status_code == 401


def test_admin_endpoint_forbidden():
    """Non-admin on /billing-config → 403."""
    fake_db = _FakeDB()
    client = _make_client(user=NORMAL_USER, fake_db=fake_db)

    mock_cs = _mock_config_service()
    with patch("app.services.config_service.config_service", mock_cs):
        resp = client.get("/api/token-billing/billing-config")
    assert resp.status_code == 403


# ===========================================================================
# 账户与套餐：验证 GET account 自动创建、GET packages 返回含汇率计算的额度
# ===========================================================================

def test_get_account_auto_creates():
    """GET /api/token-billing/account returns balance fields for new user."""
    fake_db = _FakeDB()
    client = _make_client(user=NORMAL_USER, fake_db=fake_db)

    mock_cs = _mock_config_service()
    with patch("app.services.config_service.config_service", mock_cs):
        resp = client.get("/api/token-billing/account")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "balance" in data
    assert "frozen" in data
    assert "total_recharged" in data
    assert "total_consumed" in data
    assert "total_gifted" in data
    assert data["balance"] == 0.0


def test_get_packages_with_rate():
    """GET /api/token-billing/packages returns items with quota_to_credit."""
    fake_db = _FakeDB()
    _seed_package(fake_db, "pkg_100", 100.0)
    client = _make_client(user=NORMAL_USER, fake_db=fake_db)

    mock_cs = _mock_config_service()
    with patch("app.services.config_service.config_service", mock_cs):
        resp = client.get("/api/token-billing/packages")

    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    pkg = items[0]
    assert pkg["package_id"] == "pkg_100"
    assert pkg["amount_cny"] == 100.0
    # quota_to_credit = round(100.0 * 1.1, 3) = 110.0
    assert pkg["quota_to_credit"] == 110.0
    assert pkg["gift_amount"] == 10.0


def test_get_public_packages_without_auth():
    """公开套餐只读接口无需登录，且不暴露账户字段。"""
    fake_db = _FakeDB()
    _seed_package(fake_db, "pkg_public", 50.0)
    client = _make_client(user=None, fake_db=fake_db)

    mock_cs = _mock_config_service()
    with patch("app.services.config_service.config_service", mock_cs):
        resp = client.get("/api/token-billing/public-packages")

    assert resp.status_code == 200
    payload = resp.json()["data"]
    assert payload["items"][0]["amount_cny"] == 50.0
    assert payload["items"][0]["quota_to_credit"] == 55.0
    assert "balance" not in payload["items"][0]


# ===========================================================================
# 订单接口：验证创建订单正常流程、无效套餐 400、待支付订单查询可达性（Bug B1）
# ===========================================================================

def test_orders_pending_reachable():
    """GET /api/token-billing/orders/pending returns 200 NOT 404."""
    fake_db = _FakeDB()
    client = _make_client(user=NORMAL_USER, fake_db=fake_db)

    mock_cs = _mock_config_service()
    with patch("app.services.config_service.config_service", mock_cs):
        resp = client.get("/api/token-billing/orders/pending")

    assert resp.status_code == 200
    # No pending orders → data is None
    assert resp.json()["data"] is None


def test_create_order_happy_path():
    """POST /api/token-billing/orders with valid package_id → 200."""
    fake_db = _FakeDB()
    _seed_package(fake_db, "pkg_100", 100.0)
    client = _make_client(user=NORMAL_USER, fake_db=fake_db)

    mock_cs = _mock_config_service()
    mock_checkout = AsyncMock(return_value={
        "checkout_url": "https://checkout.test/session/1",
        "session_id": "session_1",
        "expires_at": "2026-09-14T01:00:00+08:00",
    })

    with patch("app.services.config_service.config_service", mock_cs), \
         patch("app.routers.token_billing.waffo_service.create_dynamic_checkout", mock_checkout):
        resp = client.post("/api/token-billing/orders", json={
            "package_id": "pkg_100",
            "idempotency_key": "idem_test_001",
        })

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["order_id"].startswith("RC")
    assert data["status"] == "pending"
    assert data["pay_type"] == "WAFFO"
    assert data["pay_params"]["checkout_url"] == "https://checkout.test/session/1"
    assert data["amount"] == 100.0
    assert data["quota_to_credit"] == 110.0
    assert data["gift_amount"] == 10.0


def test_create_order_invalid_package_400():
    """Invalid package_id → 400."""
    fake_db = _FakeDB()
    client = _make_client(user=NORMAL_USER, fake_db=fake_db)

    mock_cs = _mock_config_service()
    with patch("app.services.config_service.config_service", mock_cs):
        resp = client.post("/api/token-billing/orders", json={
            "package_id": "nonexistent_pkg",
            "idempotency_key": "idem_bad_001",
        })

    assert resp.status_code == 400


# ===========================================================================
# Waffo Webhook：验证签名校验失败、正常入账、幂等防重和缺失订单号处理
# ===========================================================================

def _waffo_event(order_id="RC_NOTIFY_001"):
    return {
        "eventType": "order.completed",
        "id": "evt_001",
        "mode": "live",
        "data": {
            "metadata": {"order_id": order_id},
            "orderId": "WF_001",
            "amount": 100,
            "currency": "CNY",
        },
    }


def test_waffo_webhook_signature_fail():
    """Invalid webhook signature → {code: FAIL}."""
    from app.services.waffo_service import WaffoWebhookError

    fake_db = _FakeDB()
    client = _make_client(user=None, fake_db=fake_db)
    with patch(
        "app.routers.token_billing.waffo_service.verify_webhook_signature",
        side_effect=WaffoWebhookError("bad signature"),
    ):
        resp = client.post(
            "/api/token-billing/waffo/webhook",
            content=b'{"eventType":"order.completed"}',
            headers={"x-waffo-signature": "invalid"},
        )

    assert resp.status_code == 200
    assert resp.json()["code"] == "FAIL"


def test_waffo_webhook_success_credits():
    """order.completed callback → credits quota."""
    fake_db = _FakeDB()
    _seed_order(fake_db, order_id="RC_NOTIFY_001", user_id="user1",
                status="pending", amount_mq=100000, quota_mq=110000, gift_mq=10000)
    client = _make_client(user=None, fake_db=fake_db)

    mock_cs = _mock_config_service()
    with patch("app.services.config_service.config_service", mock_cs), \
         patch(
             "app.routers.token_billing.waffo_service.verify_webhook_signature",
             return_value=_waffo_event(),
         ):
        resp = client.post(
            "/api/token-billing/waffo/webhook",
            content=json.dumps(_waffo_event()),
            headers={"x-waffo-signature": "sig"},
        )

    assert resp.status_code == 200
    assert resp.json()["code"] == "SUCCESS"

    acct = fake_db["token_accounts"].docs[0]
    assert acct["balance_mq"] == 110000
    assert acct["total_recharged_mq"] == 100000
    assert acct["total_gifted_mq"] == 10000

    order = fake_db["token_recharge_orders"].docs[0]
    assert order["status"] == "credited"


def test_waffo_webhook_idempotent_no_double_credit():
    """Second callback for same order doesn't double credit."""
    fake_db = _FakeDB()
    _seed_order(fake_db, order_id="RC_IDEM_001", user_id="user1",
                status="credited", amount_mq=100000, quota_mq=110000, gift_mq=10000)
    fake_db["token_accounts"].docs.append({
        "user_id": "user1",
        "balance_mq": 110000,
        "frozen_mq": 0,
        "total_recharged_mq": 100000,
        "total_consumed_mq": 0,
        "total_gifted_mq": 10000,
        "created_at": "2025-01-01T00:00:00",
        "updated_at": "2025-01-01T00:00:00",
    })
    client = _make_client(user=None, fake_db=fake_db)

    with patch(
        "app.routers.token_billing.waffo_service.verify_webhook_signature",
        return_value=_waffo_event("RC_IDEM_001"),
    ):
        resp = client.post(
            "/api/token-billing/waffo/webhook",
            content=json.dumps(_waffo_event("RC_IDEM_001")),
            headers={"x-waffo-signature": "sig"},
        )

    assert resp.status_code == 200
    assert resp.json()["code"] == "SUCCESS"
    assert fake_db["token_accounts"].docs[0]["balance_mq"] == 110000


def test_waffo_webhook_missing_order_id():
    """Missing metadata.order_id → acknowledged, no credit."""
    fake_db = _FakeDB()
    client = _make_client(user=None, fake_db=fake_db)
    event = _waffo_event()
    event["data"]["metadata"] = {}

    with patch(
        "app.routers.token_billing.waffo_service.verify_webhook_signature",
        return_value=event,
    ):
        resp = client.post(
            "/api/token-billing/waffo/webhook",
            content=json.dumps(event),
            headers={"x-waffo-signature": "sig"},
        )

    assert resp.status_code == 200
    assert resp.json()["code"] == "SUCCESS"
    assert fake_db["token_accounts"].docs == []


# ===========================================================================
# 交易明细：验证分页查询和 CSV 导出含 UTF-8 BOM（Bug B9）
# ===========================================================================

def test_get_transactions_pagination():
    """page/page_size params work correctly."""
    fake_db = _FakeDB()
    # Seed some transactions
    from app.utils.timezone import now_tz
    now_iso = now_tz().isoformat()
    for i in range(5):
        fake_db["token_transactions"].docs.append({
            "txn_id": f"TXN_{i:03d}",
            "user_id": "user1",
            "order_id": None,
            "type": "recharge",
            "direction": "in",
            "amount_mq": 1000 * (i + 1),
            "balance_before_mq": 0,
            "balance_after_mq": 1000 * (i + 1),
            "metadata": {},
            "status": "success",
            "related_txn_id": None,
            "created_at": now_iso,
        })

    client = _make_client(user=NORMAL_USER, fake_db=fake_db)

    mock_cs = _mock_config_service()
    with patch("app.services.config_service.config_service", mock_cs):
        resp = client.get("/api/token-billing/transactions?page=1&page_size=2")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 5
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert len(data["items"]) == 2


def test_export_csv_has_bom():
    """CSV export starts with UTF-8 BOM (Bug B9)."""
    fake_db = _FakeDB()
    from app.utils.timezone import now_tz
    now_iso = now_tz().isoformat()
    fake_db["token_transactions"].docs.append({
        "txn_id": "TXN_BOM",
        "user_id": "user1",
        "order_id": None,
        "type": "recharge",
        "direction": "in",
        "amount_mq": 10000,
        "balance_before_mq": 0,
        "balance_after_mq": 10000,
        "metadata": {},
        "status": "success",
        "related_txn_id": None,
        "created_at": now_iso,
    })

    client = _make_client(user=NORMAL_USER, fake_db=fake_db)

    mock_cs = _mock_config_service()
    with patch("app.services.config_service.config_service", mock_cs):
        resp = client.get("/api/token-billing/transactions/export")

    assert resp.status_code == 200
    content = resp.content
    # UTF-8 BOM is b'\xef\xbb\xbf'
    assert content.startswith(b'\xef\xbb\xbf')


# ===========================================================================
# 管理员接口：验证计费配置更新、空更新拒绝、对账触发
# ===========================================================================

def test_update_billing_config():
    """PUT /billing-config with valid payload → success."""
    fake_db = _FakeDB()
    client = _make_client(user=ADMIN_USER, fake_db=fake_db)

    mock_cs = _mock_config_service()
    with patch("app.services.config_service.config_service", mock_cs):
        resp = client.put("/api/token-billing/billing-config", json={
            "token_exchange_rate": 1.2,
            "token_consumption_ratio": 1.5,
        })

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "updated" in data
    assert len(data["updated"]) == 2


def test_update_billing_config_empty_400():
    """All-None payload → 400."""
    fake_db = _FakeDB()
    client = _make_client(user=ADMIN_USER, fake_db=fake_db)

    mock_cs = _mock_config_service()
    with patch("app.services.config_service.config_service", mock_cs):
        resp = client.put("/api/token-billing/billing-config", json={})

    assert resp.status_code == 400


def test_reconcile_admin():
    """POST /reconcile → reconciled_accounts count."""
    fake_db = _FakeDB()
    client = _make_client(user=ADMIN_USER, fake_db=fake_db)

    mock_cs = _mock_config_service()
    with patch("app.services.config_service.config_service", mock_cs):
        resp = client.post("/api/token-billing/reconcile")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "reconciled_accounts" in data
    assert isinstance(data["reconciled_accounts"], int)


# ===========================================================================
# 管理员运营接口：验证后台充值、账户查询、权限和充值记录搜索
# ===========================================================================

def _target_user(username="bob", is_archived=False):
    return SimpleNamespace(
        id="u1",
        username=username,
        email=f"{username}@example.com",
        is_archived=is_archived,
    )


def test_admin_recharge_success(monkeypatch):
    fake_db = _FakeDB()
    client = _make_client(user=ADMIN_USER, fake_db=fake_db)
    monkeypatch.setattr(
        "app.services.user_service.user_service.get_user_admin_detail",
        AsyncMock(return_value=_target_user()),
    )
    captured_logs = []

    async def capture_log(**kwargs):
        captured_logs.append(kwargs)

    monkeypatch.setattr("app.services.operation_log_service.log_operation", capture_log)

    resp = client.post("/api/token-billing/admin/recharge", json={
        "username": "bob",
        "amount": 12.34,
        "reason": "运营补偿",
    })

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["transaction"]["amount"] == 12.34
    assert data["account"]["balance"] == 12.34
    assert len(fake_db["token_transactions"].docs) == 1
    assert fake_db["token_transactions"].docs[0]["type"] == "admin_recharge"
    assert fake_db["token_transactions"].docs[0]["metadata"]["operator_username"] == "admin"
    assert len(captured_logs) == 1
    assert captured_logs[0]["action"] == "管理员充值算力"


def test_admin_recharge_rejects_missing_archived_and_bad_amount(monkeypatch):
    fake_db = _FakeDB()
    client = _make_client(user=ADMIN_USER, fake_db=fake_db)

    monkeypatch.setattr(
        "app.services.user_service.user_service.get_user_admin_detail",
        AsyncMock(return_value=None),
    )
    assert client.post("/api/token-billing/admin/recharge", json={
        "username": "missing",
        "amount": 5,
    }).status_code == 404

    monkeypatch.setattr(
        "app.services.user_service.user_service.get_user_admin_detail",
        AsyncMock(return_value=_target_user(is_archived=True)),
    )
    assert client.post("/api/token-billing/admin/recharge", json={
        "username": "bob",
        "amount": 5,
    }).status_code == 400

    assert client.post("/api/token-billing/admin/recharge", json={
        "username": "bob",
        "amount": 0,
    }).status_code == 422
    assert len(fake_db["token_transactions"].docs) == 0


def test_admin_recharge_requires_admin():
    fake_db = _FakeDB()
    client = _make_client(user=NORMAL_USER, fake_db=fake_db)
    assert client.post("/api/token-billing/admin/recharge", json={
        "username": "bob",
        "amount": 5,
    }).status_code == 403


def test_admin_get_user_account_and_transactions_requires_admin(monkeypatch):
    fake_db = _FakeDB()
    client = _make_client(user=NORMAL_USER, fake_db=fake_db)
    monkeypatch.setattr(
        "app.services.user_service.user_service.get_user_by_username",
        AsyncMock(return_value=_target_user()),
    )

    assert client.get("/api/token-billing/admin/users/bob/account").status_code == 403
    assert client.get("/api/token-billing/admin/transactions", params={"keyword": "bob"}).status_code == 403


def test_admin_transactions_search_and_user_join():
    fake_db = _FakeDB()
    fake_db["users"].docs.append({
        "_id": "u1",
        "username": "bob",
        "email": "bob@example.com",
    })
    fake_db["token_transactions"].docs.append({
        "txn_id": "ADM_001",
        "user_id": "u1",
        "order_id": None,
        "type": "admin_recharge",
        "direction": "in",
        "amount_mq": 5000,
        "balance_before_mq": 0,
        "balance_after_mq": 5000,
        "metadata": {"source": "admin_recharge", "operator_username": "admin"},
        "status": "success",
        "related_txn_id": None,
        "created_at": "2026-09-14T00:00:00+08:00",
    })
    client = _make_client(user=ADMIN_USER, fake_db=fake_db)

    resp = client.get("/api/token-billing/admin/transactions", params={"keyword": "bob"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["metadata"]["username"] == "bob"
    assert data["items"][0]["type"] == "admin_recharge"


# ===========================================================================
# 完整生命周期 E2E：从创建账户 → 下单 → Waffo Webhook → 验证余额和交易记录的全链路测试
# ===========================================================================

def test_full_recharge_lifecycle():
    """Create account → simulate callback → verify balance + transactions."""
    fake_db = _FakeDB()
    _seed_package(fake_db, "pkg_50", 50.0)
    client = _make_client(user=NORMAL_USER, fake_db=fake_db)

    mock_cs = _mock_config_service()
    mock_checkout = AsyncMock(return_value={
        "checkout_url": "https://checkout.test/session/lifecycle",
        "session_id": "session_lifecycle",
        "expires_at": "2026-09-14T01:00:00+08:00",
    })

    # Step 1: Get account (auto-creates)
    with patch("app.services.config_service.config_service", mock_cs):
        resp = client.get("/api/token-billing/account")
    assert resp.status_code == 200
    assert resp.json()["data"]["balance"] == 0.0

    # Step 2: Create order
    with patch("app.services.config_service.config_service", mock_cs), \
         patch("app.routers.token_billing.waffo_service.create_dynamic_checkout", mock_checkout):
        resp = client.post("/api/token-billing/orders", json={
            "package_id": "pkg_50",
            "idempotency_key": "lifecycle_idem_001",
        })
    assert resp.status_code == 200
    order_data = resp.json()["data"]
    order_id = order_data["order_id"]
    assert order_data["amount"] == 50.0
    assert order_data["quota_to_credit"] == 55.0

    # Step 3: Simulate Waffo webhook
    event = _waffo_event(order_id)
    with patch(
        "app.routers.token_billing.waffo_service.verify_webhook_signature",
        return_value=event,
    ):
        resp = client.post(
            "/api/token-billing/waffo/webhook",
            content=json.dumps(event),
            headers={"x-waffo-signature": "sig"},
        )
    assert resp.status_code == 200
    assert resp.json()["code"] == "SUCCESS"

    # Step 4: Verify balance updated
    with patch("app.services.config_service.config_service", mock_cs):
        resp = client.get("/api/token-billing/account")
    assert resp.status_code == 200
    acct_data = resp.json()["data"]
    assert acct_data["balance"] == 55.0  # 55000 mq / 1000
    assert acct_data["total_recharged"] == 50.0
    assert acct_data["total_gifted"] == 5.0

    # Step 5: Verify transactions exist
    with patch("app.services.config_service.config_service", mock_cs):
        resp = client.get("/api/token-billing/transactions")
    assert resp.status_code == 200
    txns = resp.json()["data"]["items"]
    assert len(txns) >= 2  # at least recharge + gift
    types = {t["type"] for t in txns}
    assert "recharge" in types
    assert "gift" in types
