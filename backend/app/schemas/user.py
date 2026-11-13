"""用户管理与临时授权的请求/响应。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field, field_validator

from app.core.roles import ROLE_PRIORITY
from app.core.security import BCRYPT_MAX_BYTES
from app.schemas.common import AppDateTime

# 角色白名单与优先级顺序共用一份定义：输入规范化与接口输出顺序必须一致。
ROLE_VALUES = tuple(ROLE_PRIORITY)


def _validate_password(value: str) -> str:
    if len(value) < 8:
        raise ValueError("密码至少 8 位")
    if len(value.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise ValueError(f"密码不能超过 {BCRYPT_MAX_BYTES} 字节")
    return value


def _validate_roles(value: list[str]) -> list[str]:
    unique = set(value)
    if not unique:
        raise ValueError("至少选择一个角色")
    if unique - set(ROLE_VALUES):
        raise ValueError("角色不合法")
    # 按 ROLE_VALUES 固定顺序返回，便于接口输出与前端回填保持稳定
    return [role for role in ROLE_VALUES if role in unique]


class ProductLineAssignment(BaseModel):
    line_id: int
    expires_at: datetime | None = None

    @field_validator("expires_at")
    @classmethod
    def _future_or_none(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        if value <= datetime.now(timezone.utc):
            raise ValueError("到期时间必须晚于当前时间")
        return value


class ProductLineBrief(BaseModel):
    id: int
    name: str
    expires_at: AppDateTime | None = None


class UserCreate(BaseModel):
    username: str = Field(max_length=50)
    real_name: str = Field(max_length=50)
    password: str
    # 必填：角色是权限唯一来源，省略不能静默降级成 agent
    roles: list[str]
    product_lines: list[ProductLineAssignment] = Field(default_factory=list)

    @field_validator("username")
    @classmethod
    def _username_not_blank(cls, value: str) -> str:
        value = value.strip().lower()
        if not value:
            raise ValueError("不能为空")
        return value

    @field_validator("real_name")
    @classmethod
    def _real_name_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value

    @field_validator("password")
    @classmethod
    def _password_rules(cls, value: str) -> str:
        return _validate_password(value)

    @field_validator("roles")
    @classmethod
    def _roles_rules(cls, value: list[str]) -> list[str]:
        return _validate_roles(value)


class UserUpdate(BaseModel):
    username: str | None = Field(default=None, max_length=50)
    real_name: str | None = Field(default=None, max_length=50)
    roles: list[str] | None = None
    is_active: bool | None = None

    @field_validator("real_name")
    @classmethod
    def _not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("姓名不能为空")
        return value

    @field_validator("username")
    @classmethod
    def _username_not_blank_lower(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip().lower()
        if not value:
            raise ValueError("不能为空")
        return value

    @field_validator("roles")
    @classmethod
    def _roles_rules(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        return _validate_roles(value)


class UserListItem(BaseModel):
    id: int
    username: str
    real_name: str
    role: str
    roles: list[str] = Field(default_factory=list)
    is_active: bool
    active_grant_count: int = 0
    last_login_at: AppDateTime | None = None
    created_at: AppDateTime
    product_lines: list[ProductLineBrief] = Field(default_factory=list)


class UserPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[UserListItem]


class ResetPasswordResponse(BaseModel):
    password: str


class AssignableUser(BaseModel):
    id: int
    real_name: str


class GrantCreate(BaseModel):
    permission: str
    expires_at: datetime
    reason: str = Field(min_length=1, max_length=200)

    @field_validator("reason")
    @classmethod
    def _reason_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("请填写授权事由")
        return value

    @field_validator("expires_at")
    @classmethod
    def _future_within_limit(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if value <= now:
            raise ValueError("到期时间必须晚于当前时间")
        if value > now + timedelta(days=180):
            raise ValueError("临时授权最长 180 天")
        return value


class GrantOut(BaseModel):
    id: int
    permission: str
    expires_at: AppDateTime
    reason: str
    granted_by_name: str | None = None
    granted_at: AppDateTime
    revoked_at: AppDateTime | None = None
    is_active: bool
