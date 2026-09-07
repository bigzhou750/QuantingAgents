"""
Token 计费模块 - 数据模型单元测试

纯函数/模型验证，无需 DB/Redis。
"""
import re
import asyncio
from pydantic import ValidationError

from app.models.token_billing import (
    yuan_to_mq,
    mq_to_yuan,
    generate_order_id,
    generate_txn_id,
    TokenAccountResponse,
    TransactionResponse,
    PackageInfo,
    TokenBillingSettings,
    RechargeOrderCreate,
    BillingConfigUpdateRequest,
)
from app.services.wxpay_service import WxPayService


# ==================== yuan_to_mq / mq_to_yuan ====================

def test_yuan_to_mq_basic():
    assert yuan_to_mq(1.0) == 1000
    assert yuan_to_mq(0.001) == 1
    assert yuan_to_mq(100.0) == 100000
    assert yuan_to_mq(0.0) == 0


def test_yuan_to_mq_edge_cases():
    # 浮点伪影: 19.99 * 1000 = 19989.999... → round → 19990
    assert yuan_to_mq(19.99) == 19990
    # 半偶舍入: 0.0005 → 0 (banker's rounding)
    assert yuan_to_mq(0.0005) == 0
    # 0.0015 → 2 (banker's rounding)
    assert yuan_to_mq(0.0015) == 2
    # 大数
    assert yuan_to_mq(5000.0) == 5000000
    # 负数
    assert yuan_to_mq(-1.0) == -1000


def test_mq_to_yuan_basic():
    assert mq_to_yuan(1000) == 1.0
    assert mq_to_yuan(1) == 0.001
    assert mq_to_yuan(0) == 0.0
    assert mq_to_yuan(100000) == 100.0


def test_round_trip():
    """yuan_to_mq(mq_to_yuan(x)) == x for integer mq"""
    for mq in [0, 1, 100, 1000, 19990, 100000, 5000000]:
        assert yuan_to_mq(mq_to_yuan(mq)) == mq


# ==================== generate_order_id ====================

def test_generate_order_id_format():
    oid = generate_order_id()
    assert oid.startswith("RC")
    assert re.match(r"^RC\d{8}\d{6}$", oid), f"格式不匹配: {oid}"


def test_generate_order_id_uniqueness():
    ids = {generate_order_id() for _ in range(100)}
    assert len(ids) == 100, "100次生成应有100个唯一ID"


# ==================== generate_txn_id ====================

def test_generate_txn_id_format():
    tid = generate_txn_id("PRE")
    assert tid.startswith("PRE_")
    assert re.match(r"^PRE_\d{14}_\d{6}$", tid), f"格式不匹配: {tid}"


def test_generate_txn_id_default_prefix():
    tid = generate_txn_id()
    assert tid.startswith("TXN_")


def test_generate_txn_id_custom_prefixes():
    for prefix in ["CON", "REL", "RCH", "GFT"]:
        tid = generate_txn_id(prefix)
        assert tid.startswith(f"{prefix}_")


# ==================== TokenAccountResponse ====================

def test_token_account_response_from_account_full():
    doc = {
        "balance_mq": 110000,
        "frozen_mq": 12,
        "total_recharged_mq": 200000,
        "total_consumed_mq": 90000,
        "total_gifted_mq": 10000,
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-08-26T12:00:00",
    }
    resp = TokenAccountResponse.from_account(doc)
    assert resp.balance == 110.0
    assert resp.frozen == 0.012
    assert resp.total_recharged == 200.0
    assert resp.total_consumed == 90.0
    assert resp.total_gifted == 10.0
    assert resp.created_at == "2026-01-01T00:00:00"


def test_token_account_response_from_account_missing_keys():
    """空字典应全部默认为0/空字符串"""
    resp = TokenAccountResponse.from_account({})
    assert resp.balance == 0.0
    assert resp.frozen == 0.0
    assert resp.total_recharged == 0.0
    assert resp.total_consumed == 0.0
    assert resp.total_gifted == 0.0
    assert resp.created_at == ""
    assert resp.updated_at == ""


# ==================== TransactionResponse ====================

def test_transaction_response_from_record_full():
    record = {
        "txn_id": "CON_20260826120000_123456",
        "type": "consume",
        "direction": "out",
        "amount_mq": 12,
        "balance_before_mq": 110000,
        "balance_after_mq": 109988,
        "metadata": {"model": "deepseek-v3", "prompt_tokens": 100},
        "status": "success",
        "order_id": None,
        "related_txn_id": "PRE_20260826120000_654321",
        "created_at": "2026-08-26T12:00:00",
    }
    resp = TransactionResponse.from_record(record)
    assert resp.txn_id == "CON_20260826120000_123456"
    assert resp.amount == 0.012
    assert resp.balance_before == 110.0
    assert resp.balance_after == 109.988
    assert resp.metadata["model"] == "deepseek-v3"
    assert resp.related_txn_id == "PRE_20260826120000_654321"


def test_transaction_response_from_record_missing_keys():
    resp = TransactionResponse.from_record({})
    assert resp.txn_id == ""
    assert resp.type == ""
    assert resp.amount == 0.0
    assert resp.status == "success"  # default
    assert resp.metadata == {}  # default
    assert resp.order_id is None
    assert resp.related_txn_id is None


# ==================== PackageInfo ====================

def test_package_info_from_doc():
    doc = {
        "package_id": "pkg_100",
        "name": "100元套餐",
        "amount_cny": 100.0,
        "sort_order": 3,
        "enabled": True,
        "tags": ["hot"],
    }
    pkg = PackageInfo.from_doc(doc)
    assert pkg.package_id == "pkg_100"
    assert pkg.amount_cny == 100.0
    assert pkg.tags == ["hot"]


def test_package_info_from_doc_missing_fields():
    pkg = PackageInfo.from_doc({})
    assert pkg.package_id == ""
    assert pkg.name == ""
    assert pkg.amount_cny == 0
    assert pkg.enabled is True  # default
    assert pkg.tags == []  # default


# ==================== TokenBillingSettings ====================

def test_token_billing_settings_defaults():
    settings = TokenBillingSettings.from_system_settings({})
    assert settings.token_exchange_rate == 1.1
    assert settings.token_consumption_ratio == 1.2
    assert settings.token_input_price_per_1m == 1.0
    assert settings.token_output_price_per_1m == 2.0
    assert settings.token_preoccupy_ratio == 1.2
    assert settings.token_balance_warn_threshold == 5.0
    assert settings.token_order_expire_minutes == 30


def test_token_billing_settings_custom():
    settings = TokenBillingSettings.from_system_settings({
        "token_exchange_rate": 1.5,
        "token_consumption_ratio": 2.0,
    })
    assert settings.token_exchange_rate == 1.5
    assert settings.token_consumption_ratio == 2.0
    # 其他保持默认
    assert settings.token_input_price_per_1m == 1.0


# ==================== RechargeOrderCreate 校验 ====================

def test_recharge_order_create_valid_package():
    obj = RechargeOrderCreate(package_id="pkg_100", idempotency_key="test_key")
    assert obj.package_id == "pkg_100"
    assert obj.custom_amount is None


def test_recharge_order_create_valid_custom_amount():
    obj = RechargeOrderCreate(custom_amount=50000, idempotency_key="k")
    assert obj.custom_amount == 50000


def test_recharge_order_create_below_min():
    try:
        RechargeOrderCreate(custom_amount=999, idempotency_key="k")
        assert False, "应该抛出ValidationError"
    except ValidationError:
        pass


def test_recharge_order_create_above_max():
    try:
        RechargeOrderCreate(custom_amount=5000001, idempotency_key="k")
        assert False, "应该抛出ValidationError"
    except ValidationError:
        pass


def test_recharge_order_create_idempotency_key_empty():
    try:
        RechargeOrderCreate(package_id="pkg_100", idempotency_key="")
        assert False, "空idempotency_key应被拒绝"
    except ValidationError:
        pass


def test_recharge_order_create_idempotency_key_too_long():
    try:
        RechargeOrderCreate(package_id="pkg_100", idempotency_key="x" * 129)
        assert False, "超长idempotency_key应被拒绝"
    except ValidationError:
        pass


# ==================== BillingConfigUpdateRequest 校验 ====================

def test_billing_config_update_all_none():
    """全None是合法的（路由层会检查空更新）"""
    obj = BillingConfigUpdateRequest()
    assert obj.model_dump(exclude_none=True) == {}


def test_billing_config_update_valid():
    obj = BillingConfigUpdateRequest(token_exchange_rate=1.5)
    assert obj.token_exchange_rate == 1.5


def test_billing_config_update_rate_below_min():
    try:
        BillingConfigUpdateRequest(token_exchange_rate=0.05)
        assert False, "exchange_rate < 0.1 应被拒绝"
    except ValidationError:
        pass


def test_billing_config_update_rate_above_max():
    try:
        BillingConfigUpdateRequest(token_exchange_rate=10.1)
        assert False, "exchange_rate > 10.0 应被拒绝"
    except ValidationError:
        pass


def test_billing_config_update_preoccupy_ratio_bounds():
    try:
        BillingConfigUpdateRequest(token_preoccupy_ratio=0.5)
        assert False, "preoccupy_ratio < 1.0 应被拒绝"
    except ValidationError:
        pass
    try:
        BillingConfigUpdateRequest(token_preoccupy_ratio=5.1)
        assert False, "preoccupy_ratio > 5.0 应被拒绝"
    except ValidationError:
        pass


def test_billing_config_update_expire_minutes_bounds():
    try:
        BillingConfigUpdateRequest(token_order_expire_minutes=4)
        assert False, "expire_minutes < 5 应被拒绝"
    except ValidationError:
        pass
    try:
        BillingConfigUpdateRequest(token_order_expire_minutes=1441)
        assert False, "expire_minutes > 1440 应被拒绝"
    except ValidationError:
        pass


# ==================== detect_pay_type ====================

def test_detect_pay_type_wechat():
    ua = "Mozilla/5.0 (Linux; Android 10) MicroMessenger/8.0.0"
    assert WxPayService.detect_pay_type(ua) == "JSAPI"


def test_detect_pay_type_wechat_case_insensitive():
    ua = "micromessenger/7.0"
    assert WxPayService.detect_pay_type(ua) == "JSAPI"


def test_detect_pay_type_android():
    ua = "Mozilla/5.0 (Linux; Android 12; Pixel 6)"
    assert WxPayService.detect_pay_type(ua) == "MWEB"


def test_detect_pay_type_iphone():
    ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)"
    assert WxPayService.detect_pay_type(ua) == "MWEB"


def test_detect_pay_type_ipad():
    ua = "Mozilla/5.0 (iPad; CPU OS 16_0 like Mac OS X)"
    assert WxPayService.detect_pay_type(ua) == "MWEB"


def test_detect_pay_type_desktop():
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"
    assert WxPayService.detect_pay_type(ua) == "NATIVE"


def test_detect_pay_type_empty():
    assert WxPayService.detect_pay_type("") == "NATIVE"


def test_detect_pay_type_none():
    assert WxPayService.detect_pay_type(None) == "NATIVE"


def test_detect_pay_type_wechat_overrides_mobile():
    """微信UA中包含Android/iPhone时应优先返回JSAPI"""
    ua = "Mozilla/5.0 (iPhone) MicroMessenger/8.0"
    assert WxPayService.detect_pay_type(ua) == "JSAPI"
