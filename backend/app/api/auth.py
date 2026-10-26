"""鉴权接口：登录、修改自己的密码。"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.exceptions import BusinessError
from app.core.permissions import current_permissions
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
    MeResponse,
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
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> LoginResponse:
    user = db.scalar(
        select(User).where(func.lower(User.username) == payload.username.strip().lower())
    )

    # 审计埋点：登录是「人的问题」最关键的证据，失败原因用固定码值（前端再翻译）
    attempted = payload.username.strip()[:50]
    if user is None:
        # 用户名不存在也走一次 bcrypt，避免用响应时间探测账号是否存在
        request.state.audit = {
            "username": attempted,
            "target_id": None,
            "target_name": attempted,
            "detail": {"reason": "user_not_found", "identity_verified": False},
        }
        waste_time_like_verify()
        raise BusinessError("AUTH_INVALID_CREDENTIALS", "用户名或密码错误", 401)

    if not verify_password(payload.password, user.password_hash):
        request.state.audit = {
            "username": user.username,
            "user_id": user.id,
            "target_id": str(user.id),
            "target_name": user.username,
            # 用户名是从输入里拿的，还没被密码证明——不能在审计里当成「已确认身份」
            "detail": {"reason": "wrong_password", "identity_verified": False},
        }
        raise BusinessError("AUTH_INVALID_CREDENTIALS", "用户名或密码错误", 401)

    if not user.is_active:
        request.state.audit = {
            "username": user.username,
            "user_id": user.id,
            "target_id": str(user.id),
            "target_name": user.username,
            # 密码已通过，身份是确认的，只是账号被停用
            "detail": {"reason": "disabled", "identity_verified": True},
        }
        raise BusinessError("AUTH_USER_DISABLED", "账号已停用", 403)

    request.state.audit = {
        "username": user.username,
        "user_id": user.id,
        "target_id": str(user.id),
        "target_name": user.username,
        "detail": {"reason": "success", "role": user.role, "identity_verified": True},
    }

    token, expires_at = create_access_token(user.id, user.username, user.token_version)
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    return LoginResponse(
        access_token=token,
        expires_at=expires_at,
        user=UserOut.model_validate(user),
        permissions=current_permissions(user, db),
    )


@router.get("/me", response_model=MeResponse, summary="当前账号与生效权限")
def me(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MeResponse:
    return MeResponse(
        user=UserOut.model_validate(user),
        permissions=current_permissions(user, db),
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
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PasswordChangeResponse:
    # 改密是有后果的动作（会把该账号所有旧 token 踢掉），成功失败都要留痕
    request.state.audit = {
        "username": user.username,
        "user_id": user.id,
        "target_id": str(user.id),
        "target_name": user.username,
        "detail": {"reason": "self_change"},
    }

    if not verify_password(payload.old_password, user.password_hash):
        raise BusinessError("PASSWORD_INVALID", "原密码不正确", 400)

    # 用哈希比对而不是明文比对：新密码与原密码等价即拒绝
    if verify_password(payload.new_password, user.password_hash):
        raise BusinessError("PASSWORD_SAME", "新密码不能与原密码相同", 400)

    user.password_hash = hash_password(payload.new_password)
    user.token_version += 1
    user.updated_at = datetime.now(timezone.utc)
    db.commit()

    # 改密即吊销此前签发的所有 token，需要重新登录
    return PasswordChangeResponse()
