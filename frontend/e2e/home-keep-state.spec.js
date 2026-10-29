// 回归用例：客户在首页选好产品 / 零件、输入关键词后，点进某条故障详情，
// 再点返回（el-page-header 的 router.back / 浏览器后退），首页筛选状态必须原样保留，
// 不能重新加载并清空，逼用户再选一遍。
//
// 修复手段：PublicLayout 的 router-view 用 <keep-alive include="Home"> 缓存首页，
// Home 组件在路由切换时不被销毁，返回时直接复用、筛选条件全在。
//
// 数据前提：同 main-flow —— 库里存在产品「植保无人机 16L」、零件「隔膜泵」，
// 且该产品+零件下至少有一条故障（如「喷洒不出水，喷头无雾化」）。
import { test, expect } from '@playwright/test'

async function pickSelect(page, fieldLabel, optionText) {
  const field = page.locator('.field', { hasText: fieldLabel })
  await field.locator('.el-select').click()
  await page
    .locator('.el-select-dropdown:visible .el-select-dropdown__item', { hasText: optionText })
    .first()
    .click()
}

test('@smoke 进故障详情返回后保留产品/零件/关键词筛选', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: '售后自助故障诊断' })).toBeVisible()

  // 选产品、选零件（可选过滤器，但选上后也应保留）
  await pickSelect(page, '1. 选择产品', '植保无人机 16L')
  await pickSelect(page, '2. 选择零件', '隔膜泵')

  // 用列表第一条故障标题当关键词，保证过滤后仍有结果可点进详情
  const firstTitle = (await page.locator('.fault-item .fault-title').first().textContent())?.trim()
  expect(firstTitle).toBeTruthy()
  const kw = page.getByPlaceholder(/关键词/)
  await kw.fill(firstTitle)
  await page.waitForTimeout(700) // 等关键词 600ms 防抖过滤生效

  // 进第一条故障详情
  await page.locator('.fault-item').first().click()
  await expect(page).toHaveURL(/\/faults\/\d+/)

  // 点返回（等价于 el-page-header 的返回 / 浏览器后退）
  await page.goBack()
  await expect(page).toHaveURL(/\/$/)

  // 产品 / 零件下拉应仍选中（keep-alive 缓存了首页筛选状态）
  await expect(
    page.locator('.field', { hasText: '1. 选择产品' }).locator('.el-select')
  ).toContainText('植保无人机 16L')
  await expect(
    page.locator('.field', { hasText: '2. 选择零件' }).locator('.el-select')
  ).toContainText('隔膜泵')
  // 关键词框内容应保留
  await expect(page.getByPlaceholder(/关键词/)).toHaveValue(firstTitle)

  // 故障列表应仍在：筛选条件确实恢复了，而不是回到"请先选择产品"的初始空态
  await expect(page.locator('.fault-item').first()).toBeVisible()
})
