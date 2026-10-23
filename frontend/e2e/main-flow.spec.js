// 主链路冒烟（唯一一条 E2E）：
//   客户三级级联 → 方案页 → 反馈未解决 → 提交工单
//   → 后台登录 → 工单列表看到它 → 改状态带备注 → 看板数值随之变化
//
// 为什么只写这一条：单测已覆盖各页分支，E2E 的价值在"跨页面 + 真实后端 + 真实浏览器"，
// 加 CRUD 会让维护成本翻倍而边际收益很低（技能 §14：E2E 少而精，只覆盖主链路）。
//
// 数据前提：docker 全栈已启动且已 init，库里存在产品「智能扫地机器人 X1」、
// 零件「主刷模组」（动力系统）、故障「主刷不转动」。
import { test, expect } from '@playwright/test'

const ADMIN_USER = process.env.E2E_ADMIN_USER || 'admin'
const ADMIN_PASS = process.env.E2E_ADMIN_PASS || 'yyzk123456'

// 每次跑都生成唯一联系方式，避免与历史工单混淆
const stamp = Date.now().toString().slice(-8)
const CONTACT = `138${stamp}`
const DESCRIPTION = `E2E 自动化验证工单 ${stamp}：开机后主刷不转，已按方案排查未解决。`

/** Element Plus 的 el-select 不是原生 select：点开下拉再点选项 */
async function pickSelect(page, fieldLabel, optionText) {
  const field = page.locator('.field', { hasText: fieldLabel })
  await field.locator('.el-select').click()
  // 下拉是 teleport 到 body 的，按可见的文字选项点
  await page.locator('.el-select-dropdown:visible .el-select-dropdown__item', { hasText: optionText })
    .first()
    .click()
}

test('@smoke 客户排查到后台处理的主链路', async ({ page }) => {
  // ---------- 1. 客户侧：三级级联 ----------
  await page.goto('/')
  await expect(page.getByRole('heading', { name: '售后自助故障诊断' })).toBeVisible()

  await pickSelect(page, '1. 选择产品', '智能扫地机器人')
  await pickSelect(page, '2. 选择零件', '主刷模组')
  await pickSelect(page, '3. 选择故障现象', '主刷不转动')

  // 选中故障后出现"查看解决方案"
  await page.getByRole('button', { name: '查看解决方案' }).click()

  // ---------- 2. 方案详情：反馈未解决 ----------
  await expect(page).toHaveURL(/\/faults\/\d+/)
  await expect(page.getByText('这个方案解决您的问题了吗？')).toBeVisible()
  await page.getByRole('button', { name: '未解决' }).click()
  // 反馈成功后按钮禁用，提示文案切换
  await expect(page.getByRole('button', { name: '未解决' })).toBeDisabled()

  // ---------- 3. 提交工单 ----------
  await page.getByRole('button', { name: '仍然不行，提交工单' }).click()
  await expect(page).toHaveURL(/\/tickets\/new/)

  await page.getByPlaceholder('手机号或邮箱，便于工程师联系您').fill(CONTACT)
  await page.getByPlaceholder('选填，如：张先生').fill('E2E 测试')
  await page
    .getByPlaceholder(/请描述故障现象/)
    .fill(DESCRIPTION)
  await page.getByRole('button', { name: '提交工单' }).click()

  // 成功页应出现工单号（DOM 是 .ticket-no > .value）
  await expect(page).toHaveURL(/\/tickets\/success/)
  const ticketNoLocator = page.locator('.ticket-no .value')
  await expect(ticketNoLocator).toBeVisible()
  const ticketNo = (await ticketNoLocator.textContent())?.trim()
  expect(ticketNo).toMatch(/^TK\d+/)

  // ---------- 4. 后台登录 ----------
  await page.goto('/admin/login')
  await page.getByPlaceholder('请输入用户名').fill(ADMIN_USER)
  await page.getByPlaceholder('请输入密码').fill(ADMIN_PASS)
  await page.getByRole('button', { name: '登录' }).click()
  // 登录后默认落到工单列表
  await expect(page).toHaveURL(/\/admin\/tickets/)

  // 超级管理员应看到用户管理入口
  await expect(page.getByRole('menuitem', { name: '用户管理' })).toBeVisible()

  // ---------- 5. 按单号搜到刚才那张工单 ----------
  await page.getByPlaceholder('工单号或联系方式').fill(ticketNo)
  await page.waitForTimeout(500) // 关键词 300ms 防抖
  const row = page.locator('.el-table__row', { hasText: ticketNo })
  await expect(row).toHaveCount(1)

  // ---------- 6. 打开详情，改状态（强制备注） ----------
  await row.click()
  // 详情已改为居中弹窗（components/DetailPanel.vue），不再是右侧抽屉
  const panel = page.locator('.detail-panel')
  await expect(panel).toBeVisible()
  await expect(panel).toContainText(ticketNo)
  // 未认领时提示"由你认领"
  await expect(panel).toContainText('本单暂无处理人')

  // 状态下拉只应列出合法目标：open → processing / closed
  await panel.locator('.el-select').first().click()
  const options = page.locator('.el-select-dropdown:visible .el-select-dropdown__item')
  await expect(options).toHaveCount(2)
  await options.filter({ hasText: '处理中' }).click()

  // 备注框按 role 定位，不绑 placeholder 文案——placeholder 随状态变化（选定状态后
  // 换成"如：已电话指导……"），而报错文案只在校验失败时出现。两者刻意不同：
  // placeholder 说"该写什么"，报错说"为什么不行"，用文案互相定位是脆的。
  const remark = panel.getByRole('textbox', { name: '备注' })
  const saveBtn = panel.getByRole('button', { name: '保存' })

  // 备注为空时点保存：必须被拦下，不能发请求
  await saveBtn.click()
  await expect(panel).toContainText('变更状态必须填写备注')

  await remark.fill('E2E：已远程指导更换主刷电机')
  await saveBtn.click()
  await expect(page.locator('.el-message--success')).toBeVisible()
  // 保存后作为当前用户认领，提示文案随之变化
  await expect(panel).toContainText('系统管理员')

  // ---------- 7. 看板：解决率与工单数应为合理数值 ----------
  await page.goto('/admin/stats')
  const metrics = page.locator('.metric-value')
  await expect(metrics.first()).toBeVisible()
  // 四张卡都必须是数字或占位符，不能出现 NaN / undefined
  const texts = await metrics.allTextContents()
  expect(texts.length).toBeGreaterThanOrEqual(4)
  for (const t of texts) {
    expect(t.trim()).not.toMatch(/NaN|undefined/)
  }
})
