-- 002_token_version
-- 1) 会话版本号：改密/重置密码后自增，使旧的 JWT 立即失效
-- 2) 用户名统一小写，并用表达式唯一索引保证大小写不敏感

ALTER TABLE users ADD COLUMN token_version INT NOT NULL DEFAULT 0;

UPDATE users SET username = LOWER(username) WHERE username <> LOWER(username);

CREATE UNIQUE INDEX idx_users_username_lower ON users (LOWER(username));
