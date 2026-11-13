-- ============================================================
-- 售后自助故障诊断系统 - 数据库建表脚本
-- PostgreSQL 15+
-- 修订：v1.6  2026-11-13（多角色：user_roles 唯一来源）
--   v1.1 变更：删假哈希、加 need_on_site、RESTRICT、TIMESTAMPTZ、
--             ticket_status_logs 替 attachments、去无效 GIN 索引
--   v1.2 变更：
--     1) 删除故障时，tickets/query_logs 的 fault_id 置 NULL（原为 NO ACTION，
--        契约说置 NULL 但外键会直接报错）
--     2) 删除工单/日志引用的产品、零件时置 NULL，避免删除产品 500
--     3) faults.part_id 改 NOT NULL（PRD 要求零件必选，原可空导致数据在
--        前台永远查不到）
--     4) 工单号序号改 4 位并加格式 CHECK（原 3 位在 1000 单后字典序比较失效）
--     5) 补 char_length 约束，避免超长数据落库后 500
--     6) 补 (status, created_at) 与未命中表达式索引；删除与 UNIQUE 重复的
--        idx_tickets_no
--     7) 创建 pg_stat_statements 扩展（仅 preload 库不会自动建扩展）
--   v1.3 变更（与 deploy/migrations/005_inventory.sql 同步）：
--     1) users.role 的 CHECK 增加 'warehouse'（仓管）
--     2) 新增 6 张表：inventory_warehouses / inventory_skus /
--        inventory_balances / inventory_documents /
--        inventory_document_items / stock_movements
--     3) stock_movements 挂 append-only 触发器（UPDATE/DELETE/TRUNCATE 拒绝）
--     4) 插入默认仓 DEFAULT；登记迁移版本 005_inventory
--   v1.4 变更（与 deploy/migrations/006_warehouse_roles.sql、
--     007_inventory_categories.sql 同步）：
--     1) users.role 的 CHECK 由 'warehouse' 改为 'warehouse_clerk'（录入员）
--        与 'warehouse_manager'（主管），原 warehouse 账号升级为主管
--     2) 新增 inventory_categories / inventory_sku_categories /
--        inventory_sku_products 三张表；inventory_skus 去掉自由文本 category
--     3) 新增权限码 inventory:doc:edit（仅 warehouse_manager 具备）
--     4) 登记迁移版本 006_warehouse_roles / 007_inventory_categories
--   v1.5 变更（与 deploy/migrations/008_product_planner.sql 同步）：
--     1) users.role 增加 'product_planner'（产品计划）
--     2) 该角色是产品/零件/产品线主数据的唯一常规写者，
--        售后与物资只读引用；主数据写权限不进入临时授权
--     3) 登记迁移版本 008_product_planner
--   v1.6 变更（与 deploy/migrations/009_multi_role.sql 同步）：
--     1) 新增 user_roles(user_id, role)，作为账号角色的唯一来源
--     2) 删除 users.role 单角色列，权限与数据范围按多角色并集计算
--     3) 登记迁移版本 009_multi_role
--
-- ⚠ 本脚本仅在数据卷为空时由 initdb 执行一次，直接建到最新结构；
--    已有环境的升级由 deploy/migrations 下的迁移文件完成（migrate.py 按版本执行）。
-- ============================================================

-- 扩展：用于 gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
-- 慢查询统计（docker-compose 已在 shared_preload_libraries 中预加载）
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- ------------------------------------------------------------
-- 0. 迁移登记（已有环境升级用；全新库由本脚本直接建到最新结构）
-- ------------------------------------------------------------
CREATE TABLE schema_migrations (
    version    VARCHAR(50) PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO schema_migrations (version) VALUES ('000_baseline');

-- ------------------------------------------------------------
-- 1. 后台用户表（仅在册内部人员，账号可界面维护）
-- ------------------------------------------------------------
CREATE TABLE users (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(200) NOT NULL,
    real_name     VARCHAR(50) NOT NULL,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    token_version INT NOT NULL DEFAULT 0,
    last_login_at TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_users_username_lower ON users (LOWER(username));
-- 说明：账号可界面维护，init_admin.py 与运维 SQL 保留为兜底入口；
--       「修改自己密码」走 API 完成。

-- 1.1 用户角色（一人可多岗；角色是权限与数据范围的唯一来源）
CREATE TABLE user_roles (
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role    VARCHAR(20) NOT NULL
            CHECK (role IN ('super_admin', 'supervisor', 'product_planner', 'agent', 'auditor', 'warehouse_clerk', 'warehouse_manager')),
    PRIMARY KEY (user_id, role)
);
CREATE INDEX idx_user_roles_role ON user_roles(role);

-- ------------------------------------------------------------
-- 2. 产品线表（客服数据范围按产品线划分）
-- ------------------------------------------------------------
CREATE TABLE product_lines (
    id         SERIAL PRIMARY KEY,
    name       VARCHAR(50) NOT NULL UNIQUE,
    sort_order INT NOT NULL DEFAULT 0,
    is_active  BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------
-- 3. 用户产品线授权
-- ------------------------------------------------------------
CREATE TABLE user_product_lines (
    user_id    INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    line_id    INT NOT NULL REFERENCES product_lines(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ,
    PRIMARY KEY (user_id, line_id)
);
CREATE INDEX idx_user_product_lines_line ON user_product_lines(line_id);

-- ------------------------------------------------------------
-- 4. 用户临时权限授权
-- ------------------------------------------------------------
CREATE TABLE user_permission_grants (
    id          SERIAL PRIMARY KEY,
    user_id     INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    permission  VARCHAR(30) NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    reason      VARCHAR(200) NOT NULL,
    granted_by  INT REFERENCES users(id) ON DELETE SET NULL,
    granted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at  TIMESTAMPTZ
);
CREATE INDEX idx_user_grants_active ON user_permission_grants (user_id, expires_at)
    WHERE revoked_at IS NULL;

-- ------------------------------------------------------------
-- 5. 产品表
-- ------------------------------------------------------------
CREATE TABLE products (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    model       VARCHAR(50) NOT NULL UNIQUE,
    line_id     INT NOT NULL REFERENCES product_lines(id) ON DELETE RESTRICT,
    description TEXT,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order  INT NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_products_active ON products(is_active);
CREATE INDEX idx_products_line ON products(line_id);

-- ------------------------------------------------------------
-- 6. 零件表（归属产品）
--    ON DELETE RESTRICT：产品下还有零件时禁止删除产品（API 返回 409）
-- ------------------------------------------------------------
CREATE TABLE parts (
    id          SERIAL PRIMARY KEY,
    product_id  INT NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    part_no     VARCHAR(50),
    name        VARCHAR(100) NOT NULL,
    group_name  VARCHAR(50),   -- 分组，如 电源模块/显示模块
    sort_order  INT NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_parts_product ON parts(product_id);

-- ------------------------------------------------------------
-- 7. 故障知识库表
--    part_id NOT NULL：与 PRD「所属零件必选」一致
-- ------------------------------------------------------------
CREATE TABLE faults (
    id                 SERIAL PRIMARY KEY,
    product_id         INT NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    part_id            INT NOT NULL REFERENCES parts(id) ON DELETE RESTRICT,
    title              VARCHAR(200) NOT NULL,
    symptom            TEXT,
    root_cause         TEXT,
    solution_steps     JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- 结构: [{"step":1,"text":"...","image_url":"..."}, ...]
    required_tools     VARCHAR(200),                    -- 所需工具
    needs_professional BOOLEAN NOT NULL DEFAULT FALSE,  -- 是否需专业人员
    attachment_urls    JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- 结构: [{"name":"维修手册.pdf","url":"/uploads/xxx.pdf","size":102400}, ...]
    -- 附件元数据随故障存储，文件本体在 ./data/uploads，由 Nginx 直出
    view_count         INT NOT NULL DEFAULT 0 CHECK (view_count >= 0),
    resolved_count     INT NOT NULL DEFAULT 0 CHECK (resolved_count >= 0),
    is_published       BOOLEAN NOT NULL DEFAULT TRUE,   -- 是否发布（前台可见）
    created_by         INT REFERENCES users(id) ON DELETE SET NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_faults_product ON faults(product_id);
CREATE INDEX idx_faults_part ON faults(part_id);
CREATE INDEX idx_faults_published ON faults(is_published);
-- 前台列表：按 product+part 过滤、按 view_count 降序
CREATE INDEX idx_faults_list ON faults(product_id, part_id, view_count DESC);
-- 上面 (product_id)、(part_id) 两个单列索引看着像被 idx_faults_list 覆盖，
-- 但**不能删**。实测（5 万行）：后台"按零件统计故障数"只按 part_id 过滤时，
-- idx_faults_list 的首列是 product_id 用不上，只能做 skip scan，
-- 扫 15154 个 buffer 耗时 88ms；有 idx_faults_part 走 Bitmap Index Scan 只要 9 个 buffer / 0.1ms。
-- 写放大确实会被这两个索引放大（每次 UPDATE view_count 多改两页），
-- 但读路径的 800 倍差距更不可接受，所以保留。

-- ------------------------------------------------------------
-- 8. 查询日志表
--    每次详情访问写入；检索无结果时由前端补写 hit=false
--    关联对象删除后置 NULL，保留历史计数（hit 不受影响）
-- ------------------------------------------------------------
CREATE TABLE query_logs (
    id          SERIAL PRIMARY KEY,
    product_id  INT REFERENCES products(id) ON DELETE SET NULL,
    part_id     INT REFERENCES parts(id) ON DELETE SET NULL,
    fault_id    INT REFERENCES faults(id) ON DELETE SET NULL,
    raw_query   VARCHAR(100),                   -- 用户输入的关键词（未输入为 NULL）
    hit         BOOLEAN NOT NULL DEFAULT FALSE, -- 是否命中故障方案
    resolved    BOOLEAN,                        -- 用户是否标记已解决（反馈时回填）
    ip          VARCHAR(50),
    user_agent  VARCHAR(200),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_query_logs_created ON query_logs(created_at);
CREATE INDEX idx_query_logs_fault ON query_logs(fault_id);
-- 未命中统计只扫 hit=false
CREATE INDEX idx_query_logs_missed ON query_logs(created_at) WHERE hit = FALSE;
-- 未命中按归一化检索词分组
CREATE INDEX idx_query_logs_missed_q ON query_logs (lower(btrim(raw_query))) WHERE hit = FALSE;
-- 解决率分母按 hit=true 统计
CREATE INDEX idx_query_logs_hit ON query_logs(created_at) WHERE hit = TRUE;

-- ------------------------------------------------------------
-- 9. 工单表
-- ------------------------------------------------------------
CREATE TABLE tickets (
    id           SERIAL PRIMARY KEY,
    -- 工单号：TK + 8 位日期 + 4 位当日序号，如 TK202610190001
    ticket_no    VARCHAR(32) NOT NULL UNIQUE
                 CHECK (ticket_no ~ '^TK[0-9]{8}[0-9]{4}$'),
    product_id   INT REFERENCES products(id) ON DELETE SET NULL,
    part_id      INT REFERENCES parts(id) ON DELETE SET NULL,
    fault_id     INT REFERENCES faults(id) ON DELETE SET NULL,
    contact      VARCHAR(100) NOT NULL
                 CHECK (char_length(contact) BETWEEN 5 AND 100),
    contact_name VARCHAR(50),
    description  TEXT NOT NULL
                 CHECK (char_length(description) BETWEEN 5 AND 2000),
    need_on_site BOOLEAN NOT NULL DEFAULT FALSE,
    status       VARCHAR(20) NOT NULL DEFAULT 'open'
                 CHECK (status IN ('open', 'processing', 'resolved', 'closed')),
    assignee_id  INT REFERENCES users(id) ON DELETE SET NULL,
    remark       TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 列表按 status 过滤 + created_at 倒序 / 时间范围
CREATE INDEX idx_tickets_status_created ON tickets(status, created_at DESC);
CREATE INDEX idx_tickets_created ON tickets(created_at);

-- ------------------------------------------------------------
-- 10. 工单状态变更日志（PRD F-10「流转时记录操作人」的落地表）
-- ------------------------------------------------------------
CREATE TABLE ticket_status_logs (
    id          SERIAL PRIMARY KEY,
    ticket_id   INT NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    from_status VARCHAR(20),                        -- 建单首条为空
    to_status   VARCHAR(20) NOT NULL
                CHECK (to_status IN ('open', 'processing', 'resolved', 'closed')),
    operator_id INT REFERENCES users(id) ON DELETE SET NULL,
    remark      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_ticket_logs_ticket ON ticket_status_logs(ticket_id, created_at);

-- ------------------------------------------------------------
-- 11. 操作审计（谁、何时、从哪、做了什么、结果如何）
--     只记「动作与对象」，不记请求体：密码、客户手机号不进审计表。
--     与 003_audit_logs.sql 保持一致，改一处必须同步另一处。
-- ------------------------------------------------------------
CREATE TABLE audit_logs (
    id          BIGSERIAL PRIMARY KEY,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    request_id  VARCHAR(64),
    user_id     INT REFERENCES users(id) ON DELETE SET NULL,
    username    VARCHAR(50) NOT NULL,          -- 冗余存：账号删除或改名后仍可追溯
    action      VARCHAR(50) NOT NULL,          -- auth.login / fault.update ...
    target_type VARCHAR(30),                   -- fault / product / ticket / user ...
    target_id   VARCHAR(50),                   -- 自增 id 或工单号，统一按字符串存
    target_name VARCHAR(200),                  -- 冗余展示名，列表里不用再回查
    method      VARCHAR(10) NOT NULL,
    path        VARCHAR(200) NOT NULL,
    status      INT NOT NULL,
    result      VARCHAR(10) NOT NULL CHECK (result IN ('success', 'failure')),
    error_code  VARCHAR(40),
    ip          VARCHAR(50),
    user_agent  VARCHAR(200),
    detail      JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX idx_audit_logs_created ON audit_logs(created_at DESC);
CREATE INDEX idx_audit_logs_user ON audit_logs(user_id, created_at DESC);
CREATE INDEX idx_audit_logs_action ON audit_logs(action, created_at DESC);
CREATE INDEX idx_audit_logs_target ON audit_logs(target_type, target_id);
CREATE INDEX idx_audit_logs_ip ON audit_logs(ip, created_at DESC);

-- 只追加：UPDATE / DELETE / TRUNCATE 直接抛错（与 004_audit_immutable.sql 一致）
-- 说明见迁移文件头：应用账号是超级用户，REVOKE 无效，只能靠触发器兜
CREATE OR REPLACE FUNCTION audit_logs_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION USING
        MESSAGE = '审计记录为只追加（append-only），不允许修改或删除',
        HINT = '如确需清理过期数据，请用 deploy/scripts/cleanup-audit.sh';
END $$;

CREATE TRIGGER trg_audit_logs_immutable
    BEFORE UPDATE OR DELETE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION audit_logs_immutable();

CREATE TRIGGER trg_audit_logs_no_truncate
    BEFORE TRUNCATE ON audit_logs
    FOR EACH STATEMENT EXECUTE FUNCTION audit_logs_immutable();

-- ============================================================
-- 初始化数据
-- ⚠ 不在此插入管理员账号。bcrypt 哈希必须运行时生成，
--   由 scripts/init_admin.py 在首次部署时创建（幂等）。
-- ============================================================

-- ============================================================
-- 视图：故障命中率统计（按故障维度，供运维排查，非看板口径）
-- 看板「自助解决率」以 query_logs.hit 为准，二者不可混用。
-- ============================================================
CREATE OR REPLACE VIEW v_fault_stats AS
SELECT
    f.id AS fault_id,
    f.title,
    p.name AS product_name,
    pt.name AS part_name,
    f.view_count,
    f.resolved_count,
    CASE WHEN f.view_count > 0
         THEN ROUND(f.resolved_count::NUMERIC / f.view_count * 100, 1)
         ELSE 0 END AS resolve_rate_pct
FROM faults f
JOIN products p ON f.product_id = p.id
LEFT JOIN parts pt ON f.part_id = pt.id
ORDER BY f.view_count DESC;

INSERT INTO schema_migrations (version) VALUES ('001_user_permissions');
INSERT INTO schema_migrations (version) VALUES ('002_token_version');

-- ------------------------------------------------------------
-- 进销存模块（v1.3，对应 deploy/migrations/005_inventory.sql）
--     内部轻量库存台账：SKU 对 parts 为可空弱关联；流水只增不改。
--     本脚本用于全新库，故不带 IF NOT EXISTS；已有库走 005 迁移。
-- ------------------------------------------------------------
CREATE TABLE inventory_warehouses (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(30) NOT NULL UNIQUE,
    name        VARCHAR(50) NOT NULL,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE inventory_skus (
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

CREATE TABLE inventory_balances (
    sku_id        INT NOT NULL REFERENCES inventory_skus(id) ON DELETE CASCADE,
    warehouse_id  INT NOT NULL REFERENCES inventory_warehouses(id) ON DELETE RESTRICT,
    quantity      INT NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (sku_id, warehouse_id)
);

CREATE TABLE inventory_documents (
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

CREATE TABLE inventory_document_items (
    id            SERIAL PRIMARY KEY,
    document_id   INT NOT NULL REFERENCES inventory_documents(id) ON DELETE CASCADE,
    sku_id        INT NOT NULL REFERENCES inventory_skus(id) ON DELETE RESTRICT,
    quantity      INT NOT NULL CHECK (quantity > 0),
    unit_cost     NUMERIC(12,2),
    remark        VARCHAR(200)
);

CREATE TABLE stock_movements (
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

CREATE INDEX idx_inv_skus_part
    ON inventory_skus(part_id) WHERE part_id IS NOT NULL;
CREATE INDEX idx_inv_skus_active
    ON inventory_skus(warehouse_id, is_active);
CREATE INDEX idx_inv_documents_type_time
    ON inventory_documents(doc_type, created_at DESC);
CREATE INDEX idx_inv_documents_status
    ON inventory_documents(status, created_at DESC);
CREATE INDEX idx_inv_items_doc
    ON inventory_document_items(document_id);
CREATE INDEX idx_inv_movements_sku_time
    ON stock_movements(sku_id, created_at DESC);
CREATE INDEX idx_inv_movements_doc
    ON stock_movements(document_id);

-- 物资分类主数据（数据表管理，录入时下拉多选）
CREATE TABLE inventory_categories (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(50) NOT NULL UNIQUE,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    remark      VARCHAR(200),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 物资 ↔ 分类（多对多：一个物资可属于多个分类）
CREATE TABLE inventory_sku_categories (
    sku_id       INT NOT NULL REFERENCES inventory_skus(id) ON DELETE CASCADE,
    category_id  INT NOT NULL REFERENCES inventory_categories(id) ON DELETE CASCADE,
    PRIMARY KEY (sku_id, category_id)
);

-- 物资 ↔ 产品（多对多：镜像零件↔产品，关联售后系统但不强制）
CREATE TABLE inventory_sku_products (
    sku_id      INT NOT NULL REFERENCES inventory_skus(id) ON DELETE CASCADE,
    product_id  INT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    PRIMARY KEY (sku_id, product_id)
);

CREATE INDEX idx_inv_sku_cat_cat ON inventory_sku_categories(category_id);
CREATE INDEX idx_inv_sku_prod_prod ON inventory_sku_products(product_id);

INSERT INTO inventory_warehouses (code, name) VALUES ('DEFAULT', '默认仓');

CREATE OR REPLACE FUNCTION stock_movements_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION USING
        MESSAGE = '库存流水为只追加（append-only），不允许修改或删除',
        HINT = '如需更正请登记冲正单（反向单据）';
END $$;

CREATE TRIGGER trg_stock_movements_immutable
    BEFORE UPDATE OR DELETE ON stock_movements
    FOR EACH ROW EXECUTE FUNCTION stock_movements_immutable();

CREATE TRIGGER trg_stock_movements_no_truncate
    BEFORE TRUNCATE ON stock_movements
    FOR EACH STATEMENT EXECUTE FUNCTION stock_movements_immutable();

INSERT INTO schema_migrations (version) VALUES ('005_inventory');
INSERT INTO schema_migrations (version) VALUES ('006_warehouse_roles');
INSERT INTO schema_migrations (version) VALUES ('007_inventory_categories');
INSERT INTO schema_migrations (version) VALUES ('008_product_planner');
INSERT INTO schema_migrations (version) VALUES ('009_multi_role');
