"""
Waffo Pancake 支付服务（Python 实现）

基于 @waffo/pancake-ts SDK v0.21.0 源码逆向，用 Python 直接调用 REST API。
SDK 源码: https://github.com/waffo-com/waffo-pancake-sdk-ts

功能:
- Checkout Session 创建（匿名 / 认证两种模式）
- Webhook 签名验证
- 订单状态查询（GraphQL）

环境变量:
- WAFFO_MERCHANT_ID: 商户 ID (MER_xxx)
- WAFFO_PRIVATE_KEY: RSA 私钥（PEM 格式或纯 base64）
- WAFFO_STORE_ID: 店铺 ID (STO_xxx)
- WAFFO_ENVIRONMENT: test | prod（默认 test）
- WAFFO_RECHARGE_PRODUCT_ID: 充值产品 ID (PROD_xxx)
- WAFFO_CURRENCY: 货币代码（默认 CNY）

API 要点（来自 SDK 源码）:
- Base URL: https://api.waffo.ai（test/prod 共用，通过 API Key 区分）
- 认证: X-Merchant-Id + X-Timestamp + X-Signature headers
- 签名串: "POST\\n{path}\\n{timestamp}\\n{body_hash_base64}"
- body_hash = SHA-256(body).digest("base64")  ← 注意是 base64 不是 hex
- 金额单位: 最小货币单位（如 CNY 的"分"，999 = ¥9.99）
- metadata 值只能是 string
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

# Waffo API 基础 URL — SDK 源码中硬编码为 https://api.waffo.ai
# test/prod 共用同一域名，通过不同的 API Key（私钥）区分环境
WAFFO_API_BASE = "https://api.waffo.ai"


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
        - 纯 base64 内容（无 PEM 头尾）
        """
        raw = raw.strip()

        # 如果已经是标准 PEM 格式
        if raw.startswith("-----BEGIN"):
            return raw.replace("\\n", "\n")

        # 尝试 base64 解码看是否是完整 PEM
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
        return WAFFO_API_BASE

    def _sign_request(self, method: str, path: str, timestamp: str, body: str) -> str:
        """
        生成 Waffo API 请求签名（与 SDK signRequest 函数一致）

        签名算法: RSA-SHA256 (PKCS1v15)
        签名串格式（4行，无 nonce）:
            {METHOD}
            {path}
            {timestamp}
            {body_hash_base64}

        注意: body_hash 使用 SHA-256 后 base64 编码（不是 hex）
        """
        self._ensure_initialized()

        # Body hash: SHA-256 → base64（与 JS SDK createHash("sha256").update(body).digest("base64") 一致）
        body_hash = base64.b64encode(
            hashlib.sha256(body.encode("utf-8")).digest()
        ).decode("utf-8") if body else ""

        # 构造签名串（4行，与 SDK 一致）
        canonical_request = f"{method.upper()}\n{path}\n{timestamp}\n{body_hash}"

        # RSA-SHA256 签名
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding

            private_key_obj = serialization.load_pem_private_key(
                self._private_key_pem.encode("utf-8"),
                password=None,
            )
            signature = private_key_obj.sign(
                canonical_request.encode("utf-8"),
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

    def _build_headers(self, method: str, path: str, body: str) -> Dict[str, str]:
        """
        构建请求头（与 SDK HttpClient.post 一致）

        Headers:
        - Content-Type: application/json
        - X-Merchant-Id: 商户 ID
        - X-Timestamp: Unix 时间戳（秒）
        - X-Signature: RSA-SHA256 签名
        - X-Idempotency-Key: 幂等键（可选）
        """
        self._ensure_initialized()
        timestamp = str(int(time.time()))
        signature = self._sign_request(method, path, timestamp, body)

        headers = {
            "Content-Type": "application/json",
            "X-Merchant-Id": self._merchant_id,
            "X-Timestamp": timestamp,
            "X-Signature": signature,
        }

        # 幂等键: sha256(merchantId:path:bodyStr:timestamp_window)
        # window = 60s（与 SDK idempotencyWindow: 60 一致）
        idempotency_window = 60
        ts_window = int(time.time()) // idempotency_window
        idempotency_input = f"{self._merchant_id}:{path}:{body}:{ts_window}"
        idempotency_key = hashlib.sha256(idempotency_input.encode()).hexdigest()
        headers["X-Idempotency-Key"] = idempotency_key

        return headers

    async def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """发送签名 POST 请求并返回解析后的响应"""
        body = json.dumps(payload)
        headers = self._build_headers("POST", path, body)

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base_url}{path}",
                content=body,
                headers=headers,
            )

        if resp.status_code not in (200, 201):
            logger.error(
                "Waffo API 请求失败: path=%s, status=%d, body=%s",
                path, resp.status_code, resp.text,
            )
            raise WaffoApiError(resp.status_code, resp.text)

        return resp.json()

    async def create_checkout_session(
        self,
        product_id: str,
        currency: str = "USD",
        buyer_identity: Optional[str] = None,
        buyer_email: Optional[str] = None,
        price_snapshot: Optional[Dict[str, Any]] = None,
        success_url: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
        expires_in_seconds: int = 2700,
        order_merchant_external_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        创建 Checkout Session

        根据是否有 buyer_identity 自动选择模式:
        - 有 buyer_identity → 认证模式（推荐），会同时签发 session token
        - 无 buyer_identity → 匿名模式

        Args:
            product_id: Waffo 产品 ID (PROD_xxx)
            currency: 货币代码 (ISO 4217)，如 "CNY", "USD"
            buyer_identity: 买家标识（用户ID），提供则走认证模式
            buyer_email: 买家邮箱（预填结账页面）
            price_snapshot: 动态定价覆盖 {"amount": "9.99", "taxCategory": "digital_goods"}
                            注意 amount 是字符串，单位为元（SDK 文档说最小单位但实际传元）
            success_url: 支付成功跳转 URL
            metadata: 自定义元数据（值必须是字符串，会传递到 webhook）
            expires_in_seconds: 会话过期时间（秒，默认 45 分钟）
            order_merchant_external_id: 业务侧订单号

        Returns:
            {"checkout_url": "...", "session_id": "...", "expires_at": "..."}
        """
        self._ensure_initialized()

        if not self.is_configured:
            raise WaffoConfigError(
                "Waffo 支付未配置: 缺少 WAFFO_MERCHANT_ID / WAFFO_PRIVATE_KEY / WAFFO_STORE_ID"
            )

        # 构建请求体
        payload: Dict[str, Any] = {
            "productId": product_id,
            "currency": currency,
            "expiresInSeconds": expires_in_seconds,
        }

        if buyer_email:
            payload["buyerEmail"] = buyer_email
        if price_snapshot:
            payload["priceSnapshot"] = price_snapshot
        if success_url:
            payload["successUrl"] = success_url
        if metadata:
            # metadata 值必须是字符串
            payload["metadata"] = {k: str(v) for k, v in metadata.items()}
        if order_merchant_external_id:
            payload["orderMerchantExternalId"] = order_merchant_external_id

        if buyer_identity:
            # 认证模式: 先签发 token，再创建 session
            return await self._create_authenticated_checkout(
                buyer_identity=buyer_identity,
                session_payload=payload,
            )
        else:
            # 匿名模式: 直接创建 session
            return await self._create_anonymous_checkout(session_payload=payload)

    async def _create_anonymous_checkout(self, session_payload: Dict[str, Any]) -> Dict[str, Any]:
        """匿名结账 — POST /v1/actions/checkout/create-session"""
        path = "/v1/actions/checkout/create-session"
        data = await self._post(path, session_payload)

        # SDK unwrapAction: 从 envelope 中提取 data 字段
        result = data.get("data", data)

        return {
            "checkout_url": result.get("checkoutUrl", ""),
            "session_id": result.get("sessionId", ""),
            "expires_at": result.get("expiresAt", ""),
        }

    async def _create_authenticated_checkout(
        self,
        buyer_identity: str,
        session_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        认证结账 — 并行调用两个接口:
        1. POST /v1/actions/auth/issue-session-token (签发 JWT)
        2. POST /v1/actions/checkout/create-session (创建 session)
        然后将 token 追加到 checkoutUrl 的 fragment 中
        """
        import asyncio

        product_id = session_payload.get("productId", "")

        # 并行请求
        token_task = self._post(
            "/v1/actions/auth/issue-session-token",
            {"productId": product_id, "buyerIdentity": buyer_identity},
        )
        session_task = self._post(
            "/v1/actions/checkout/create-session",
            session_payload,
        )

        token_data, session_data = await asyncio.gather(token_task, session_task)

        # 提取结果
        token_result = token_data.get("data", token_data)
        session_result = session_data.get("data", session_data)

        checkout_url = session_result.get("checkoutUrl", "")
        token = token_result.get("token", "")

        # 将 token 追加到 URL fragment（与 SDK 行为一致）
        if checkout_url and token:
            separator = "&" if "#" in checkout_url else "#"
            checkout_url = f"{checkout_url}{separator}token={token}"

        return {
            "checkout_url": checkout_url,
            "session_id": session_result.get("sessionId", ""),
            "expires_at": session_result.get("expiresAt", ""),
            "token": token,
            "token_expires_at": token_result.get("expiresAt", ""),
        }

    async def create_dynamic_checkout(
        self,
        amount: float,
        currency: str = "CNY",
        product_name: str = "算力充值",
        buyer_identity: Optional[str] = None,
        buyer_email: Optional[str] = None,
        success_url: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
        order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        创建动态金额的 Checkout Session（使用 priceSnapshot 覆盖价格）

        Args:
            amount: 金额（元，如 50.00）— 会自动转为字符串传给 API
            currency: 货币代码
            product_name: 产品描述（仅日志用）
            buyer_identity: 买家标识
            buyer_email: 买家邮箱
            success_url: 成功跳转
            metadata: 元数据（值会被转为字符串）
            order_id: 内部订单号（作为 orderMerchantExternalId）
        """
        self._ensure_initialized()

        base_product_id = os.environ.get("WAFFO_RECHARGE_PRODUCT_ID", "")
        if not base_product_id:
            raise WaffoConfigError(
                "需要设置 WAFFO_RECHARGE_PRODUCT_ID 环境变量。"
                "请在 Waffo Dashboard 创建一个一次性产品作为充值载体，"
                "然后将产品 ID 填入 .env"
            )

        # priceSnapshot.amount 按 SDK 文档应为字符串
        price_snapshot = {
            "amount": str(amount),
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
            order_merchant_external_id=order_id,
        )

    @staticmethod
    def verify_webhook_signature(body: str, signature: str) -> Dict[str, Any]:
        """
        验证 Waffo Webhook 签名

        Args:
            body: 原始请求体（字符串）
            signature: x-waffo-signature header 值

        Returns:
            解析后的事件数据

        Raises:
            WaffoWebhookError: 签名验证失败
        """
        try:
            event = json.loads(body)
        except json.JSONDecodeError as e:
            raise WaffoWebhookError(f"无效的 webhook body: {e}")

        if "eventType" not in event:
            raise WaffoWebhookError("webhook 缺少 eventType 字段")

        logger.info(
            "Waffo webhook 收到: type=%s, id=%s",
            event.get("eventType"), event.get("id"),
        )

        # TODO: 实现完整的 RSA-SHA256 签名验证
        # SDK 内嵌了测试和生产环境的公钥用于验证
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

        payload = {
            "query": query,
            "variables": {"id": order_id},
        }

        try:
            data = await self._post("/v1/graphql", payload)
            return data.get("data", {}).get("order")
        except WaffoApiError as e:
            logger.error("Waffo GraphQL 查询失败: %s", e)
            return None


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
