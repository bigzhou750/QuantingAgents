"""
微信支付服务 — 单元测试。

测试 WxPayService 的核心方法：
- detect_pay_type：根据 User-Agent 判断支付场景（JSAPI/MWEB/NATIVE）
- verify_callback_signature：校验微信回调请求头的完整性
- parse_callback：解析回调 body 中的支付结果
- 配置缓存 TTL：验证 _get_config 在有效期内不重复拉取配置

本文件所有测试均为纯函数/内存操作，无需 DB/Redis 连接。
"""

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ===========================================================================
# detect_pay_type：静态纯函数，根据 UA 字符串判断支付类型（微信内/移动端/桌面端）
# ===========================================================================

def test_detect_wechat_ua():
    """WeChat UA → JSAPI."""
    from app.services.wxpay_service import WxPayService
    ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) MicroMessenger/8.0.38"
    assert WxPayService.detect_pay_type(ua) == "JSAPI"


def test_detect_android_ua():
    """Android browser UA → MWEB."""
    from app.services.wxpay_service import WxPayService
    ua = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 Chrome/120.0 Mobile Safari/537.36"
    assert WxPayService.detect_pay_type(ua) == "MWEB"


def test_detect_iphone_ua():
    """iPhone Safari UA (non-WeChat) → MWEB."""
    from app.services.wxpay_service import WxPayService
    ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1"
    assert WxPayService.detect_pay_type(ua) == "MWEB"


def test_detect_desktop_ua():
    """Desktop Chrome UA → NATIVE."""
    from app.services.wxpay_service import WxPayService
    ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
    assert WxPayService.detect_pay_type(ua) == "NATIVE"


def test_detect_empty_ua():
    """Empty/None UA → NATIVE."""
    from app.services.wxpay_service import WxPayService
    assert WxPayService.detect_pay_type("") == "NATIVE"
    assert WxPayService.detect_pay_type(None) == "NATIVE"


# ===========================================================================
# verify_callback_signature：验证微信回调必需的 4 个 wechatpay-* 请求头是否齐全
# ===========================================================================

def _full_headers():
    """Return a dict with all required wechatpay-* headers."""
    return {
        "wechatpay-timestamp": "1700000000",
        "wechatpay-nonce": "abc123def456",
        "wechatpay-signature": "base64sig==",
        "wechatpay-serial": "cert_serial_001",
    }


def test_verify_all_headers_present():
    """All required headers present → True (v1 simplified)."""
    from app.services.wxpay_service import WxPayService
    svc = WxPayService()
    assert svc.verify_callback_signature(_full_headers(), b'{}') is True


def test_verify_missing_timestamp():
    """Missing wechatpay-timestamp → False."""
    from app.services.wxpay_service import WxPayService
    svc = WxPayService()
    headers = _full_headers()
    del headers["wechatpay-timestamp"]
    assert svc.verify_callback_signature(headers, b'{}') is False


def test_verify_missing_nonce():
    """Missing wechatpay-nonce → False."""
    from app.services.wxpay_service import WxPayService
    svc = WxPayService()
    headers = _full_headers()
    del headers["wechatpay-nonce"]
    assert svc.verify_callback_signature(headers, b'{}') is False


def test_verify_missing_signature():
    """Missing wechatpay-signature → False."""
    from app.services.wxpay_service import WxPayService
    svc = WxPayService()
    headers = _full_headers()
    del headers["wechatpay-signature"]
    assert svc.verify_callback_signature(headers, b'{}') is False


def test_verify_missing_serial():
    """Missing wechatpay-serial → False."""
    from app.services.wxpay_service import WxPayService
    svc = WxPayService()
    headers = _full_headers()
    del headers["wechatpay-serial"]
    assert svc.verify_callback_signature(headers, b'{}') is False


# ===========================================================================
# parse_callback：解析微信回调 body，提取 resource.plaintext 中的支付结果
# ===========================================================================

def test_parse_valid_plaintext():
    """resource.plaintext dict → extracted payment data."""
    from app.services.wxpay_service import WxPayService
    svc = WxPayService()

    body = json.dumps({
        "event_type": "TRANSACTION.SUCCESS",
        "resource": {
            "plaintext": {
                "out_trade_no": "RC20250101000001",
                "trade_state": "SUCCESS",
                "transaction_id": "WX_TXN_001",
                "amount": {"total": 10000},
            }
        },
    }).encode()

    result = svc.parse_callback(body)
    assert result["event_type"] == "TRANSACTION.SUCCESS"
    assert result["payment"]["out_trade_no"] == "RC20250101000001"
    assert result["payment"]["trade_state"] == "SUCCESS"
    assert result["payment"]["transaction_id"] == "WX_TXN_001"
    assert "raw" in result


def test_parse_invalid_json_raises():
    """Garbage bytes → ValueError."""
    from app.services.wxpay_service import WxPayService
    svc = WxPayService()

    with pytest.raises(ValueError, match="无效的回调数据"):
        svc.parse_callback(b"this is not json at all {{{")


# ===========================================================================
# 配置缓存 TTL：验证 _get_config 在有效期内使用缓存，过期后重新拉取
# ===========================================================================

def test_config_cache_ttl():
    """Within TTL the config is NOT refetched from config_service."""
    from app.services.wxpay_service import WxPayService
    svc = WxPayService()

    # Reset cache state
    svc._config_cache = {}
    svc._config_cache_ts = 0

    fake_config = MagicMock()
    fake_config.system_settings = {
        "wxpay_mch_id": "mch_test",
        "wxpay_app_id": "app_test",
        "wxpay_api_key": "key_test",
        "wxpay_notify_url": "https://example.com/notify",
        "wxpay_cert_serial": "serial_test",
        "wxpay_private_key": "",
    }

    mock_cs = AsyncMock()
    mock_cs.get_system_config = AsyncMock(return_value=fake_config)

    async def _run():
        with patch("app.services.config_service.config_service", mock_cs):
            # First call — should fetch
            cfg1 = await svc._get_config()
            assert mock_cs.get_system_config.call_count == 1
            assert cfg1["mch_id"] == "mch_test"

            # Second call within TTL — should use cache
            cfg2 = await svc._get_config()
            assert mock_cs.get_system_config.call_count == 1  # still 1
            assert cfg2["mch_id"] == "mch_test"

            # Force cache expiry
            svc._config_cache_ts = 0

            # Third call after expiry — should refetch
            cfg3 = await svc._get_config()
            assert mock_cs.get_system_config.call_count == 2
            assert cfg3["mch_id"] == "mch_test"

    import asyncio
    asyncio.run(_run())
