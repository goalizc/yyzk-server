"""后台用户、多角色关联、产品线授权与临时权限授权。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.roles import ROLE_PRIORITY, primary_role
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    real_name: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    token_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    roles: Mapped[list["UserRole"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", order_by="UserRole.role"
    )
    product_lines: Mapped[list["UserProductLine"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    grants: Mapped[list["UserPermissionGrant"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="UserPermissionGrant.user_id",
    )

    @property
    def role_values(self) -> list[str]:
        """按 ROLE_PRIORITY 固定顺序返回，与入参规范化/接口输出保持一致。"""
        values = {item.role for item in self.roles}
        return [role for role in ROLE_PRIORITY if role in values]

    @property
    def role(self) -> str:
        """兼容旧接口/旧 token 的单一角色展示，权限判定不得使用。"""
        return primary_role(self.role_values)


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(20), primary_key=True)

    user: Mapped["User"] = relationship(back_populates="roles")


class UserProductLine(Base):
    __tablename__ = "user_product_lines"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    line_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("product_lines.id", ondelete="CASCADE"), primary_key=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="product_lines")
    line: Mapped["ProductLine"] = relationship()  # noqa: F821


class UserPermissionGrant(Base):
    __tablename__ = "user_permission_grants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    permission: Mapped[str] = mapped_column(String(30), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    granted_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL")
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="grants", foreign_keys=[user_id])
