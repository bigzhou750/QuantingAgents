"""
基于数据库的认证路由 - 改进版
替代原有的基于配置文件的认证机制
"""

import time
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query, Request
from pydantic import BaseModel, Field

from app.services.auth_service import AuthService
from app.core.config import settings
from app.services.user_service import user_service
from app.models.user import UserCreate, UserUpdate
from app.services.operation_log_service import log_operation
from app.models.operation_log import ActionType
from app.core.auth_guard import AuthAttemptGuard, client_identity

# 尝试导入日志管理器
try:
    from tradingagents.utils.logging_manager import get_logger
except ImportError:
    # 如果导入失败，使用标准日志
    import logging
    def get_logger(name: str) -> logging.Logger:
        return logging.getLogger(name)

logger = get_logger('auth_db')

# 统一响应格式
class ApiResponse(BaseModel):
    success: bool = True
    data: dict = {}
    message: str = ""

router = APIRouter()
_login_guard = AuthAttemptGuard(settings.AUTH_LOGIN_RATE_LIMIT)
_register_guard = AuthAttemptGuard(settings.AUTH_REGISTER_RATE_LIMIT)

@router.get("/registration-status")
async def registration_status():
    """公开查询当前是否开放注册。"""
    return ApiResponse(
        success=True,
        data={"enabled": settings.AUTH_REGISTRATION_ENABLED},
        message="ok",
    )

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class RefreshTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

class ResetPasswordRequest(BaseModel):
    username: str
    new_password: str

class CreateUserRequest(BaseModel):
    username: str
    email: str
    password: str
    is_admin: bool = False

class AdminRoleRequest(BaseModel):
    is_admin: bool

class AdminStatusRequest(BaseModel):
    is_active: bool

class AdminUpdateUserRequest(BaseModel):
    email: Optional[str] = Field(default=None, pattern=r'^[^@]+@[^@]+\.[^@]+$')
    daily_quota: Optional[int] = Field(default=None, ge=0)
    concurrent_limit: Optional[int] = Field(default=None, ge=1)

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    confirm_password: Optional[str] = None
    agreement: bool = True

async def get_current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    """获取当前用户信息"""
    logger.debug(f"🔐 认证检查开始")

    if not authorization:
        from app.core.isolation_metrics import record_auth_failure
        record_auth_failure("missing_authorization")
        logger.warning("❌ 没有Authorization header")
        raise HTTPException(status_code=401, detail="No authorization header")

    if not authorization.lower().startswith("bearer "):
        from app.core.isolation_metrics import record_auth_failure
        record_auth_failure("invalid_authorization_format")
        logger.warning(f"❌ Authorization header格式错误: {authorization[:20]}...")
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    token = authorization.split(" ", 1)[1]

    token_data = AuthService.verify_token(token)
    logger.debug(f"🔍 Token验证结果: {token_data is not None}")

    if not token_data:
        from app.core.isolation_metrics import record_auth_failure
        record_auth_failure("invalid_token")
        logger.warning("❌ Token验证失败")
        raise HTTPException(status_code=401, detail="Invalid token")
    if token_data.token_type != "access":
        from app.core.isolation_metrics import record_auth_failure
        record_auth_failure("wrong_token_type")
        raise HTTPException(status_code=401, detail="Invalid access token")

    # 从数据库获取用户信息
    user = await user_service.get_user_by_id(token_data.user_id or token_data.sub)
    if not user:
        # Legacy tokens used username as sub during the compatibility window.
        user = await user_service.get_user_by_username(token_data.sub)
    if not user:
        logger.warning(f"❌ 用户不存在: {token_data.sub}")
        raise HTTPException(status_code=401, detail="User not found")

    if not user.is_active:
        logger.warning(f"❌ 用户已禁用: {token_data.sub}")
        raise HTTPException(status_code=401, detail="User is inactive")
    if getattr(user, "is_archived", False):
        logger.warning(f"❌ 用户已归档: {token_data.sub}")
        raise HTTPException(status_code=401, detail="User is inactive")
    if token_data.token_version != getattr(user, "token_version", 0):
        raise HTTPException(status_code=401, detail="Token has been revoked")

    logger.debug(f"✅ 认证成功，用户: {token_data.sub}")

    # 返回完整的用户信息，包括偏好设置
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "name": user.username,
        "is_admin": user.is_admin,
        "roles": ["admin"] if user.is_admin else ["user"],
        "preferences": user.preferences.model_dump() if user.preferences else {}
    }


async def get_current_admin(user: dict = Depends(get_current_user)) -> dict:
    """Authenticated dependency for admin-only operational surfaces."""
    if not user.get("is_admin", False):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user

@router.post("/login")
async def login(payload: LoginRequest, request: Request):
    """用户登录"""
    start_time = time.time()

    # 获取客户端信息
    ip_address = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    if not _login_guard.allow(f"ip:{ip_address}", f"account:{payload.username.strip().lower()}"):
        raise HTTPException(status_code=429, detail="登录尝试过于频繁，请稍后重试")

    logger.info(f"🔐 登录请求 - 用户名: {payload.username}, IP: {ip_address}")

    try:
        # 验证输入
        if not payload.username or not payload.password:
            logger.warning(f"❌ 登录失败 - 用户名或密码为空")
            await log_operation(
                user_id="unknown",
                username=payload.username or "unknown",
                action_type=ActionType.USER_LOGIN,
                action="用户登录",
                details={"reason": "用户名和密码不能为空"},
                success=False,
                error_message="用户名和密码不能为空",
                duration_ms=int((time.time() - start_time) * 1000),
                ip_address=ip_address,
                user_agent=user_agent
            )
            raise HTTPException(status_code=400, detail="用户名和密码不能为空")

        logger.info(f"🔍 开始认证用户: {payload.username}")

        # 使用数据库认证
        user = await user_service.authenticate_user(payload.username, payload.password)

        logger.info(f"🔍 认证结果: user={'存在' if user else '不存在'}")

        if not user:
            logger.warning(f"❌ 登录失败 - 用户名或密码错误: {payload.username}")
            await log_operation(
                user_id="unknown",
                username=payload.username,
                action_type=ActionType.USER_LOGIN,
                action="用户登录",
                details={"reason": "用户名或密码错误"},
                success=False,
                error_message="用户名或密码错误",
                duration_ms=int((time.time() - start_time) * 1000),
                ip_address=ip_address,
                user_agent=user_agent
            )
            raise HTTPException(status_code=401, detail="用户名或密码错误")

        # 生成 token
        token = AuthService.create_access_token(sub=user.username, user_id=str(user.id), token_version=user.token_version)
        refresh_jti = uuid.uuid4().hex
        refresh_token = AuthService.create_access_token(
            sub=user.username,
            user_id=str(user.id),
            token_type="refresh",
            token_version=user.token_version,
            expires_delta=60*60*24*7,
            jti=refresh_jti,
        )
        if not await user_service.create_refresh_session(
            user_id=str(user.id), jti=refresh_jti,
            expires_at=datetime.utcnow() + timedelta(days=7),
            metadata={"ip_address": ip_address, "user_agent": user_agent},
        ):
            raise HTTPException(status_code=503, detail="认证服务暂时不可用")

        # 记录登录成功日志
        await log_operation(
            user_id=str(user.id),
            username=user.username,
            action_type=ActionType.USER_LOGIN,
            action="用户登录",
            details={"login_method": "password"},
            success=True,
            duration_ms=int((time.time() - start_time) * 1000),
            ip_address=ip_address,
            user_agent=user_agent
        )

        return {
            "success": True,
            "data": {
                "access_token": token,
                "refresh_token": refresh_token,
                "expires_in": 60 * 60,
                "user": {
                    "id": str(user.id),
                    "username": user.username,
                    "email": user.email,
                    "name": user.username,
                    "is_admin": user.is_admin
                }
            },
        "message": "登录成功"
    }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 登录异常: {e}")
        await log_operation(
            user_id="unknown",
            username=payload.username or "unknown",
            action_type=ActionType.USER_LOGIN,
            action="用户登录",
            details={"error": str(e)},
            success=False,
            error_message=f"系统错误: {str(e)}",
            duration_ms=int((time.time() - start_time) * 1000),
            ip_address=ip_address,
            user_agent=user_agent
        )
        raise HTTPException(status_code=500, detail="登录过程中发生系统错误")

@router.post("/register")
async def register(payload: RegisterRequest, request: Request):
    """公开注册普通用户。注册不会自动登录或授予管理员权限。"""
    if not settings.AUTH_REGISTRATION_ENABLED:
        raise HTTPException(status_code=403, detail="注册功能已关闭")
    ip_address = client_identity(request)
    if not _register_guard.allow(f"ip:{ip_address}"):
        raise HTTPException(status_code=429, detail="注册请求过于频繁，请稍后重试")
    if not payload.agreement:
        raise HTTPException(status_code=400, detail="请先同意用户协议")
    if payload.confirm_password is not None and payload.password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="两次输入的密码不一致")
    password_error = user_service.validate_password(payload.password)
    if password_error:
        raise HTTPException(status_code=422, detail=password_error)

    new_user = await user_service.create_user(UserCreate(
        username=payload.username.strip(),
        email=payload.email.strip().lower(),
        password=payload.password,
    ))
    if not new_user:
        raise HTTPException(status_code=409, detail="用户名或邮箱已存在")
    return {
        "success": True,
        "data": {"id": str(new_user.id), "username": new_user.username, "email": new_user.email},
        "message": "注册成功，请登录",
    }

@router.post("/refresh")
async def refresh_token(payload: RefreshTokenRequest):
    """刷新访问令牌"""
    try:
        logger.debug(f"🔄 收到refresh token请求")
        logger.debug(f"📝 Refresh token长度: {len(payload.refresh_token) if payload.refresh_token else 0}")

        if not payload.refresh_token:
            logger.warning("❌ Refresh token为空")
            raise HTTPException(status_code=401, detail="Refresh token is required")

        # 验证refresh token
        token_data = AuthService.verify_token(payload.refresh_token)
        logger.debug(f"🔍 Token验证结果: {token_data is not None}")

        if not token_data:
            logger.warning("❌ Refresh token验证失败")
            raise HTTPException(status_code=401, detail="Invalid refresh token")

        # 验证用户是否仍然存在且激活
        if token_data.token_type != "refresh":
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        user = await user_service.get_user_by_id(token_data.user_id or token_data.sub)
        if not user:
            user = await user_service.get_user_by_username(token_data.sub)
        if not user or not user.is_active or getattr(user, "is_archived", False):
            logger.warning(f"❌ 用户不存在或已禁用: {token_data.sub}")
            raise HTTPException(status_code=401, detail="User not found or inactive")
        if token_data.token_version != getattr(user, "token_version", 0):
            raise HTTPException(status_code=401, detail="Refresh token has been revoked")

        logger.debug(f"✅ Token验证成功，用户: {token_data.sub}")

        new_jti = uuid.uuid4().hex
        if not token_data.jti or not await user_service.rotate_refresh_session(
            user_id=str(user.id), old_jti=token_data.jti, new_jti=new_jti,
            expires_at=datetime.utcnow() + timedelta(days=7),
        ):
            raise HTTPException(status_code=401, detail="Refresh token已失效")

        # 生成新的tokens
        new_token = AuthService.create_access_token(sub=user.username, user_id=str(user.id), token_version=user.token_version)
        new_refresh_token = AuthService.create_access_token(
            sub=user.username,
            user_id=str(user.id),
            token_type="refresh",
            token_version=user.token_version,
            expires_delta=60*60*24*7,
            jti=new_jti,
        )

        logger.debug(f"🎉 新token生成成功")

        return {
            "success": True,
            "data": {
                "access_token": new_token,
                "refresh_token": new_refresh_token,
                "expires_in": 60 * 60
            },
            "message": "Token刷新成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Refresh token处理异常: {str(e)}")
        raise HTTPException(status_code=401, detail=f"Token refresh failed: {str(e)}")

@router.post("/logout")
async def logout(request: Request, user: dict = Depends(get_current_user)):
    """用户登出"""
    start_time = time.time()

    # 获取客户端信息
    ip_address = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    try:
        if settings.AUTH_TOKEN_REVOCATION_ENABLED:
            await user_service.revoke_tokens(user["username"])
        # 记录登出日志
        await log_operation(
            user_id=user["id"],
            username=user["username"],
            action_type=ActionType.USER_LOGOUT,
            action="用户登出",
            details={"logout_method": "manual"},
            success=True,
            duration_ms=int((time.time() - start_time) * 1000),
            ip_address=ip_address,
            user_agent=user_agent
        )

        return {
            "success": True,
            "data": {},
            "message": "登出成功"
        }
    except Exception as e:
        logger.error(f"记录登出日志失败: {e}")
        return {
            "success": True,
            "data": {},
            "message": "登出成功"
        }

@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    """获取当前用户信息"""
    return {
        "success": True,
        "data": user,
        "message": "获取用户信息成功"
    }

@router.put("/me")
async def update_me(
    payload: dict,
    user: dict = Depends(get_current_user)
):
    """更新当前用户信息"""
    try:
        from app.models.user import UserUpdate, UserPreferences

        # 构建更新数据
        update_data = {}

        # 更新邮箱
        if "email" in payload:
            update_data["email"] = payload["email"]

        # 更新偏好设置（支持部分更新）
        if "preferences" in payload:
            # 获取当前偏好
            current_prefs = user.get("preferences", {})

            # 合并新的偏好设置
            merged_prefs = {**current_prefs, **payload["preferences"]}

            # 创建 UserPreferences 对象
            update_data["preferences"] = UserPreferences(**merged_prefs)

        # 如果有语言设置，更新到偏好中
        if "language" in payload:
            if "preferences" not in update_data:
                # 获取当前偏好
                current_prefs = user.get("preferences", {})
                update_data["preferences"] = UserPreferences(**current_prefs)
            update_data["preferences"].language = payload["language"]

        # 如果有时区设置，更新到偏好中（如果需要）
        # 注意：时区通常是系统级设置，不是用户级设置

        # 调用服务更新用户
        user_update = UserUpdate(**update_data)
        updated_user = await user_service.update_user(user["username"], user_update)

        if not updated_user:
            raise HTTPException(status_code=400, detail="更新失败，邮箱可能已被使用")

        # 返回更新后的用户信息
        return {
            "success": True,
            "data": updated_user.model_dump(by_alias=True),
            "message": "用户信息更新成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新用户信息失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新用户信息失败: {str(e)}")

@router.post("/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    user: dict = Depends(get_current_user)
):
    """修改密码"""
    try:
        # 使用数据库服务修改密码
        success = await user_service.change_password(
            user["username"], 
            payload.old_password, 
            payload.new_password
        )
        
        if not success:
            raise HTTPException(status_code=400, detail="旧密码错误")

        return {
            "success": True,
            "data": {},
            "message": "密码修改成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"修改密码失败: {e}")
        raise HTTPException(status_code=500, detail=f"修改密码失败: {str(e)}")

@router.post("/reset-password")
async def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    user: dict = Depends(get_current_admin)
):
    """重置密码（管理员操作）"""
    try:
        target = await user_service.get_user_admin_detail(payload.username)
        if not target:
            raise HTTPException(status_code=404, detail="用户不存在")
        if target.is_archived:
            raise HTTPException(status_code=400, detail="归档账号不能重置密码")
        success = await user_service.reset_password(payload.username, payload.new_password)
        if not success:
            raise HTTPException(status_code=400, detail="新密码不符合密码策略")
        await log_operation(
            user_id=user["id"],
            username=user["username"],
            action_type=ActionType.USER_MANAGEMENT,
            action="管理员重置密码",
            details={"target_username": payload.username},
            success=True,
        )

        return {
            "success": True,
            "data": {},
            "message": f"用户 {payload.username} 的密码已重置"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重置密码失败: {e}")
        raise HTTPException(status_code=500, detail=f"重置密码失败: {str(e)}")

@router.post("/create-user")
async def create_user(
    payload: CreateUserRequest,
    request: Request,
    user: dict = Depends(get_current_admin)
):
    """创建用户（管理员操作）"""
    try:
        user_create = UserCreate(
            username=payload.username,
            email=payload.email,
            password=payload.password
        )
        
        new_user = await user_service.create_user(user_create)
        
        if not new_user:
            raise HTTPException(status_code=400, detail="用户名或邮箱已存在")

        # 如果需要设置为管理员
        if payload.is_admin:
            await user_service.set_admin_role(payload.username, True)

        await log_operation(
            user_id=user["id"],
            username=user["username"],
            action_type=ActionType.USER_MANAGEMENT,
            action="管理员创建用户",
            details={"target_username": payload.username, "is_admin": payload.is_admin},
            success=True,
        )

        return {
            "success": True,
            "data": {
                "id": str(new_user.id),
                "username": new_user.username,
                "email": new_user.email,
                "is_admin": payload.is_admin
            },
            "message": f"用户 {payload.username} 创建成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建用户失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建用户失败: {str(e)}")

@router.get("/users")
async def list_users(
    keyword: Optional[str] = Query(default=None, max_length=100),
    status: Optional[str] = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=200),
    user: dict = Depends(get_current_admin)
):
    """获取用户列表（管理员操作）"""
    try:
        if status and status not in {"active", "disabled", "archived"}:
            raise HTTPException(status_code=400, detail="无效的账号状态")
        result = await user_service.list_users(
            keyword=keyword,
            status=status,
            skip=skip,
            limit=limit,
        )
        
        return {
            "success": True,
            "data": {
                "users": [item.model_dump() for item in result.users],
                "total": result.total,
                "skip": skip,
                "limit": limit
            },
            "message": "获取用户列表成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取用户列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取用户列表失败: {str(e)}")

@router.get("/users/{username}")
async def get_user_detail(
    username: str,
    user: dict = Depends(get_current_admin)
):
    """获取单个账号的管理员详情。"""
    detail = await user_service.get_user_admin_detail(username)
    if not detail:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {
        "success": True,
        "data": detail.model_dump(),
        "message": "获取用户详情成功"
    }

@router.patch("/users/{username}")
async def update_user_detail(
    username: str,
    payload: AdminUpdateUserRequest,
    user: dict = Depends(get_current_admin)
):
    """管理员更新账号邮箱、每日配额和并发限制。"""
    if all(value is None for value in (payload.email, payload.daily_quota, payload.concurrent_limit)):
        raise HTTPException(status_code=400, detail="至少提供一个更新字段")
    target = await user_service.get_user_admin_detail(username)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    if target.is_archived:
        raise HTTPException(status_code=400, detail="归档账号不能更新")
    update_data = UserUpdate(
        email=payload.email,
        daily_quota=payload.daily_quota,
        concurrent_limit=payload.concurrent_limit,
    )
    updated = await user_service.update_user_admin(username, update_data)
    if not updated:
        raise HTTPException(status_code=400, detail="更新失败，邮箱可能已被使用")
    await log_operation(
        user_id=user["id"],
        username=user["username"],
        action_type=ActionType.USER_MANAGEMENT,
        action="管理员更新账号资料",
        details={"target_username": username},
        success=True,
    )
    return {
        "success": True,
        "data": updated.model_dump(),
        "message": "账号资料已更新"
    }

@router.delete("/users/{username}")
async def archive_user(
    username: str,
    user: dict = Depends(get_current_admin)
):
    """安全归档账号，保留历史资源归属。"""
    if username == user["username"]:
        raise HTTPException(status_code=400, detail="不能归档当前登录管理员")
    target = await user_service.get_user_admin_detail(username)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    if target.is_archived:
        raise HTTPException(status_code=400, detail="账号已归档")
    ok = await user_service.archive_user(username)
    if not ok:
        raise HTTPException(status_code=500, detail="归档账号失败")
    await log_operation(
        user_id=user["id"],
        username=user["username"],
        action_type=ActionType.USER_MANAGEMENT,
        action="管理员归档账号",
        details={"target_username": username},
        success=True,
    )
    return {
        "success": True,
        "data": {"username": username, "is_active": False, "is_archived": True},
        "message": f"用户 {username} 已归档"
    }

@router.patch("/users/{username}/status")
async def update_user_status(
    username: str,
    payload: AdminStatusRequest,
    user: dict = Depends(get_current_admin)
):
    if username == user["username"] and not payload.is_active:
        raise HTTPException(status_code=400, detail="不能禁用当前登录管理员")
    target = await user_service.get_user_admin_detail(username)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    if target.is_archived:
        raise HTTPException(status_code=400, detail="归档账号不能修改状态")
    ok = await (user_service.activate_user(username) if payload.is_active else user_service.deactivate_user(username))
    if not ok:
        raise HTTPException(status_code=404, detail="用户不存在")
    await log_operation(user_id=user["id"], username=user["username"], action_type=ActionType.USER_MANAGEMENT, action="管理员更新账号状态", details={"target_username": username, "is_active": payload.is_active}, success=True)
    return {"success": True, "data": {"username": username, "is_active": payload.is_active}, "message": "账号状态已更新"}

@router.patch("/users/{username}/role")
async def update_user_role(
    username: str,
    payload: AdminRoleRequest,
    user: dict = Depends(get_current_admin)
):
    if username == user["username"] and not payload.is_admin:
        # 防止最后一个管理员误操作导致管理面不可恢复。
        raise HTTPException(status_code=400, detail="不能移除当前管理员自身角色")
    target = await user_service.get_user_admin_detail(username)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    if target.is_archived:
        raise HTTPException(status_code=400, detail="归档账号不能修改角色")
    ok = await user_service.set_admin_role(username, payload.is_admin)
    if not ok:
        raise HTTPException(status_code=404, detail="用户不存在或角色未变化")
    await log_operation(user_id=user["id"], username=user["username"], action_type=ActionType.USER_MANAGEMENT, action="管理员更新账号角色", details={"target_username": username, "is_admin": payload.is_admin}, success=True)
    return {"success": True, "data": {"username": username, "is_admin": payload.is_admin}, "message": "账号角色已更新"}
