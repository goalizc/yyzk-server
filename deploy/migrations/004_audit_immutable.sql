-- 004_audit_immutable
-- 让审计表变成「只追加」：UPDATE / DELETE / TRUNCATE 一律抛错。
--
-- 为什么用触发器而不是收权限：
--   应用连库用的是 `fault`，而它在这套部署里是超级用户（POSTGRES_USER 就是它），
--   PostgreSQL 里超级用户绕过所有权限检查，REVOKE 对它完全无效。
--   触发器不受超级用户豁免（只有 session_replication_role=replica 或 DISABLE TRIGGER 才绕过），
--   所以这是当前架构下唯一能立刻生效的防线。
--
-- 它能挡住什么：手滑 UPDATE、误删、SQL 注入里的批量删除、清理脚本写错条件。
-- 它挡不住什么：拿到超级用户凭据的人可以 ALTER TABLE ... DISABLE TRIGGER 再删。
--   要真正挡住这一类，必须把应用换成非超级用户角色（报告 P0-1 的方案 B），属部署改造。

CREATE OR REPLACE FUNCTION audit_logs_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION USING
        MESSAGE = '审计记录为只追加（append-only），不允许修改或删除',
        HINT = '如确需清理过期数据，请用 deploy/scripts/cleanup-audit.sh';
END $$;

DROP TRIGGER IF EXISTS trg_audit_logs_immutable ON audit_logs;
CREATE TRIGGER trg_audit_logs_immutable
    BEFORE UPDATE OR DELETE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION audit_logs_immutable();

-- TRUNCATE 不触发行级触发器，要单独挂语句级触发器（PG 11+）
DROP TRIGGER IF EXISTS trg_audit_logs_no_truncate ON audit_logs;
CREATE TRIGGER trg_audit_logs_no_truncate
    BEFORE TRUNCATE ON audit_logs
    FOR EACH STATEMENT EXECUTE FUNCTION audit_logs_immutable();
