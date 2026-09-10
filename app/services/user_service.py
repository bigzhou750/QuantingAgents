"""
用户服务 - 基于数据库的用户管理
"""

import hashlib
import re
import bcrypt
from datetime import datetime
from typing import Optional, Dict, Any
from pymongo import MongoClient, ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError
from bson import ObjectId

from app.core.config import settings
from app.models.user import (
    User,
    UserCreate,
    UserUpdate,
    UserResponse,
    UserAdminResponse,
    UserListResult,
)

# 尝试导入日志管理器
try:
    from tradingagents.utils.logging_manager import get_logger
except ImportError:
    # 如果导入失败，使用标准日志
    import logging
    def get_logger(name: str) -> logging.Logger:
        return logging.getLogger(name)

logger = get_logger('user_service')


class UserService:
    """用户服务类"""

    def __init__(self):
        self.client = MongoClient(settings.MONGO_URI)
        self.db = self.client[settings.MONGO_DB]
        self.users_collection = self.db.users
        try:
            self.users_collection.create_index([("username", ASCENDING)], unique=True)
            self.users_collection.create_index([("email", ASCENDING)], unique=True)
            self.db.refresh_sessions.create_index([("jti", ASCENDING)], unique=True)
            self.db.refresh_sessions.create_index([("user_id", ASCENDING), ("revoked", ASCENDING)])
        except Exception as exc:
            logger.warning("无法创建用户唯一索引: %s", exc)

    def close(self):
        """关闭数据库连接"""
        if hasattr(self, 'client') and self.client:
            self.client.close()
            logger.info("✅ UserService MongoDB 连接已关闭")

    def __del__(self):
        """析构函数，确保连接被关闭"""
        self.close()
    
    @staticmethod
    def hash_password(password: str) -> str:
        """密码哈希（bcrypt, rounds=12）"""
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """验证密码（兼容 bcrypt 和旧 SHA-256）"""
        if hashed_password.startswith("$2b$") or hashed_password.startswith("$2a$"):
            # bcrypt 格式
            return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())
        # 旧 SHA-256 格式（兼容）
        return hashlib.sha256(plain_password.encode()).hexdigest() == hashed_password
    
    async def create_user(self, user_data: UserCreate) -> Optional[User]:
        """创建用户"""
        try:
            if self.validate_password(user_data.password):
                logger.warning("用户注册被拒绝: 密码不符合策略")
                return None
            # 检查用户名是否已存在
            existing_user = self.users_collection.find_one({"username": user_data.username})
            if existing_user:
                logger.warning(f"用户名已存在: {user_data.username}")
                return None
            
            # 检查邮箱是否已存在
            existing_email = self.users_collection.find_one({"email": user_data.email})
            if existing_email:
                logger.warning(f"邮箱已存在: {user_data.email}")
                return None
            
            # 创建用户文档
            user_doc = {
                "username": user_data.username,
                "email": user_data.email,
                "hashed_password": self.hash_password(user_data.password),
                "is_active": True,
                "is_verified": False,
                "is_admin": False,
                "is_archived": False,
                "token_version": 0,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "last_login": None,
                "preferences": {
                    # 分析偏好
                    "default_market": "A股",
                    "default_depth": "3",  # 1-5级，3级为标准分析（推荐）
                    "default_analysts": ["市场分析师", "基本面分析师"],
                    "auto_refresh": True,
                    "refresh_interval": 30,
                    # 外观设置
                    "ui_theme": "light",
                    "sidebar_width": 240,
                    # 语言和地区
                    "language": "zh-CN",
                    # 通知设置
                    "notifications_enabled": True,
                    "email_notifications": False,
                    "desktop_notifications": True,
                    "analysis_complete_notification": True,
                    "system_maintenance_notification": True
                },
                "daily_quota": 1000,
                "concurrent_limit": 3,
                "total_analyses": 0,
                "successful_analyses": 0,
                "failed_analyses": 0,
                "favorite_stocks": []
            }
            
            result = self.users_collection.insert_one(user_doc)
            user_doc["_id"] = result.inserted_id
            
            logger.info(f"✅ 用户创建成功: {user_data.username}")
            return User(**user_doc)
            
        except DuplicateKeyError:
            logger.warning("用户注册被拒绝: 用户名或邮箱已存在")
            return None
        except Exception as e:
            logger.error(f"❌ 创建用户失败: {e}")
            return None

    @staticmethod
    def validate_password(password: str) -> Optional[str]:
        """Return a validation message, or None when the password is valid."""
        if len(password) < settings.AUTH_PASSWORD_MIN_LENGTH:
            return f"密码长度不能少于 {settings.AUTH_PASSWORD_MIN_LENGTH} 位"
        if len(password) > 128:
            return "密码长度不能超过 128 位"
        if not any(char.isalpha() for char in password):
            return "密码必须包含字母"
        if not any(char.isdigit() for char in password):
            return "密码必须包含数字"
        return None
    
    async def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """用户认证"""
        try:
            logger.info(f"🔍 [authenticate_user] 开始认证用户: {username}")

            # 查找用户
            user_doc = self.users_collection.find_one({"username": username})
            logger.info(f"🔍 [authenticate_user] 数据库查询结果: {'找到用户' if user_doc else '用户不存在'}")

            if not user_doc:
                logger.warning(f"❌ [authenticate_user] 用户不存在: {username}")
                return None

            logger.info(f"🔍 [authenticate_user] 用户信息: username={user_doc.get('username')}, email={user_doc.get('email')}, is_active={user_doc.get('is_active')}")

            # 验证密码
            stored_password_hash = user_doc["hashed_password"]

            if not self.verify_password(password, user_doc["hashed_password"]):
                logger.warning(f"❌ [authenticate_user] 密码错误: {username}")
                return None

            # 如果是旧 SHA-256 格式，自动升级为 bcrypt
            stored_hash = user_doc["hashed_password"]
            if not (stored_hash.startswith("$2b$") or stored_hash.startswith("$2a$")):
                new_hash = self.hash_password(password)
                self.users_collection.update_one(
                    {"_id": user_doc["_id"]},
                    {"$set": {"hashed_password": new_hash, "password_hash_algo": "bcrypt"}}
                )
                user_doc["hashed_password"] = new_hash
                logger.info(f"🔄 [authenticate_user] SHA-256 密码已自动升级为 bcrypt: {username}")

            # 检查用户是否激活
            if not user_doc.get("is_active", True):
                logger.warning(f"❌ [authenticate_user] 用户已禁用: {username}")
                return None
            if user_doc.get("is_archived", False):
                logger.warning(f"❌ [authenticate_user] 用户已归档: {username}")
                return None

            # 更新最后登录时间
            self.users_collection.update_one(
                {"_id": user_doc["_id"]},
                {"$set": {"last_login": datetime.utcnow()}}
            )

            logger.info(f"✅ [authenticate_user] 用户认证成功: {username}")
            return User(**user_doc)
            
        except Exception as e:
            logger.error(f"❌ 用户认证失败: {e}")
            return None
    
    async def get_user_by_username(self, username: str) -> Optional[User]:
        """根据用户名获取用户"""
        try:
            user_doc = self.users_collection.find_one({"username": username})
            if user_doc:
                return User(**user_doc)
            return None
        except Exception as e:
            logger.error(f"❌ 获取用户失败: {e}")
            return None
    
    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """根据用户ID获取用户"""
        try:
            if not ObjectId.is_valid(user_id):
                return None
            
            user_doc = self.users_collection.find_one({"_id": ObjectId(user_id)})
            if user_doc:
                return User(**user_doc)
            return None
        except Exception as e:
            logger.error(f"❌ 获取用户失败: {e}")
            return None
    
    async def update_user(self, username: str, user_data: UserUpdate) -> Optional[User]:
        """更新用户信息"""
        try:
            update_data = {"updated_at": datetime.utcnow()}
            
            # 只更新提供的字段
            if user_data.email:
                # 检查邮箱是否已被其他用户使用
                existing_email = self.users_collection.find_one({
                    "email": user_data.email,
                    "username": {"$ne": username}
                })
                if existing_email:
                    logger.warning(f"邮箱已被使用: {user_data.email}")
                    return None
                update_data["email"] = user_data.email
            
            if user_data.preferences:
                update_data["preferences"] = user_data.preferences.model_dump()
            
            if user_data.daily_quota is not None:
                update_data["daily_quota"] = user_data.daily_quota
            
            if user_data.concurrent_limit is not None:
                update_data["concurrent_limit"] = user_data.concurrent_limit
            
            result = self.users_collection.update_one(
                {"username": username},
                {"$set": update_data}
            )
            
            if result.modified_count > 0:
                logger.info(f"✅ 用户信息更新成功: {username}")
                return await self.get_user_by_username(username)
            else:
                logger.warning(f"用户不存在或无需更新: {username}")
                return None
                
        except Exception as e:
            logger.error(f"❌ 更新用户信息失败: {e}")
            return None
    
    async def change_password(self, username: str, old_password: str, new_password: str) -> bool:
        """修改密码"""
        try:
            if self.validate_password(new_password):
                return False
            # 验证旧密码
            user = await self.authenticate_user(username, old_password)
            if not user:
                logger.warning(f"旧密码验证失败: {username}")
                return False
            
            # 更新密码
            new_hashed_password = self.hash_password(new_password)
            result = self.users_collection.update_one(
                {"username": username},
                {
                    "$set": {
                        "hashed_password": new_hashed_password,
                        "updated_at": datetime.utcnow()
                    },
                    "$inc": {"token_version": 1}
                }
            )
            
            if result.modified_count > 0:
                logger.info(f"✅ 密码修改成功: {username}")
                return True
            else:
                logger.error(f"❌ 密码修改失败: {username}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 修改密码失败: {e}")
            return False
    
    async def reset_password(self, username: str, new_password: str) -> bool:
        """重置密码（管理员操作）"""
        try:
            if self.validate_password(new_password):
                return False
            new_hashed_password = self.hash_password(new_password)
            result = self.users_collection.update_one(
                {"username": username},
                {
                    "$set": {
                        "hashed_password": new_hashed_password,
                        "updated_at": datetime.utcnow()
                    },
                    "$inc": {"token_version": 1}
                }
            )
            
            if result.modified_count > 0:
                logger.info(f"✅ 密码重置成功: {username}")
                return True
            else:
                logger.error(f"❌ 密码重置失败: {username}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 重置密码失败: {e}")
            return False

    async def revoke_tokens(self, username: str) -> bool:
        """Invalidate all tokens issued for a user."""
        try:
            result = self.users_collection.update_one(
                {"username": username},
                {"$inc": {"token_version": 1}, "$set": {"updated_at": datetime.utcnow()}},
            )
            user = self.users_collection.find_one({"username": username}, {"_id": 1})
            if user:
                self.db.refresh_sessions.update_many({"user_id": str(user["_id"])}, {"$set": {"revoked": True}})
            return result.matched_count == 1
        except Exception as exc:
            logger.error("❌ 撤销用户 Token 失败: %s", exc)
            return False

    async def create_refresh_session(self, *, user_id: str, jti: str, expires_at: datetime, metadata: Optional[dict] = None) -> bool:
        try:
            self.db.refresh_sessions.insert_one({
                "user_id": user_id, "jti": jti, "expires_at": expires_at,
                "revoked": False, **(metadata or {})
            })
            return True
        except Exception as exc:
            logger.error("创建刷新会话失败: %s", type(exc).__name__)
            return False

    async def rotate_refresh_session(self, *, user_id: str, old_jti: str, new_jti: str, expires_at: datetime) -> bool:
        """Atomically consume one refresh token; replayed tokens cannot rotate."""
        try:
            consumed = self.db.refresh_sessions.find_one_and_update(
                {"user_id": user_id, "jti": old_jti, "revoked": False, "expires_at": {"$gt": datetime.utcnow()}},
                {"$set": {"revoked": True, "replaced_by": new_jti, "rotated_at": datetime.utcnow()}},
                return_document=ReturnDocument.AFTER,
            )
            if not consumed:
                return False
            self.db.refresh_sessions.insert_one({
                "user_id": user_id, "jti": new_jti, "expires_at": expires_at,
                "revoked": False, "parent_jti": old_jti
            })
            return True
        except Exception as exc:
            logger.error("轮换刷新会话失败: %s", type(exc).__name__)
            return False
    
    async def create_admin_user(self, username: str = "admin", password: str = "", email: str = "zh75067197@gmail.com") -> Optional[User]:
        """创建管理员用户"""
        try:
            password_error = self.validate_password(password)
            if password_error:
                logger.warning("管理员创建被拒绝：初始密码不符合策略")
                return None

            # 检查是否已存在管理员
            existing_admin = self.users_collection.find_one({"username": username})
            if existing_admin:
                logger.info(f"管理员用户已存在: {username}")
                return User(**existing_admin)
            
            # 创建管理员用户文档
            admin_doc = {
                "username": username,
                "email": email,
                "hashed_password": self.hash_password(password),
                "is_active": True,
                "is_verified": True,
                "is_admin": True,
                "is_archived": False,
                "token_version": 0,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "last_login": None,
                "preferences": {
                    "default_market": "A股",
                    "default_depth": "深度",
                    "ui_theme": "light",
                    "language": "zh-CN",
                    "notifications_enabled": True,
                    "email_notifications": False
                },
                "daily_quota": 10000,  # 管理员更高配额
                "concurrent_limit": 10,
                "total_analyses": 0,
                "successful_analyses": 0,
                "failed_analyses": 0,
                "favorite_stocks": []
            }
            
            result = self.users_collection.insert_one(admin_doc)
            admin_doc["_id"] = result.inserted_id
            
            logger.info(f"✅ 管理员用户创建成功: {username}")
            
            return User(**admin_doc)
            
        except Exception as e:
            logger.error(f"❌ 创建管理员用户失败: {e}")
            return None
    
    async def list_users(
        self,
        keyword: Optional[str] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> UserListResult:
        """获取用户列表，返回当前页和满足条件的总数。"""
        try:
            query: Dict[str, Any] = {}
            if keyword and keyword.strip():
                pattern = re.escape(keyword.strip())
                query["$or"] = [
                    {"username": {"$regex": pattern, "$options": "i"}},
                    {"email": {"$regex": pattern, "$options": "i"}},
                ]
            if status == "active":
                query["is_active"] = True
                query["is_archived"] = False
            elif status == "disabled":
                query["is_active"] = False
                query["is_archived"] = False
            elif status == "archived":
                query["is_archived"] = True

            total = self.users_collection.count_documents(query)
            cursor = (
                self.users_collection.find(query)
                .sort([("created_at", -1), ("_id", -1)])
                .skip(skip)
                .limit(limit)
            )
            users = []

            for user_doc in cursor:
                user = User(**user_doc)
                users.append(UserResponse(
                    id=str(user.id),
                    username=user.username,
                    email=user.email,
                    is_active=user.is_active,
                    is_verified=user.is_verified,
                    is_admin=user.is_admin,
                    is_archived=user.is_archived,
                    created_at=user.created_at,
                    last_login=user.last_login,
                    preferences=user.preferences,
                    daily_quota=user.daily_quota,
                    concurrent_limit=user.concurrent_limit,
                    total_analyses=user.total_analyses,
                    successful_analyses=user.successful_analyses,
                    failed_analyses=user.failed_analyses
                ))

            return UserListResult(users=users, total=total)

        except Exception as e:
            logger.error(f"❌ 获取用户列表失败: {e}")
            return UserListResult(users=[], total=0)

    async def get_user_admin_detail(self, username: str) -> Optional[UserAdminResponse]:
        """获取单个用户的非敏感管理详情。"""
        try:
            user_doc = self.users_collection.find_one({"username": username})
            if not user_doc:
                return None
            user = User(**user_doc)
            return UserAdminResponse(
                id=str(user.id),
                username=user.username,
                email=user.email,
                is_active=user.is_active,
                is_verified=user.is_verified,
                is_admin=user.is_admin,
                is_archived=user.is_archived,
                created_at=user.created_at,
                updated_at=user.updated_at,
                last_login=user.last_login,
                preferences=user.preferences,
                daily_quota=user.daily_quota,
                concurrent_limit=user.concurrent_limit,
                total_analyses=user.total_analyses,
                successful_analyses=user.successful_analyses,
                failed_analyses=user.failed_analyses,
            )
        except Exception as e:
            logger.error(f"❌ 获取用户管理详情失败: {e}")
            return None

    async def update_user_admin(self, username: str, user_data: UserUpdate) -> Optional[UserAdminResponse]:
        """管理员更新用户资料和配额，返回非敏感管理详情。"""
        updated_user = await self.update_user(username, user_data)
        if not updated_user:
            return None
        return await self.get_user_admin_detail(username)

    async def archive_user(self, username: str) -> bool:
        """安全归档账号：禁用登录并保留用户资源归属。"""
        try:
            result = self.users_collection.update_one(
                {"username": username, "is_archived": {"$ne": True}},
                {
                    "$set": {
                        "is_active": False,
                        "is_archived": True,
                        "updated_at": datetime.utcnow(),
                    },
                    "$inc": {"token_version": 1},
                },
            )
            user = self.users_collection.find_one({"username": username}, {"_id": 1})
            if result.matched_count == 1 and user:
                self.db.refresh_sessions.update_many(
                    {"user_id": str(user["_id"])},
                    {"$set": {"revoked": True}},
                )
            return result.matched_count == 1
        except Exception as e:
            logger.error(f"❌ 归档用户失败: {e}")
            return False
    
    async def deactivate_user(self, username: str) -> bool:
        """禁用用户"""
        try:
            result = self.users_collection.update_one(
                {"username": username},
                {
                    "$set": {
                        "is_active": False,
                        "updated_at": datetime.utcnow()
                    },
                    "$inc": {"token_version": 1}
                }
            )
            
            if result.modified_count > 0:
                logger.info(f"✅ 用户已禁用: {username}")
                return True
            else:
                logger.warning(f"用户不存在: {username}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 禁用用户失败: {e}")
            return False
    
    async def activate_user(self, username: str) -> bool:
        """激活用户"""
        try:
            result = self.users_collection.update_one(
                {"username": username},
                {
                    "$set": {
                        "is_active": True,
                        "updated_at": datetime.utcnow()
                    },
                    "$inc": {"token_version": 1}
                }
            )
            
            if result.modified_count > 0:
                logger.info(f"✅ 用户已激活: {username}")
                return True
            else:
                logger.warning(f"用户不存在: {username}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 激活用户失败: {e}")
            return False

    async def set_admin_role(self, username: str, is_admin: bool) -> bool:
        """Change a user's role and revoke existing sessions."""
        try:
            result = self.users_collection.update_one(
                {"username": username},
                {"$set": {"is_admin": bool(is_admin), "updated_at": datetime.utcnow()}, "$inc": {"token_version": 1}},
            )
            return result.modified_count == 1
        except Exception as exc:
            logger.error("更新用户角色失败: %s", type(exc).__name__)
            return False


# 全局用户服务实例
user_service = UserService()
