// 客户侧「后台入口」的登录态行为
//
// 缺陷回归：以前点「后台入口」一律进 /admin/login，已登录的人也得再登一次。
// 现在分三种情况：
//   已登录（token 未过期）→ 直接进后台首页
//   未登录               → 登录页
//   token 已过期         → 登录页（不能因为"有 token 残留"就放行，否则后台闪一下再被 401 踹回）
import { expect, test } from '@playwright/test'

const ADMIN_USER = process.env.E2E_ADMIN_USER || 'admin'
const ADMIN_PASS = process.env.E2E_ADMIN_PASS || 'yyzk123456'

const b64url = (obj) => Buffer.from(JSON.stringify(obj)).toString('base64url')

/** 造一个只用于"本地时间判断"的过期凭证：签名不重要，前端不解签名 */
function expiredToken() {
  const now = Math.floor(Date.now() / 1000)
  return `${b64url({ alg: 'HS256', typ: 'JWT' })}.${b64url({ sub: 'admin', exp: now - 60 })}.sig`
}

async function login(page) {
  await page.goto('/admin/login')
  await page.getByPlaceholder('请输入用户名').fill(ADMIN_USER)
  await page.getByPlaceholder('请输入密码').fill(ADMIN_PASS)
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(/\/admin\/tickets/)
}

test('@smoke 未登录：客户侧「后台入口」进登录页', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('link', { name: '后台入口' }).click()

  await expect(page).toHaveURL(/\/admin\/login$/)
  await expect(page.locator('.login-card')).toBeVisible()
})

test('@smoke 已登录：客户侧「后台入口」直接进后台，不再要求登录', async ({ page }) => {
  await login(page)

  // 模拟"管理员登录后又回到客户侧页面翻内容"
  await page.goto('/')
  await page.getByRole('link', { name: '后台入口' }).click()

  await expect(page).toHaveURL(/\/admin\/tickets/)
  // 关键断言：中间不能出现登录表单
  await expect(page.locator('.login-card')).toHaveCount(0)
  await expect(page.getByRole('menuitem', { name: '工单管理' })).toBeVisible()
})

test('@smoke 本地 token 已过期：回登录页，不放行脏凭证', async ({ page }) => {
  await page.goto('/')
  await page.evaluate((token) => {
    localStorage.setItem('token', token)
    localStorage.setItem('user', JSON.stringify({ username: 'admin', role: 'super_admin' }))
  }, expiredToken())

  await page.reload()
  // 页面上链接此时已按"未登录"渲染（过期 = 未登录）
  await page.getByRole('link', { name: '后台入口' }).click()

  await expect(page).toHaveURL(/\/admin\/login$/)
  await expect(page.locator('.login-card')).toBeVisible()
})

test('@smoke 直接访问 /admin/login 时已登录也会被送去后台', async ({ page }) => {
  await login(page)
  // 书签 / 手敲 URL 也要享受同一条规则
  await page.goto('/admin/login')

  await expect(page).toHaveURL(/\/admin\/tickets/)
  await expect(page.locator('.login-card')).toHaveCount(0)
})
