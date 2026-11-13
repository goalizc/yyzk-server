-- 005_inventory：进销存模块（6 张表 + warehouse 角色 + 流水 append-only）
-- 全部幂等，可被 deploy/scripts/migrate.py 重复执行。
-- 与 deploy/schema.sql v1.3 一一对应；全新库由 schema.sql 直接建到最新结构。
-- 注意：本文件内禁止出现百分号字符（psycopg2 占位符冲突）。

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
    category      VARCHAR(50),
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

-- 新增仓管角色：约束名由 001_user_permissions.sql 固定，沿用其先例
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
ALTER TABLE users ADD CONSTRAINT users_role_check
    CHECK (role IN ('super_admin','supervisor','agent','auditor','warehouse'));

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
