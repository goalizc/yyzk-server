-- 008_product_planner：产品/零件/产品线主数据唯一业务写者
-- 全部幂等，可被 deploy/scripts/migrate.py 重复执行。
-- 与 deploy/schema.sql v1.5 的角色 CHECK 对应；009 之后 users.role 已删除，
-- 本文件用列存在性判断保持可重放。
-- 注意：本文件内禁止出现百分号字符（psycopg2 占位符冲突）。

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'users'
          AND column_name = 'role'
    ) THEN
        ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
        ALTER TABLE users ADD CONSTRAINT users_role_check
            CHECK (role IN (
                'super_admin',
                'supervisor',
                'product_planner',
                'agent',
                'auditor',
                'warehouse_clerk',
                'warehouse_manager'
            ));
    END IF;
END $$;

-- 主数据写改为不可临时授予：收回既有未过期授权，
-- 否则历史授权会继续给 supervisor/其他角色留下 product:write 等写入口。
UPDATE user_permission_grants
SET revoked_at = NOW()
WHERE permission IN ('product:write', 'part:write', 'product_line:write')
  AND revoked_at IS NULL
  AND (expires_at IS NULL OR expires_at > NOW());
