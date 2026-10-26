-- 003_audit_logs
-- 操作审计：谁、什么时间、从哪个 IP、做了什么、结果如何。
-- 设计取舍：
--   1) username 冗余存一份而不是只留 user_id：账号被删/改名后审计记录仍可追溯；
--   2) target_id 用 VARCHAR：故障用自增 id，工单用 TK 业务号，两类都能放；
--   3) detail 用 JSONB：不同动作要记的字段不一样（状态 from/to、角色变更前后），
--      建宽表会让一半列永远为 NULL；
--   4) 不记录任何请求体：密码、客户手机号都不进审计表，避免二次泄漏。

CREATE TABLE IF NOT EXISTS audit_logs (
    id          BIGSERIAL PRIMARY KEY,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    request_id  VARCHAR(64),
    user_id     INT REFERENCES users(id) ON DELETE SET NULL,
    username    VARCHAR(50) NOT NULL,
    action      VARCHAR(50) NOT NULL,
    target_type VARCHAR(30),
    target_id   VARCHAR(50),
    target_name VARCHAR(200),
    method      VARCHAR(10) NOT NULL,
    path        VARCHAR(200) NOT NULL,
    status      INT NOT NULL,
    result      VARCHAR(10) NOT NULL CHECK (result IN ('success', 'failure')),
    error_code  VARCHAR(40),
    ip          VARCHAR(50),
    user_agent  VARCHAR(200),
    detail      JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- 列表默认按时间倒序翻页
CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON audit_logs(created_at DESC);
-- 「某个人最近做了什么」：排查人员问题的主路径
CREATE INDEX IF NOT EXISTS idx_audit_logs_user ON audit_logs(user_id, created_at DESC);
-- 「某个动作最近发生过几次」：如连续重置密码
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action, created_at DESC);
-- 「这条故障/工单被谁动过」
CREATE INDEX IF NOT EXISTS idx_audit_logs_target ON audit_logs(target_type, target_id);
-- 「这个 IP 还操作过什么」：账号外传时定位来源
CREATE INDEX IF NOT EXISTS idx_audit_logs_ip ON audit_logs(ip, created_at DESC);
