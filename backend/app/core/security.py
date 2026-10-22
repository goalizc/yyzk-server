"""密码哈希与 JWT。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache

from jose import JWTError, jwt
from passlib.context import CryptContext
from passlib.exc import UnknownHashError

from app.config import get_settings
from app.core.exceptions import BusinessError

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# bcrypt 只取前 72 字节，超长密码会被静默截断，因此在入口处直接拒绝
BCRYPT_MAX_BYTES = 72


def hash_password(plain_password: str) -> str:
    if len(plain_password.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise ValueError(f"密码不能超过 {BCRYPT_MAX_BYTES} 字节")
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return pwd_context.verify(plain_password, password_hash)
    except (UnknownHashError, ValueError):
        # 库里的哈希格式损坏时按验证失败处理，避免 500
        return False


@lru_cache
def _dummy_hash() -> str:
    """用于用户名不存在时也走一次 bcrypt，抹平响应时间差。"""
    return pwd_context.hash("timing-equalizer")


def waste_time_like_verify() -> None:
    verify_password("timing-equalizer", _dummy_hash())


def create_access_token(
    user_id: int, username: str, token_version: int
) -> tuple[str, datetime]:
    """返回 (token, 过期时间)；过期时间按应用时区输出。"""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=settings.jwt_expire_hours)
    payload = {
        "sub": str(user_id),
        "username": username,
        "ver": token_version,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_at.astimezone(settings.timezone)


def decode_access_token(token: str) -> dict:
    """解析 token；任何异常统一按"登录已过期"处理（契约 §0.3）。"""
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise BusinessError("AUTH_TOKEN_EXPIRED", "登录已过期，请重新登录", 401) from exc
