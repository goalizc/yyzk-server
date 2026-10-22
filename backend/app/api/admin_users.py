"""用户管理。临时授权与候选人接口在后续任务追加。"""

from __future__ import annotations

import secrets
import string
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import BusinessError
from app.core.permissions import (
    TICKET_ASSIGN,
    USER_READ,
    USER_WRITE,
    effective_permissions,
    grantable_permissions,
    require,
)
from app.core.security import hash_password
from app.database import get_db
from app.models import (
    ProductLine,
    User,
    UserPermissionGrant,
    UserProductLine,
)
from app.schemas.common import ErrorBody, SuccessResponse
from app.schemas.user import (
    AssignableUser,
    GrantCreate,
    GrantOut,
    ProductLineAssignment,
    ProductLineBrief,
    ResetPasswordResponse,
    UserCreate,
    UserListItem,
    UserPage,
    UserUpdate,
)
from app.services.ticket_scope import assignable_users
from app.utils.search import LIKE_ESCAPE, like_pattern

router = APIRouter()

_PASSWORD_ALPHABET = "".join(
    c for c in string.ascii_letters + string.digits if c not in "0O1lI"
)


def _gen_password(length: int = 12) -> str:
    return "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))


def _to_item(user: User) -> UserListItem:
    return UserListItem(
        id=user.id,
        username=user.username,
        real_name=user.real_name,
        role=user.role,
        is_active=user.is_active,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        product_lines=[
            ProductLineBrief(
                id=assignment.line.id,
                name=assignment.line.name,
                expires_at=assignment.expires_at,
            )
            for assignment in user.product_lines
        ],
    )


def _ensure_lines_exist(
    db: Session, assignments: list[ProductLineAssignment]
) -> dict[int, ProductLine]:
    ids = {item.line_id for item in assignments}
    if not ids:
        return {}
    rows = db.scalars(select(ProductLine).where(ProductLine.id.in_(ids))).all()
    found = {line.id: line for line in rows}
    missing = ids - found.keys()
    if missing:
        raise BusinessError("NOT_FOUND", f"产品线不存在：{sorted(missing)}", 404)
    return found


def _replace_lines(db: Session, user: User, assignments: list[ProductLineAssignment]) -> None:
    lines = _ensure_lines_exist(db, assignments)
    existing = set(
        db.scalars(
            select(UserProductLine.line_id).where(UserProductLine.user_id == user.id)
        ).all()
    )
    for item in assignments:
        if item.line_id in existing:
            continue
        if not lines[item.line_id].is_active:
            raise BusinessError("LINE_INACTIVE", "产品线已停用，不能新授权", 400)
    db.execute(
        UserProductLine.__table__.delete().where(UserProductLine.user_id == user.id)
    )
    db.add_all(
        [
            UserProductLine(
                user_id=user.id, line_id=item.line_id, expires_at=item.expires_at
            )
            for item in assignments
        ]
    )


def _ensure_other_super_admin(db: Session, user_id: int) -> None:
    # 锁全部在用超管行再计数：ORDER BY id 保证并发时锁顺序一致，避免互相锁对方
    active_ids = set(
        db.scalars(
            select(User.id)
            .where(User.role == "super_admin", User.is_active.is_(True))
            .order_by(User.id)
            .with_for_update()
        ).all()
    )
    if len(active_ids - {user_id}) == 0:
        raise BusinessError("LAST_SUPER_ADMIN", "系统至少需要保留一个在用超级管理员", 400)


@router.get("/users", response_model=UserPage, summary="用户列表")
def list_users(
    keyword: str | None = Query(None, max_length=100),
    role: str | None = Query(None),
    is_active: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require(USER_READ)),
) -> UserPage:
    stmt = select(User).options(
        selectinload(User.product_lines).selectinload(UserProductLine.line)
    )
    conditions = []
    if role:
        conditions.append(User.role == role)
    if is_active is not None:
        conditions.append(User.is_active.is_(is_active))
    if keyword and keyword.strip():
        pattern = like_pattern(keyword.strip().lower())
        conditions.append(
            or_(
                func.lower(User.username).like(pattern, escape=LIKE_ESCAPE),
                func.lower(User.real_name).like(pattern, escape=LIKE_ESCAPE),
            )
        )

    total = db.scalar(select(func.count(User.id)).where(*conditions)) or 0
    stmt = (
        stmt.where(*conditions)
        .order_by(User.is_active.desc(), User.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return UserPage(
        total=total,
        page=page,
        page_size=page_size,
        items=[_to_item(user) for user in db.scalars(stmt)],
    )


@router.post(
    "/users",
    status_code=201,
    response_model=UserListItem,
    summary="新建用户",
    responses={409: {"model": ErrorBody, "description": "用户名重复"}},
)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require(USER_WRITE)),
) -> UserListItem:
    _ensure_lines_exist(db, payload.product_lines)
    user = User(
        username=payload.username,
        real_name=payload.real_name,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    try:
        db.flush()
        _replace_lines(db, user, payload.product_lines)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BusinessError(
            "USERNAME_DUPLICATED", f"用户名 {payload.username} 已存在", 409
        ) from exc
    db.refresh(user)
    user = db.scalar(
        select(User)
        .options(selectinload(User.product_lines).selectinload(UserProductLine.line))
        .where(User.id == user.id)
    )
    return _to_item(user)


@router.put("/users/{user_id}", response_model=UserListItem, summary="修改用户")
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require(USER_WRITE)),
) -> UserListItem:
    user = db.get(User, user_id)
    if user is None:
        raise BusinessError("NOT_FOUND", "用户不存在", 404)

    data = {
        key: value
        for key, value in payload.model_dump(exclude_unset=True).items()
        if value is not None
    }
    if user_id == actor.id:
        if "is_active" in data and data["is_active"] is False:
            raise BusinessError("SELF_DISABLE", "不能停用自己", 400)
        if "role" in data and data["role"] != actor.role:
            raise BusinessError("SELF_ROLE_CHANGE", "不能修改自己的角色", 400)

    demoting = data.get("role") not in (None, "super_admin") and user.role == "super_admin"
    disabling = data.get("is_active") is False and user.is_active and user.role == "super_admin"
    if (demoting or disabling) and user.is_active:
        _ensure_other_super_admin(db, user.id)

    for field, value in data.items():
        setattr(user, field, value)
    user.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    user = db.scalar(
        select(User)
        .options(selectinload(User.product_lines).selectinload(UserProductLine.line))
        .where(User.id == user.id)
    )
    return _to_item(user)


@router.post(
    "/users/{user_id}/reset-password",
    response_model=ResetPasswordResponse,
    summary="重置密码（一次性返回明文）",
)
def reset_password(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require(USER_WRITE)),
) -> ResetPasswordResponse:
    user = db.get(User, user_id)
    if user is None:
        raise BusinessError("NOT_FOUND", "用户不存在", 404)

    password = _gen_password()
    user.password_hash = hash_password(password)
    user.updated_at = datetime.now(timezone.utc)
    db.commit()
    return ResetPasswordResponse(password=password)


@router.get("/users/{user_id}/grants", response_model=list[GrantOut], summary="临时授权列表")
def list_grants(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require(USER_READ)),
) -> list[GrantOut]:
    if db.get(User, user_id) is None:
        raise BusinessError("NOT_FOUND", "用户不存在", 404)
    now = datetime.now(timezone.utc)
    rows = db.execute(
        select(UserPermissionGrant, User.real_name)
        .outerjoin(User, UserPermissionGrant.granted_by == User.id)
        .where(UserPermissionGrant.user_id == user_id)
        .order_by(UserPermissionGrant.granted_at.desc(), UserPermissionGrant.id.desc())
    ).all()
    return [
        GrantOut(
            id=grant.id,
            permission=grant.permission,
            expires_at=grant.expires_at,
            reason=grant.reason,
            granted_by_name=granted_by_name,
            granted_at=grant.granted_at,
            revoked_at=grant.revoked_at,
            is_active=grant.revoked_at is None
            and (grant.expires_at if grant.expires_at.tzinfo else grant.expires_at.replace(tzinfo=timezone.utc)) > now,
        )
        for grant, granted_by_name in rows
    ]


@router.post(
    "/users/{user_id}/grants",
    status_code=201,
    response_model=GrantOut,
    summary="发放临时授权",
)
def create_grant(
    user_id: int,
    payload: GrantCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require(USER_WRITE)),
) -> GrantOut:
    target = db.get(User, user_id)
    if target is None:
        raise BusinessError("NOT_FOUND", "用户不存在", 404)
    if not target.is_active:
        raise BusinessError("USER_DISABLED", "账号已停用，不能发放临时授权", 400)
    if payload.permission not in grantable_permissions():
        raise BusinessError("INVALID_PERMISSION", "该权限不可临时授予", 400)
    if payload.permission not in effective_permissions(db, actor):
        raise BusinessError("INVALID_PERMISSION", "不能授予自己不具备的权限", 400)

    grant = UserPermissionGrant(
        user_id=user_id,
        permission=payload.permission,
        expires_at=payload.expires_at,
        reason=payload.reason.strip(),
        granted_by=actor.id,
    )
    db.add(grant)
    db.commit()
    db.refresh(grant)
    return GrantOut(
        id=grant.id,
        permission=grant.permission,
        expires_at=grant.expires_at,
        reason=grant.reason,
        granted_by_name=actor.real_name,
        granted_at=grant.granted_at,
        revoked_at=None,
        is_active=True,
    )


@router.delete(
    "/users/{user_id}/grants/{grant_id}",
    response_model=SuccessResponse,
    summary="提前收回临时授权",
)
def revoke_grant(
    user_id: int,
    grant_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require(USER_WRITE)),
) -> SuccessResponse:
    grant = db.get(UserPermissionGrant, grant_id)
    if grant is None or grant.user_id != user_id:
        raise BusinessError("NOT_FOUND", "临时授权不存在", 404)
    if grant.revoked_at is None:
        grant.revoked_at = datetime.now(timezone.utc)
        db.commit()
    return SuccessResponse()


@router.put(
    "/users/{user_id}/product-lines",
    response_model=UserListItem,
    summary="整体替换产品线授权",
)
def replace_product_lines(
    user_id: int,
    assignments: list[ProductLineAssignment],
    db: Session = Depends(get_db),
    _: User = Depends(require(USER_WRITE)),
) -> UserListItem:
    user = db.get(User, user_id)
    if user is None:
        raise BusinessError("NOT_FOUND", "用户不存在", 404)

    _replace_lines(db, user, assignments)
    db.commit()
    user = db.scalar(
        select(User)
        .options(selectinload(User.product_lines).selectinload(UserProductLine.line))
        .where(User.id == user_id)
    )
    return _to_item(user)


@router.get(
    "/users/assignable",
    response_model=list[AssignableUser],
    summary="可改派的处理人",
)
def list_assignable(
    product_id: int | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require(TICKET_ASSIGN)),
) -> list[AssignableUser]:
    return [
        AssignableUser(id=user.id, real_name=user.real_name)
        for user in assignable_users(db, product_id)
    ]
