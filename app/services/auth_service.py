import time
import uuid
from datetime import datetime, timedelta, timezone
from app.utils.timezone import now_tz
from typing import Optional
import jwt
from pydantic import BaseModel
from app.core.config import settings

class TokenData(BaseModel):
    sub: str
    exp: int
    token_type: str = "access"
    user_id: Optional[str] = None
    token_version: int = 0
    issuer: Optional[str] = None
    jti: Optional[str] = None

class AuthService:
    @staticmethod
    def create_access_token(
        sub: str,
        expires_minutes: int | None = None,
        expires_delta: int | None = None,
        *,
        token_type: str = "access",
        user_id: str | None = None,
        token_version: int = 0,
        jti: str | None = None,
    ) -> str:
        if expires_delta:
            # 如果指定了秒数，使用秒数
            expire = now_tz() + timedelta(seconds=expires_delta)
        else:
            # 否则使用分钟数
            expire = now_tz() + timedelta(minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        payload = {
            "sub": sub,
            "user_id": user_id or sub,
            "type": token_type,
            "token_version": token_version,
            "iss": settings.AUTH_TOKEN_ISSUER,
            "jti": jti or str(uuid.uuid4()),
            "exp": expire,
        }
        token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
        return token

    @staticmethod
    def verify_token(token: str) -> Optional[TokenData]:
        import logging
        logger = logging.getLogger(__name__)

        try:
            logger.debug(f"🔍 开始验证token")
            logger.debug(f"📝 Token长度: {len(token)}")
            logger.debug(f"🔧 JWT算法: {settings.JWT_ALGORITHM}")

            unverified = jwt.decode(token, options={"verify_signature": False})
            decode_options = {"verify_iss": "iss" in unverified}
            decode_kwargs = {
                "algorithms": [settings.JWT_ALGORITHM],
                "options": decode_options,
            }
            if "iss" in unverified:
                decode_kwargs["issuer"] = settings.AUTH_TOKEN_ISSUER
            payload = jwt.decode(
                token,
                settings.JWT_SECRET,
                **decode_kwargs,
            )
            logger.debug(f"✅ Token解码成功")

            token_data = TokenData(
                sub=payload.get("sub"),
                user_id=payload.get("user_id"),
                token_type=payload.get("type", "access"),
                token_version=int(payload.get("token_version", 0)),
                issuer=payload.get("iss"),
                jti=payload.get("jti"),
                exp=int(payload.get("exp", time.time())),
            )

            # 检查是否过期
            current_time = int(time.time())
            if token_data.exp < current_time:
                logger.warning("⏰ Token已过期")
                return None

            logger.debug(f"✅ Token验证成功")
            return token_data

        except jwt.ExpiredSignatureError:
            logger.warning("⏰ Token已过期")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"❌ Token无效: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"❌ Token验证异常: {str(e)}")
            return None
