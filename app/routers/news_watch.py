"""
新闻关注工作台 API 路由
提供关注收集、持仓影响分析和模拟告警接口
"""
from fastapi import APIRouter, HTTPException, Depends, Query, status
from typing import Optional, List
from pydantic import BaseModel, Field
import logging

from app.routers.auth_db import get_current_user
from app.core.response import ok
from app.services.news_watch_service import (
    get_news_watch_service,
    IMPACT_LEVELS,
    ALERT_THRESHOLD_LOW,
    ALERT_THRESHOLD_MEDIUM,
    ALERT_THRESHOLD_HIGH,
)

router = APIRouter(tags=["news-watch"])
logger = logging.getLogger("webapi")


# ── 请求模型 ──────────────────────────────────────────────────

class CollectRequest(BaseModel):
    """收集一条股票或新闻到关注工作台"""
    item_type: str = Field(..., description="收集类型: stock | news")
    symbol: Optional[str] = Field(None, description="股票代码（item_type=stock 时必填）")
    news_id: Optional[str] = Field(None, description="新闻 ID（item_type=news 时必填）")
    source_page: str = Field("", description="来源页面标识")
    title: str = Field("", description="标题或摘要")


class AlertConfigUpdate(BaseModel):
    """更新告警阈值配置"""
    threshold: str = Field(
        ...,
        description=f"告警阈值: {ALERT_THRESHOLD_LOW} | {ALERT_THRESHOLD_MEDIUM} | {ALERT_THRESHOLD_HIGH}",
    )


# ── 1. 关注收集 ───────────────────────────────────────────────

@router.post("/collect", response_model=dict)
async def collect_item(
    request: CollectRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    一键收集股票或新闻到关注工作台。
    - item_type='stock': 从详情页/自选股收集股票
    - item_type='news': 从新闻列表收集新闻条目
    """
    if request.item_type not in ("stock", "news"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="item_type 必须是 'stock' 或 'news'",
        )
    if request.item_type == "stock" and not request.symbol:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="收集股票时必须提供 symbol",
        )

    try:
        service = await get_news_watch_service()
        doc = await service.collect_item(
            user_id=current_user["id"],
            item_type=request.item_type,
            symbol=request.symbol,
            news_id=request.news_id,
            source_page=request.source_page,
            title=request.title,
        )
        return ok(data=doc, message="已加入关注工作台")
    except Exception as e:
        logger.error(f"❌ 收集失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"收集失败: {str(e)}",
        )


@router.get("/collected", response_model=dict)
async def get_collected_items(
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    item_type: Optional[str] = Query(None, description="过滤类型: stock | news"),
    current_user: dict = Depends(get_current_user),
):
    """获取用户最近收集的关注记录"""
    try:
        service = await get_news_watch_service()
        items = await service.get_collected_items(
            user_id=current_user["id"],
            limit=limit,
            skip=skip,
            item_type=item_type,
        )
        return ok(data={"items": items, "total": len(items)})
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取收集记录失败: {str(e)}",
        )


@router.delete("/collected/{item_id}", response_model=dict)
async def remove_collected_item(
    item_id: str,
    current_user: dict = Depends(get_current_user),
):
    """移除一条收集记录"""
    try:
        service = await get_news_watch_service()
        success = await service.remove_collected_item(current_user["id"], item_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="收集记录不存在",
            )
        return ok(message="已移除")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"移除失败: {str(e)}",
        )


# ── 2. 持仓新闻影响分析 ──────────────────────────────────────

@router.post("/impact-analysis", response_model=dict)
async def analyze_holdings_impact(
    hours_back: int = Query(72, ge=1, le=720, description="回溯小时数"),
    current_user: dict = Depends(get_current_user),
):
    """
    基于当前持仓分析近期新闻影响。
    返回受影响持仓、影响等级（低/中/高）、证据充分性标记和边界说明。
    """
    try:
        service = await get_news_watch_service()
        result = await service.analyze_holdings_impact(
            user_id=current_user["id"],
            hours_back=hours_back,
        )
        return ok(data=result)
    except Exception as e:
        logger.error(f"❌ 持仓影响分析失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"分析失败: {str(e)}",
        )


# ── 3. 告警配置与模拟投递 ────────────────────────────────────

@router.get("/alerts/config", response_model=dict)
async def get_alert_config(
    current_user: dict = Depends(get_current_user),
):
    """获取当前用户的告警阈值配置"""
    try:
        service = await get_news_watch_service()
        config = await service.get_alert_config(current_user["id"])
        return ok(data=config)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取告警配置失败: {str(e)}",
        )


@router.put("/alerts/config", response_model=dict)
async def update_alert_config(
    request: AlertConfigUpdate,
    current_user: dict = Depends(get_current_user),
):
    """
    更新告警阈值。
    - low: 低/中/高等级都触发告警
    - medium: 中/高等级触发告警
    - high: 仅高等级触发告警
    """
    try:
        service = await get_news_watch_service()
        config = await service.update_alert_config(
            user_id=current_user["id"],
            threshold=request.threshold,
        )
        return ok(data=config, message="告警阈值已更新")
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新告警配置失败: {str(e)}",
        )


@router.post("/alerts/simulate", response_model=dict)
async def simulate_alerts(
    hours_back: int = Query(72, ge=1, le=720),
    current_user: dict = Depends(get_current_user),
):
    """
    手动触发一次模拟告警检测。
    先执行持仓影响分析，再根据告警阈值生成模拟投递记录。
    所有记录明确标记为"模拟"，不会实际发送任何消息。
    """
    try:
        service = await get_news_watch_service()

        # 1) 执行影响分析
        analysis = await service.analyze_holdings_impact(
            user_id=current_user["id"],
            hours_back=hours_back,
        )

        if not analysis.get("has_holdings"):
            return ok(data={
                "generated_count": 0,
                "alerts": [],
                "note": analysis.get("boundary_note", "无持仓数据"),
            })

        # 2) 生成模拟告警
        alerts = await service.simulate_alerts(
            user_id=current_user["id"],
            impacts=analysis.get("impacts", []),
        )

        return ok(data={
            "generated_count": len(alerts),
            "alerts": alerts,
            "analysis_summary": {
                "holdings_count": analysis["holdings_count"],
                "data_sufficient": analysis["data_sufficient"],
            },
            "note": "以下为模拟告警记录，未实际发送任何消息。",
        })
    except Exception as e:
        logger.error(f"❌ 模拟告警失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"模拟告警失败: {str(e)}",
        )


@router.get("/alerts", response_model=dict)
async def get_alert_records(
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    """获取用户的告警记录列表（含模拟标记）"""
    try:
        service = await get_news_watch_service()
        records = await service.get_alert_records(
            user_id=current_user["id"],
            limit=limit,
            skip=skip,
        )
        return ok(data={"records": records, "total": len(records)})
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取告警记录失败: {str(e)}",
        )
