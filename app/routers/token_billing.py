"""
算力充值计费 API 路由

端点前缀: /api/token-billing
"""

import csv
import io
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, Header, HTTPException
from fastapi.responses import StreamingResponse

from app.core.response import ok
from app.routers.auth_db import get_current_user
from app.services.token_billing_service import (
    token_billing_service,
    InsufficientBalanceError,
    DuplicateOrderError,
)
from app.services.wxpay_service import wxpay_service, WxPayApiError
from app.models.token_billing import (
    RechargeOrderCreate,
    RechargeOrderResponse,
    OrderStatusResponse,
    BillingConfigUpdateRequest,
    PackageUpdateRequest,
    mq_to_yuan,
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
    """创建充值订单 + 获取支付参数（R3/R4）"""
    user_id = current_user["id"]

    # 检测支付类型
    user_agent = request.headers.get("user-agent", "")
    pay_type = wxpay_service.detect_pay_type(user_agent)

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

    # 模拟支付模式：通过环境变量 WXPAY_MOCK=true 显式开启
    # 本地开发设置 WXPAY_MOCK=true 可跳过微信API直接入账
    # 生产环境必须为 false 或不设置，强制走微信支付
    import os as _os
    is_mock_mode = _os.environ.get("WXPAY_MOCK", "").lower() in ("true", "1", "yes")
    if is_mock_mode:
        logger.warning("⚠️ 模拟支付模式已启用（WXPAY_MOCK=true），请勿在生产环境使用")

    if is_mock_mode:
        # 模拟支付：跳过微信API，直接标记订单为已支付并入账
        logger.info("🧪 模拟支付模式：跳过微信API，直接入账 (order=%s)", order_doc["order_id"])
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
        # 正式支付：调用微信支付API
        amount_cents = round(order_doc["amount_mq"] / 10)  # 毫额度→分（÷10，四舍五入避免精度损失）
        description = f"算力充值-{mq_to_yuan(order_doc['amount_mq']):.0f}元"

        try:
            if pay_type == "NATIVE":
                pay_params = await wxpay_service.create_native_order(
                    order_doc["order_id"], amount_cents, description
                )
            elif pay_type == "JSAPI":
                # JSAPI需要openid，v1先返回提示
                pay_params = {"message": "JSAPI支付需要openid，请先完成微信授权"}
            elif pay_type == "MWEB":
                client_ip = request.client.host if request.client else ""
                pay_params = await wxpay_service.create_mweb_order(
                    order_doc["order_id"], amount_cents, description, client_ip
                )
            else:
                pay_params = {}
        except WxPayApiError as e:
            logger.error("微信支付下单失败: %s", e)
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


# ==================== 微信支付回调（无auth） ====================

@router.post("/wxpay/notify")
async def wxpay_notify(request: Request):
    """
    微信支付异步回调通知

    注意：此端点不需要JWT认证，通过签名验证安全性
    """
    body = await request.body()
    headers = dict(request.headers)

    # 验签
    if not wxpay_service.verify_callback_signature(headers, body):
        logger.warning("微信支付回调验签失败")
        return {"code": "FAIL", "message": "签名验证失败"}

    # 解析回调
    try:
        callback_data = wxpay_service.parse_callback(body)
    except ValueError as e:
        logger.error("回调解析失败: %s", e)
        return {"code": "FAIL", "message": str(e)}

    payment = callback_data.get("payment", {})
    out_trade_no = payment.get("out_trade_no", "")
    trade_state = payment.get("trade_state", "")
    transaction_id = payment.get("transaction_id", "")

    if not out_trade_no:
        logger.warning("回调缺少out_trade_no")
        return {"code": "FAIL", "message": "缺少订单号"}

    logger.info(
        "收到微信支付回调: order=%s, state=%s, txn=%s",
        out_trade_no, trade_state, transaction_id
    )

    if trade_state == "SUCCESS":
        # 获取订单信息
        from app.core.database import get_mongo_db
        db = get_mongo_db()
        order = await db["token_recharge_orders"].find_one({"order_id": out_trade_no})

        if not order:
            logger.error("回调对应的订单不存在: %s", out_trade_no)
            return {"code": "FAIL", "message": "订单不存在"}

        if order["status"] == "credited":
            # 幂等：已入账
            logger.info("订单已入账（幂等跳过）: %s", out_trade_no)
            return {"code": "SUCCESS", "message": "OK"}

        # 标记订单为已支付
        credited = await token_billing_service.mark_order_credited(
            out_trade_no, transaction_id, callback_data.get("raw", {})
        )

        if credited:
            # 入账
            success = await token_billing_service.credit_quota(
                user_id=order["user_id"],
                quota_mq=order["quota_to_credit_mq"],
                gift_mq=order["gift_amount_mq"],
                order_id=out_trade_no,
                amount_cny_mq=order["amount_mq"],
            )

            if success:
                logger.info("✅ 充值入账成功: order=%s, user=%s", out_trade_no, order["user_id"])
            else:
                logger.error("❌ 充值入账失败: order=%s（需人工介入）", out_trade_no)
        else:
            logger.warning("标记入账返回False: order=%s", out_trade_no)

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
