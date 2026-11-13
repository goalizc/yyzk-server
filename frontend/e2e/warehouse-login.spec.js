// 回归：warehouse 角色（仅进销存权限，无任何售后模块权限）登录后曾卡死。
//
// 根因：/admin 默认重定向到 /admin/tickets（需 ticket:read），warehouse 无此权限；
// 守卫的 403 兜底又写死跳 /admin/faults（需 fault:read），warehouse 同样没有，
// 于是无限重定向循环，浏览器表现为"登录就卡住"。
// 修复：登录落地页与 403 兜底页都改为按角色权限动态取第一个可见页面
// （见 router/index.js 的 firstAccessibleAdminPath）。
//
// 本用例锁定：warehouse 登录后稳定停在 /admin/inventory/skus，不死循环、不回登录页。
import { expect, test } from '@playwright/test'

const WH_USER = process.env.E2E_WAREHOUSE_USER || 'warehouse'
const WH_PASS = process.env.E2E_WAREHOUSE_PASS || '12345678'

async function loginWarehouse(page) {
  await page.goto('/admin/login')
  await page.getByPlaceholder('请输入用户名').fill(WH_USER)
  await page.getByPlaceholder('请输入密码').fill(WH_PASS)
  await page.getByRole('button', { name: '登录' }).click()
}

test('@smoke warehouse 角色登录不卡死，落在库存首页', async ({ page }) => {
  await loginWarehouse(page)

  // 关键断言：最终稳定停在库存 SKU 页。若仍是重定向死循环，URL 会不停跳动，
  // 这里在 10s 内不满足而超时失败。
  await expect(page).toHaveURL(/\/admin\/inventory\/skus/)

  // 没被踢回登录页
  await expect(page.locator('.login-card')).toHaveCount(0)

  // 库存页真实渲染（菜单/标题含「物资 SKU」）
  await expect(page.getByText('物资 SKU').first()).toBeVisible()

  // 双保险：停留 3 秒，URL 仍稳定，证明不是"某次恰好命中"
  await page.waitForTimeout(3000)
  await expect(page).toHaveURL(/\/admin\/inventory\/skus/)
})
