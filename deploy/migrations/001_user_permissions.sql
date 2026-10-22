CREATE TABLE IF NOT EXISTS schema_migrations (
    version    VARCHAR(50) PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE product_lines (
    id         SERIAL PRIMARY KEY,
    name       VARCHAR(50) NOT NULL UNIQUE,
    sort_order INT NOT NULL DEFAULT 0,
    is_active  BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE user_product_lines (
    user_id    INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    line_id    INT NOT NULL REFERENCES product_lines(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ,
    PRIMARY KEY (user_id, line_id)
);
CREATE INDEX idx_user_product_lines_line ON user_product_lines(line_id);

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

ALTER TABLE products ADD COLUMN line_id INT REFERENCES product_lines(id) ON DELETE RESTRICT;

INSERT INTO product_lines (name)
SELECT DISTINCT TRIM(category) FROM products
WHERE category IS NOT NULL AND TRIM(category) <> ''
ON CONFLICT (name) DO NOTHING;

INSERT INTO product_lines (name)
SELECT '未分类'
WHERE EXISTS (
    SELECT 1 FROM products WHERE category IS NULL OR TRIM(category) = ''
)
ON CONFLICT (name) DO NOTHING;

UPDATE products p
SET line_id = l.id
FROM product_lines l
WHERE l.name = TRIM(p.category);

UPDATE products p
SET line_id = (SELECT id FROM product_lines WHERE name = '未分类')
WHERE p.line_id IS NULL;

ALTER TABLE products ALTER COLUMN line_id SET NOT NULL;
CREATE INDEX idx_products_line ON products(line_id);
ALTER TABLE products DROP COLUMN category;

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
UPDATE users SET role = 'super_admin' WHERE role = 'admin';
ALTER TABLE users ADD CONSTRAINT users_role_check
    CHECK (role IN ('super_admin', 'supervisor', 'agent', 'auditor'));
