"""
数据就绪状态 API

提供数据可用性报告的查询和手动刷新接口。
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.routers.auth_db import get_current_user
from app.services.data_readiness_service import get_data_readiness_service


class ApiResponse(BaseModel):
    success: bool = True
    data: dict = {}
    message: str = ""

router = APIRouter(tags=["data-readiness"])


@router.get("/data-readiness", summary="获取数据就绪报告")
async def get_data_readiness(current_user=Depends(get_current_user)):
    """获取当前各类数据的就绪状态"""
    service = await get_data_readiness_service()
    report = await service.get_report()
    return ApiResponse(success=True, data=report.to_dict())


@router.post("/data-readiness/refresh", summary="手动刷新数据就绪状态")
async def refresh_data_readiness(current_user=Depends(get_current_user)):
    """手动触发一次数据就绪检查（需要登录）"""
    service = await get_data_readiness_service()
    report = await service.refresh()
    return ApiResponse(success=True, data=report.to_dict(), message="数据就绪状态已刷新")
