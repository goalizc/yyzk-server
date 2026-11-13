-- 009_multi_role：一人多岗，user_roles 成为角色唯一来源
-- 全部幂等，可被 deploy/scripts/migrate.py 重复执行。
-- 与 deploy/schema.sql v1.6 一一对应。
-- 注意：本文件内禁止出现百分号字符（psycopg2 占位符冲突）。

CREATE TABLE IF NOT EXISTS user_roles (
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role    VARCHAR(20) NOT NULL
            CHECK (role IN (
                'super_admin',
                'supervisor',
                'product_planner',
                'agent',
                'auditor',
                'warehouse_clerk',
                'warehouse_manager'
            )),
    PRIMARY KEY (user_id, role)
);

CREATE INDEX IF NOT EXISTS idx_user_roles_role ON user_roles(role);

-- 回填既有单角色；回填后删除 users.role。
-- 用列存在性判断包裹，重复执行时不会因列已删除而失败。
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'users'
          AND column_name = 'role'
    ) THEN
        INSERT INTO user_roles (user_id, role)
        SELECT id, role FROM users
        ON CONFLICT (user_id, role) DO NOTHING;

        ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
        ALTER TABLE users DROP COLUMN role;
    END IF;
END $$;
