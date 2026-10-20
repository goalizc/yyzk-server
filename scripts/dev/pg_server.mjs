#!/usr/bin/env node
/**
 * 本地没有 PostgreSQL 时的替代方案：用 WASM PostgreSQL（PGlite）起一个真实的
 * pg 协议服务，供后端 psycopg2 连接。
 *
 * 为什么存在：沙箱/受限开发机上装不了 PostgreSQL，也起不了容器，但后端要用真库
 * 才能验证 schema.sql + ORM 的实际行为（SQLite 少了 JSONB、CHECK、部分索引）。
 *
 * ⚠ 只用于开发与验收演练，不是生产方案：单进程、查询全局串行、无并发能力。
 *
 * 用法：
 *   node scripts/dev/pg_server.mjs                 # 首次自动执行 schema.sql
 *   node scripts/dev/pg_server.mjs --reset         # 清空数据目录重建
 *   PG_PORT=55432 node scripts/dev/pg_server.mjs   # 换端口
 *
 * 连接串：postgresql+psycopg2://postgres@127.0.0.1:55432/postgres
 */

import { existsSync, rmSync, readFileSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

import { PGlite } from '@electric-sql/pglite'
import { PGLiteSocketServer } from '@electric-sql/pglite-socket'
import { pgcrypto } from '@electric-sql/pglite/contrib/pgcrypto'
import { pg_stat_statements } from '@electric-sql/pglite/contrib/pg_stat_statements'

const here = dirname(fileURLToPath(import.meta.url))
const repoRoot = resolve(here, '../..')
const dataDir = resolve(repoRoot, '.tmp/pgdata')
const schemaPath = resolve(repoRoot, 'deploy/schema.sql')
const port = Number(process.env.PG_PORT || 55432)
const reset = process.argv.includes('--reset')

if (reset && existsSync(dataDir)) {
  rmSync(dataDir, { recursive: true, force: true })
  console.log('[pg] 已清空数据目录')
}
mkdirSync(dataDir, { recursive: true })

const db = await PGlite.create({
  dataDir,
  extensions: { pgcrypto, pg_stat_statements }
})

// 空库才建表：判断依据是 users 表是否存在（schema.sql 只在 initdb 时执行一次，行为一致）
const { rows } = await db.query(
  `SELECT to_regclass('public.users') IS NOT NULL AS exists`
)
if (!rows[0].exists) {
  const sql = readFileSync(schemaPath, 'utf8')
  await db.exec(sql)
  console.log(`[pg] 已执行 deploy/schema.sql（${sql.length} 字符）`)
} else {
  console.log('[pg] 复用已有数据目录（要重建加 --reset）')
}

const server = new PGLiteSocketServer({
  db,
  host: '127.0.0.1',
  port,
  // 后端的连接池会同时开多条连接，默认 1 条会互相阻塞
  maxConnections: 8
})
await server.start()

console.log(`[pg] 监听 ${server.getServerConn()}`)
console.log('[pg] DATABASE_URL=postgresql+psycopg2://postgres@127.0.0.1:%d/postgres', port)

let closing = false
async function shutdown(signal) {
  if (closing) return
  closing = true
  console.log(`[pg] 收到 ${signal}，关闭中…`)
  await server.stop()
  await db.close()
  process.exit(0)
}
process.on('SIGINT', () => shutdown('SIGINT'))
process.on('SIGTERM', () => shutdown('SIGTERM'))
