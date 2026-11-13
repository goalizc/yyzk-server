"""进销存模块：仓库、SKU、分类、SKU↔分类/产品关联、余额、单据、明细、库存流水（9 张表）。

与 `deploy/schema.sql` v1.4、`deploy/migrations/005_inventory.sql` + `007_inventory_categories.sql`
一一对应。
模型只负责读写映射，CHECK 约束与索引在 DDL 中声明（见 models/__init__.py 约定）。
业务规则（行锁过账、幂等、冲正）在 `app/services/inventory/` 实现，不在此处。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class InventoryWarehouse(Base):
    __tablename__ = "inventory_warehouses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class InventorySku(Base):
    __tablename__ = "inventory_skus"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku_no: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    spec: Mapped[str | None] = mapped_column(String(100))
    unit: Mapped[str] = mapped_column(String(20), nullable=False, default="件")
    # 分类为多对多（inventory_sku_categories），不在此存自由文本；关联零件/产品均为可选
    # 可空弱关联：纯物资不属于任何产品；一个零件也可对应多个 SKU
    part_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("parts.id", ondelete="SET NULL")
    )
    warehouse_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("inventory_warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    min_stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    batch_no: Mapped[str | None] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    remark: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    # 多对多：一个物资可属于多个分类 / 多个产品（镜像零件↔产品，关联售后系统但不强制）
    categories: Mapped[list["InventoryCategory"]] = relationship(
        secondary="inventory_sku_categories",
        primaryjoin="InventorySku.id == InventorySkuCategory.sku_id",
        secondaryjoin="InventorySkuCategory.category_id == InventoryCategory.id",
        lazy="selectin",
        order_by="InventoryCategory.name",
    )
    products: Mapped[list["Product"]] = relationship(
        secondary="inventory_sku_products",
        primaryjoin="InventorySku.id == InventorySkuProduct.sku_id",
        secondaryjoin="InventorySkuProduct.product_id == Product.id",
        lazy="selectin",
    )


class InventoryCategory(Base):
    """物资分类主数据（数据表管理，录入时下拉多选）。"""

    __tablename__ = "inventory_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    remark: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class InventorySkuCategory(Base):
    """物资 ↔ 分类 关联（多对多）。"""

    __tablename__ = "inventory_sku_categories"

    sku_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("inventory_skus.id", ondelete="CASCADE"), primary_key=True
    )
    category_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("inventory_categories.id", ondelete="CASCADE"), primary_key=True
    )


class InventorySkuProduct(Base):
    """物资 ↔ 产品 关联（多对多，镜像零件↔产品，关联售后系统但不强制）。"""

    __tablename__ = "inventory_sku_products"

    sku_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("inventory_skus.id", ondelete="CASCADE"), primary_key=True
    )
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )


class InventoryBalance(Base):
    __tablename__ = "inventory_balances"

    # 复合主键为多仓预留；quantity 的 >= 0 约束在 DDL 里
    sku_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("inventory_skus.id", ondelete="CASCADE"), primary_key=True
    )
    warehouse_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("inventory_warehouses.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class InventoryDocument(Base):
    __tablename__ = "inventory_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_no: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    # inbound / outbound / adjust_in / adjust_out；方向由类型决定，明细数量恒正
    doc_type: Mapped[str] = mapped_column(String(20), nullable=False)
    warehouse_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("inventory_warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    # L1 恒 confirmed；draft / pending / void 是未来审批流的预留值
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="confirmed")
    operator_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL")
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL")
    )
    review_remark: Mapped[str | None] = mapped_column(Text)
    remark: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    items: Mapped[list["InventoryDocumentItem"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="InventoryDocumentItem.id",
    )


class InventoryDocumentItem(Base):
    __tablename__ = "inventory_document_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("inventory_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    sku_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("inventory_skus.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    remark: Mapped[str | None] = mapped_column(String(200))

    document: Mapped["InventoryDocument"] = relationship(back_populates="items")


class StockMovement(Base):
    """库存流水，append-only：更正只能登记反向单据，不物理改删。"""

    __tablename__ = "stock_movements"

    # PG 用 BIGSERIAL（DDL 里是 BIGSERIAL）；SQLite 测试库必须用 INTEGER 才能自增，
    # 否则 BIGINT PRIMARY KEY 不是 rowid 别名，插入会报 NOT NULL constraint failed。
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True
    )
    sku_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("inventory_skus.id", ondelete="RESTRICT"), nullable=False
    )
    warehouse_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("inventory_warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    document_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("inventory_documents.id", ondelete="SET NULL")
    )
    # 通用引用伏笔：未来接工单/采购单，不加外键
    ref_type: Mapped[str | None] = mapped_column(String(30))
    ref_id: Mapped[str | None] = mapped_column(String(50))
    operator_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
