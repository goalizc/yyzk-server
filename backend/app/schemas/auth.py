"""鉴权相关请求/响应模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.security import BCRYPT_MAX_BYTES


class LoginRequest(BaseModel):
    username: str = Field(examples=["admin"])
    password: str = Field(examples=["Admin@12345"])

    @field_validator("username")
    @classmethod
    def _username_rules(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("请输入用户名")
        if len(value) > 50:
            raise ValueError("用户名不能超过 50 个字符")
        return value

    @field_validator("password")
    @classmethod
    def _password_rules(cls, value: str) -> str:
        if not value:
            raise ValueError("请输入密码")
        # bcrypt 只取前 72 字节，超长部分会被静默忽略，必须在入口拦住
        if len(value.encode("utf-8")) > BCRYPT_MAX_BYTES:
            raise ValueError(f"密码不能超过 {BCRYPT_MAX_BYTES} 字节")
        return value


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    real_name: str
    role: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime = Field(description="带 +08:00 偏移的 ISO 8601 时间")
    user: UserOut
    permissions: list[str] = Field(default_factory=list, description="生效权限码，已展开依赖")


class MeResponse(BaseModel):
    user: UserOut
    permissions: list[str] = Field(default_factory=list)


class PasswordChangeRequest(BaseModel):
    old_password: str = Field(examples=["Admin@12345"])
    new_password: str = Field(examples=["NewPwd@2026"])

    @field_validator("old_password")
    @classmethod
    def _old_password_required(cls, value: str) -> str:
        if not value:
            raise ValueError("请输入原密码")
        return value

    @field_validator("new_password")
    @classmethod
    def _new_password_rules(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("新密码至少 8 位")
        if len(value.encode("utf-8")) > BCRYPT_MAX_BYTES:
            raise ValueError(f"新密码不能超过 {BCRYPT_MAX_BYTES} 字节")
        return value


class PasswordChangeResponse(BaseModel):
    success: bool = True
    message: str = "密码已修改"
