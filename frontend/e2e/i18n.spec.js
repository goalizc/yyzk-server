// 国际化：客户侧 URL 前缀决定语言，且切换后查询参数保留
//
// 只测客户侧：后台语言跟随 localStorage，属本机偏好，不适合放进共享的无状态 E2E。
import { expect, test } from '@playwright/test'

test('@smoke 客户侧中英双语：URL 前缀决定语言，切换保留路径与参数', async ({ page }) => {
  // ---------- 1. 无前缀 = 中文 ----------
  await page.goto('/')
  await expect(page.getByRole('heading', { name: '售后自助故障诊断' })).toBeVisible()
  await expect(page.locator('.field label').first()).toContainText('选择产品')

  // ---------- 2. /en = 英文 ----------
  await page.goto('/en')
  await expect(page.getByRole('heading', { name: 'Self-Service Fault Diagnosis' })).toBeVisible()
  await expect(page.locator('.field label').first()).toContainText('Select product')
  // Element Plus 内置文案也要跟着走，否则会出现"英文界面 + 中文空态"
  await expect(page.locator('.el-select').first()).toContainText('Select a product')

  // ---------- 3. 切换回中文，路径不变 ----------
  await page.locator('.lang-switch').click()
  await expect(page).toHaveURL(/\/$|\/[^e]/)
  await expect(page.getByRole('heading', { name: '售后自助故障诊断' })).toBeVisible()

  // ---------- 4. 带查询参数切换，参数不能丢 ----------
  await page.goto('/faults/1?q=%E6%BC%8F%E6%B0%B4')
  await page.locator('.lang-switch').click()
  await expect(page).toHaveURL(/\/en\/faults\/1\?q=/)
})

test('@smoke 客户侧切到英文后进后台，登录页也是英文', async ({ page }) => {
  // 回归：语言必须能从客户侧传导到后台。
  // 曾经的实现里客户侧切换不落 localStorage，导致英文界面点 Admin 进去是中文后台。
  await page.goto('/')
  await page.locator('.lang-switch').click()
  await expect(page).toHaveURL(/\/en$/)

  await page.getByRole('link', { name: 'Admin' }).click()
  await expect(page).toHaveURL(/\/admin\/login/)
  await expect(page.getByRole('heading', { name: 'Fault Diagnosis System' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible()

  // 标签页标题也要跟着语言走，否则英文页面的 tab 上还是中文
  await expect(page).toHaveTitle(/Fault Diagnosis System/)
})
