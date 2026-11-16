"""进销存模块 Pydantic schemas（PRD §4 端点契约）。

约定：
- 响应 schema **一律不含 `unit_cost`**（§3.6：可选写入留档、不返回、不计算）；
- 列表统一 `{total, page, page_size, items}`；
- 时间字段用 `AppDateTime`（UTC 存、`+08:00` 输出）。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.common import AppDateTime


def _strip_required(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("不能为空")
    return value


def _strip_optional(value: str | None) -> str | None:
    return None if value is None else _strip_required(value)


# 与列定义 NUMERIC(12,2) 对齐：上限 9999999999.99、两位小数。
# 不校验的话 1e20 会在 PG 里溢出成 500，0.005 会被静默舍入成 0.01/0.00。
UnitCost = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]


# ---------------------------------------------------------------- 仓库


class WarehouseItem(BaseModel):
    id: int
    code: str
    name: str
    is_active: bool


class WarehousePage(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[WarehouseItem]


# ---------------------------------------------------------------- SKU


class CategoryRef(BaseModel):
    id: int
    name: str


class ProductRef(BaseModel):
    id: int
    name: str


class RefProduct(BaseModel):
    """库存域只读引用：产品下拉（`/refs/products`）。

    与售后 `GET /admin/products` 的区别：只要 id / 名称 / 型号，
    不返回故障数、产品线等运营字段，故可挂 `inventory:sku:read`，
    让仓管在自己的权限域内选「关联产品」。
    """

    id: int
    name: str
    model: str


class RefPart(BaseModel):
    """库存域只读引用：零件下拉（`/refs/parts`）。

    `product_name` 用于前端拼「产品 / 零件」标签：省略 `product_id` 时一次取全部零件，
    避免按产品逐个请求造成 N+1。
    """

    id: int
    name: str
    part_no: str | None = None
    product_id: int
    product_name: str | None = None


class SkuItem(BaseModel):
    id: int
    sku_no: str
    name: str
    spec: str | None = None
    unit: str
    part_id: int | None = None
    part_name: str | None = None
    warehouse_id: int
    min_stock: int
    quantity: int = 0
    batch_no: str | None = None
    is_active: bool
    remark: str | None = None
    # 多对多：一个物资可属于多个分类 / 多个产品
    categories: list[CategoryRef] = Field(default_factory=list)
    products: list[ProductRef] = Field(default_factory=list)
    created_at: AppDateTime
    updated_at: AppDateTime


class SkuPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[SkuItem]


class RecentMovement(BaseModel):
    id: int
    delta: int
    balance_after: int
    doc_no: str | None = None
    created_at: AppDateTime


class SkuDetail(SkuItem):
    recent_movements: list[RecentMovement] = Field(default_factory=list)


class SkuCreate(BaseModel):
    sku_no: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    spec: str | None = Field(default=None, max_length=100)
    unit: str = Field(default="件", max_length=20)
    # 上限防一次请求塞几万条关联：N+1 查询 + 长事务会把锁持有时间放大
    category_ids: list[int] = Field(default_factory=list, max_length=100)
    product_ids: list[int] = Field(default_factory=list, max_length=100)
    part_id: int | None = None
    warehouse_id: int
    min_stock: int = Field(default=0, ge=0)
    # 只写留档：响应不返回（§3.6）
    unit_cost: UnitCost | None = None
    batch_no: str | None = Field(default=None, max_length=50)
    is_active: bool = True
    remark: str | None = Field(default=None, max_length=500)

    @field_validator("sku_no", "name")
    @classmethod
    def _required(cls, value: str) -> str:
        return _strip_required(value)


class SkuUpdate(BaseModel):
    # sku_no / warehouse_id 创建后不可改：换仓会让 (sku_id, warehouse_id) 余额行
    # 与历史流水（warehouse_id 是当时事实）失配；L1 单仓也没有换仓场景。
    name: str | None = Field(default=None, min_length=1, max_length=100)
    spec: str | None = Field(default=None, max_length=100)
    unit: str | None = Field(default=None, max_length=20)
    category_ids: list[int] | None = None
    product_ids: list[int] | None = None
    part_id: int | None = None
    min_stock: int | None = Field(default=None, ge=0)
    unit_cost: UnitCost | None = None
    batch_no: str | None = Field(default=None, max_length=50)
    is_active: bool | None = None
    remark: str | None = Field(default=None, max_length=500)

    @field_validator("name")
    @classmethod
    def _optional_blank(cls, value: str | None) -> str | None:
        return _strip_optional(value)


class LowStockItem(BaseModel):
    id: int
    sku_no: str
    name: str
    unit: str
    warehouse_id: int
    min_stock: int
    quantity: int
    shortage: int  # 缺口 = min_stock - quantity，前端标红用


class LowStockPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[LowStockItem]


# ---------------------------------------------------------------- 单据


class DocumentItemInput(BaseModel):
    sku_id: int
    quantity: int = Field(gt=0)
    # 只写留档：不返回、不计算（§3.6）
    unit_cost: UnitCost | None = None
    remark: str | None = Field(default=None, max_length=200)


class DocumentCreate(BaseModel):
    warehouse_id: int
    remark: str | None = Field(default=None, max_length=500)
    # 空明细交给 service 抛 400 INVENTORY_ITEM_EMPTY；这里不用 min_length，
    # 否则会变成 422 VALIDATION_ERROR，与契约 §8 的机器码不一致。
    items: list[DocumentItemInput] = Field(default_factory=list, max_length=200)


class AdjustmentCreate(DocumentCreate):
    adjust_type: Literal["in", "out"]


class DocumentUpdate(BaseModel):
    """修改已生效单据：只允许改数量 / 种类 / 备注，仓库与单据类型不可改。"""

    remark: str | None = Field(default=None, max_length=500)
    items: list[DocumentItemInput] = Field(default_factory=list, max_length=200)


class ReverseRequest(BaseModel):
    remark: str = Field(min_length=1, max_length=200)

    @field_validator("remark")
    @classmethod
    def _required(cls, value: str) -> str:
        return _strip_required(value)


class DocumentItemOut(BaseModel):
    sku_id: int
    sku_no: str
    sku_name: str
    quantity: int
    remark: str | None = None
    # 故意不含 unit_cost（§3.6）


class DocumentItem(BaseModel):
    id: int
    doc_no: str
    doc_type: str
    status: str
    warehouse_id: int
    operator_id: int | None = None
    confirmed_at: AppDateTime | None = None
    confirmed_by: int | None = None
    remark: str | None = None
    created_at: AppDateTime


class DocumentDetail(DocumentItem):
    items: list[DocumentItemOut] = Field(default_factory=list)


class DocumentPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[DocumentItem]


# ---------------------------------------------------------------- 流水


class MovementItem(BaseModel):
    id: int
    sku_id: int
    sku_no: str
    sku_name: str
    warehouse_id: int
    delta: int
    balance_after: int
    document_id: int | None = None
    doc_no: str | None = None
    # 单据状态：void 的流水仍在，但不能再冲正；前端据此隐藏冲正按钮
    doc_status: str | None = None
    operator_id: int | None = None
    # 姓名优先，缺失时回落用户名；账号被删时为空
    operator_name: str | None = None
    created_at: AppDateTime


class MovementPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[MovementItem]


# ---------------------------------------------------------------- 汇总


class InventorySummary(BaseModel):
    sku_count: int
    low_stock_count: int
    inbound_this_month: int
    outbound_this_month: int


# ---------------------------------------------------------------- 分类主数据


class CategoryItem(BaseModel):
    id: int
    name: str
    is_active: bool
    remark: str | None = None
    created_at: AppDateTime
    updated_at: AppDateTime


class CategoryPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[CategoryItem]


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    remark: str | None = Field(default=None, max_length=200)

    @field_validator("name")
    @classmethod
    def _required(cls, value: str) -> str:
        return _strip_required(value)


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    remark: str | None = Field(default=None, max_length=200)
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        # 空白串（"  "）过不了 min_length，但 strip 后是空，必须在这里拒掉
        return _strip_optional(value)

    @model_validator(mode="after")
    def _name_not_null(self) -> "CategoryUpdate":
        # 显式传 null 会撞 NOT NULL，之前被 IntegrityError 误报成「名称已存在」；
        # 这里直接按参数非法拒绝，语义才对。
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("分类名称不能为空")
        return self
