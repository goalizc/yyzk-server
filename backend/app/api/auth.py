"""鉴权接口：登录、修改自己的密码。"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.exceptions import BusinessError
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
    waste_time_like_verify,
)
from app.database import get_db
from app.models import User
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    PasswordChangeRequest,
    PasswordChangeResponse,
    UserOut,
)
from app.schemas.common import ErrorBody

router = APIRouter()


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="登录获取 token",
    responses={
        401: {"model": ErrorBody, "description": "用户名或密码错误"},
        403: {"model": ErrorBody, "description": "账号已停用"},
    },
)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    user = db.scalar(select(User).where(User.username == payload.username))

    if user is None:
        # 用户名不存在也走一次 bcrypt，避免用响应时间探测账号是否存在
        waste_time_like_verify()
        raise BusinessError("AUTH_INVALID_CREDENTIALS", "用户名或密码错误", 401)

    if not verify_password(payload.password, user.password_hash):
        raise BusinessError("AUTH_INVALID_CREDENTIALS", "用户名或密码错误", 401)

    if not user.is_active:
        raise BusinessError("AUTH_USER_DISABLED", "账号已停用", 403)

    token, expires_at = create_access_token(user.id, user.username)
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    return LoginResponse(
        access_token=token,
        expires_at=expires_at,
        user=UserOut.model_validate(user),
    )


@router.put(
    "/password",
    response_model=PasswordChangeResponse,
    summary="修改当前账号密码",
    responses={
        400: {"model": ErrorBody, "description": "原密码不正确 / 新旧密码相同"},
        401: {"model": ErrorBody, "description": "未登录或 token 过期"},
        422: {"model": ErrorBody, "description": "新密码不满足规则"},
    },
)
def change_password(
    payload: PasswordChangeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PasswordChangeResponse:
    if not verify_password(payload.old_password, user.password_hash):
        raise BusinessError("PASSWORD_INVALID", "原密码不正确", 400)

    # 用哈希比对而不是明文比对：新密码与原密码等价即拒绝
    if verify_password(payload.new_password, user.password_hash):
        raise BusinessError("PASSWORD_SAME", "新密码不能与原密码相同", 400)

    user.password_hash = hash_password(payload.new_password)
    user.updated_at = datetime.now(timezone.utc)
    db.commit()

    # 契约：改密后不强制下线，当前 token 继续有效至过期
    return PasswordChangeResponse()
