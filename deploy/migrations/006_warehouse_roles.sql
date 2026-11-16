-- 006_warehouse_roles：仓管角色拆分为录入员与主管
-- 全部幂等，可被 deploy/scripts/migrate.py 重复执行。
-- 与 deploy/schema.sql v1.4 一一对应；全新库由 schema.sql 直接落到最新结构。
-- 注意：本文件内禁止出现百分号字符（psycopg2 占位符冲突）。

-- 顺序要求：必须先摘掉旧 CHECK 约束，再 UPDATE。
-- 旧约束的白名单只有 warehouse，不含 warehouse_manager，
-- 若先 UPDATE 会被约束拒绝（CheckViolation: users_role_check）。
-- 009 之后 users.role 列已删除，重放时整段跳过（否则报 column "role" does not exist）。
-- 约束名由 001_user_permissions.sql 固定，沿用先例。
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

        -- 既有 warehouse 账号整体升级为主管（录入员只录入、无改单权限；
        -- 主管继承录入员全部权限，并独有修改已生效单据能力）。
        -- 测试账号 warehouse 由调用方按需重建为 warehouse_manager / warehouse_clerk。
        UPDATE users SET role = 'warehouse_manager' WHERE role = 'warehouse';

        -- 白名单含 008 的 product_planner：在 008 之后重放本文件时若收窄到 6 个值，
        -- 已存在的 product_planner 账号会让 ADD CONSTRAINT 失败。
        ALTER TABLE users ADD CONSTRAINT users_role_check
            CHECK (role IN (
                'super_admin', 'supervisor', 'product_planner', 'agent', 'auditor',
                'warehouse_clerk', 'warehouse_manager'
            ));
    END IF;
END $$;
