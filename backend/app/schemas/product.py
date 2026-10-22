"""产品 schema（契约 §2）。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import AppDateTime


class ProductPublic(BaseModel):
    """客户侧列表：只暴露下拉需要的字段。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    model: str
    line_id: int
    line_name: str | None = None
    sort_order: int


class ProductAdmin(BaseModel):
    """后台列表/详情：含 fault_count，便于删除前提示。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    model: str
    line_id: int
    line_name: str | None = None
    description: str = ""
    is_active: bool
    sort_order: int
    fault_count: int = 0
    created_at: AppDateTime
    updated_at: AppDateTime


class ProductCreate(BaseModel):
    name: str = Field(max_length=100, examples=["智能扫地机器人"])
    model: str = Field(max_length=50, examples=["X1"])
    line_id: int
    description: str | None = None
    is_active: bool = True
    sort_order: int = 0

    @field_validator("name", "model")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("名称与型号不能为空")
        return value


class ProductUpdate(BaseModel):
    """字段全部可选：传什么改什么。"""

    name: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=50)
    line_id: int | None = None
    description: str | None = None
    is_active: bool | None = None
    sort_order: int | None = None

    @field_validator("name", "model")
    @classmethod
    def _not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("名称与型号不能为空")
        return value


class ProductPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ProductAdmin]
