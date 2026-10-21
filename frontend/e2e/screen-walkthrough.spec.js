// 逐屏人工验证清单（不是回归测试，一次性走查）
//
// 目的：补组件测试的两个环境盲区——
//   1. happy-dom 下 el-form-item 的报错节点不渲染
//   2. el-dialog / el-drawer 懒渲染
// 这两类只有真实浏览器能看出来，走查时重点盯。
//
// 截图产出在 .e2e-output/screens/，供人工复核。
import { test, expect } from '@playwright/test'
import { mkdirSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const ADMIN_USER = 'admin'
const ADMIN_PASS = 'yyzk123456'
// 必须用 fileURLToPath：pathname 会把中文路径百分号编码，mkdir 出来的目录对不上，
// 而 page.screenshot 写不进去时**不抛错**，表现为"用例通过但一张图都没有"
const SCREEN_DIR = fileURLToPath(new URL('../.e2e-output/screens/', import.meta.url))

async function shot(page, name) {
  const path = `${SCREEN_DIR}/${name}.png`
  // Chrome 的 Page.captureScreenshot 在页面还有动画/字体未稳时会报
  // "Unable to capture screenshot"（非尺寸问题，探针已验证 headless 截图本身可用）。
  // 等两帧再拍，并重试，避免偶发失败把整条走查打断。
  await page.mouse.move(0, 0) // 移走 hover，防止 tooltip / hover 态入镜
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    try {
      await page.screenshot({ path, fullPage: true, animations: 'disabled' })
      if (existsSync(path)) return
    } catch (e) {
      if (attempt === 3) throw e
      await page.waitForTimeout(300)
    }
  }
  // 截图写失败时 Playwright 不抛错，这里显式确认落盘，
  // 避免"用例全绿但一张证据都没有"的假绿
  if (!existsSync(path)) throw new Error(`截图未落盘：${path}`)
}

async function login(page) {
  await page.goto('/admin/login')
  await page.getByPlaceholder('请输入用户名').fill(ADMIN_USER)
  await page.getByPlaceholder('请输入密码').fill(ADMIN_PASS)
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(/\/admin\/tickets/)
}

/**
 * 选中一个 el-select 的选项。
 *
 * 不能直接用 `.el-select-dropdown:visible`：Element Plus 的下拉容器是复用的，
 * 关闭后 DOM 仍在，`:visible` 会命中上一个已关闭的下拉，点不到真正的那一项。
 * 改为从触发它的 input 的 aria-controls 找到对应下拉。
 */
async function pickOption(selectLocator, optionText) {
  await selectLocator.click()
  const input = selectLocator.locator('input').first()
  const listId = await input.getAttribute('aria-controls')
  const dropdown = listId
    ? selectLocator.page().locator(`#${listId}`).locator('..')
    : selectLocator.page().locator('.el-select-dropdown').last()
  const option = optionText
    ? dropdown.locator('.el-select-dropdown__item', { hasText: optionText }).first()
    : dropdown.locator('.el-select-dropdown__item').first()
  await option.click()
  return dropdown
}

async function openDropdown(selectLocator) {
  await selectLocator.click()
  const input = selectLocator.locator('input').first()
  const listId = await input.getAttribute('aria-controls')
  return listId
    ? selectLocator.page().locator(`#${listId}`).locator('..')
    : selectLocator.page().locator('.el-select-dropdown').last()
}

test.beforeAll(() => {
  mkdirSync(SCREEN_DIR, { recursive: true })
})

test('@walkthrough 逐屏验证：客户侧三页', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: '售后自助故障诊断' })).toBeVisible()
  await shot(page, '01-客户-首页-空态')

  // ---------- 三级级联 ----------
  const field = (label) => page.locator('.field', { hasText: label })
  await pickOption(field('1. 选择产品').locator('.el-select'))
  await pickOption(field('2. 选择零件').locator('.el-select'))
  await pickOption(field('3. 选择故障现象').locator('.el-select'))
  await shot(page, '02-客户-首页-已选故障')
  await page.getByRole('button', { name: '查看解决方案' }).click()
  await expect(page).toHaveURL(/\/faults\/\d+/)

  // ---------- 方案详情 ----------
  await expect(page.getByText('这个方案解决您的问题了吗？')).toBeVisible()
  await shot(page, '03-客户-方案详情')

  // ---------- 提交工单页 ----------
  await page.getByRole('button', { name: '仍然不行，提交工单' }).click()
  await expect(page).toHaveURL(/\/tickets\/new/)
  await shot(page, '04-客户-提交工单-空表单')

  // 空提交：必须看到字段级校验提示（组件测试看不到这个）
  await page.getByRole('button', { name: '提交工单' }).click()
  await page.waitForTimeout(500)
  const errCount = await page.locator('.el-form-item.is-error').count()
  console.log(`[提交工单] 空提交后 is-error 字段数 = ${errCount}`)
  await shot(page, '05-客户-提交工单-校验报错')
  expect(errCount).toBeGreaterThan(0)
})

test('@walkthrough 逐屏验证：提交成功页', async ({ page }) => {
  await page.goto('/tickets/success?ticket_no=TK202610210004&created_at=2026-10-21T11:24:26%2B08:00')
  await page.waitForTimeout(600)
  await shot(page, '06-客户-提交成功')
})

test('@walkthrough 逐屏验证：后台各页', async ({ page }) => {
  await login(page)

  // ---------- 工单列表 ----------
  await expect(page.locator('.el-table__row').first()).toBeVisible()
  const totalRows = await page.locator('.el-table__row').count()
  console.log(`[工单列表] 首屏行数 = ${totalRows}`)
  await shot(page, '07-后台-工单列表')

  // 筛选：状态
  await pickOption(page.locator('.filters .el-select').first(), '处理中')
  await page.waitForTimeout(600)
  const processingRows = await page.locator('.el-table__row').count()
  console.log(`[工单列表] 筛选"处理中"后行数 = ${processingRows}`)
  await shot(page, '08-后台-工单列表-筛选处理中')

  await page.getByRole('button', { name: '重置' }).click()
  await page.waitForTimeout(600)

  // ---------- 工单详情抽屉 ----------
  await page.locator('.el-table__row').first().click()
  const drawer = page.locator('.el-drawer')
  await expect(drawer).toBeVisible()
  await shot(page, '09-后台-工单详情抽屉')

  // 状态变更但不填备注 → 必须看到字段级报错（组件测试的盲区）
  const opts = await openDropdown(drawer.locator('.el-select').first())
  const optTexts = await opts.locator('.el-select-dropdown__item').allTextContents()
  console.log(`[工单详情] 状态可选项 = ${JSON.stringify(optTexts)}`)
  expect(optTexts.length).toBeGreaterThan(0)
  await opts.locator('.el-select-dropdown__item').last().click()

  await drawer.getByRole('button', { name: '保存' }).click()
  await page.waitForTimeout(500)
  const remarkErr = await drawer.locator('.el-form-item.is-error').count()
  console.log(`[工单详情] 备注为空时 is-error 字段数 = ${remarkErr}`)
  await shot(page, '10-后台-工单详情-备注必填报错')
  expect(remarkErr).toBeGreaterThan(0)

  await page.keyboard.press('Escape')
  await page.waitForTimeout(400)

  // ---------- 产品管理 ----------
  await page.goto('/admin/products')
  await expect(page.locator('.el-table__row').first()).toBeVisible()
  await shot(page, '11-后台-产品管理')

  await page.getByRole('button', { name: '新增产品' }).click()
  const dialog = page.locator('.el-dialog')
  await expect(dialog).toBeVisible()
  await shot(page, '12-后台-产品管理-新增弹窗')

  await dialog.getByRole('button', { name: '保存' }).click()
  await page.waitForTimeout(500)
  const formErrs = await dialog.locator('.el-form-item.is-error').count()
  console.log(`[产品新增] 空提交后 is-error 字段数 = ${formErrs}`)
  await shot(page, '13-后台-产品管理-空提交报错')
  expect(formErrs).toBeGreaterThan(0)

  await dialog.getByRole('button', { name: '取消' }).click()
  await page.waitForTimeout(400)

  // ---------- 零件管理 ----------
  await page.goto('/admin/parts')
  await expect(page.locator('.el-table__row').first()).toBeVisible()
  const partCount = await page.locator('.el-table__row').count()
  console.log(`[零件管理] 首产品零件数 = ${partCount}`)
  await shot(page, '14-后台-零件管理')

  // ---------- 故障知识库 ----------
  await page.goto('/admin/faults')
  await page.waitForTimeout(500)
  await shot(page, '15-后台-故障知识库')

  // ---------- 故障编辑 ----------
  const editBtn = page.locator('.el-table__row').first().getByRole('button', { name: '编辑' })
  await editBtn.click()
  await expect(page).toHaveURL(/\/admin\/faults\/edit\/\d+/)
  await page.waitForTimeout(800)
  await shot(page, '16-后台-故障编辑')
})

test('@walkthrough 逐屏验证：数据看板', async ({ page }) => {
  await login(page)
  await page.goto('/admin/stats')
  await expect(page.locator('.metric-value').first()).toBeVisible()
  await page.waitForTimeout(1500) // 等 echarts 画完
  await shot(page, '17-后台-数据看板')

  const metrics = await page.locator('.metric-value').allTextContents()
  console.log(`[看板] 四张卡 = ${JSON.stringify(metrics)}`)
  for (const m of metrics) expect(m.trim()).not.toMatch(/NaN|undefined/)

  const canvasCount = await page.locator('canvas').count()
  console.log(`[看板] canvas 数量 = ${canvasCount}`)
  expect(canvasCount).toBeGreaterThan(0)
})

test('@walkthrough 逐屏验证：错误态', async ({ page }) => {
  await login(page)
  await page.route('**/api/admin/tickets**', (route) =>
    route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ detail: '数据库不可用', code: 'SERVICE_UNAVAILABLE' })
    })
  )
  await page.goto('/admin/tickets')
  await page.reload()
  await page.waitForTimeout(1500)

  const tableGone = (await page.locator('.el-table').count()) === 0
  const hasRetry = await page
    .getByRole('button', { name: '重新加载' })
    .isVisible()
    .catch(() => false)
  console.log(`[错误态] 表格已卸载 = ${tableGone}，有重试按钮 = ${hasRetry}`)
  await shot(page, '18-后台-工单列表-错误态')
  expect(tableGone).toBe(true)
  expect(hasRetry).toBe(true)
})
