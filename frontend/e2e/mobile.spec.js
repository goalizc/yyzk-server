// 移动端适配验收（TC-61）
//
// 三条硬性口径，全部可自动断言：
//   1. 无横向滚动：scrollWidth <= clientWidth + 1
//   2. 可点区域 >= 44px（高度）：el-button / el-input / el-select / el-switch / a
//   3. 输入框字号 >= 16px：低于 16px 时 iOS Safari 聚焦会自动放大页面
//
// 运行：npm run e2e:mobile
// 前置：docker compose 全栈已起（同 playwright.config.js）
//
// 为什么用 (pointer: coarse) 而不是窗口宽度驱动样式：平板触摸屏 1000px 宽
// 同样需要 44px 命中区，桌面窄窗口（鼠标）不需要。这里用 isMobile + hasTouch
// 复现真实触摸设备，样式才会走 main.css 里 pointer: coarse 那条分支。
import { test, expect } from '@playwright/test'
import { mkdirSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const SCREEN_DIR = fileURLToPath(new URL('../.e2e-output/mobile/', import.meta.url))

// 真实 iOS Safari 的 UA。除了让服务端/前端能识别移动端，也让 Chrome
// 打开"移动端"分支（isMobile 只有在移动 UA 下才完全生效）。
const IPHONE_UA =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 ' +
  '(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'

// 覆盖面取主流窄屏：360 是国产安卓最常见宽度，390 是 iPhone 12–15，
// 414 是 iPhone Plus/Max。320（iPhone SE 一代）已基本淘汰，不纳入。
const VIEWPORTS = [
  { name: '360x800', width: 360, height: 800 },
  { name: '390x844', width: 390, height: 844 },
  { name: '414x896', width: 414, height: 896 }
]

const TAP_MIN = 44

// 后台用例需要登录。默认值与 init_admin.py 的演示口令一致；
// 线上环境改过密码时用 E2E_ADMIN_PASS 覆盖，避免把真实口令写进仓库。
const ADMIN_USER = process.env.E2E_ADMIN_USER || 'admin'
const ADMIN_PASS = process.env.E2E_ADMIN_PASS || 'yyzk123456'

// 演示库里的固定数据：产品 1「植保无人机 16L」/ 零件 10「智能电池」/ 故障 9
// （seed_demo.py 重建后 id 从 1 起，故障 9 是「满电续航明显缩短」）
// 不写死也行，但移动端用例需要"打开就是有内容"的状态来量真实渲染尺寸，
// 探测式取首条会引入顺序依赖，这里用初始化脚本里的演示数据更稳。
const FAULT_ID = 9

async function shot(page, name) {
  const path = `${SCREEN_DIR}/${name}.png`
  await page.mouse.move(0, 0)
  await page.screenshot({ path, fullPage: true, animations: 'disabled' })
  if (!existsSync(path)) throw new Error(`截图未落盘：${path}`)
}

/**
 * 量当前页面的三个指标。
 *
 * 只统计"真正呈现给用户"的元素：display:none / 零尺寸的一律跳过，
 * 否则 el-select 内部那个 width:0 的隐藏 input 会稳定刷出一堆假阳性。
 */
async function audit(page) {
  return page.evaluate((tapMin) => {
    const de = document.documentElement

    const visible = (el) => {
      const rect = el.getBoundingClientRect()
      if (rect.width === 0 || rect.height === 0) return null
      const style = getComputedStyle(el)
      if (style.visibility === 'hidden' || style.display === 'none') return null
      return rect
    }

    const tooSmall = []
    const smallSelector =
      '.el-button, .el-select, .el-switch, .el-input__wrapper, a[href], .fault-item'
    for (const el of document.querySelectorAll(smallSelector)) {
      const rect = visible(el)
      if (!rect) continue
      // 只卡高度：宽度天然由内容决定（"返回"只有 60px 宽也合规），
      // WCAG 2.5.5 要求的是 44×44 的命中区，对我们这类通栏布局，
      // 高度不足才是真问题（拇指纵向定位精度更差）。
      if (rect.height < tapMin) {
        tooSmall.push({
          cls: String(el.className || '').slice(0, 60),
          text: (el.textContent || '').trim().slice(0, 20),
          w: Math.round(rect.width),
          h: Math.round(rect.height)
        })
      }
    }

    // 输入类元素聚焦时的实际字号
    const smallFont = []
    for (const el of document.querySelectorAll('input, textarea, .el-textarea__inner')) {
      const rect = visible(el)
      if (!rect) continue
      const size = parseFloat(getComputedStyle(el).fontSize)
      if (size > 0 && size < 16) {
        smallFont.push({
          cls: String(el.className || '').slice(0, 60),
          fontPx: size
        })
      }
    }

    return {
      scrollWidth: de.scrollWidth,
      clientWidth: de.clientWidth,
      overflow: de.scrollWidth > de.clientWidth + 1,
      tooSmall,
      smallFont
    }
  }, TAP_MIN)
}

async function pickOption(page, selectLocator) {
  await selectLocator.click()
  const input = selectLocator.locator('input').first()
  const listId = await input.getAttribute('aria-controls')
  const dropdown = listId
    ? page.locator(`#${listId}`).locator('..')
    : page.locator('.el-select-dropdown').last()
  await dropdown.locator('.el-select-dropdown__item').first().click()
  // 等级联下一级的请求落地，否则量到的是加载中的骨架
  await page.waitForTimeout(500)
}

test.beforeAll(() => {
  mkdirSync(SCREEN_DIR, { recursive: true })
})

for (const vp of VIEWPORTS) {
  test.describe(`视口 ${vp.name}`, () => {
    // 不能直接展开 devices['iPhone 12']：它带 defaultBrowserType，
    // 在 describe 内使用会强开新 worker，Playwright 直接报错。
    // 只取真正影响断言的几项，浏览器仍沿用配置里的 channel: 'chrome'。
    test.use({
      viewport: { width: vp.width, height: vp.height },
      deviceScaleFactor: 2,
      isMobile: true,
      hasTouch: true,
      userAgent: IPHONE_UA
    })

    test(`@mobile 客户侧四页无横向滚动、可点区与字号达标（${vp.name}）`, async ({ page }) => {
      // ---------- 首页：空态 ----------
      await page.goto('/')
      await expect(page.getByRole('heading', { name: '售后自助故障诊断' })).toBeVisible()
      let m = await audit(page)
      await shot(page, `${vp.name}-01-首页-空态`)
      expect(m.overflow, `首页空态横向溢出 ${m.scrollWidth}/${m.clientWidth}`).toBe(false)
      expect(m.tooSmall, `首页空态可点区不足：${JSON.stringify(m.tooSmall)}`).toHaveLength(0)
      expect(m.smallFont, `首页空态输入框字号过小：${JSON.stringify(m.smallFont)}`).toHaveLength(0)

      // ---------- 首页：选完两级后的故障现象列表 ----------
      const fields = page.locator('.field .el-select')
      await pickOption(page, fields.nth(0))
      await pickOption(page, fields.nth(1))
      await page.waitForTimeout(400)
      expect(
        await page.locator('.fault-item').count(),
        '零件下应有故障列表，用例依赖此前提'
      ).toBeGreaterThan(0)
      m = await audit(page)
      await shot(page, `${vp.name}-02-首页-故障列表`)
      expect(m.overflow, `首页列表态横向溢出 ${m.scrollWidth}/${m.clientWidth}`).toBe(false)
      expect(m.tooSmall, `首页列表态可点区不足：${JSON.stringify(m.tooSmall)}`).toHaveLength(0)

      // ---------- 首页：关键词搜不到时的空态（提交工单入口必须点得到） ----------
      await page.locator('.search input').fill('zzzzzz')
      await page.waitForTimeout(1200)
      await expect(page.getByText('没有找到匹配的解决方案')).toBeVisible()
      m = await audit(page)
      await shot(page, `${vp.name}-03-首页-无结果`)
      expect(m.overflow, `首页空结果横向溢出 ${m.scrollWidth}/${m.clientWidth}`).toBe(false)
      expect(m.tooSmall, `首页空结果可点区不足：${JSON.stringify(m.tooSmall)}`).toHaveLength(0)

      // ---------- 方案详情 ----------
      await page.goto(`/faults/${FAULT_ID}`)
      await expect(page.getByText('这个方案解决您的问题了吗？')).toBeVisible()
      m = await audit(page)
      await shot(page, `${vp.name}-04-方案详情`)
      expect(m.overflow, `详情页横向溢出 ${m.scrollWidth}/${m.clientWidth}`).toBe(false)
      expect(m.tooSmall, `详情页可点区不足：${JSON.stringify(m.tooSmall)}`).toHaveLength(0)

      // 详情页的描述表最容易在窄屏上出问题：label 被挤成一字一行。
      // 直接量高度不可靠——单元格自带 8px 上下内边距，单行也有 32px。
      // 改为量 label 的"文字宽度"与"实际宽度"：折行时实际宽度会被压缩，
      // 未折行时两者相等。
      const descLabels = await page.locator('.el-descriptions__label').evaluateAll((els) =>
        els.map((el) => {
          const range = document.createRange()
          range.selectNodeContents(el)
          return {
            text: (el.textContent || '').trim(),
            contentWidth: Math.round(range.getBoundingClientRect().width),
            boxWidth: Math.round(el.getBoundingClientRect().width)
          }
        })
      )
      for (const item of descLabels) {
        // 允许 2px 误差（字体亚像素取整）
        expect(
          item.boxWidth,
          `详情页 label「${item.text}」被挤窄（文字 ${item.contentWidth}px / 容器 ${item.boxWidth}px），已折行`
        ).toBeGreaterThanOrEqual(item.contentWidth - 2)
      }

      // ---------- 提交工单 ----------
      await page.goto(`/tickets/new?product_id=12&part_id=9&fault_id=${FAULT_ID}`)
      await expect(page.getByRole('button', { name: '提交工单' })).toBeVisible()
      m = await audit(page)
      await shot(page, `${vp.name}-05-提交工单`)
      expect(m.overflow, `工单页横向溢出 ${m.scrollWidth}/${m.clientWidth}`).toBe(false)
      expect(m.tooSmall, `工单页可点区不足：${JSON.stringify(m.tooSmall)}`).toHaveLength(0)
      expect(m.smallFont, `工单页输入框字号过小：${JSON.stringify(m.smallFont)}`).toHaveLength(0)

      // 手机上 label 必须在上方（label-position=top），否则 96px 左栏会挤掉输入宽度
      const labelPosition = await page.evaluate(() => {
        const item = document.querySelector('.el-form-item')
        const label = item?.querySelector('.el-form-item__label')
        if (!label) return 'none'
        // 标签与内容左右并排时 label 的右边会贴住内容左边；上下堆叠时两者顶边接近
        const content = item.querySelector('.el-form-item__content')
        if (!content) return 'none'
        const l = label.getBoundingClientRect()
        const c = content.getBoundingClientRect()
        return c.top >= l.bottom - 2 ? 'top' : 'left'
      })
      expect(labelPosition, '手机上工单表单标签应在上方').toBe('top')

      // ---------- 提交成功 ----------
      // 用超长工单号压一压，确认真实生成的号码不会把布局撑破
      await page.goto('/tickets/success?ticket_no=TK202610210004&created_at=2026-10-21T11:24:26%2B08:00')
      await expect(page.getByText('工单已提交')).toBeVisible()
      m = await audit(page)
      await shot(page, `${vp.name}-06-提交成功`)
      expect(m.overflow, `成功页横向溢出 ${m.scrollWidth}/${m.clientWidth}`).toBe(false)
      expect(m.tooSmall, `成功页可点区不足：${JSON.stringify(m.tooSmall)}`).toHaveLength(0)

      // ---------- 后台（运维偶尔要在手机上看一眼工单） ----------
      // 口径与前四页不同：后台的表格列宽之和必然超过手机宽度，
      // 表格自身的横向滚动是合理设计，不能按"整页不溢出"一刀切。
      // 这里只断言两件事：整页不溢出（容器不把页面撑宽）、侧栏在窄屏收起。
      await page.goto('/admin/login')
      await page.getByPlaceholder('请输入用户名').fill(ADMIN_USER)
      await page.getByPlaceholder('请输入密码').fill(ADMIN_PASS)
      await page.getByRole('button', { name: '登录' }).click()
      await expect(page).toHaveURL(/\/admin\/tickets/)
      // 等 el-message 的"登录成功"提示淡出，否则它会遮住顶栏按钮
      await page.waitForTimeout(3000)

      m = await audit(page)
      await shot(page, `${vp.name}-07-后台-工单列表`)
      expect(m.overflow, `后台横向溢出 ${m.scrollWidth}/${m.clientWidth}`).toBe(false)
      // 表格可能被 el-table 包在内层滚动容器里，这里只检查顶栏与筛选区
      expect(m.tooSmall, `后台可点区不足：${JSON.stringify(m.tooSmall)}`).toHaveLength(0)

      // 窄屏必须收起侧栏：固定 200px 的 aside 会把 390px 屏的表格挤成一列
      const asideCount = await page.locator('.el-aside').count()
      expect(asideCount, '窄屏下侧栏应收起（改由顶栏下拉导航）').toBe(0)

      // 顶栏下拉是窄屏唯一的导航入口，必须存在且能打开。
      // el-dropdown 把点击事件绑在内层触发元素上，点外层容器不会打开。
      const navButton = page.locator('.nav-dropdown button')
      await expect(navButton).toBeVisible()
      await navButton.click()
      const navItem = page.locator('.el-dropdown-menu__item', { hasText: '数据看板' })
      await expect(navItem).toBeVisible()
      await navItem.click()
      await expect(page).toHaveURL(/\/admin\/stats/)
      await page.waitForTimeout(1500)
      m = await audit(page)
      await shot(page, `${vp.name}-08-后台-数据看板`)
      expect(m.overflow, `数据看板横向溢出 ${m.scrollWidth}/${m.clientWidth}`).toBe(false)
    })
  })
}
