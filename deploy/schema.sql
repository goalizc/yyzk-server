-- ============================================================
-- 售后自助故障诊断系统 - 数据库建表脚本
-- PostgreSQL 15+
-- 修订：v1.2  2026-10-20（第二轮复审后修正）
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
--
-- ⚠ 本脚本仅在数据卷为空时由 initdb 执行一次。已有环境升级需手工执行
--    对应 DDL（本项目一期不引入迁移框架）。
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
-- 1. 后台用户表（仅在册内部人员，一期不做用户管理界面）
-- ------------------------------------------------------------
CREATE TABLE users (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(200) NOT NULL,
    real_name     VARCHAR(50) NOT NULL,
    role          VARCHAR(20) NOT NULL DEFAULT 'agent'
                  CHECK (role IN ('admin', 'agent')),
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- 说明：一期不提供用户增删改界面，账号由 init_admin.py 与运维 SQL 维护；
--       「修改自己密码」走 API 完成。

-- ------------------------------------------------------------
-- 2. 产品表
-- ------------------------------------------------------------
CREATE TABLE products (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    model       VARCHAR(50) NOT NULL UNIQUE,
    category    VARCHAR(50),
    description TEXT,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order  INT NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_products_active ON products(is_active);

-- ------------------------------------------------------------
-- 3. 零件表（归属产品）
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
-- 4. 故障知识库表
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
-- 5. 查询日志表
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
-- 6. 工单表
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
-- 7. 工单状态变更日志（PRD F-10「流转时记录操作人」的落地表）
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
