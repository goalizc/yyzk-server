-- 007_inventory_categories：物资分类主数据 + SKU↔分类 + SKU↔产品 多对多
-- 全部幂等，可被 deploy/scripts/migrate.py 重复执行。
-- 与 deploy/schema.sql v1.4 一一对应；全新库由 schema.sql 直接落到最新结构。
-- 注意：本文件内禁止出现百分号字符（psycopg2 占位符冲突）。

-- 物资分类主数据
CREATE TABLE IF NOT EXISTS inventory_categories (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(50) NOT NULL UNIQUE,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    remark      VARCHAR(200),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 物资 ↔ 分类（多对多：一个物资可属于多个分类）
CREATE TABLE IF NOT EXISTS inventory_sku_categories (
    sku_id       INT NOT NULL REFERENCES inventory_skus(id) ON DELETE CASCADE,
    category_id  INT NOT NULL REFERENCES inventory_categories(id) ON DELETE CASCADE,
    PRIMARY KEY (sku_id, category_id)
);

-- 物资 ↔ 产品（多对多：镜像零件↔产品，关联售后系统但不强制）
CREATE TABLE IF NOT EXISTS inventory_sku_products (
    sku_id      INT NOT NULL REFERENCES inventory_skus(id) ON DELETE CASCADE,
    product_id  INT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    PRIMARY KEY (sku_id, product_id)
);

CREATE INDEX IF NOT EXISTS idx_inv_sku_cat_cat ON inventory_sku_categories(category_id);
CREATE INDEX IF NOT EXISTS idx_inv_sku_prod_prod ON inventory_sku_products(product_id);

-- 旧自由文本大类字段下线前先回填：先按 DISTINCT 值建分类，再挂到 SKU 上，
-- 最后才删列。直接 DROP 会让历史 SKU 的分类永久丢失（审查 Q1）。
-- 列不存在（全新库由 schema.sql 建成最新结构）时整段跳过，保持幂等。
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'inventory_skus'
          AND column_name = 'category'
    ) THEN
        INSERT INTO inventory_categories (name)
        SELECT DISTINCT btrim(category)
        FROM inventory_skus
        WHERE category IS NOT NULL AND btrim(category) <> ''
        ON CONFLICT (name) DO NOTHING;

        INSERT INTO inventory_sku_categories (sku_id, category_id)
        SELECT s.id, c.id
        FROM inventory_skus s
        JOIN inventory_categories c ON c.name = btrim(s.category)
        WHERE s.category IS NOT NULL AND btrim(s.category) <> ''
        ON CONFLICT DO NOTHING;
    END IF;
END $$;

ALTER TABLE inventory_skus DROP COLUMN IF EXISTS category;
