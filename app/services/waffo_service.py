"""
Waffo Pancake 支付服务（Python 实现）

Waffo 官方仅提供 TypeScript SDK，此模块用 Python 直接调用 REST API。
参考: https://docs.waffo.ai/integrate/sdks

功能:
- Checkout Session 创建（一次性支付）
- Webhook 签名验证
- 订单状态查询（GraphQL）

环境变量:
- WAFFO_MERCHANT_ID: 商户 ID
- WAFFO_PRIVATE_KEY: RSA 私钥（PEM 格式，支持 \\n 转义或 base64）
- WAFFO_STORE_ID: 店铺 ID
- WAFFO_ENVIRONMENT: test | prod（默认 test）
"""

import os
import time
import json
import base64
import hashlib
import logging
from typing import Optional, Dict, Any

import httpx

logger = logging.getLogger(__name__)

# Waffo API 基础 URL（test/prod 通过 API Key 区分，共用同一域名）
WAFFO_API_BASE = {
    "test": "https://api.waffo.ai",
    "prod": "https://api.waffo.ai",
}


class WaffoService:
    """Waffo Pancake 支付服务"""

    def __init__(self):
        self._private_key_pem: Optional[str] = None
        self._merchant_id: Optional[str] = None
        self._store_id: Optional[str] = None
        self._environment: str = "test"
        self._initialized = False

    def _ensure_initialized(self):
        """延迟初始化，从环境变量读取配置"""
        if self._initialized:
            return

        self._merchant_id = os.environ.get("WAFFO_MERCHANT_ID", "")
        self._store_id = os.environ.get("WAFFO_STORE_ID", "")
        self._environment = os.environ.get("WAFFO_ENVIRONMENT", "test")

        # 读取私钥（支持多种格式）
        private_key_raw = os.environ.get("WAFFO_PRIVATE_KEY", "")
        if private_key_raw:
            self._private_key_pem = self._normalize_private_key(private_key_raw)

        self._initialized = True

    @staticmethod
    def _normalize_private_key(raw: str) -> str:
        """
        标准化私钥格式

        支持:
        - PEM 格式（带 -----BEGIN PRIVATE KEY----- 头尾）
        - 转义换行符的 PEM（\\n）
        - Base64 编码的完整 PEM
        """
        raw = raw.strip()

        # 如果已经是标准 PEM 格式
        if raw.startswith("-----BEGIN"):
            return raw.replace("\\n", "\n")

        # 尝试 base64 解码
        try:
            decoded = base64.b64decode(raw).decode("utf-8")
            if decoded.startswith("-----BEGIN"):
                return decoded
        except Exception:
            pass

        # 假设是去掉头尾的 base64 内容，包装成 PEM
        cleaned = raw.replace("\\n", "").replace("\n", "").replace(" ", "")
        pem_lines = ["-----BEGIN PRIVATE KEY-----"]
        for i in range(0, len(cleaned), 64):
            pem_lines.append(cleaned[i:i+64])
        pem_lines.append("-----END PRIVATE KEY-----")
        return "\n".join(pem_lines)

    @property
    def is_configured(self) -> bool:
        """检查是否已配置必要参数"""
        self._ensure_initialized()
        return bool(self._merchant_id and self._private_key_pem and self._store_id)

    @property
    def base_url(self) -> str:
        self._ensure_initialized()
        return WAFFO_API_BASE.get(self._environment, WAFFO_API_BASE["test"])

    def _sign_request(self, method: str, path: str, body: str) -> str:
        """
        生成 Waffo API 请求签名

        签名算法: RSA-SHA256
        签名串格式: "{method}\n{path}\n{timestamp}\n{nonce}\n{body_hash}\n"
        """
        self._ensure_initialized()

        timestamp = str(int(time.time()))
        nonce = hashlib.sha256(f"{timestamp}{path}".encode()).hexdigest()[:16]

        # Body hash (SHA-256)
        body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest() if body else ""

        # 构造签名串
        message = f"{method.upper()}\n{path}\n{timestamp}\n{nonce}\n{body_hash}\n"

        # RSA-SHA256 签名
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding

            private_key_obj = serialization.load_pem_private_key(
                self._private_key_pem.encode("utf-8"),
                password=None,
            )
            signature = private_key_obj.sign(
                message.encode("utf-8"),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
            sign_b64 = base64.b64encode(signature).decode("utf-8")
        except ImportError:
            logger.error("cryptography 库未安装，无法生成 Waffo 签名")
            raise RuntimeError("cryptography library required for Waffo signing")
        except Exception as e:
            logger.error("Waffo 签名生成失败: %s", e)
            raise

        return sign_b64

    def _build_auth_header(self, method: str, path: str, body: str) -> Dict[str, str]:
        """构建 Authorization 头"""
        self._ensure_initialized()
        signature = self._sign_request(method, path, body)
        timestamp = str(int(time.time()))

        return {
            "Authorization": f'Bearer merchant_id="{self._merchant_id}",signature="{signature}",timestamp="{timestamp}"',
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def create_checkout_session(
        self,
        product_id: str,
        currency: str = "USD",
        buyer_identity: Optional[str] = None,
        buyer_email: Optional[str] = None,
        price_snapshot: Optional[Dict[str, Any]] = None,
        success_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        expires_in_seconds: int = 3600,
    ) -> Dict[str, Any]:
        """
        创建 Checkout Session

        Args:
            product_id: Waffo 产品 ID
            currency: 货币代码 (ISO 4217)
            buyer_identity: 买家标识（用户ID，用于绑定订单）
            buyer_email: 买家邮箱（预填表单）
            price_snapshot: 动态定价覆盖
            success_url: 支付成功跳转 URL
            metadata: 自定义元数据（会传递到 webhook）
            expires_in_seconds: 会话过期时间（秒）

        Returns:
            {"checkout_url": "...", "session_id": "...", "expires_at": "..."}
        """
        self._ensure_initialized()

        if not self.is_configured:
            raise WaffoConfigError("Waffo 支付未配置: 缺少 WAFFO_MERCHANT_ID / WAFFO_PRIVATE_KEY / WAFFO_STORE_ID")

        # 构建请求体
        payload: Dict[str, Any] = {
            "storeId": self._store_id,
            "productId": product_id,
            "productType": "onetime",
            "currency": currency,
            "expiresInSeconds": expires_in_seconds,
        }

        if buyer_identity:
            payload["buyerIdentity"] = buyer_identity
        if buyer_email:
            payload["buyerEmail"] = buyer_email
        if price_snapshot:
            payload["priceSnapshot"] = price_snapshot
        if success_url:
            payload["successUrl"] = success_url
        if metadata:
            payload["metadata"] = metadata

        body = json.dumps(payload)
        path = "/v1/checkout/sessions"
        headers = self._build_auth_header("POST", path, body)

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base_url}{path}",
                content=body,
                headers=headers,
            )

        if resp.status_code not in (200, 201):
            logger.error(
                "Waffo checkout 创建失败: status=%d, body=%s",
                resp.status_code, resp.text,
            )
            raise WaffoApiError(resp.status_code, resp.text)

        data = resp.json()
        return {
            "checkout_url": data.get("checkoutUrl", ""),
            "session_id": data.get("sessionId", ""),
            "expires_at": data.get("expiresAt", ""),
        }

    async def create_dynamic_checkout(
        self,
        amount: float,
        currency: str = "CNY",
        product_name: str = "算力充值",
        buyer_identity: Optional[str] = None,
        buyer_email: Optional[str] = None,
        success_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        创建动态金额的 Checkout Session（无需预创建产品）

        使用 priceSnapshot 覆盖价格，适用于充值场景。
        需要一个基础的 onetime 产品作为载体。

        Args:
            amount: 金额（显示金额，如 50.00）
            currency: 货币代码
            product_name: 产品描述
            buyer_identity: 买家标识
            buyer_email: 买家邮箱
            success_url: 成功跳转
            metadata: 元数据
        """
        self._ensure_initialized()

        # 获取或创建基础充值产品
        base_product_id = os.environ.get("WAFFO_RECHARGE_PRODUCT_ID", "")
        if not base_product_id:
            raise WaffoConfigError(
                "需要设置 WAFFO_RECHARGE_PRODUCT_ID 环境变量。"
                "请在 Waffo Dashboard 创建一个一次性产品作为充值载体，"
                "然后将产品 ID 填入 .env"
            )

        price_snapshot = {
            "amount": amount,
            "taxIncluded": True,
            "taxCategory": "digital_goods",
        }

        return await self.create_checkout_session(
            product_id=base_product_id,
            currency=currency,
            buyer_identity=buyer_identity,
            buyer_email=buyer_email,
            price_snapshot=price_snapshot,
            success_url=success_url,
            metadata=metadata or {},
        )

    @staticmethod
    def verify_webhook_signature(body: str, signature: str) -> Dict[str, Any]:
        """
        验证 Waffo Webhook 签名

        Args:
            body: 原始请求体（字符串，不能是解析后的 JSON）
            signature: x-waffo-signature header 值

        Returns:
            解析后的事件数据

        Raises:
            WaffoWebhookError: 签名验证失败
        """
        # Waffo webhook 使用 RSA-SHA256 签名
        # SDK 内嵌了测试和生产环境的公钥
        # Python 实现需要从 Waffo 获取公钥或使用已知公钥

        # TODO: 从 Waffo 获取公钥并验证签名
        # 当前简化版：解析 JSON 并返回（生产环境需完善签名验证）

        try:
            event = json.loads(body)
        except json.JSONDecodeError as e:
            raise WaffoWebhookError(f"无效的 webhook body: {e}")

        # 基本结构验证
        if "eventType" not in event:
            raise WaffoWebhookError("webhook 缺少 eventType 字段")

        logger.info(
            "Waffo webhook 收到: type=%s, id=%s",
            event.get("eventType"), event.get("id"),
        )

        # TODO: 实现完整的 RSA-SHA256 签名验证
        # 需要从 Waffo 获取公钥或使用内置公钥
        # 当前信任所有格式正确的 webhook（开发阶段）

        return event

    async def query_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        通过 GraphQL 查询订单状态

        Args:
            order_id: Waffo 订单 ID

        Returns:
            订单信息字典，不存在返回 None
        """
        self._ensure_initialized()

        query = """
        query ($id: String!) {
          order(id: $id) {
            id
            status
            amount
            currency
            buyerEmail
            createdAt
          }
        }
        """

        payload = json.dumps({
            "query": query,
            "variables": {"id": order_id},
        })

        path = "/v1/graphql"
        headers = self._build_auth_header("POST", path, payload)

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base_url}{path}",
                content=payload,
                headers=headers,
            )

        if resp.status_code != 200:
            logger.error("Waffo GraphQL 查询失败: %d %s", resp.status_code, resp.text)
            return None

        data = resp.json()
        return data.get("data", {}).get("order")


# ==================== 异常类 ====================

class WaffoConfigError(Exception):
    """Waffo 配置错误"""
    pass


class WaffoApiError(Exception):
    """Waffo API 调用错误"""
    def __init__(self, status_code: int, response_body: str):
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(f"Waffo API 错误: HTTP {status_code}")


class WaffoWebhookError(Exception):
    """Waffo Webhook 验证错误"""
    pass


# ==================== 模块级单例 ====================
waffo_service = WaffoService()
