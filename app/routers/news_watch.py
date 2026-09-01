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


class ObservationReviewRequest(BaseModel):
    """触发观察任务复盘请求"""
    observation_id: str
    window_days: int = Field(default=7, ge=1, le=30)


class IgnoreNewsRequest(BaseModel):
    """忽略一条新闻"""
    symbol: Optional[str] = None
    news_id: Optional[str] = None
    title: str = ""


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
    symbol: Optional[str] = Query(None, description="可选：只分析单个观察标的"),
    current_user: dict = Depends(get_current_user),
):
    """
    基于当前持仓分析近期新闻影响。
    返回受影响持仓、影响等级（低/中/高）、证据充分性标记和边界说明。
    """
    try:
        service = await get_news_watch_service()
        if symbol:
            result = await service.analyze_stock_impact(
                user_id=current_user["id"],
                stock_code=symbol,
                hours_back=hours_back,
            )
        else:
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


# ── 4. 新闻聚合与覆盖 ────────────────────────────────────────

from app.models.news_intelligence import (
    AnalyzeNewsRequest,
    AnalyzeBatchRequest,
    AlertStatusUpdateRequest,
    ObservationFromNewsRequest,
)


@router.get("/aggregated-news")
async def get_aggregated_news(
    symbol: str = Query(..., description="股票代码"),
    current_user: dict = Depends(get_current_user),
):
    """获取聚合新闻（含降级链和来源状态）"""
    try:
        from app.services.news_aggregator_service import get_news_aggregator_service
        aggregator = await get_news_aggregator_service()
        result = await aggregator.aggregate(symbol, current_user["id"])
        return ok(data=result.to_dict())
    except Exception as e:
        logger.error(f"Aggregated news failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/source-coverage")
async def get_source_coverage(current_user: dict = Depends(get_current_user)):
    """获取新闻来源覆盖调试信息"""
    try:
        from app.services.news_aggregator_service import get_news_aggregator_service
        aggregator = await get_news_aggregator_service()
        result = await aggregator.get_source_coverage()
        return ok(data=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 5. Agent 新闻影响分析 ─────────────────────────────────────

@router.post("/analyze")
async def analyze_news(
    request: AnalyzeNewsRequest,
    current_user: dict = Depends(get_current_user),
):
    """单条新闻 Agent 结构化分析"""
    try:
        from app.services.news_impact_agent_service import get_news_impact_agent_service
        agent = await get_news_impact_agent_service()
        news_item = request.model_dump()
        record = await agent.analyze_single(news_item)
        return ok(data=record.to_doc())
    except Exception as e:
        logger.error(f"News analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze-batch")
async def analyze_batch(
    request: AnalyzeBatchRequest,
    current_user: dict = Depends(get_current_user),
):
    """批量新闻 Agent 分析"""
    try:
        from app.services.news_impact_agent_service import get_news_impact_agent_service
        agent = await get_news_impact_agent_service()
        items = [item.model_dump() for item in request.news_items]
        records = await agent.analyze_batch(items, cluster_first=request.cluster_first)
        return ok(data={"items": [r.to_doc() for r in records], "count": len(records)})
    except Exception as e:
        logger.error(f"Batch analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── 6. 持仓影响自动分析 ───────────────────────────────────────

@router.get("/holdings-impact/auto")
async def auto_holdings_impact(current_user: dict = Depends(get_current_user)):
    """自动加载持仓影响分析（缓存+后台刷新）"""
    try:
        service = await get_news_watch_service()
        result = await service.get_auto_holdings_impact(
            user_id=current_user["id"],
            hours_back=72,
        )
        return ok(data=result)
    except Exception as e:
        logger.error(f"Auto holdings impact failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── 7. 告警状态管理 ───────────────────────────────────────────

@router.put("/alerts/{alert_id}/status")
async def update_alert_status(
    alert_id: str,
    request: AlertStatusUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    """更新告警状态（确认/忽略/转观察/复盘）"""
    try:
        from app.services.news_closed_loop_service import get_news_closed_loop_service
        closed_loop = await get_news_closed_loop_service()
        result = await closed_loop.update_alert_status(
            alert_id=alert_id,
            user_id=current_user["id"],
            action=request.action,
            note=request.note,
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return ok(data=result, message="状态已更新")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Alert status update failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── 8. 观察任务桥接 ──────────────────────────────────────────

@router.post("/observation-from-news")
async def create_observation_from_news(
    request: ObservationFromNewsRequest,
    current_user: dict = Depends(get_current_user),
):
    """从新闻分析创建观察任务"""
    try:
        from app.services.news_closed_loop_service import get_news_closed_loop_service
        closed_loop = await get_news_closed_loop_service()
        result = await closed_loop.create_observation_from_news(
            user_id=current_user["id"],
            stock_code=request.stock_code,
            stock_name=request.stock_name,
            news_event_id=request.news_event_id,
            analysis_id=request.analysis_id,
            verification_indicators=request.verification_indicators,
            user_notes=request.user_notes,
        )
        return ok(data=result, message="观察任务已创建")
    except Exception as e:
        logger.error(f"Create observation from news failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── 9. 复盘与闭环指标 ────────────────────────────────────────

@router.get("/review-summary")
async def get_review_summary(current_user: dict = Depends(get_current_user)):
    """获取复盘汇总"""
    try:
        from app.services.news_closed_loop_service import get_news_closed_loop_service
        closed_loop = await get_news_closed_loop_service()
        result = await closed_loop.get_review_summary(current_user["id"])
        return ok(data=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/closed-loop-metrics")
async def get_closed_loop_metrics(current_user: dict = Depends(get_current_user)):
    """获取闭环指标概览"""
    try:
        from app.services.news_closed_loop_service import get_news_closed_loop_service
        closed_loop = await get_news_closed_loop_service()
        metrics = await closed_loop.get_metrics(current_user["id"])
        return ok(data=metrics.to_dict())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/observation-tasks")
async def list_news_observation_tasks(
    status: Optional[str] = Query(None, description="待观察/已确认/已失效/已复盘"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    """列出新闻来源的观察任务及其状态"""
    try:
        from app.services.personal_investment.observation_service import observation_service
        result = await observation_service.list_observations(
            user_id=current_user["id"],
            status=status,
            source_type="news",
            skip=skip,
            limit=limit,
        )
        return ok(data=result)
    except Exception as e:
        logger.error(f"List news observation tasks failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/review")
async def trigger_observation_review(
    request: ObservationReviewRequest,
    current_user: dict = Depends(get_current_user),
):
    """按窗口触发新闻观察复盘"""
    try:
        from app.services.news_closed_loop_service import get_news_closed_loop_service
        closed_loop = await get_news_closed_loop_service()
        result = await closed_loop.trigger_review(
            observation_id=request.observation_id,
            user_id=current_user["id"],
            window_days=request.window_days,
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return ok(data=result, message="复盘完成")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Trigger review failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ignore")
async def ignore_news(
    request: IgnoreNewsRequest,
    current_user: dict = Depends(get_current_user),
):
    """记录用户忽略的新闻"""
    try:
        service = await get_news_watch_service()
        result = await service.ignore_item(
            user_id=current_user["id"],
            symbol=request.symbol,
            news_id=request.news_id,
            title=request.title,
        )
        return ok(data=result, message="已忽略")
    except Exception as e:
        logger.error(f"Ignore news failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
