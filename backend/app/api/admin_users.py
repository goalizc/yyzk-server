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
from app.core.permissions import USER_READ, USER_WRITE, require
from app.core.security import hash_password
from app.database import get_db
from app.models import ProductLine, User, UserProductLine
from app.schemas.common import ErrorBody
from app.schemas.user import (
    ProductLineAssignment,
    ProductLineBrief,
    ResetPasswordResponse,
    UserCreate,
    UserListItem,
    UserPage,
    UserUpdate,
)
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


def _ensure_lines_exist(db: Session, assignments: list[ProductLineAssignment]) -> None:
    ids = {item.line_id for item in assignments}
    if not ids:
        return
    found = set(db.scalars(select(ProductLine.id).where(ProductLine.id.in_(ids))).all())
    missing = ids - found
    if missing:
        raise BusinessError("NOT_FOUND", f"产品线不存在：{sorted(missing)}", 404)


def _replace_lines(db: Session, user: User, assignments: list[ProductLineAssignment]) -> None:
    _ensure_lines_exist(db, assignments)
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
    others = db.scalars(
        select(User.id)
        .where(
            User.role == "super_admin",
            User.is_active.is_(True),
            User.id != user_id,
        )
        .with_for_update()
    ).all()
    if not others:
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
