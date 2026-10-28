// 空闲自动登出（60 分钟）
//
// 场景：下班直接关机，第二天开机浏览器恢复后台某页，JWT 还在 24 小时有效期内，
// 任何人打开电脑都能直接看工单（含客户手机号）。这里验证超时后必须回到登录页。
import { expect, test } from '@playwright/test'

const ADMIN_USER = process.env.E2E_ADMIN_USER || 'admin'
const ADMIN_PASS = process.env.E2E_ADMIN_PASS || 'yyzk123456'

async function login(page) {
  await page.goto('/admin/login')
  await page.getByPlaceholder('请输入用户名').fill(ADMIN_USER)
  await page.getByPlaceholder('请输入密码').fill(ADMIN_PASS)
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(/\/admin\/tickets/)
}

/** 把"最后一次操作时间"往前拨（等价于"这台电脑已经 N 分钟没人动过"） */
function backdateActivity(page, minutes) {
  return page.evaluate(
    (mins) => localStorage.setItem('lastActiveAt', String(Date.now() - mins * 60 * 1000)),
    minutes
  )
}

test('@smoke 空闲 2 小时后打开后台页：回登录页并提示，凭证被清掉', async ({ page }) => {
  await login(page)
  await backdateActivity(page, 120)

  // reload = 第二天开机浏览器恢复同一个地址：守卫在渲染前就应该拦住
  await page.reload()

  await expect(page).toHaveURL(/\/admin\/login\?reason=idle/)
  await expect(page.getByText('长时间未操作，已自动退出')).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('token'))).toBeNull()
})

test('@smoke 刚操作过的会话不会被误踢', async ({ page }) => {
  await login(page)
  await backdateActivity(page, 1)
  await page.reload()

  await expect(page).toHaveURL(/\/admin\/tickets/)
  await expect(page.getByRole('menuitem', { name: '工单管理' })).toBeVisible()
})

test('@smoke 切回标签页时补判一次（后台标签的定时器会被节流）', async ({ page }) => {
  await login(page)
  await backdateActivity(page, 90)

  // 不刷新页面，靠 visibilitychange 的补判：模拟"从别的窗口切回来"
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
    document.dispatchEvent(new Event('visibilitychange'))
  })

  await expect(page).toHaveURL(/\/admin\/login\?reason=idle/)
})
