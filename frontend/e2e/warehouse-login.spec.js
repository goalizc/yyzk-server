// 回归：warehouse 角色（仅进销存权限，无任何售后模块权限）登录后曾卡死。
//
// 根因：/admin 默认重定向到 /admin/tickets（需 ticket:read），warehouse 无此权限；
// 守卫的 403 兜底又写死跳 /admin/faults（需 fault:read），warehouse 同样没有，
// 于是无限重定向循环，浏览器表现为"登录就卡住"。
// 修复：登录落地页与 403 兜底页都改为按角色权限动态取第一个可见页面
// （见 router/index.js 的 firstAccessibleAdminPath）。
//
// 本用例锁定：warehouse 登录后稳定停在 /admin/inventory/skus，不死循环、不回登录页。
//
// 前置账号（幂等，可重复执行）：
//   cd deploy && ./scripts/ensure-e2e-user.sh
//   测试栈：STACK_ENV_FILE=.env.test STACK_PROJECT=fault-test ./scripts/ensure-e2e-user.sh
// 账号/口令用 E2E_WAREHOUSE_USER / E2E_WAREHOUSE_PASS 覆盖，默认 warehouse / 12345678。
import { expect, test } from '@playwright/test'

const WH_USER = process.env.E2E_WAREHOUSE_USER || 'warehouse'
const WH_PASS = process.env.E2E_WAREHOUSE_PASS || '12345678'

async function loginWarehouse(page) {
  await page.goto('/admin/login')
  await page.getByPlaceholder('请输入用户名').fill(WH_USER)
  await page.getByPlaceholder('请输入密码').fill(WH_PASS)
  await page.getByRole('button', { name: '登录' }).click()
}

test('@smoke warehouse 账号登录不卡死，按权限稳定落地', async ({ page }) => {
  await loginWarehouse(page)
  await expect(page.locator('.layout')).toBeVisible()

  const permissions = await page.evaluate(() =>
    JSON.parse(localStorage.getItem('permissions') || '[]')
  )
  // 账号可能被人工追加了其它角色（例如产品计划），此时落地页会随权限变化。
  // 纯仓管账号仍必须落在物资 SKU；所有情况都不得停在登录页或来回跳转。
  const pureWarehouse = ![
    'ticket:read',
    'product:read',
    'product_line:read',
    'part:read',
    'fault:read',
    'stats:read',
    'user:read'
  ].some((code) => permissions.includes(code))
  if (pureWarehouse) {
    await expect(page).toHaveURL(/\/admin\/inventory\/skus/)
    // 库存页真实渲染（菜单/标题含「物资 SKU」）
    await expect(page.getByText('物资 SKU').first()).toBeVisible()
  }

  // 没被踢回登录页，后台布局真实渲染
  await expect(page.locator('.login-card')).toHaveCount(0)
  await expect(page.locator('.layout')).toBeVisible()

  // 双保险：停留 3 秒，URL 仍稳定，证明不是"某次恰好命中"
  const landing = page.url()
  await page.waitForTimeout(3000)
  expect(page.url()).toBe(landing)
  await expect(page.locator('.login-card')).toHaveCount(0)
})
