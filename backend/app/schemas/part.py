"""零件 schema（契约 §3）。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PartPublic(BaseModel):
    """客户侧级联下拉。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    part_no: str | None = None
    name: str
    group_name: str | None = None
    sort_order: int


class PartAdmin(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    part_no: str | None = None
    name: str
    group_name: str | None = None
    sort_order: int
    fault_count: int = 0


class PartCreate(BaseModel):
    product_id: int
    part_no: str | None = Field(default=None, max_length=50, examples=["P-X1-001"])
    name: str = Field(max_length=100, examples=["主刷模组"])
    group_name: str | None = Field(default=None, max_length=50, examples=["动力系统"])
    sort_order: int = 0

    @field_validator("name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("零件名称不能为空")
        return value


class PartUpdate(BaseModel):
    product_id: int | None = None
    part_no: str | None = Field(default=None, max_length=50)
    name: str | None = Field(default=None, max_length=100)
    group_name: str | None = Field(default=None, max_length=50)
    sort_order: int | None = None

    @field_validator("name")
    @classmethod
    def _not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("零件名称不能为空")
        return value


class PartPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[PartAdmin]
