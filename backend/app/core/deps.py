"""依赖注入：数据库会话与当前登录用户。

鉴权在 app.core.permissions 中完成，本模块只负责识别用户与停用校验。
"""

from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.core.security import decode_access_token
from app.database import get_db
from app.models import User

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise BusinessError("AUTH_TOKEN_EXPIRED", "登录已过期，请重新登录", 401)

    payload = decode_access_token(credentials.credentials)
    try:
        user_id = int(payload.get("sub", ""))
    except (TypeError, ValueError) as exc:
        raise BusinessError("AUTH_TOKEN_EXPIRED", "登录已过期，请重新登录", 401) from exc

    user = db.get(User, user_id)
    if user is None:
        raise BusinessError("AUTH_TOKEN_EXPIRED", "登录已过期，请重新登录", 401)
    if not user.is_active:
        raise BusinessError("AUTH_USER_DISABLED", "账号已停用", 403)
    return user
