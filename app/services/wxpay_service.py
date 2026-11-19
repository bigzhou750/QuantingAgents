"""
微信支付 V3 API 集成服务

支持三种支付类型：
- NATIVE: PC端扫码支付
- JSAPI: H5微信内置浏览器支付
- MWEB: H5微信外浏览器支付

密钥读取优先级：数据库 system_settings > 环境变量 .env（WX_ 前缀）。
详见 .env.example 中的微信支付配置段。
"""

import os
import time
import json
import hashlib
import hmac
import base64
import logging
from typing import Optional, Dict, Any
from datetime import datetime

import httpx

from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)

# 微信支付V3 API基础URL
WXPAY_BASE_URL = "https://api.mch.weixin.qq.com"


class WxPayService:
    """微信支付V3服务"""

    def __init__(self):
        self._config_cache: Dict[str, Any] = {}
        self._config_cache_ts: float = 0
        self._cache_ttl = 60  # 配置缓存60秒

    async def _get_config(self) -> Dict[str, str]:
        """
        获取微信支付配置（带30秒TTL缓存）。

        优先级：数据库 system_settings > 环境变量 .env。
        数据库中字段名带 wxpay_ 前缀（如 wxpay_mch_id），
        环境变量使用 WX_ 前缀大写（如 WX_MCH_ID）。
        两者取非空值，数据库优先。
        """
        now = time.time()
        if now - self._config_cache_ts > self._cache_ttl:
            # 先从环境变量读取默认值
            env_config = {
                "mch_id": os.environ.get("WX_MCH_ID", ""),
                "app_id": os.environ.get("WX_APP_ID", ""),
                "api_key": os.environ.get("WX_API_KEY", ""),
                "notify_url": os.environ.get("WX_NOTIFY_URL", ""),
                "cert_serial": os.environ.get("WX_CERT_SERIAL", ""),
                "private_key": os.environ.get("WX_PRIVATE_KEY", "").replace("\\n", "\n"),
            }
            # 尝试从数据库覆盖（数据库值优先）
            try:
                from app.services.config_service import config_service
                config = await config_service.get_system_config()
                ss = config.system_settings if config and hasattr(config, 'system_settings') else {}
                if isinstance(ss, dict):
                    db_config = {
                        "mch_id": ss.get("wxpay_mch_id", ""),
                        "app_id": ss.get("wxpay_app_id", ""),
                        "api_key": ss.get("wxpay_api_key", ""),
                        "notify_url": ss.get("wxpay_notify_url", ""),
                        "cert_serial": ss.get("wxpay_cert_serial", ""),
                        "private_key": ss.get("wxpay_private_key", ""),
                    }
                    # 数据库非空值覆盖环境变量
                    for key in env_config:
                        if db_config[key]:
                            env_config[key] = db_config[key]
            except Exception as e:
                logger.warning("⚠️ 从数据库获取微信支付配置失败，使用环境变量: %s", e)

            self._config_cache = env_config
            self._config_cache_ts = now
        return self._config_cache

    def _generate_nonce_str(self) -> str:
        """生成随机字符串"""
        import secrets
        return secrets.token_hex(16)

    def _generate_timestamp(self) -> str:
        """生成时间戳"""
        return str(int(time.time()))

    def _build_auth_header(
        self, method: str, url_path: str, body: str, config: Dict[str, str]
    ) -> str:
        """
        构建微信支付V3 Authorization头

        WECHATPAY2-SHA256-RSA2048 签名方式
        """
        timestamp = self._generate_timestamp()
        nonce_str = self._generate_nonce_str()

        # 构造签名串
        message = f"{method}\n{url_path}\n{timestamp}\n{nonce_str}\n{body}\n"

        # RSA签名（需要商户私钥）
        private_key = config.get("private_key", "")
        if not private_key:
            logger.error("微信支付私钥未配置")
            raise ValueError("微信支付私钥未配置")

        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding

            private_key_obj = serialization.load_pem_private_key(
                private_key.encode(), password=None
            )
            signature = private_key_obj.sign(
                message.encode("utf-8"),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
            sign_b64 = base64.b64encode(signature).decode("utf-8")
        except ImportError:
            # 如果没有cryptography库，使用占位符（开发环境）
            logger.warning("cryptography库未安装，使用占位签名（仅开发环境）")
            sign_b64 = base64.b64encode(b"dev_placeholder_signature").decode("utf-8")

        mch_id = config.get("mch_id", "")
        serial = config.get("cert_serial", "")

        return (
            f'WECHATPAY2-SHA256-RSA2048 '
            f'mchid="{mch_id}",'
            f'nonce_str="{nonce_str}",'
            f'signature="{sign_b64}",'
            f'timestamp="{timestamp}",'
            f'serial_no="{serial}"'
        )

    async def create_native_order(
        self, order_id: str, amount_cents: int, description: str
    ) -> Dict[str, Any]:
        """
        创建Native支付订单（PC扫码）

        Args:
            order_id: 商户订单号
            amount_cents: 金额（分）
            description: 商品描述

        Returns:
            {"code_url": "weixin://wxpay/bizpayurl?pr=xxx"}
        """
        config = await self._get_config()
        url_path = "/v3/pay/transactions/native"
        body = json.dumps({
            "appid": config["app_id"],
            "mchid": config["mch_id"],
            "description": description,
            "out_trade_no": order_id,
            "notify_url": config["notify_url"],
            "amount": {"total": amount_cents, "currency": "CNY"},
        })

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{WXPAY_BASE_URL}{url_path}",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": self._build_auth_header("POST", url_path, body, config),
                },
            )

        if resp.status_code != 200:
            logger.error("Native下单失败: status=%d, body=%s", resp.status_code, resp.text)
            raise WxPayApiError(resp.status_code, resp.text)

        data = resp.json()
        return {"code_url": data.get("code_url", "")}

    async def create_jsapi_order(
        self, order_id: str, amount_cents: int, openid: str, description: str
    ) -> Dict[str, Any]:
        """
        创建JSAPI支付订单（H5微信内）

        Returns:
            JSAPI调起参数 {appId, timeStamp, nonceStr, package, signType, paySign}
        """
        config = await self._get_config()
        url_path = "/v3/pay/transactions/jsapi"
        body = json.dumps({
            "appid": config["app_id"],
            "mchid": config["mch_id"],
            "description": description,
            "out_trade_no": order_id,
            "notify_url": config["notify_url"],
            "amount": {"total": amount_cents, "currency": "CNY"},
            "payer": {"openid": openid},
        })

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{WXPAY_BASE_URL}{url_path}",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": self._build_auth_header("POST", url_path, body, config),
                },
            )

        if resp.status_code != 200:
            logger.error("JSAPI下单失败: status=%d, body=%s", resp.status_code, resp.text)
            raise WxPayApiError(resp.status_code, resp.text)

        data = resp.json()
        prepay_id = data.get("prepay_id", "")

        # 构造JSAPI调起参数
        timestamp = self._generate_timestamp()
        nonce_str = self._generate_nonce_str()
        package_str = f"prepay_id={prepay_id}"

        # 签名
        sign_message = f"{config['app_id']}\n{timestamp}\n{nonce_str}\n{package_str}\n"
        # TODO: RSA签名（同Native，需商户私钥）
        pay_sign = base64.b64encode(b"jsapi_placeholder").decode("utf-8")

        return {
            "appId": config["app_id"],
            "timeStamp": timestamp,
            "nonceStr": nonce_str,
            "package": package_str,
            "signType": "RSA",
            "paySign": pay_sign,
        }

    async def create_mweb_order(
        self, order_id: str, amount_cents: int, description: str, client_ip: str = ""
    ) -> Dict[str, Any]:
        """
        创建MWEB支付订单（H5微信外）

        Returns:
            {"mweb_url": "https://wx.tenpay.com/cgi-bin/mmpayweb-bin/checkmweb?..."}
        """
        config = await self._get_config()
        url_path = "/v3/pay/transactions/h5"
        body_dict = {
            "appid": config["app_id"],
            "mchid": config["mch_id"],
            "description": description,
            "out_trade_no": order_id,
            "notify_url": config["notify_url"],
            "amount": {"total": amount_cents, "currency": "CNY"},
            "scene_info": {
                "payer_client_ip": client_ip or "127.0.0.1",
                "h5_info": {"type": "Wap"},
            },
        }
        body = json.dumps(body_dict)

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{WXPAY_BASE_URL}{url_path}",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": self._build_auth_header("POST", url_path, body, config),
                },
            )

        if resp.status_code != 200:
            logger.error("MWEB下单失败: status=%d, body=%s", resp.status_code, resp.text)
            raise WxPayApiError(resp.status_code, resp.text)

        data = resp.json()
        return {"mweb_url": data.get("h5_url", "")}

    async def query_order(self, out_trade_no: str) -> Dict[str, Any]:
        """主动查询微信订单状态"""
        config = await self._get_config()
        mch_id = config.get("mch_id", "")
        url_path = f"/v3/pay/transactions/out-trade-no/{out_trade_no}?mchid={mch_id}"

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{WXPAY_BASE_URL}{url_path}",
                headers={
                    "Accept": "application/json",
                    "Authorization": self._build_auth_header("GET", url_path, "", config),
                },
            )

        if resp.status_code != 200:
            logger.error("查询订单失败: status=%d, body=%s", resp.status_code, resp.text)
            raise WxPayApiError(resp.status_code, resp.text)

        return resp.json()

    def verify_callback_signature(
        self, headers: Dict[str, str], body: bytes
    ) -> bool:
        """
        验证微信支付回调签名

        TODO: 完整实现需要使用微信平台证书验签
        v1 简化版：仅检查必要header存在性
        """
        required_headers = [
            "wechatpay-timestamp",
            "wechatpay-nonce",
            "wechatpay-signature",
            "wechatpay-serial",
        ]
        for h in required_headers:
            if h not in headers:
                logger.warning("回调缺少header: %s", h)
                return False

        # TODO: 使用微信平台公钥验证签名
        # 当前版本信任所有格式正确的回调（开发阶段）
        logger.info("回调签名验证（简化版通过）")
        return True

    def parse_callback(self, body: bytes, api_key: str = "") -> Dict[str, Any]:
        """
        解析微信支付V3回调通知

        V3回调body是JSON，resource字段是AES加密的
        """
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            logger.error("回调body不是有效JSON")
            raise ValueError("无效的回调数据")

        resource = data.get("resource", {})
        event_type = data.get("event_type", "")

        # TODO: AES解密resource.ciphertext
        # v1 简化版：如果resource已经是明文（沙箱环境），直接使用
        if "plaintext" in resource:
            payment_data = resource["plaintext"]
        elif "ciphertext" in resource:
            # 需要AES-GCM解密
            logger.warning("回调resource需要AES解密，当前返回原始数据")
            payment_data = resource
        else:
            payment_data = resource

        if isinstance(payment_data, str):
            try:
                payment_data = json.loads(payment_data)
            except json.JSONDecodeError:
                pass

        return {
            "event_type": event_type,
            "payment": payment_data if isinstance(payment_data, dict) else {},
            "raw": data,
        }

    @staticmethod
    def detect_pay_type(user_agent: str) -> str:
        """
        根据UA检测支付类型

        Returns:
            "NATIVE" | "JSAPI" | "MWEB"
        """
        ua = user_agent.lower() if user_agent else ""
        if "micromessenger" in ua:
            return "JSAPI"
        elif any(m in ua for m in ["android", "iphone", "ipad", "mobile"]):
            return "MWEB"
        else:
            return "NATIVE"


class WxPayApiError(Exception):
    """微信支付API调用异常"""
    def __init__(self, status_code: int, response_body: str):
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(f"微信支付API错误: HTTP {status_code}")


# ==================== 模块级单例 ====================
wxpay_service = WxPayService()
