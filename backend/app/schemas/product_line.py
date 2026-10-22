"""产品线请求/响应。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import AppDateTime


class ProductLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    sort_order: int
    is_active: bool
    product_count: int = 0
    created_at: AppDateTime
    updated_at: AppDateTime


class ProductLineList(BaseModel):
    items: list[ProductLineOut]


class ProductLineCreate(BaseModel):
    name: str = Field(max_length=50, examples=["扫地机"])
    sort_order: int = 0

    @field_validator("name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("产品线名称不能为空")
        return value


class ProductLineUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=50)
    sort_order: int | None = None
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def _not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("产品线名称不能为空")
        return value
