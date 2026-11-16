# 进销存模块 — 正式 PRD 与数据模型设计

> 版本：v1.0 ｜ 日期：2026-11-12 ｜ 状态：**已定案 · 可开工**（§3.6 取舍已于 2026-11-12 经用户确认）
> 上游依据：`docs/01-需求设计/进销存模块需求定案.md` v0.2（需求已全部定案）
> 契约依据：`docs/02-技术设计/API接口契约.md` §0.1 分页 / §0.2 错误体 / **§8 错误码表**
> 设计依据：`docs/02-技术设计/国际化设计.md` §11、`docs/02-技术设计/代码与目录规范.md`
> 本文细化定案稿 §3 的数据模型并展开可开发细节；已定案项不再复述，冲突时以定案稿为准。

---

## 0. 本文要回答什么

1. 建哪些表、每个字段什么类型与约束（§3，含可直接落库的完整 DDL）
2. 开哪些端点、各自挂哪个权限码（§4）
3. 做哪些页面、双语 key 落在哪（§5、§8）
4. 新增 `warehouse_clerk` / `warehouse_manager` 两个角色要动哪些既有文件（§6）
5. 迁移怎么写才幂等、怎么烤进镜像（§10）
6. 怎么测、怎么验收、多少人天（§12–§14）

**不在本文范围**：客户侧任何页面、金额核算/成本账、多仓调拨、批次效期、审批流（仅保留 §3.5 的扩展口子）、与工单/故障方案的业务联动。

---

## 1. 业务目标与范围

### 1.1 目标

给内部仓库一套**权威数量台账**：登记物资/备件、记录每一次入库与出库、随时查当前余额与历史流水、低于安全库存时能被看见。公司目前无任何 ERP 或表格，本系统即为唯一账本。

### 1.2 做 / 不做

| 做 | 不做 |
|---|---|
| SKU 主数据（可空关联 `parts`，覆盖纯物资） | 整机序列号 / 一机一码 |
| 单仓、按件号 + 数量管理 | 多仓调拨、库位 |
| 入库单、出库单、盘盈/盘亏调整单 | 采购单、供应商、销售订单 |
| 冲正（反向单，不物理改删） | 物理删除/改写库存流水 |
| 主管改单：按「新明细 − 旧明细」补净更正流水 | 改单时重写历史流水或删除明细版本 |
| 库存流水 append-only、余额快照 | 批次号、效期、保质期预警 |
| 低库存阈值与列表标红 | 自动补货建议、采购申请 |
| 后台 6 页、双语、权限分细 | 客户侧任何入口 |
| 审批扩展口子（数据与代码结构层） | 审批状态机、复核界面、空端点 |

### 1.3 使用者

| 角色 | 典型动作 |
|---|---|
| `warehouse_clerk` 仓管录入员 | 建 SKU、登记入出库、查流水、导出（**不能**改已生效单、不能冲正）；建 SKU 选「关联产品 / 零件」时走库存域只读引用端点 `/refs/*`，**不授予** `product:read` / `part:read` |
| `warehouse_manager` 仓管主管 | 录入员全部动作，外加修改已生效入库/出库单的数量与种类（**不含**冲正） |
| `product_planner` 产品计划 | **产品 / 零件 / 产品线主数据的唯一常规写者**；不参与售后与库存业务 |
| `supervisor` 售后主管 | 库存全部动作（含冲正 `inventory:adjust:write` 与盘点）；产品 / 零件 / 产品线**只读** |
| `super_admin` 超级管理员 | 全部动作（**break-glass**）；账号与角色维护 |
| `auditor` 只读审计 | 只读台账与流水、导出 |
| `agent` 一线客服 | 无库存权限（长期不与售后挂钩） |

> **账号表单的角色下拉按职责分区且可多选**：系统管理（`super_admin`）/ 主数据（`product_planner`）/ 售后角色（`supervisor`、`agent`、`auditor`）/ 仓管角色（`warehouse_clerk`、`warehouse_manager`）。7 项平铺时「售后主管」「仓管主管」「产品计划」极易选错；一人多岗时勾选多个角色，权限取并集。
> **产品线分配只对售后线开放**：`super_admin`、`product_planner` 与两个仓管角色不参与工单数据范围，表单隐藏该字段、列表显示「不适用」，且编辑保存时**不调用**产品线替换接口（避免把历史分配清空）。

---

## 2. 业务流程

### 2.1 入库

```
选择仓库（一期固定默认仓）
  → 录入明细：SKU + 数量（>0）+ 单价（选填，仅留档）
  → 提交
  → create_document() 写单据主从，status = confirmed
  → post_document() 行锁加余额、逐明细写 stock_movements
  → 返回单号 RK + YYYYMMDD + 4 位当日序号
```

### 2.2 出库

同入库，但方向为减。提交前前端展示该 SKU 当前可用余额；服务端**必须**再次校验（前端展示不作数）：`balance_after < 0` 则整单回滚并抛 `INSUFFICIENT_STOCK`，**不允许任何一条流水落库**。

### 2.3 盘盈 / 盘亏 / 冲正

- 盘盈 `adjust_in`、盘亏 `adjust_out`：与入出库共用同一过账函数，仅 `doc_type` 与权限码不同（`inventory:adjust:write`）。
- **冲正 = 生成一张反向单据**，不是修改原单流水。原单 `status` 置 `void`，新单 `remark` 记「冲正 <原单号>」。原单再次冲正返回 `DOCUMENT_ALREADY_VOIDED`。冲正/改单前先锁单据行（`SELECT ... FOR UPDATE`）并复核状态，并发只允许一次成功。
- **主管改单**（仅 `inventory:doc:edit`）：明细整体替换，按「新明细 − 旧明细」逐 SKU 补净更正流水；历史 `stock_movements` 一条不改、一条不删。
- 流水表 append-only：任何 UPDATE / DELETE / TRUNCATE 由触发器直接抛错（§3.4）。

### 2.4 低库存预警

`inventory_skus.min_stock >= 0`；`inventory_balances.quantity < min_stock` 即在 SKU 列表标红，并在 `/summary` 返回待办数。前端在 SKU 列表标题旁显示「低库存 N」标签，点击即筛出低库存物资。**只做展示，不发通知、不生成采购单**。

### 2.5 单据状态（L1 与审批口子）

| 时点 | status | 过账时机 |
|---|---|---|
| L1 | 恒 `confirmed` | `create_document()` 内立即调用 `post_document()` |
| 未来启用审批 | `draft` → `pending` → `confirmed` / `void` | `confirm_document()` 内调用**同一个** `post_document()` |

`status` 的 CHECK 一期就放行 `confirmed / draft / pending / void` 四个值，`confirmed_at` / `confirmed_by` / `review_remark` 一期就有合理值。未来启用审批**不加列、不改 CHECK、不改过账函数内部**，详见定案稿 §6。

---

## 3. 数据模型设计

### 3.1 表关系

```
inventory_warehouses ──1:N── inventory_skus ──1:N── inventory_document_items
                                   │                        │
                                   │                        └──N:1── inventory_documents
                                   └──1:1(每仓)── inventory_balances
                                   └──1:N── stock_movements ──N:1── inventory_documents

parts (既有) ──0..1:N── inventory_skus   ← part_id 可空弱关联，ON DELETE SET NULL
inventory_skus ──N:M── inventory_categories   ← inventory_sku_categories
inventory_skus ──N:M── products (既有)        ← inventory_sku_products
users (既有) ──1:N── inventory_documents (operator_id / confirmed_by)
```

### 3.2 字段定义

#### `inventory_warehouses` 仓库（一期 1 条）

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | SERIAL | PK | |
| `code` | VARCHAR(30) | NOT NULL UNIQUE | `DEFAULT` |
| `name` | VARCHAR(50) | NOT NULL | 默认仓 |
| `is_active` | BOOLEAN | NOT NULL DEFAULT TRUE | |
| `created_at` / `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | UTC 存 |

#### `inventory_skus` SKU 主数据

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | SERIAL | PK | |
| `sku_no` | VARCHAR(50) | NOT NULL UNIQUE | 独立编码，如 `WL-0001` |
| `name` | VARCHAR(100) | NOT NULL | |
| `spec` | VARCHAR(100) | NULL | 规格 |
| `unit` | VARCHAR(20) | NOT NULL DEFAULT '件' | 计量单位 |
| `part_id` | INT | NULL，FK `parts(id)` ON DELETE SET NULL | **可空弱关联**，纯物资为 NULL |
| `warehouse_id` | INT | NOT NULL，FK warehouses ON DELETE RESTRICT | 一期固定默认仓 |
| `min_stock` | INT | NOT NULL DEFAULT 0 CHECK (>= 0) | 低库存阈值 |
| `unit_cost` | NUMERIC(12,2) | NULL | 参考单价，L1 只留档（见 §3.6） |
| `batch_no` | VARCHAR(50) | NULL | 多批次预留，L1 不用 |
| `is_active` | BOOLEAN | NOT NULL DEFAULT TRUE | 停用为软删，不物理删 |
| `remark` | TEXT | NULL | |
| `created_at` / `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

#### `inventory_categories` 物资分类主数据

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | SERIAL | PK | |
| `name` | VARCHAR(50) | NOT NULL UNIQUE | 分类名，录入时下拉多选 |
| `is_active` | BOOLEAN | NOT NULL DEFAULT TRUE | 停用后不再出现在录入下拉 |
| `remark` | VARCHAR(200) | NULL | |
| `created_at` / `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

#### `inventory_sku_categories` / `inventory_sku_products` 关联

| 表 | 列 | 约束 |
|---|---|---|
| `inventory_sku_categories` | `sku_id` / `category_id` | 复合 PK；两侧 FK ON DELETE CASCADE |
| `inventory_sku_products` | `sku_id` / `product_id` | 复合 PK；两侧 FK ON DELETE CASCADE |

> 分类与产品均为多对多：一个物资可属于多个分类、关联多个产品；纯物资两者都可为空。

#### `inventory_balances` 当前余额快照

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `sku_id` | INT | PK 复合，FK skus ON DELETE CASCADE | |
| `warehouse_id` | INT | PK 复合，FK warehouses ON DELETE RESTRICT | 复合主键为多仓预留 |
| `quantity` | INT | NOT NULL DEFAULT 0 **CHECK (>= 0)** | DB 层堵死负库存 |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

> 余额是流水的派生快照，不是权威账；权威账是 `stock_movements`。二者必须在**同一事务**内更新。

#### `inventory_documents` 单据主表

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | SERIAL | PK | |
| `doc_no` | VARCHAR(32) | NOT NULL UNIQUE | 见 §3.3 |
| `doc_type` | VARCHAR(20) | NOT NULL CHECK IN (`inbound`, `outbound`, `adjust_in`, `adjust_out`) | 方向由类型决定，明细数量恒正 |
| `warehouse_id` | INT | NOT NULL，FK warehouses ON DELETE RESTRICT | |
| `status` | VARCHAR(20) | NOT NULL DEFAULT `'confirmed'` CHECK IN (`confirmed`, `draft`, `pending`, `void`) | **一期只用 confirmed，其余为审批口子** |
| `operator_id` | INT | NULL，FK users ON DELETE SET NULL | 制单人 |
| `confirmed_at` | TIMESTAMPTZ | NULL | L1 = 创建时间 |
| `confirmed_by` | INT | NULL，FK users ON DELETE SET NULL | L1 = operator_id |
| `review_remark` | TEXT | NULL | L1 = NULL，未来审核/驳回意见 |
| `remark` | VARCHAR(500) | NULL | 冲正原因等 |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

#### `inventory_document_items` 单据明细

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | SERIAL | PK | |
| `document_id` | INT | NOT NULL，FK documents ON DELETE CASCADE | |
| `sku_id` | INT | NOT NULL，FK skus ON DELETE RESTRICT | 有单据引用的 SKU 不可删 |
| `quantity` | INT | NOT NULL CHECK (> 0) | 恒正，方向看 doc_type |
| `unit_cost` | NUMERIC(12,2) | NULL | 本次单价，仅留档（见 §3.6） |
| `remark` | VARCHAR(200) | NULL | |

#### `stock_movements` 库存流水（append-only）

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGSERIAL | PK | 流水量大，用 BIGSERIAL |
| `sku_id` | INT | NOT NULL，FK skus ON DELETE RESTRICT | |
| `warehouse_id` | INT | NOT NULL，FK warehouses ON DELETE RESTRICT | |
| `delta` | INT | NOT NULL CHECK (<> 0) | 正入负出 |
| `balance_after` | INT | NOT NULL CHECK (>= 0) | 过账后快照，便于对账 |
| `document_id` | INT | NULL，FK documents ON DELETE SET NULL | |
| `ref_type` / `ref_id` | VARCHAR(30) / VARCHAR(50) | NULL，**不加外键** | 未来接工单/采购单的通用伏笔 |
| `operator_id` | INT | NULL，FK users ON DELETE SET NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

### 3.3 单号规则

`<前缀><YYYYMMDD><4 位当日序号>`，前缀 `RK` 入库 / `CK` 出库 / `PD` 盘盈 / `PK` 盘亏。

生成放 `backend/app/services/inventory/doc_no.py`：先 `pg_advisory_xact_lock(hashtext(prefix || 日期))`，再查当日同前缀最大序号 +1，`lpad(..., 4, '0')`。**与 `backend/app/services/ticket_no.py` 的日期+序号思路一致，但用 advisory lock 避免并发重号**。同一事务内完成，不另建序列表。

### 3.4 完整 DDL（可直接用于 schema.sql 与 005 迁移）

> 复制成 `deploy/migrations/005_inventory.sql` 时，**SQL 内禁止出现百分号字符**（psycopg2 占位符冲突）。下方代码块已规避该字符，`$$` 不受影响。

```sql
-- 005_inventory：全部幂等，可被 migrate.py 重复执行

CREATE TABLE IF NOT EXISTS inventory_warehouses (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(30) NOT NULL UNIQUE,
    name        VARCHAR(50) NOT NULL,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS inventory_skus (
    id            SERIAL PRIMARY KEY,
    sku_no        VARCHAR(50) NOT NULL UNIQUE,
    name          VARCHAR(100) NOT NULL,
    spec          VARCHAR(100),
    unit          VARCHAR(20) NOT NULL DEFAULT '件',
    part_id       INT REFERENCES parts(id) ON DELETE SET NULL,
    warehouse_id  INT NOT NULL REFERENCES inventory_warehouses(id) ON DELETE RESTRICT,
    min_stock     INT NOT NULL DEFAULT 0 CHECK (min_stock >= 0),
    unit_cost     NUMERIC(12,2),
    batch_no      VARCHAR(50),
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    remark        TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS inventory_categories (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(50) NOT NULL UNIQUE,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    remark      VARCHAR(200),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS inventory_sku_categories (
    sku_id       INT NOT NULL REFERENCES inventory_skus(id) ON DELETE CASCADE,
    category_id  INT NOT NULL REFERENCES inventory_categories(id) ON DELETE CASCADE,
    PRIMARY KEY (sku_id, category_id)
);

CREATE TABLE IF NOT EXISTS inventory_sku_products (
    sku_id      INT NOT NULL REFERENCES inventory_skus(id) ON DELETE CASCADE,
    product_id  INT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    PRIMARY KEY (sku_id, product_id)
);

CREATE TABLE IF NOT EXISTS inventory_balances (
    sku_id        INT NOT NULL REFERENCES inventory_skus(id) ON DELETE CASCADE,
    warehouse_id  INT NOT NULL REFERENCES inventory_warehouses(id) ON DELETE RESTRICT,
    quantity      INT NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (sku_id, warehouse_id)
);

CREATE TABLE IF NOT EXISTS inventory_documents (
    id             SERIAL PRIMARY KEY,
    doc_no         VARCHAR(32) NOT NULL UNIQUE,
    doc_type       VARCHAR(20) NOT NULL
                   CHECK (doc_type IN ('inbound','outbound','adjust_in','adjust_out')),
    warehouse_id   INT NOT NULL REFERENCES inventory_warehouses(id) ON DELETE RESTRICT,
    status         VARCHAR(20) NOT NULL DEFAULT 'confirmed'
                   CHECK (status IN ('confirmed','draft','pending','void')),
    operator_id    INT REFERENCES users(id) ON DELETE SET NULL,
    confirmed_at   TIMESTAMPTZ,
    confirmed_by   INT REFERENCES users(id) ON DELETE SET NULL,
    review_remark  TEXT,
    remark         VARCHAR(500),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS inventory_document_items (
    id            SERIAL PRIMARY KEY,
    document_id   INT NOT NULL REFERENCES inventory_documents(id) ON DELETE CASCADE,
    sku_id        INT NOT NULL REFERENCES inventory_skus(id) ON DELETE RESTRICT,
    quantity      INT NOT NULL CHECK (quantity > 0),
    unit_cost     NUMERIC(12,2),
    remark        VARCHAR(200)
);

CREATE TABLE IF NOT EXISTS stock_movements (
    id             BIGSERIAL PRIMARY KEY,
    sku_id         INT NOT NULL REFERENCES inventory_skus(id) ON DELETE RESTRICT,
    warehouse_id   INT NOT NULL REFERENCES inventory_warehouses(id) ON DELETE RESTRICT,
    delta          INT NOT NULL CHECK (delta <> 0),
    balance_after  INT NOT NULL CHECK (balance_after >= 0),
    document_id    INT REFERENCES inventory_documents(id) ON DELETE SET NULL,
    ref_type       VARCHAR(30),
    ref_id         VARCHAR(50),
    operator_id    INT REFERENCES users(id) ON DELETE SET NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_inv_skus_part
    ON inventory_skus(part_id) WHERE part_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_inv_skus_active
    ON inventory_skus(warehouse_id, is_active);
CREATE INDEX IF NOT EXISTS idx_inv_documents_type_time
    ON inventory_documents(doc_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_inv_documents_status
    ON inventory_documents(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_inv_items_doc
    ON inventory_document_items(document_id);
CREATE INDEX IF NOT EXISTS idx_inv_movements_sku_time
    ON stock_movements(sku_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_inv_movements_doc
    ON stock_movements(document_id);
CREATE INDEX IF NOT EXISTS idx_inv_sku_cat_cat
    ON inventory_sku_categories(category_id);
CREATE INDEX IF NOT EXISTS idx_inv_sku_prod_prod
    ON inventory_sku_products(product_id);

-- 新增角色必须放宽既有 CHECK（约束名由 001 迁移固定为 users_role_check）。
-- 注意：009 之后 users.role 列已删除，重放本文件时整段跳过；
-- 白名单用最终角色全集，否则在 008 之后重放会把约束收窄并拒绝 product_planner 行。
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'users' AND column_name = 'role'
    ) THEN
        ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
        ALTER TABLE users ADD CONSTRAINT users_role_check
            CHECK (role IN (
                'super_admin','supervisor','product_planner','agent','auditor',
                'warehouse','warehouse_clerk','warehouse_manager'
            ));
    END IF;
END $$;

INSERT INTO inventory_warehouses (code, name)
VALUES ('DEFAULT', '默认仓')
ON CONFLICT (code) DO NOTHING;

-- 流水只增不改：复用 004_audit_immutable 的触发器范式
CREATE OR REPLACE FUNCTION stock_movements_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION USING
        MESSAGE = '库存流水为只追加（append-only），不允许修改或删除',
        HINT = '如需更正请登记冲正单（反向单据）';
END $$;

DROP TRIGGER IF EXISTS trg_stock_movements_immutable ON stock_movements;
CREATE TRIGGER trg_stock_movements_immutable
    BEFORE UPDATE OR DELETE ON stock_movements
    FOR EACH ROW EXECUTE FUNCTION stock_movements_immutable();

DROP TRIGGER IF EXISTS trg_stock_movements_no_truncate ON stock_movements;
CREATE TRIGGER trg_stock_movements_no_truncate
    BEFORE TRUNCATE ON stock_movements
    FOR EACH STATEMENT EXECUTE FUNCTION stock_movements_immutable();
```

> **`LANGUAGE plpgsql AS $$ ... $$` 内含 `$$`，不含 `%`**，符合"迁移 SQL 禁 %"约束。触发器在超级用户连接下同样生效（004 已验证该思路）。

### 3.5 创建与过账解耦（审批口子的代码实现）

`backend/app/services/inventory/posting.py` 独立模块，router 不得直接写余额：

```python
def create_document(db, payload, user) -> InventoryDocument:
    doc = InventoryDocument(
        doc_no=next_doc_no(db, payload.doc_type),
        doc_type=payload.doc_type,
        status="confirmed",              # L1 恒 confirmed；未来改 draft
        confirmed_at=now(), confirmed_by=user.id,
        operator_id=user.id, ...
    )
    db.add(doc); db.flush()
    db.add_all(build_items(doc, payload.items))
    post_document(db, doc, user)         # ← 未来审批时删掉这行，挪到 confirm 端点
    return doc

def post_document(db, doc, user) -> None:
    if doc.status != "confirmed":
        raise BusinessError("VALIDATION_ERROR", "单据未生效，不能过账", 400)
    # 幂等：同一单据已有流水则直接返回（防重复确认/重复提交）
    if db.scalar(select(func.count()).select_from(StockMovement)
                 .where(StockMovement.document_id == doc.id)):
        return
    sign = 1 if doc.doc_type in ("inbound", "adjust_in") else -1
    for item in doc.items:
        bal = db.execute(
            select(InventoryBalance)
            .where(InventoryBalance.sku_id == item.sku_id,
                   InventoryBalance.warehouse_id == doc.warehouse_id)
            .with_for_update()                       # 行锁，防并发超卖
        ).scalar_one_or_none()
        new_qty = (bal.quantity if bal else 0) + sign * item.quantity
        if new_qty < 0:
            raise BusinessError("INSUFFICIENT_STOCK", "库存不足", 400)  # 整单回滚
        upsert_balance(db, item.sku_id, doc.warehouse_id, new_qty)
        db.add(StockMovement(sku_id=item.sku_id, delta=sign * item.quantity,
                             balance_after=new_qty, document_id=doc.id,
                             operator_id=user.id, ...))
```

`create_document` 与 `post_document` 在**同一个 `db.begin()` 事务**内；任何异常整单回滚，不留半条流水。router 只负责参数校验与调用 service，保持 ≤50 行。

### 3.6 `unit_cost` 的取舍（略反直觉，务必按此实现）

L1 的定位是"只记数量、不做金额账"，但定案稿要求为未来成本账留下历史单价。因此：

- **写**：入库/出库/调整单明细允许**可选**传入 `unit_cost`，前端提供一个标为「单价（选填，仅留档）」的输入框；SKU 上的 `unit_cost` 为参考价。
- **不读**：列表、详情、导出、summary **一律不返回** `unit_cost`；Pydantic 响应 schema 不含该字段。
- **不算**：无总价、无移动加权平均、无成本报表。
- **不控**：`inventory:cost:read` 权限码只登记、不分配、不做字段级权限（见 §6.1）。

这不是漏做读路径，而是刻意让"留档写入"与"金额能力"解耦：将来启用金额账时补读路径与计算即可，历史单价不会缺失。

---

## 4. API 端点清单

统一前缀 `/api/admin/inventory`，**全部需登录**。列表响应 `{total, page, page_size, items}`，`page_size` 最大 100；时间字段用 `AppDateTime`（UTC 存、`+08:00` 输出）；错误体 `{"detail": 中文, "code": 稳定机器码}`。

| # | 方法 | 路径 | 权限码 | 说明 |
|---|---|---|---|---|
| 1 | GET | `/warehouses` | `inventory:sku:read` | 仓库下拉（一期 1 条） |
| 2 | GET | `/skus` | `inventory:sku:read` | SKU 列表；支持 `keyword` / `category_id` / `product_id` / `is_active` / `low_stock` / `part_id` 筛选 |
| 3 | GET | `/skus/{id}` | `inventory:sku:read` | 详情 + 当前余额 + 最近 10 条流水 |
| 4 | POST | `/skus` | `inventory:sku:write` | 新建；`sku_no` 重复 → 409；`category_ids` / `product_ids` 多选 |
| 5 | PUT | `/skus/{id}` | `inventory:sku:write` | 编辑（不可改 `sku_no` / `warehouse_id`）；`is_active=false` 与 DELETE 同规则，有单据引用 → 409 `SKU_IN_USE` |
| 6 | DELETE | `/skus/{id}` | `inventory:sku:write` | **软删**置 `is_active=false`；有单据引用 → 409 `SKU_IN_USE` |
| 7 | GET | `/low-stock` | `inventory:sku:read` | 低库存清单 |
| 8 | GET | `/inbound-orders` | `inventory:inbound:read` | 入库单列表，按 `doc_type='inbound'` 过滤 |
| 9 | GET | `/inbound-orders/{id}` | `inventory:inbound:read` | 详情（含明细） |
| 10 | POST | `/inbound-orders` | `inventory:inbound:write` | 登记入库 |
| 11 | GET | `/outbound-orders` | `inventory:outbound:read` | 出库单列表 |
| 12 | GET | `/outbound-orders/{id}` | `inventory:outbound:read` | 详情（含明细） |
| 13 | POST | `/outbound-orders` | `inventory:outbound:write` | 登记出库；余额不足 → 400 |
| 14 | POST | `/adjustments` | `inventory:adjust:write` | 盘盈/盘亏，`adjust_type: in\|out` |
| 15 | POST | `/documents/{id}/reverse` | `inventory:adjust:write` | 冲正：生成反向单 + 原单置 `void`；并发只允许成功一次（行锁） |
| 16 | GET | `/movements` | `inventory:movement:read` | 流水列表；`sku_id` / `doc_no` / 时间范围筛选；返回 `doc_status`，前端据此隐藏已冲正单据的冲正入口 |
| 17 | GET | `/export` | `inventory:export` | CSV 导出（SKU 余额 + 流水），**不含 `unit_cost`**；超过 5000 行时响应头 `X-Export-Truncated: 1` + `X-Export-Total` |
| 18 | GET | `/summary` | `inventory:sku:read` | 后台首页卡片：SKU 数、低库存数、本月出入库笔数 |
| 19 | GET | `/refs/products` | `inventory:sku:read` | 产品下拉引用（id/名称/型号），**不含运营字段**，仓管可用 |
| 20 | GET | `/refs/parts` | `inventory:sku:read` | 零件下拉引用；`product_id` 可选，省略时一次返回全部零件（含 `product_name`） |
| 21 | GET | `/categories` | `inventory:sku:read` | 物资分类列表（`keyword` / `is_active`） |
| 22 | POST | `/categories` | `inventory:sku:write` | 新建分类；重名 → 409 `CATEGORY_NAME_DUPLICATED` |
| 23 | PUT | `/categories/{id}` | `inventory:sku:write` | 编辑名称/备注/启停；重名 → 409 |
| 24 | PUT | `/documents/{id}` | `inventory:doc:edit` | 主管改已生效入库/出库单：按差额补净更正流水 + 替换明细；已冲正 → 400 |

**为什么按资源拆端点而不做统一 `/documents`**：每个端点挂一个静态 `require(...)` 即可，不需要在 service 里动态判断 `doc_type` 对应哪个权限码。`inbound-orders/{id}` 与 `outbound-orders/{id}` 共用 `inventory_documents` 表，查到单据后校验 `doc_type` 与路径一致，不一致按 `NOT_FOUND` 处理。

**入库 / 出库列表支持的查询参数**：`doc_no`、`status`、`start_date`、`end_date`、`category_id`、`product_id`、`page`、`page_size`。`category_id` 与 `product_id` 都是「单据明细里含任一命中 SKU 即算命中」，两者可叠加（AND）；分类与产品对 SKU 均为多对多，故各追加一次 join。

**请求体示例**（`POST /inbound-orders`）：

```json
{
  "warehouse_id": 1,
  "remark": "采购入库",
  "items": [
    { "sku_id": 12, "quantity": 20, "unit_cost": 35.50 },
    { "sku_id": 15, "quantity": 5 }
  ]
}
```

**响应示例**（201，节选）：

```json
{
  "id": 31,
  "doc_no": "RK202611120001",
  "doc_type": "inbound",
  "status": "confirmed",
  "confirmed_at": "2026-11-12T13:20:00+08:00",
  "confirmed_by": 3,
  "items": [{ "sku_id": 12, "quantity": 20 }, { "sku_id": 15, "quantity": 5 }]
}
```

**分页与校验**：`page >= 1`、`1 <= page_size <= 100`；明细为空 → 400 `INVENTORY_ITEM_EMPTY`；含停用 SKU → 400 `INVENTORY_SKU_INACTIVE`；单据已冲正 → 400 `DOCUMENT_ALREADY_VOIDED`。

---

## 5. 页面清单与交互

| 路由 | 页面文件 | meta.permission | 关键交互 |
|---|---|---|---|
| `/admin/inventory/categories` | `views/admin/inventory/CategoryList.vue` | `inventory:sku:read` | 分类主数据列表、新建/编辑、启停（`home: false`，只进菜单不当落地页） |
| `/admin/inventory/skus` | `views/admin/inventory/SkuList.vue` | `inventory:sku:read` | 分页表格、筛选、低库存标红、新建/编辑 el-dialog、停用二次确认；`part_id` 下拉可留空，零件选项首次展开下拉时一次加载（不按产品 N+1） |
| `/admin/inventory/inbound` | `views/admin/inventory/InboundList.vue` | `inventory:inbound:read` | 列表 + 日期/单号/分类/产品筛选、新建单据（弹窗内先按分类/产品筛候选 SKU，再逐行选）、详情抽屉 |
| `/admin/inventory/outbound` | `views/admin/inventory/OutboundList.vue` | `inventory:outbound:read` | 同上；选 SKU 后实时显示可用余额，库存不足行内报错 |
| `/admin/inventory/movements` | `views/admin/inventory/MovementList.vue` | `inventory:movement:read` | 只读流水、按 SKU/时间/单据筛选、导出按钮（按钮按 `inventory:export` 显隐） |
| `/admin/inventory/adjustments` | `views/admin/inventory/AdjustmentList.vue` | `inventory:adjust:write` | 盘盈/盘亏登记、冲正入口（二次确认 + 原因必填） |

> 出库登记 / 改单弹窗桌面宽度已加到 1000px / 900px；视口 ≤1000px 时自动切紧凑列宽并隐藏「单价（仅留档）」列，1440/1366/1280/1024/900/800 六档宽度下明细表均不横向滚动（E2E 锁定）。改单不做 `unit_cost` 回显，后端按 SKU 沿用旧档案。

**单据弹窗内的物资选择**（2026-11-13 补：用户反馈「逐物资选择，条目特别多时很不容易选中」）：
- 明细表上方固定一行「筛选：关键词 / 分类 / 产品」，与列表页同源，三者可叠加（AND）；**筛选走服务端**——`GET /skus` 的 `page_size` 上限 100，纯前端过滤是在残缺集合里搜，会出现「明明有这个物资却选不到」；
- 关键词匹配 `sku_no` / `name`（后端已有参数），回车或清空触发；分类 / 产品下拉变更即触发；
- 候选被截断时提示「共 N 个物资，仅列出前 100 个，请用关键词 / 分类 / 产品缩小范围」，不能让人误以为物资没建档；
- 切换筛选后，行内**已选中的 SKU 强制保留在候选里**，否则已选值会显示成空白框；
- 改单弹窗里已停用的 SKU 靠单据明细兜底登记（`quantity` 缺省 0，不得覆盖启用清单里的真实余额）；
- 关闭弹窗清空筛选，避免上一单的条件影响下一单。

**菜单**：`Layout.vue` 的 `NAV_ITEMS` 追加 6 项（分类 + SKU + 入库 + 出库 + 流水 + 盘点），按 `hasPermission` 过滤。若侧栏过长，后续可收敛为一个二级菜单，本期不做。

**前端已知坑**（务必遵守，见项目记忆与 `docs/05-评估审查/`）：
- el-dialog 懒渲染，未打开时 `formRef` 为 null，`validate()` 会静默 return → 提交前判空并显式触发；
- 表单标签宽度用 `useFormLabelWidth('88px','120px')`，**禁 auto**；英文标签折行判据 `scrollHeight >= 1.5 × line-height`；
- 禁 `v-html`；E2E 用 `getByRole`，teleport 组件在 `afterEach` unmount；
- 错误文案唯一出口 `utils/error.js#errorMessage()`，中文环境用后端 `detail`。

---

## 6. 权限与角色落地

### 6.1 后端 `backend/app/core/permissions.py`

- `ALL_PERMISSIONS` 追加 11 个码（定案稿 §2.1 的 10 个 + 主管改单 `inventory:doc:edit`）；`inventory:cost:read` **只登记不分配**。
- `ROLE_NAMES` 追加 `"warehouse_clerk": "仓管录入员"` 与 `"warehouse_manager": "仓管主管"`。中文名必须带「仓管」限定词：`supervisor` 已是「售后主管」，裸写「录入员」「主管」两个角色分不清。
- `_ROLE_PERMISSIONS` 按定案稿 §2.2 分配（录入员 8 码；主管 = 录入员全部 + `inventory:doc:edit`）；`_DATA_SCOPE` 中两个仓管角色均取 `ALL`。
- `_DEPENDENCIES` 登记闭包：`*:write` → 对应 `*:read`；`inventory:adjust:write` → `movement:read` + `inbound:read` + `outbound:read`；`inventory:export` → 全部 `:read`。
- 新增角色 `product_planner`（产品计划）：`product:read/write`、`part:read/write`、`product_line:read/write`，是产品 / 零件 / 产品线主数据的**唯一常规写者**。
- `supervisor` 移除 `product:write` / `part:write` / `product_line:write`，保留三个 `:read`；售后台账动作不变。
- `grantable_permissions()` 在原有排除项之外**再排除 `product:write` / `part:write` / `product_line:write`**：主数据单写者，`super_admin` 仅保留自身 break-glass，不通过临时授权转授。
- 迁移 008 会收回既有的未过期主数据写临时授权，避免历史授权绕过新边界。
- 账号采用多角色：角色存 `user_roles(user_id, role)`，一人可多岗；生效权限为全部角色模板权限的并集，数据范围任一角色为 `ALL` 即 `ALL`。旧 `users.role` 列在迁移 009 中回填后删除，接口保留派生的 `role` 字段仅作兼容展示。
- 迁移 009 会把存量单角色回填到 `user_roles`，并删除 `users.role` 与旧 CHECK；`schema.sql` 修订号 → v1.6。

**数据范围**：库存域统一 `ALL`，在 service 层显式写死，**不得复用 `apply_ticket_scope`**（它按产品线过滤，纯物资 `part_id` 为空会导致谁都看不见）。

### 6.2 既有文件改动清单

| 文件 | 改动 |
|---|---|
| `deploy/schema.sql` | 新增 `user_roles` 多角色表（v1.6）；7 角色 CHECK 落在 `user_roles.role`；追加 9 张库存表与流水触发器；登记 `005` / `006` / `007` / `008` / `009`；修订号 → v1.6 |
| `deploy/migrations/005_inventory.sql` | 6 张库存表 + 默认仓 + append-only 触发器（幂等） |
| `deploy/migrations/006_warehouse_roles.sql` | `warehouse` 拆为 `warehouse_clerk` / `warehouse_manager`，旧账号升级为主管 |
| `deploy/migrations/007_inventory_categories.sql` | 分类主数据 + 两张多对多关联；删旧 `category` 列前先回填分类 |
| `deploy/migrations/008_product_planner.sql` | 角色 CHECK 放宽到 7 角色；收回既有主数据写临时授权 |
| `deploy/migrations/009_multi_role.sql` | 新建 `user_roles`；回填存量单角色；删除 `users.role` 与旧 CHECK（幂等） |
| `frontend/src/locales/{zh-CN,en-US}/common.js` | `role.warehouse_clerk` / `role.warehouse_manager` / `role.product_planner` + `roleGroup.master` |
| `frontend/src/utils/roles.js` | `ROLE_KEYS` / `ROLE_GROUPS` / `usesProductLines`（角色唯一来源，含 product_planner） |
| `frontend/src/utils/permissionLabels.js` | 追加 11 个 `permission.*` key 映射 |
| `frontend/src/locales/{zh-CN,en-US}/permission.js` | 追加 11 个权限名 |
| `frontend/src/locales/{zh-CN,en-US}/error.js` | 追加本文 §7 列出的 7 个错误码文案 |
| `frontend/src/locales/{zh-CN,en-US}/admin.js` | `admin.nav.inventory*` 6 项 + `admin.page.inventory*` 6 项 + 4 个菜单分组标题 |
| `frontend/src/locales/{zh-CN,en-US}/admin-inventory.js` | **新建**，6 个页面的全部业务文案 + 缺档提示 |
| `frontend/src/locales/{zh-CN,en-US}/index.js` | 注册 `admin.inventory = adminInventory` |
| `frontend/src/router/index.js` | 追加 6 条后台子路由 + `meta.permission` |
| `frontend/src/views/admin/Layout.vue` | `NAV_ITEMS` 追加 6 项；侧栏分为售后 / 主数据 / 进销存 / 系统四组 |
| `frontend/src/views/admin/inventory/SkuList.vue` / `faults/FaultEdit.vue` | 产品/零件缺档时提示联系产品/计划岗 |
| `backend/app/services/audit.py` | `_RULES` 补 11 行、`_NAME_FIELDS` 加 3 项（见 §9） |
| `backend/app/api/admin_inventory*.py` | 3 个 router，共 24 个端点（§4） |
| `backend/app/models/__init__.py` | 注册 9 个新模型，注释「11 张表」→「21 张业务表」 |
| `backend/app/schemas/user.py` | `ROLE_VALUES` whitelist 为 7 个角色 |
| `backend/tests/test_permissions.py` / `frontend/src/utils/permissionLabels.spec.js` / `frontend/src/views/admin/users/UserList.spec.js` | 基线断言同步：角色闭包循环加仓管/产品计划角色；grantable 等式排除 6 码；权限码清单 16→27；角色下拉 4→7 |
| `frontend/src/views/admin/users/UserList.vue` | 授权下拉改由 `GET /admin/permissions/grantable` 提供，与后端 `grantable_permissions()` 单一来源 |
| `backend/tests/test_inventory_permissions.py` | **新建**（任务卡 #2 验收）：11 码登记、7 角色矩阵、依赖闭包封闭、仓管数据范围 ALL、grantable 6 类排除，纯函数无需 db |

> 新增语言包必须**两个 `index.js` 都注册**，否则界面文案取不到 key。
> 注意 `check_i18n.py` 只查硬编码中文，**不做键集合校验**——双语对称由
> `frontend/src/locales/locale.spec.js` 双向断言（zh 有 en 无 / en 有 zh 无都会红）。

---

## 7. 错误码（登记到 API 契约 §8）

| HTTP | code | 含义 | 前端处理 |
|---|---|---|---|
| 400 | `INSUFFICIENT_STOCK` | 出库/盘亏后余额为负 | 明细行内联报错，显示当前余额，刷新余额 |
| 400 | `INVENTORY_ITEM_EMPTY` | 单据无明细行 | 高亮明细表格 |
| 400 | `INVENTORY_SKU_INACTIVE` | 明细包含已停用 SKU | 提示移除该行 |
| 400 | `DOCUMENT_ALREADY_VOIDED` | 单据已冲正，不可重复操作 | 刷新详情 |
| 409 | `SKU_NO_DUPLICATED` | SKU 编码重复 | 编码输入框内联报错 |
| 409 | `SKU_IN_USE` | SKU 被单据引用，不可停用（DELETE 与 PUT `is_active=false` 同规则） | 展示 `detail` 中的引用统计 |
| 409 | `CATEGORY_NAME_DUPLICATED` | 物资分类名称重复（POST / PUT） | 名称输入框内联报错 |

**复用不新增**：`NOT_FOUND`（资源不存在/单据类型不匹配）、`VALIDATION_ERROR`（Pydantic / 参数语义）、`PERMISSION_DENIED`、`DELETE_BLOCKED`。定案稿草案中的 `SKU_NOT_FOUND` **不新增**，统一用 `NOT_FOUND`，避免错误码膨胀。

新码必须同时进 `zh-CN/error.js` 与 `en-US/error.js`；`frontend/src/locales/locale.spec.js` 会扫描后端 `BusinessError` 码做比对，**漏一个就红**。带参数的码（本批无）需与 `params` 插值占位符一致。

> **登记时序（任务卡 #3 实测补记）**：`locale.spec.js` 另有一条反向校验——「前端字典里没有后端已经不用的码」，
> 所以前端文案**不能先于**后端 `BusinessError` 落地。任务卡 #3 已把 service 实际抛出的 5 个码
> 登记进契约 §8 与两套 `error.js`：`INSUFFICIENT_STOCK`、`INVENTORY_ITEM_EMPTY`、
> `INVENTORY_SKU_INACTIVE`、`DOCUMENT_ALREADY_VOIDED`、`SKU_IN_USE`。
> 第 6 个 `SKU_NO_DUPLICATED` 在任务卡 #4 的 `POST /skus` 端点真正 `raise` 后已补进两套 `error.js`
> （`_ensure_sku_no_available()` + `IntegrityError` 兜底），六个码至此全部登记完成。
> 任务卡 #5 只做审计规则与复核，不重复登记错误码。
>
> **任务卡 #5 复核结论**：三方一致 —— 契约 §8（6 行）、`zh-CN/en-US/error.js`（各 6 个 key）、
> 后端实际 `raise` 的 6 个码（`posting.py` 5 个 + `admin_inventory_skus.py` 的 `SKU_NO_DUPLICATED`）
> 完全对齐，无遗漏、无多余；通用码 `VALIDATION_ERROR` / `NOT_FOUND` / `INTERNAL_ERROR` 沿用既有登记，
> `locale.spec.js` 双向校验通过。

---

## 8. 国际化

- 新增 `admin-inventory.js`（中/英各一份），命名空间 `admin.inventory.*`，两个 `index.js` 均注册。
- 所有业务文案只走 `t('admin.inventory.xxx')`，**禁拼 key、禁硬编码中文**（`check_i18n.py` 退出码 1）。
- 后台默认中文、不跟随 navigator；错误文案唯一出口 `utils/error.js#errorMessage()`。
- 权限名、角色名、错误码名、菜单名、页面标题全部双语（§6.2）。
- 闸门：`python scripts/dev/check_i18n.py` + `frontend/e2e/i18n-layout.spec.js`（英文界面表单标签不折行，`useFormLabelWidth('88px','120px')`）。
- URL 拼接一律用 `localeHref()`；本模块纯后台，无 `/en` 客户侧路径。

---

## 9. 审计留痕

`backend/app/services/audit.py` 的 `_RULES` 追加（零侵入，不写 router 埋点）：

```python
(r"POST", r"^/api/admin/inventory/skus$", "inventory.sku.create", "inventory_sku", None),
(r"PUT", r"^/api/admin/inventory/skus/(?P<id>\d+)$", "inventory.sku.update", "inventory_sku", "id"),
(r"DELETE", r"^/api/admin/inventory/skus/(?P<id>\d+)$", "inventory.sku.disable", "inventory_sku", "id"),
(r"POST", r"^/api/admin/inventory/categories$", "inventory.category.create", "inventory_category", None),
(r"PUT", r"^/api/admin/inventory/categories/(?P<id>\d+)$", "inventory.category.update", "inventory_category", "id"),
(r"POST", r"^/api/admin/inventory/inbound-orders$", "inventory.inbound.create", "inventory_document", None),
(r"POST", r"^/api/admin/inventory/outbound-orders$", "inventory.outbound.create", "inventory_document", None),
(r"POST", r"^/api/admin/inventory/adjustments$", "inventory.adjust.create", "inventory_document", None),
(r"POST", r"^/api/admin/inventory/documents/(?P<id>\d+)/reverse$", "inventory.document.reverse", "inventory_document", "id"),
(r"PUT", r"^/api/admin/inventory/documents/(?P<id>\d+)$", "inventory.document.edit", "inventory_document", "id"),
(r"GET", r"^/api/admin/inventory/export$", "inventory.export", "inventory", None),
```

`_NAME_FIELDS` 追加：

```python
"inventory_sku": (InventorySku, "name"),
"inventory_category": (InventoryCategory, "name"),
"inventory_document": (InventoryDocument, "doc_no"),
```

`known_actions()` 自动带出 `inventory.*` 分组，筛选下拉的**选项**无需改动；但 `AuditLogList.vue` 的 `ACTION_KEYS` 是硬编码映射，新动作必须同步补文案（见下方实测补记），否则列表与下拉全显示「其他操作」。审计失败不得影响业务（现有中间件已整段 try 包住，**勿回退**）。单据表自带的 `operator_id` 与审计表职责不同：前者是业务数据（谁出的库），后者是安全留痕（含 IP、request_id，403 也记），**两者都做**。

> **任务卡 #5 实测补记**：`_RULES` 11 行 + `_NAME_FIELDS` 3 项已落地（`backend/app/services/audit.py`）。
> 规则表决定「哪些请求进审计表」，是零侵入的一层；任务卡 #4 的 router 里另外写了
> `request.state.audit` 埋点补 `target_name`（如 `doc.doc_no`、SKU 编码），两者不冲突、互为补充：
> 埋点让 `target_name` 在对象被删后仍冗余可追，`_NAME_FIELDS` 则是 `target_name` 缺失时的兜底。
> 验收见 `backend/tests/test_inventory_audit.py`（21 项：11 条规则命中、读路径不产生噪声、
> `known_actions()` 带出 11 个 `inventory.*`、按 id 兜底取名、SKU 建单/单据建单/导出落库、403 失败留痕）。
>
> **另修正 §9 正文的一处不严谨**：下拉选项虽由 `known_actions()` 自动带出，但 `actionLabel()` 走的
> `ACTION_KEYS` 是硬编码映射，11 个 `inventory.*` 原本会全部落到 `unknown`（「其他操作」）。
> 任务卡 #5 已补 `AuditLogList.vue` 11 行映射 + `zh-CN/en-US/admin-audit.js` 各 11 个文案 key，
> 并加 `AuditLogList.spec.js` 防回归测试（断言 11 个动作映射存在且两套语言包都有对应文案）。
> 这属于「新动作码必须在前台可读」，不是任务卡 #6 的 6 个新页面范围。

---

## 10. 迁移与部署

### 10.1 两个文件必须同步

| 文件 | 用途 | 改动 |
|---|---|---|
| `deploy/migrations/005_inventory.sql` | 已有环境升级 | 6 张库存表 + 默认仓 + append-only 触发器，全部幂等 |
| `deploy/migrations/006_warehouse_roles.sql` | 角色拆分 | 旧 `warehouse` 账号升级为 `warehouse_manager`，CHECK 放宽 |
| `deploy/migrations/007_inventory_categories.sql` | 分类主数据 | 建分类/关联表；**先回填旧 `category` 再删列** |
| `deploy/migrations/008_product_planner.sql` | 主数据角色 | 角色 CHECK 放宽到 7 角色；收回既有主数据写临时授权 |
| `deploy/migrations/009_multi_role.sql` | 一人多岗 | 建 `user_roles`、回填既有角色、删除 `users.role`（发布时必须先停旧 backend） |
| `deploy/schema.sql` | 全新库 initdb 一次建到最新 | 同步 9 张库存表 DDL + `user_roles` + 触发器 + 登记 `005`–`009` |

`migrate.py` 用 `path.stem`（如 `005_inventory`）作版本号；全新库的 `schema.sql` 必须显式登记 `005`–`009`，否则 migrate 会在全新库上再跑一遍。五个迁移本身也写成幂等（005/006 的角色 DDL 用 `information_schema.columns` 判存在性，009 删列后重放会整段跳过），双保险。

### 10.2 迁移硬约束

- **SQL 内禁止出现 `%`**（psycopg2 占位符冲突）——§3.4 已规避，`$$` 不受影响。
- 全部 `CREATE TABLE/INDEX IF NOT EXISTS`、`DROP CONSTRAINT/TRIGGER IF EXISTS`、`ON CONFLICT DO NOTHING`。
- 角色 CHECK 的变更一律包在 `DO $$ ... IF EXISTS (SELECT 1 FROM information_schema.columns WHERE ... column_name='role') ... END $$` 里：009 删列后重放 005/006/008 必须整段跳过，否则报 `column "role" does not exist`。约束名沿用 001 迁移的先例，固定为 `users_role_check`。
- 验证：`docker compose run --rm migrate` **连跑两次均成功且第二次显示"没有待执行的迁移"**。

### 10.3 镜像（方案 B）— 未落地，待补

**当前仓库里没有镜像化产物**：`deploy/` 下只有 `docker-compose.yml`、`docker-compose.test.yml`、`deploy.sh`、`deploy-test.sh`。生产发布走 `deploy.sh` 在**服务器上就地 `docker compose build`**（build context 指向仓库根），也就是源码需要在构建机上。

这与「部署单元只能是构建物、源码不出构建机」的硬约束冲突，属于**已知缺口**，不是已完成项：

- 待补：`docker-compose.prod.yml`（全 `image:`）、`build-and-push.sh`、`deploy-remote.sh`；
- 待补：把 `migrate` / `migrations` 烤进 backend 镜像、`schema.sql` 烤进 db 镜像；
- 在那之前，生产发布仍然依赖服务器上有源码，不能对外宣称「源码不出构建机」。

---

## 11. 演示数据

`scripts/dev/demo_inventory.py`（沿用 `demo_data.py` / `seed_demo.py` 风格，支持 `--reset`）：

- 默认仓 1 条；
- SKU 20 条：12 条关联现有 `parts`（含「一零件多 SKU」2 组）、8 条纯物资（`part_id` 为空），覆盖两类输入；
- 余额：其中 3 条低于 `min_stock`，用于低库存标红；
- 单据 22 张（入库 8 / 出库 12 / 调整 2），47 条明细；流水由过账逻辑生成，**不手工插流水**；
- 全部走 service 层写入，保证 `balance_after` 与流水自洽，可直接用于对账测试。

> **任务卡 #7 已落地并验完（2026-11-13）**。实现要点与「走 service 层」的口径说明：
> - **写入路径是后台 API**（`httpx` → nginx `:80` → 端点），端点内部即 `create_document()` → `post_document()`，
>   与「走 service 层」等价且更强：顺带验证了鉴权、Pydantic 校验、单号、行锁过账、审计留痕全链路。
>   脚本**不直接连库写任何业务表**，余额与流水完全由过账逻辑生成。
>   db 端口未映射到宿主机，故 `--reset` / 对账走 `docker compose exec -T db psql`（与 `seed_demo.py` 一致）。
> - 数据本体是 `SKU_SPECS` / `DOCUMENT_PLAN` 两个常量，**确定性可复现、不用随机**；
>   `simulate()` 在写库前按同一份计划推演余额，任何出库超卖会提前失败，并断言恰好 3 条低库存。
> - `--reset` 清 5 张业务表（保留默认仓）。`stock_movements` 有**两个** append-only 触发器
>   （行级 UPDATE/DELETE + 语句级 TRUNCATE），故在同一事务里 `DISABLE TRIGGER USER` → TRUNCATE →
>   `ENABLE TRIGGER USER`；失败回滚时触发器自动恢复（同 `cleanup-audit.sh` 范式）。
>   已实测 reset 后两触发器均为 `O`（启用），且 DELETE / TRUNCATE 均被拒绝。
> - `--verify` 只做纯对账（Σ`delta` 按 `(sku_id, warehouse_id)` 分组 == `balances.quantity`，
>   `FULL JOIN` 同时暴露「有流水没余额」与「有余额没流水」两种缺口），不检查演示数据内容规格；
>   写入完成后才额外校验低库存 3 条。不带参数重复运行会检测已有流水并跳过写入，避免重复过账。
> - 口令用 `ADMIN_PASSWORD` 环境变量或 `deploy/.env` 的 `ADMIN_INIT_PASSWORD`，**不硬编码进仓库**；
>   本机两者不一致时需 `ADMIN_PASSWORD=真实口令` 覆盖。
> - 实测：20 SKU（8 纯物资）· 仓库 1 · 单据 22（全 `confirmed`、`confirmed_by` 非空）·
>   明细 47 · 流水 47 · 低库存 3 · **对账 0 处不一致**；重复 `--reset` 可重入；
>   `TRUNCATE ... CASCADE` 未误伤故障域（4 产品 / 42 零件 / 51 故障 / 37 工单 / 3 用户不变）。

---

## 12. 测试用例清单

### 后端 pytest

| 组 | 用例要点 |
|---|---|
| SKU | CRUD、`sku_no` 重复 409、软删、被引用 409、停用 SKU 入单 400 |
| 弱关联 | `part_id` 为空的纯物资可建/可查/可出入库；一个 part 对应多个 SKU |
| 入库 | 余额增加、流水 `delta`/`balance_after` 正确、单号格式与当日序号 |
| 出库 | 余额减少；**库存不足整单回滚**（余额与流水都不变） |
| 并发 | 两会话同时扣同一 SKU，最终余额正确（`SELECT ... FOR UPDATE`；SQLite 单测不支持行锁时标记跳过，留 PG 集成测） |
| 冲正 | 生成反向单、原单 `void`、重复冲正 400、流水条数只增 |
| append-only | 对 `stock_movements` 的 UPDATE/DELETE/TRUNCATE 被触发器拒绝（PG 环境） |
| 权限 | 11 码 × 7 角色矩阵；403 `PERMISSION_DENIED`；`adjust:write` / 主数据三写码不在 `grantable_permissions()`；product_planner 可写主数据、supervisor 403 |
| 数据范围 | 库存域不受 `LINES` 影响；`agent` 无菜单权限 |
| 契约 | 分页 `{total,page,page_size,items}`、`page_size=101` 截断、时间 `+08:00` |
| **防回归** | L1 单据 `status == 'confirmed'`、`confirmed_by` 非空、流水条数 = 明细条数（防未来改默认值忘接审核流） |

> ⚠ pytest **函数重名会静默覆盖**，新测试文件命名加 `inventory_` 前缀。
> `UserList.spec.js`（任务卡 #3）与 `TicketList.spec.js`（任务卡 #5）的基线失败同源：
> `attachTo: document.body` 挂载后未卸载，Element Plus teleport 逐条堆积导致 5s 超时。
> 两处均已加 `afterEach` 集中 `unmount()` + 清空 body，前端测试稳定 **247/247**；**勿回退**该卸载逻辑。

### 前端 vitest

6 个页面渲染与权限按钮显隐、`permissionLabels.js` 11 个 key、语言包键集合一致、表单校验（注意 el-dialog 懒渲染坑）、`useFormLabelWidth` 未用 auto。

> **任务卡 #6 已完成并验完（2026-11-12）**：6 个页面（CategoryList / SkuList / InboundList / OutboundList / MovementList / AdjustmentList）+ 路由 + 菜单 + `admin-inventory` 双语语言包；`DocumentList.vue` 复用件覆盖入库/出库列表+建单+详情，`MovementTable.vue` 复用件覆盖流水页与调整页「近期变动（可冲正）」，`ReverseDialog.vue` 统一冲正（二次确认 + 原因必填）。新增 `inventoryPages.spec.js` 冒烟用例（6 个页面挂载 + 冲正原因必填）全绿，当前前端全量 **270/270**、`npm run build` 通过、`check_i18n / check_links / check_duplicate_tests` 全过。SKU 默认单位 `'件'` 加 `i18n-ignore`（数据字段默认值，非界面文案）。
> **冲正入口分布（已知约束）**：详情面板（入库/出库）与调整页的近期变动表格两处均可触发；后端 `POST /documents/{id}/reverse` 对任意 `doc_type` 通用，故调整单冲正经其生成的流水行触发即可（调整单本身无 GET 列表端点，这是 PRD §4「24 端点」范围内的固有限制，非缺陷）。

### E2E

仓管登录 → 建 SKU → 入库 → 出库 → 查流水；库存不足报错；英文界面标签不折行；`agent` 看不到库存菜单。

### 闸门

```bash
cd frontend && npm run lint && npm run test && npm run e2e
python scripts/dev/check_i18n.py && python scripts/dev/check_links.py && python scripts/dev/check_duplicate_tests.py
.venv/bin/python -m pytest backend/tests -q
```

改前端后 `docker compose build frontend && up -d frontend`（产物在镜像）；`export TMPDIR=$PWD/.tmp`（/tmp 仅 10MB）。

---

## 13. 任务卡与工作量

| # | 任务 | 人天 | 依赖 |
|---|---|---|---|
| 1 | DDL + `005_inventory.sql` + `schema.sql` 同步 + 6 个 models | 1.5 | — |
| 2 | 权限体系接入（后端 5 处 + role CHECK + 前端角色/标签/双语） | 1.0 | 1 |
| 3 | service：`doc_no`、create/post 解耦、行锁过账、幂等、冲正 | 2.0 | 1 |
| 4 | 24 个端点 + Pydantic schemas + router（≤50 行） | 2.0 | 2, 3 |
| 5 | 审计规则、§8 错误码登记、双语错误映射 | 0.5 | 4 |
| 6 | 前端 5 页面 + 路由 + 菜单 + `admin-inventory` 语言包 | 3.0 | 4 |
| 7 | 演示数据脚本 | 0.5 | 3 |
| 8 | 测试：后端 / 前端 / E2E / 闸门 | 2.0 | 4, 6 |
| 9 | 联调 + 镜像构建 + 迁移幂等验证 | 1.5 | 全部 |
| | **合计** | **14.0** | |

与定案稿 10–14 人天一致（取上限，因权限分细到 10 码、双语登记面较广）。2 人并行约 **1.5 周**。

> **进度（2026-11-13）**：任务卡 **#1–#9 已全部落地并逐卡验完**。
> - #8 测试闸门全绿：后端 pytest `EXIT=0`（0 失败，含库存 4 文件 55 项）；前端 vitest **257/257** + `lint` 0 错误；E2E 主链路 **14 passed**；`check_i18n`(58 文件) / `check_links`(569 引用 0 无法解析) / `check_duplicate_tests`(26 文件 0 重名) 三项全过；英文 5 页用 `useFormLabelWidth(zh,en)` 动态宽度，E2E `i18n-layout` 已验证标签不折行、弹窗不横向溢出。
> - #9 联调与交付：migrate 连跑两次幂等（均为「没有待执行的迁移」）；全新库由 `schema.sql` 直接起服建 21 表（含 inventory 5 表及 append-only 触发器）；`docker compose build` 重建镜像 + `up -d` 后 4 容器 healthy；`deploy.sh --check` 体检通过（`/health` 200、SPA 200、API 401）。
> #7 的实现与实测数据见 §11 注记。

---

## 14. 交付关卡

1. 后端全量测试**零回归** + 新增库存测试全绿；前端全量测试零新增失败；E2E 冒烟通过。
2. `check_i18n.py` / `check_links.py` / `check_duplicate_tests.py` 全过；`locale.spec.js` 错误码比对通过。
3. `docker compose run --rm migrate` 连跑两次幂等；全新库由 `schema.sql` 直接起服。
4. 英文界面 6 个页面表单标签不折行，`useFormLabelWidth('88px','120px')`。
5. 主数据权限：product_planner 可维护产品/零件/产品线；supervisor 写主数据返回 403；仓管仍只读引用；主数据写不在临时授权清单。
6. 演示数据可对账：Σ`stock_movements.delta` 按 SKU 分组 == `inventory_balances.quantity`。
7. 镜像重新构建并部署验证（方案 B），`deploy.sh --check` 通过。

> 本文为可开发版 PRD，需求侧全部收口：§3.6 的 `unit_cost`「可选写入留档、不返回、不计算」取舍已于 2026-11-12 经用户确认（「反直觉没关系」），按此实现即可。
