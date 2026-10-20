/**
 * schema.sql 校验器（WASM PostgreSQL 16，无需 root / 无需 Docker）
 *
 * 用途：在没有 PostgreSQL 服务的开发机上，验证 deploy/schema.sql 能否被真实
 *       PG 引擎接受，并抽查关键约束（CHECK / 外键删除策略 / 部分索引 / JSONB / 视图）。
 *
 * 运行：
 *   node scripts/dev/verify_schema.mjs
 *
 * 退出码：0 全部通过；1 有失败项；2 脚本自身错误（如依赖未安装）
 */

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { PGlite } from '@electric-sql/pglite'
import { pgcrypto } from '@electric-sql/pglite/contrib/pgcrypto'
import { pg_stat_statements } from '@electric-sql/pglite/contrib/pg_stat_statements'

const here = dirname(fileURLToPath(import.meta.url))
const schemaPath = resolve(here, '../../deploy/schema.sql')

const results = []
const check = (name, fn) => results.push({ name, fn })
const ok = (name, detail = '') => ({ ok: true, name, detail })

check('schema.sql 可整体执行', async (db) => {
  const sql = readFileSync(schemaPath, 'utf8')
  await db.exec(sql)
  return ok('schema.sql 可整体执行', `${sql.length} 字符`)
})

check('7 张表齐备', async (db) => {
  const { rows } = await db.query(
    `SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename`
  )
  const got = rows.map((r) => r.tablename)
  const want = ['faults', 'parts', 'products', 'query_logs', 'ticket_status_logs', 'tickets', 'users']
  const missing = want.filter((t) => !got.includes(t))
  if (missing.length) throw new Error(`缺少表：${missing.join(',')}（实际：${got.join(',')}）`)
  return ok('7 张表齐备', got.join(' / '))
})

check('部分索引与表达式索引已创建', async (db) => {
  const { rows } = await db.query(
    `SELECT indexname FROM pg_indexes WHERE schemaname='public' ORDER BY indexname`
  )
  const names = rows.map((r) => r.indexname)
  const want = ['idx_query_logs_missed', 'idx_query_logs_missed_q', 'idx_query_logs_hit', 'idx_faults_list', 'idx_tickets_status_created']
  const missing = want.filter((n) => !names.includes(n))
  if (missing.length) throw new Error(`缺少索引：${missing.join(',')}`)
  return ok('部分索引与表达式索引已创建', `${names.length} 个索引`)
})

check('工单号格式 CHECK 生效', async (db) => {
  await db.query(`INSERT INTO users (username,password_hash,real_name) VALUES ('u1','x','测试')`)
  const { rows } = await db.query(`SELECT id FROM users WHERE username='u1'`)
  const uid = rows[0].id
  const base = `INSERT INTO tickets (ticket_no,contact,description,assignee_id) VALUES ($1,'13800138000','描述至少五个字',$2)`

  let rejected = false
  try {
    await db.query(base, ['TK20261019001', uid]) // 3 位序号，应被拒绝
  } catch {
    rejected = true
  }
  if (!rejected) throw new Error('3 位序号的工单号未被 CHECK 拒绝')

  await db.query(base, ['TK202610190002', uid])
  return ok('工单号格式 CHECK 生效', '3 位被拒 / 4 位通过')
})

check('状态枚举 CHECK 生效', async (db) => {
  let rejected = false
  try {
    await db.query(`UPDATE tickets SET status='done' WHERE ticket_no='TK202610190002'`)
  } catch {
    rejected = true
  }
  if (!rejected) throw new Error("非法状态 'done' 未被拒绝")
  return ok('状态枚举 CHECK 生效', '非法状态被拒')
})

check('删除故障时引用置 NULL（不是报错）', async (db) => {
  const p = await db.query(`INSERT INTO products (name,model) VALUES ('扫地机','X1') RETURNING id`)
  const pid = p.rows[0].id
  const pt = await db.query(`INSERT INTO parts (product_id,name) VALUES ($1,'电源模组') RETURNING id`, [pid])
  const partId = pt.rows[0].id
  const f = await db.query(
    `INSERT INTO faults (product_id,part_id,title) VALUES ($1,$2,'开机无反应') RETURNING id`,
    [pid, partId]
  )
  const fid = f.rows[0].id

  const t = await db.query(
    `INSERT INTO tickets (ticket_no,product_id,part_id,fault_id,contact,description)
     VALUES ('TK202610190003',$1,$2,$3,'13800138000','关联故障的工单') RETURNING id`,
    [pid, partId, fid]
  )
  const tid = t.rows[0].id

  await db.query(`INSERT INTO query_logs (product_id,part_id,fault_id,hit) VALUES ($1,$2,$3,true)`, [pid, partId, fid])
  await db.query(`DELETE FROM faults WHERE id=$1`, [fid])

  const after = await db.query(`SELECT fault_id FROM tickets WHERE id=$1`, [tid])
  if (after.rows[0].fault_id !== null) throw new Error('删除故障后 tickets.fault_id 未置 NULL')

  const logs = await db.query(`SELECT fault_id FROM query_logs WHERE product_id=$1`, [pid])
  if (logs.rows.some((r) => r.fault_id !== null)) throw new Error('删除故障后 query_logs.fault_id 未置 NULL')

  return ok('删除故障时引用置 NULL', 'tickets 与 query_logs 均已置空')
})

check('删除有零件的产品被 RESTRICT 阻止', async (db) => {
  const p = await db.query(`INSERT INTO products (name,model) VALUES ('净化器','A2') RETURNING id`)
  const pid = p.rows[0].id
  await db.query(`INSERT INTO parts (product_id,name) VALUES ($1,'滤芯')`, [pid])

  let blocked = false
  try {
    await db.query(`DELETE FROM products WHERE id=$1`, [pid])
  } catch {
    blocked = true
  }
  if (!blocked) throw new Error('有零件的产品被删除了，RESTRICT 未生效')
  return ok('删除有零件的产品被 RESTRICT 阻止')
})

check('JSONB 默认值与写入', async (db) => {
  const p = await db.query(`SELECT id FROM products WHERE model='X1'`)
  const pid = p.rows[0].id
  const pt = await db.query(`SELECT id FROM parts WHERE product_id=$1`, [pid])
  const partId = pt.rows[0].id
  const f = await db.query(
    `INSERT INTO faults (product_id,part_id,title,solution_steps)
     VALUES ($1,$2,'充电不亮',$3::jsonb) RETURNING solution_steps, attachment_urls`,
    [pid, partId, JSON.stringify([{ step: 1, text: '检查适配器', image_url: null }])]
  )
  const steps = f.rows[0].solution_steps
  if (!Array.isArray(steps) || steps[0].step !== 1) throw new Error('solution_steps 未按 JSONB 数组存储')
  if (!Array.isArray(f.rows[0].attachment_urls)) throw new Error('attachment_urls 默认值不是数组')
  return ok('JSONB 默认值与写入', `steps=${JSON.stringify(steps)}`)
})

check('TIMESTAMPTZ 默认值与类型', async (db) => {
  const { rows } = await db.query(
    `SELECT pg_typeof(created_at)::text AS t, created_at IS NOT NULL AS has_val FROM products LIMIT 1`
  )
  if (rows[0].t !== 'timestamp with time zone') throw new Error(`created_at 类型为 ${rows[0].t}`)
  if (!rows[0].has_val) throw new Error('created_at 默认值未生效')
  return ok('TIMESTAMPTZ 默认值与类型', rows[0].t)
})

check('v_fault_stats 视图可查询', async (db) => {
  const { rows } = await db.query(`SELECT * FROM v_fault_stats`)
  return ok('v_fault_stats 视图可查询', `${rows.length} 行`)
})

check('联系人长度 CHECK 生效', async (db) => {
  let rejected = false
  try {
    await db.query(
      `INSERT INTO tickets (ticket_no,contact,description) VALUES ('TK202610190004','123','描述至少五个字')`
    )
  } catch {
    rejected = true
  }
  if (!rejected) throw new Error('contact 少于 5 位未被拒绝')
  return ok('联系人长度 CHECK 生效')
})

async function main() {
  let db
  try {
    db = await new PGlite({ extensions: { pgcrypto, pg_stat_statements } })
  } catch (e) {
    console.error('[verify_schema] 无法启动 pglite：', e.message)
    process.exit(2)
  }

  let failed = 0
  for (const { name, fn } of results) {
    try {
      const r = await fn(db)
      console.log(`  PASS  ${r.name}${r.detail ? `  (${r.detail})` : ''}`)
    } catch (e) {
      failed += 1
      console.log(`  FAIL  ${name}\n        ${e.message}`)
    }
  }

  await db.close()
  console.log(`\n结果：${results.length - failed}/${results.length} 通过`)
  process.exit(failed ? 1 : 0)
}

main()
