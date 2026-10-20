"""环境变量配置。

约定（系统架构设计.md §5）：必填项缺失或非法时**启动即失败**，
不要留可用的默认口令，否则线上会带着已知密钥跑起来。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------- 应用 ----------
    app_name: str = "售后故障诊断系统"
    app_version: str = "1.2.0"
    # 同时控制 /api/docs 与 /api/openapi.json 是否开放；默认关，避免对外暴露接口面
    debug: bool = False
    log_level: str = "INFO"

    # ---------- 数据库 ----------
    # postgresql+psycopg2://user:pwd@host:5432/db
    database_url: str
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=10, ge=0, le=100)
    db_pool_timeout: int = Field(default=30, ge=1)
    db_pool_recycle: int = Field(default=1800, ge=0)
    db_echo: bool = False

    # ---------- JWT ----------
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = Field(default=24, ge=1, le=720)

    # ---------- 上传与时区 ----------
    upload_dir: Path = Path("/data/uploads")
    # 供 B-05 上传接口使用（与 Nginx client_max_body_size 对齐），当前尚未接线
    max_upload_mb: int = Field(default=20, ge=1)
    tz: str = "Asia/Shanghai"

    @field_validator("jwt_secret")
    @classmethod
    def _validate_jwt_secret(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("JWT_SECRET 长度至少 32，请用 openssl rand -hex 32 生成")
        return value

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, value: str) -> str:
        if not value.startswith(("postgresql", "sqlite")):
            raise ValueError("DATABASE_URL 必须是 postgresql+psycopg2:// 或 sqlite:// 开头")
        return value

    @property
    def timezone(self) -> ZoneInfo:
        """对外输出统一使用该时区（契约要求带 +08:00）。"""
        return ZoneInfo(self.tz)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # 值由环境变量注入
