"""
算力充值计费 API 路由

端点前缀: /api/token-billing
"""

import csv
import io
import logging
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, Query, Request, Header, HTTPException
from fastapi.responses import StreamingResponse

from app.core.response import ok
from app.routers.auth_db import get_current_user
from app.services.token_billing_service import (
    token_billing_service,
    InsufficientBalanceError,
    DuplicateOrderError,
)
from app.services.waffo_service import waffo_service, WaffoApiError, WaffoConfigError
from app.models.token_billing import (
    RechargeOrderCreate,
    RechargeOrderResponse,
    OrderStatusResponse,
    BillingConfigUpdateRequest,
    PackageUpdateRequest,
    AdminRechargeRequest,
    mq_to_yuan,
    yuan_to_mq,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/token-billing", tags=["token-billing"])


# ==================== Admin 鉴权依赖 ====================

async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """要求管理员权限"""
    if not current_user.get("is_admin", False):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return current_user


# ==================== 账户接口 ====================

@router.get("/account")
async def get_account(current_user: dict = Depends(get_current_user)):
    """获取用户额度账户信息（R9）"""
    account = await token_billing_service.get_account_response(current_user["id"])
    return ok(account.model_dump())


# ==================== 管理员运营接口 ====================

@router.get("/admin/users/{target}/account")
async def admin_get_user_account(
    target: str,
    admin: dict = Depends(require_admin),
):
    """管理员查询单个用户的算力账户（用户名或用户ID）。"""
    from app.services.user_service import user_service

    target_user = await user_service.get_user_by_username(target)
    if not target_user and ObjectId.is_valid(target):
        target_user = await user_service.get_user_by_id(target)
    if not target_user:
        raise HTTPException(status_code=404, detail="用户不存在")

    account = await token_billing_service.get_account_response(str(target_user.id))
    return ok(account.model_dump())


@router.post("/admin/recharge")
async def admin_recharge(
    payload: AdminRechargeRequest,
    admin: dict = Depends(require_admin),
):
    """管理员后台手工充值算力。"""
    from app.services.user_service import user_service

    if payload.username:
        target_user = await user_service.get_user_admin_detail(payload.username)
    else:
        target_user = await user_service.get_user_by_id(payload.user_id)

    if not target_user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if getattr(target_user, "is_archived", False):
        raise HTTPException(status_code=400, detail="归档账号不能充值")

    amount_mq = yuan_to_mq(payload.amount)
    if amount_mq <= 0:
        raise HTTPException(status_code=400, detail="充值金额必须大于0")

    result = await token_billing_service.admin_recharge(
        user_id=str(target_user.id),
        amount_mq=amount_mq,
        username=target_user.username,
        email=target_user.email,
        operator_user_id=admin.get("id", ""),
        operator_username=admin.get("username", ""),
        reason=payload.reason,
    )
    if not result:
        raise HTTPException(status_code=500, detail="充值失败，请稍后重试")

    try:
        from app.services.operation_log_service import log_operation
        from app.models.operation_log import ActionType
        await log_operation(
            user_id=admin.get("id", ""),
            username=admin.get("username", ""),
            action_type=ActionType.USER_MANAGEMENT,
            action="管理员充值算力",
            details={
                "target_username": target_user.username,
                "target_user_id": str(target_user.id),
                "amount_yuan": payload.amount,
                "txn_id": result["txn_id"],
                "reason": payload.reason,
            },
            success=True,
        )
    except Exception as le:
        logger.warning("⚠️ 管理员充值审计日志写入失败: %s", le)

    account = await token_billing_service.get_account_response(str(target_user.id))
    return ok({
        "account": account.model_dump(),
        "transaction": {
            "txn_id": result["txn_id"],
            "amount": mq_to_yuan(result["amount_mq"]),
            "balance_after": mq_to_yuan(result["balance_after_mq"]),
        },
    })


@router.get("/admin/transactions")
async def admin_get_transactions(
    user_id: Optional[str] = Query(None, description="目标用户ID"),
    type: Optional[str] = Query(None, description="类型过滤: recharge/gift/admin_recharge/all"),
    keyword: Optional[str] = Query(None, max_length=200, description="用户名/邮箱/用户ID/流水号/订单号"),
    start_date: Optional[str] = Query(None, description="开始日期 ISO格式"),
    end_date: Optional[str] = Query(None, description="结束日期 ISO格式"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    admin: dict = Depends(require_admin),
):
    """管理员分页查询充值记录。"""
    result = await token_billing_service.get_admin_transactions(
        user_id=user_id,
        type_filter=type,
        keyword=keyword,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )
    return ok(result.model_dump())


# ==================== 套餐接口 ====================

async def _public_package_items():
    packages = await token_billing_service.get_packages()
    items = [pkg.model_dump() for pkg in packages]
    from app.services.token_billing_service import _get_billing_config
    config = await _get_billing_config()
    exchange_rate = config.get("exchange_rate", 1.1)
    for item in items:
        amount_cny = item["amount_cny"]
        quota = round(amount_cny * exchange_rate, 3)
        item["quota_to_credit"] = quota
        item["gift_amount"] = max(round(quota - amount_cny, 3), 0)
    return items, exchange_rate


@router.get("/public-packages")
async def get_public_packages():
    """公开展示套餐，不返回账户或支付信息。"""
    items, exchange_rate = await _public_package_items()
    return ok({"items": items, "exchange_rate": exchange_rate})


@router.get("/packages")
async def get_packages(current_user: dict = Depends(get_current_user)):
    """获取充值套餐列表（R1）"""
    items, _ = await _public_package_items()
    return ok({"items": items})


# ==================== 订单接口 ====================

@router.post("/orders")
async def create_order(
    payload: RechargeOrderCreate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """创建充值订单 + 获取 Waffo Checkout URL（R3/R4）"""
    import os as _os

    user_id = current_user["id"]
    pay_type = "WAFFO"

    try:
        order_doc = await token_billing_service.create_order(
            user_id=user_id,
            package_id=payload.package_id,
            custom_amount_mq=payload.custom_amount,
            idempotency_key=payload.idempotency_key,
            pay_type=pay_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except DuplicateOrderError as e:
        raise HTTPException(
            status_code=409,
            detail={"code": 40901, "message": str(e), "order_id": e.existing_order_id},
        )

    # 模拟支付模式：通过环境变量 PAYMENT_MOCK=true 显式开启
    is_mock_mode = _os.environ.get("PAYMENT_MOCK", "").lower() in ("true", "1", "yes")
    if is_mock_mode:
        logger.warning("⚠️ 模拟支付模式已启用（PAYMENT_MOCK=true），请勿在生产环境使用")

    if is_mock_mode:
        # 模拟支付：跳过支付网关，直接标记订单为已支付并入账
        logger.info("🧪 模拟支付模式：跳过支付网关，直接入账 (order=%s)", order_doc["order_id"])
        credited = await token_billing_service.mark_order_credited(
            order_doc["order_id"], "MOCK_TXN_" + order_doc["order_id"], {"mock": True}
        )
        if credited:
            await token_billing_service.credit_quota(
                user_id=user_id,
                quota_mq=order_doc["quota_to_credit_mq"],
                gift_mq=order_doc["gift_amount_mq"],
                order_id=order_doc["order_id"],
                amount_cny_mq=order_doc["amount_mq"],
            )
        pay_params = {"mock": True, "message": "模拟支付模式，无需真实付款"}
    else:
        # 正式支付：调用 Waffo Pancake API 创建 Checkout Session
        amount_yuan = mq_to_yuan(order_doc["amount_mq"])
        currency = _os.environ.get("WAFFO_CURRENCY", "CNY")

        # 构建成功回调 URL
        origin = request.headers.get("origin", "")
        if not origin:
            server_ip = _os.environ.get("SERVER_IP", "localhost")
            origin = f"http://{server_ip}"
        success_url = f"{origin}/token-recharge?order={order_doc['order_id']}&status=success"

        try:
            # 使用匿名模式（不传 buyer_identity）
            # 认证模式的 token 通过 URL fragment 传递，依赖 Waffo 前端 JS
            # 从 localStorage 读取并通过 Next.js Server Action 验证，
            # 跨域 window.open 场景下容易失败。
            # 匿名模式下买家在结账页手动填写信息，订单通过 metadata.order_id 关联。
            checkout_result = await waffo_service.create_dynamic_checkout(
                amount=amount_yuan,
                currency=currency,
                product_name=f"算力充值-{amount_yuan:.0f}元",
                success_url=success_url,
                metadata={
                    "order_id": order_doc["order_id"],
                    "user_id": user_id,
                    "package_id": payload.package_id or "custom",
                },
                order_id=order_doc["order_id"],
            )
            pay_params = {
                "checkout_url": checkout_result["checkout_url"],
                "session_id": checkout_result["session_id"],
                "expires_at": checkout_result["expires_at"],
            }
        except WaffoConfigError as e:
            logger.error("Waffo 支付配置错误: %s", e)
            raise HTTPException(
                status_code=500,
                detail={"code": 50002, "message": f"支付服务未配置: {e}"},
            )
        except WaffoApiError as e:
            logger.error("Waffo 支付下单失败: %s", e)
            raise HTTPException(
                status_code=500,
                detail={"code": 50001, "message": f"支付服务暂时不可用: {e}"},
            )

    response = RechargeOrderResponse(
        order_id=order_doc["order_id"],
        amount=mq_to_yuan(order_doc["amount_mq"]),
        quota_to_credit=mq_to_yuan(order_doc["quota_to_credit_mq"]),
        gift_amount=mq_to_yuan(order_doc["gift_amount_mq"]),
        pay_type=pay_type,
        pay_params=pay_params,
        expire_at=order_doc["expire_at"],
        status=order_doc["status"],
    )
    return ok(response.model_dump())


@router.get("/orders/pending")
async def get_pending_order(
    current_user: dict = Depends(get_current_user),
):
    """获取最近的pending订单（中断恢复 R12）"""
    order = await token_billing_service.get_pending_order(current_user["id"])
    if not order:
        return ok(None)

    return ok({
        "order_id": order["order_id"],
        "amount": mq_to_yuan(order["amount_mq"]),
        "pay_type": order["pay_type"],
        "created_at": order["created_at"],
        "expire_at": order["expire_at"],
    })


@router.get("/orders/{order_id}")
async def get_order_status(
    order_id: str,
    current_user: dict = Depends(get_current_user),
):
    """查询订单状态（R6/R12）"""
    order = await token_billing_service.get_order(current_user["id"], order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    response = OrderStatusResponse(
        order_id=order["order_id"],
        status=order["status"],
        amount=mq_to_yuan(order["amount_mq"]),
        quota_to_credit=mq_to_yuan(order["quota_to_credit_mq"]),
        pay_type=order["pay_type"],
        created_at=order["created_at"],
        credited_at=order.get("credited_at"),
        expire_at=order["expire_at"],
    )
    return ok(response.model_dump())


@router.post("/orders/{order_id}/query-wx")
async def query_wx_order(
    order_id: str,
    current_user: dict = Depends(get_current_user),
):
    """主动查询微信订单状态（兜底）"""
    order = await token_billing_service.get_order(current_user["id"], order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    try:
        wx_result = await wxpay_service.query_order(order["wx_out_trade_no"])
        trade_state = wx_result.get("trade_state", "")

        # 如果微信显示成功但本地还是pending，触发入账
        if trade_state == "SUCCESS" and order["status"] == "pending":
            logger.info("主动查询发现已支付，触发入账: %s", order_id)
            # TODO: 复用回调入账逻辑
            return ok({"status": "paid_pending_credit", "wx_state": trade_state})

        return ok({"status": order["status"], "wx_state": trade_state})
    except WxPayApiError as e:
        raise HTTPException(status_code=500, detail=f"查询微信订单失败: {e}")


# ==================== Waffo Webhook 回调（无auth） ====================

@router.post("/waffo/webhook")
async def waffo_webhook(request: Request):
    """
    Waffo Pancake 异步回调通知

    注意：此端点不需要JWT认证，通过签名验证安全性
    Webhook body 必须以原始文本读取，不能先解析 JSON
    """
    from app.services.waffo_service import WaffoWebhookError

    # ⚠️ 必须读取原始 body，不能先解析 JSON（会破坏签名验证）
    body_bytes = await request.body()
    body_text = body_bytes.decode("utf-8")
    signature = request.headers.get("x-waffo-signature", "")

    # 验签
    try:
        event = waffo_service.verify_webhook_signature(body_text, signature)
    except WaffoWebhookError as e:
        logger.warning("Waffo webhook 验签失败: %s", e)
        return {"code": "FAIL", "message": "签名验证失败"}

    event_type = event.get("eventType", "")
    event_id = event.get("id", "")
    event_data = event.get("data", {})
    mode = event.get("mode", "test")

    logger.info(
        "收到 Waffo webhook: type=%s, id=%s, mode=%s, data=%s",
        event_type, event_id, mode, event_data,
    )

    # 只处理订单完成事件
    if event_type != "order.completed":
        logger.debug("忽略非 order.completed 事件: %s", event_type)
        return {"code": "SUCCESS", "message": "OK"}

    # 从 metadata 中获取内部订单号
    metadata = event_data.get("metadata", {})
    internal_order_id = metadata.get("order_id", "")
    waffo_order_id = event_data.get("orderId", "")
    buyer_email = event_data.get("buyerEmail", "")
    amount = event_data.get("amount", 0)
    currency = event_data.get("currency", "")

    if not internal_order_id:
        logger.warning("Waffo webhook 缺少内部 order_id (metadata.order_id)")
        return {"code": "SUCCESS", "message": "OK"}

    logger.info(
        "Waffo 支付成功: internal_order=%s, waffo_order=%s, amount=%s %s, email=%s",
        internal_order_id, waffo_order_id, amount, currency, buyer_email,
    )

    # 获取订单信息
    from app.core.database import get_mongo_db
    db = get_mongo_db()
    order = await db["token_recharge_orders"].find_one({"order_id": internal_order_id})

    if not order:
        logger.error("Waffo webhook 对应的订单不存在: %s", internal_order_id)
        return {"code": "SUCCESS", "message": "OK"}

    if order["status"] == "credited":
        # 幂等：已入账
        logger.info("订单已入账（幂等跳过）: %s", internal_order_id)
        return {"code": "SUCCESS", "message": "OK"}

    # 标记订单为已支付
    credited = await token_billing_service.mark_order_credited(
        internal_order_id, waffo_order_id, event
    )

    if credited:
        # 入账
        success = await token_billing_service.credit_quota(
            user_id=order["user_id"],
            quota_mq=order["quota_to_credit_mq"],
            gift_mq=order["gift_amount_mq"],
            order_id=internal_order_id,
            amount_cny_mq=order["amount_mq"],
        )

        if success:
            logger.info("✅ Waffo 充值入账成功: order=%s, user=%s", internal_order_id, order["user_id"])
        else:
            logger.error("❌ Waffo 充值入账失败: order=%s（需人工介入）", internal_order_id)
    else:
        logger.warning("标记入账返回False: order=%s", internal_order_id)

    return {"code": "SUCCESS", "message": "OK"}


# ==================== 交易流水接口 ====================

@router.get("/transactions")
async def get_transactions(
    type: Optional[str] = Query(None, description="类型过滤: recharge/consume/gift/all"),
    start_date: Optional[str] = Query(None, description="开始日期 ISO格式"),
    end_date: Optional[str] = Query(None, description="结束日期 ISO格式"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    current_user: dict = Depends(get_current_user),
):
    """分页查询交易流水（R7/R8/R10）"""
    result = await token_billing_service.get_transactions(
        user_id=current_user["id"],
        type_filter=type,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )
    return ok(result.model_dump())


@router.get("/transactions/export")
async def export_transactions(
    type: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """导出交易流水CSV（R11, PC）"""
    result = await token_billing_service.get_transactions(
        user_id=current_user["id"],
        type_filter=type,
        start_date=start_date,
        end_date=end_date,
        page=1,
        page_size=10000,  # 导出全量
    )

    # 生成CSV（添加UTF-8 BOM确保Excel正确显示中文）
    output = io.StringIO()
    output.write('﻿')  # UTF-8 BOM
    writer = csv.writer(output)
    writer.writerow(["交易ID", "类型", "方向", "金额(元)", "余额(元)", "状态", "时间"])

    for item in result.items:
        writer.writerow([
            item.txn_id,
            item.type,
            "收入" if item.direction == "in" else "支出",
            f"{item.amount:.3f}",
            f"{item.balance_after:.3f}",
            item.status,
            item.created_at,
        ])

    writer.writerow([])
    writer.writerow(["支持邮箱", "zh75067197@gmail.com"])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=transactions.csv"},
    )


# ==================== 后台管理接口 ====================

@router.get("/billing-config")
async def get_billing_config(admin: dict = Depends(require_admin)):
    """读取计费配置"""
    from app.services.token_billing_service import _get_billing_config
    config = await _get_billing_config()
    return ok(config)


@router.put("/billing-config")
async def update_billing_config(
    payload: BillingConfigUpdateRequest,
    admin: dict = Depends(require_admin),
):
    """更新计费配置（R13）+ 审计留痕"""
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="没有要更新的配置项")

    # 添加token_前缀
    prefixed_updates = {}
    for key, value in updates.items():
        prefixed_updates[f"token_{key}" if not key.startswith("token_") else key] = value

    try:
        from app.services.config_service import config_service
        await config_service.update_system_settings(prefixed_updates)

        # 失效缓存
        from app.services.token_billing_service import invalidate_billing_cache
        invalidate_billing_cache()

        # 审计留痕
        try:
            from app.services.operation_log_service import log_operation
            await log_operation(
                user_id=admin.get("id", ""),
                username=admin.get("username", ""),
                action_type="system_settings",
                action="更新Token计费配置",
                details={"updated_keys": list(prefixed_updates.keys()), "values": {k: v for k, v in prefixed_updates.items()}},
                success=True,
            )
        except Exception as le:
            logger.warning("⚠️ 审计日志写入失败: %s", le)

        logger.info("计费配置更新: %s by %s", list(prefixed_updates.keys()), admin.get("username"))
        return ok({"updated": list(prefixed_updates.keys())})
    except Exception as e:
        logger.error("更新计费配置失败: %s", e)
        raise HTTPException(status_code=500, detail=f"更新失败: {e}")


@router.put("/packages")
async def update_packages(
    payload: PackageUpdateRequest,
    admin: dict = Depends(require_admin),
):
    """CRUD充值档位（R1）"""
    from app.core.database import get_mongo_db
    db = get_mongo_db()

    updated = []
    for pkg in payload.packages:
        doc = pkg.model_dump()
        existing = await db["token_packages"].find_one({"package_id": doc["package_id"]})
        if existing:
            await db["token_packages"].update_one(
                {"package_id": doc["package_id"]},
                {"$set": doc},
            )
        else:
            await db["token_packages"].insert_one(doc)
        updated.append(doc["package_id"])

    logger.info("套餐更新: %s by %s", updated, admin.get("username"))
    return ok({"updated": updated})


@router.post("/reconcile")
async def reconcile(admin: dict = Depends(require_admin)):
    """手动触发对账补偿（admin only）"""
    count = await token_billing_service.reconcile_stale_frozen()
    return ok({"reconciled_accounts": count})
