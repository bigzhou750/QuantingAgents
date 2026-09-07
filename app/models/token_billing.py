"""
算力充值计费模块 - Pydantic 数据模型

金额精度规范：所有金额字段统一使用整数毫额度（milli-quota, mq），
单位 = 厘（0.001元）。转换规则：
- 写入DB: int(round(yuan * 1000))
- 读出展示: (val / 1000).toFixed(3)
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict, field_serializer
from app.utils.timezone import now_tz


# ==================== 账户模型 ====================

class TokenAccount(BaseModel):
    """用户额度账户"""
    user_id: str = Field(..., description="用户ID")
    balance_mq: int = Field(default=0, description="当前可用额度（毫额度）")
    frozen_mq: int = Field(default=0, description="预占中待结算（毫额度）")
    total_recharged_mq: int = Field(default=0, description="累计充值（毫额度）")
    total_consumed_mq: int = Field(default=0, description="累计消耗（毫额度）")
    total_gifted_mq: int = Field(default=0, description="累计赠送（毫额度）")
    created_at: str = Field(default_factory=lambda: now_tz().isoformat())
    updated_at: str = Field(default_factory=lambda: now_tz().isoformat())

    model_config = ConfigDict(populate_by_name=True)


class TokenAccountResponse(BaseModel):
    """账户响应模型（金额转为元）"""
    balance: float = Field(description="当前可用额度（元）")
    frozen: float = Field(description="预占中（元）")
    total_recharged: float = Field(description="累计充值（元）")
    total_consumed: float = Field(description="累计消耗（元）")
    total_gifted: float = Field(description="累计赠送（元）")
    created_at: str
    updated_at: str

    @classmethod
    def from_account(cls, account: dict) -> "TokenAccountResponse":
        """从MongoDB文档构建响应"""
        return cls(
            balance=account.get("balance_mq", 0) / 1000,
            frozen=account.get("frozen_mq", 0) / 1000,
            total_recharged=account.get("total_recharged_mq", 0) / 1000,
            total_consumed=account.get("total_consumed_mq", 0) / 1000,
            total_gifted=account.get("total_gifted_mq", 0) / 1000,
            created_at=account.get("created_at", ""),
            updated_at=account.get("updated_at", ""),
        )


# ==================== 充值订单模型 ====================

class RechargeOrderCreate(BaseModel):
    """创建充值订单请求"""
    package_id: Optional[str] = Field(None, description="套餐ID（与custom_amount二选一）")
    custom_amount: Optional[int] = Field(None, ge=1000, le=5000000, description="自定义金额（毫额度，与package_id二选一）")
    idempotency_key: str = Field(..., min_length=1, max_length=128, description="幂等键")


class RechargeOrderResponse(BaseModel):
    """充值订单响应"""
    order_id: str
    amount: float = Field(description="充值金额（元）")
    quota_to_credit: float = Field(description="到账额度（元）")
    gift_amount: float = Field(description="赠送部分（元）")
    pay_type: str = Field(description="支付类型: NATIVE/JSAPI/MWEB")
    pay_params: Dict[str, Any] = Field(description="支付参数（二维码URL/JSAPI参数/MWEB跳转URL）")
    expire_at: str = Field(description="订单过期时间")
    status: str = Field(description="订单状态")


class OrderStatusResponse(BaseModel):
    """订单状态查询响应"""
    order_id: str
    status: str
    amount: float
    quota_to_credit: float
    pay_type: str
    created_at: str
    credited_at: Optional[str] = None
    expire_at: str


# ==================== 交易流水模型 ====================

class TokenTransactionRecord(BaseModel):
    """交易流水记录"""
    txn_id: str = Field(..., description="交易ID")
    user_id: str = Field(..., description="用户ID")
    order_id: Optional[str] = Field(None, description="关联订单ID")
    type: str = Field(..., description="类型: recharge/consume/gift/preoccupy/settle/settle_refund")
    direction: str = Field(..., description="方向: in/out")
    amount_mq: int = Field(..., description="变动金额（毫额度）")
    balance_before_mq: int = Field(..., description="变动前余额（毫额度）")
    balance_after_mq: int = Field(..., description="变动后余额（毫额度）")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="扩展元数据")
    status: str = Field(default="success", description="状态: success/pending/frozen/rolled_back")
    related_txn_id: Optional[str] = Field(None, description="关联交易ID（preoccupy↔settle）")
    created_at: str = Field(default_factory=lambda: now_tz().isoformat())

    model_config = ConfigDict(populate_by_name=True)


class TransactionResponse(BaseModel):
    """交易流水响应（金额转为元）"""
    txn_id: str
    type: str
    direction: str
    amount: float
    balance_before: float
    balance_after: float
    metadata: Dict[str, Any]
    status: str
    order_id: Optional[str] = None
    related_txn_id: Optional[str] = None
    created_at: str

    @classmethod
    def from_record(cls, record: dict) -> "TransactionResponse":
        """从MongoDB文档构建响应"""
        return cls(
            txn_id=record.get("txn_id", ""),
            type=record.get("type", ""),
            direction=record.get("direction", ""),
            amount=record.get("amount_mq", 0) / 1000,
            balance_before=record.get("balance_before_mq", 0) / 1000,
            balance_after=record.get("balance_after_mq", 0) / 1000,
            metadata=record.get("metadata", {}),
            status=record.get("status", "success"),
            order_id=record.get("order_id"),
            related_txn_id=record.get("related_txn_id"),
            created_at=record.get("created_at", ""),
        )


class TransactionListResponse(BaseModel):
    """交易流水列表响应"""
    items: List[TransactionResponse]
    total: int
    page: int
    page_size: int


# ==================== 充值套餐模型 ====================

class PackageInfo(BaseModel):
    """充值套餐信息"""
    package_id: str = Field(..., description="套餐ID")
    name: str = Field(..., description="套餐名称")
    amount_cny: float = Field(..., description="价格（元）")
    sort_order: int = Field(default=0, description="排序")
    enabled: bool = Field(default=True, description="是否启用")
    tags: List[str] = Field(default_factory=list, description="标签")

    @classmethod
    def from_doc(cls, doc: dict) -> "PackageInfo":
        """从MongoDB文档构建"""
        return cls(
            package_id=doc.get("package_id", ""),
            name=doc.get("name", ""),
            amount_cny=doc.get("amount_cny", 0),
            sort_order=doc.get("sort_order", 0),
            enabled=doc.get("enabled", True),
            tags=doc.get("tags", []),
        )


class PackageUpdateRequest(BaseModel):
    """套餐更新请求"""
    packages: List[PackageInfo]


# ==================== 计费配置模型 ====================

class TokenBillingSettings(BaseModel):
    """计费配置（typed wrapper over system_settings keys）"""
    token_exchange_rate: float = Field(default=1.1, description="充值兑换率")
    token_consumption_ratio: float = Field(default=1.2, description="消耗比率（B方案·单笔盈利）")
    token_input_price_per_1m: float = Field(default=1.0, description="输入价格 ¥/1M token")
    token_output_price_per_1m: float = Field(default=2.0, description="输出价格 ¥/1M token")
    token_preoccupy_ratio: float = Field(default=1.2, description="预占系数")
    token_balance_warn_threshold: float = Field(default=5.0, description="余额预警阈值（元）")
    token_order_expire_minutes: int = Field(default=30, description="订单过期时间（分钟）")

    @classmethod
    def from_system_settings(cls, settings: dict) -> "TokenBillingSettings":
        """从system_settings字典构建"""
        return cls(
            token_exchange_rate=settings.get("token_exchange_rate", 1.1),
            token_consumption_ratio=settings.get("token_consumption_ratio", 1.2),
            token_input_price_per_1m=settings.get("token_input_price_per_1m", 1.0),
            token_output_price_per_1m=settings.get("token_output_price_per_1m", 2.0),
            token_preoccupy_ratio=settings.get("token_preoccupy_ratio", 1.2),
            token_balance_warn_threshold=settings.get("token_balance_warn_threshold", 5.0),
            token_order_expire_minutes=settings.get("token_order_expire_minutes", 30),
        )


class BillingConfigUpdateRequest(BaseModel):
    """计费配置更新请求"""
    token_exchange_rate: Optional[float] = Field(None, ge=0.1, le=10.0)
    token_consumption_ratio: Optional[float] = Field(None, ge=0.1, le=10.0)
    token_input_price_per_1m: Optional[float] = Field(None, ge=0.0)
    token_output_price_per_1m: Optional[float] = Field(None, ge=0.0)
    token_preoccupy_ratio: Optional[float] = Field(None, ge=1.0, le=5.0)
    token_balance_warn_threshold: Optional[float] = Field(None, ge=0.0)
    token_order_expire_minutes: Optional[int] = Field(None, ge=5, le=1440)


# ==================== 微信支付回调模型 ====================

class WxPayCallbackData(BaseModel):
    """微信支付V3回调解析结果"""
    out_trade_no: str = Field(..., description="商户订单号")
    transaction_id: Optional[str] = Field(None, description="微信支付订单号")
    trade_state: str = Field(..., description="交易状态: SUCCESS/REFUND/NOTPAY/CLOSED/REVOKED/USERPAYING/PAYERROR")
    amount_total: Optional[int] = Field(None, description="订单总金额（分）")
    success_time: Optional[str] = Field(None, description="支付完成时间")
    openid: Optional[str] = Field(None, description="用户openid")
    raw_data: Dict[str, Any] = Field(default_factory=dict, description="原始回调数据")


# ==================== 工具函数 ====================

def yuan_to_mq(yuan: float) -> int:
    """元转毫额度（厘）"""
    return int(round(yuan * 1000))


def mq_to_yuan(mq: int) -> float:
    """毫额度转元"""
    return mq / 1000


def generate_order_id() -> str:
    """生成充值订单号: RC + 日期 + 6位随机数"""
    import random
    date_str = now_tz().strftime("%Y%m%d")
    rand_part = f"{random.randint(0, 999999):06d}"
    return f"RC{date_str}{rand_part}"


def generate_txn_id(prefix: str = "TXN") -> str:
    """生成交易流水号"""
    import random
    date_str = now_tz().strftime("%Y%m%d%H%M%S")
    rand_part = f"{random.randint(0, 999999):06d}"
    return f"{prefix}_{date_str}_{rand_part}"
