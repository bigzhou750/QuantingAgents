from fastapi import APIRouter
from fastapi import Depends, HTTPException
import time
from pathlib import Path

from app.routers.auth_db import get_current_user

router = APIRouter()


def get_version() -> str:
    """从 VERSION 文件读取版本号"""
    try:
        version_file = Path(__file__).parent.parent.parent / "VERSION"
        if version_file.exists():
            return version_file.read_text(encoding='utf-8').strip()
    except Exception:
        pass
    return "0.1.16"  # 默认版本号


@router.get("/health")
async def health():
    """健康检查接口 - 前端使用"""
    return {
        "success": True,
        "data": {
            "status": "ok",
            "version": get_version(),
            "timestamp": int(time.time()),
            "service": "zhitouagent API"
        },
        "message": "服务运行正常"
    }

@router.get("/healthz")
async def healthz():
    """Kubernetes健康检查"""
    return {"status": "ok"}

@router.get("/readyz")
async def readyz():
    """Kubernetes就绪检查"""
    return {"ready": True}


@router.get("/isolation/metrics")
async def isolation_metrics(user: dict = Depends(get_current_user)):
    """运行时隔离审计指标；仅管理员可查看。"""
    if not user.get("is_admin", False):
        raise HTTPException(status_code=403, detail="管理员权限不足")
    from app.core.isolation_metrics import snapshot
    return {"success": True, "data": snapshot(), "message": "隔离指标"}
