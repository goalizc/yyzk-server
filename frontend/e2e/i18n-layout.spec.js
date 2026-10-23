// 英文排版守卫：表单标签不得折行
//
// 为什么需要这条：中文标签短（「零件编号」4 字），英文长 1.5–2 倍
// （"Part number" / "Confirm password" / "Requires a professional"）。
// 写死 label-width 时中文正好、英文折行。
//
// 检测不能靠截图，也不能靠"盒高变大"：
//   el-form-item 的行高锁死 32px，label 折行后盒子高度**仍然是 32px**，
//   溢出的第二行直接压到下一行表单上（视觉上是文字重叠，不是行变高）。
//   唯一可靠的信号是 `label.scrollHeight` 翻倍。
//
// 标签宽度由 useFormLabelWidth(中文宽, 英文宽) 按语言给，改宽度只改那一处。
import { expect, test } from '@playwright/test'

const ADMIN_USER = process.env.E2E_ADMIN_USER || 'admin'
const ADMIN_PASS = process.env.E2E_ADMIN_PASS || 'yyzk123456'

/** 登录并强制英文（后台语言只认 localStorage，不跟随浏览器） */
async function loginEnglish(page) {
  await page.goto('/admin/login')
  await page.evaluate(() => localStorage.setItem('locale', 'en-US'))
  await page.reload()
  await page.getByPlaceholder('Enter your username').fill(ADMIN_USER)
  await page.getByPlaceholder('Enter your password').fill(ADMIN_PASS)
  await page.locator('.submit').click()
  await page.waitForURL(/\/admin\/tickets/)
}

/**
 * 返回当前页面所有折行的标签文案。
 * 判据：scrollHeight >= 1.5 × line-height（单行 32px，折行 64px）
 */
function wrappedLabels(page) {
  return page.evaluate(() =>
    [...document.querySelectorAll('.el-form-item__label')]
      .filter((el) => el.offsetParent) // 跳过隐藏的（v-if 关闭的弹窗）
      .filter((el) => {
        const lh = parseFloat(getComputedStyle(el).lineHeight) || 22
        const h = Math.max(el.getBoundingClientRect().height, el.scrollHeight)
        return h >= lh * 1.5
      })
      .map((el) => el.textContent.trim())
  )
}

test('@smoke 英文界面表单标签不折行（含各新建弹窗与详情面板）', async ({ page }) => {
  await loginEnglish(page)

  // 每个场景：进页面 →（可选）打开弹窗 → 收集折行标签
  const scenes = [
    {
      name: '故障编辑器',
      open: async () => {
        await page.goto('/admin/faults/edit')
        // 最长标签 "Requires a professional"
        await expect(page.getByText('Requires a professional', { exact: true }).first()).toBeVisible()
      }
    },
    {
      name: '用户新建弹窗',
      open: async () => {
        await page.goto('/admin/users')
        await page.getByRole('button', { name: 'New user' }).click()
        // 最长标签 "Confirm password"
        await expect(page.getByText('Confirm password', { exact: true }).first()).toBeVisible()
      }
    },
    {
      name: '临时授权面板',
      open: async () => {
        await page.goto('/admin/users')
        await page.getByRole('button', { name: 'Grants' }).first().click()
        await expect(page.getByText('Issue a new grant')).toBeVisible()
      }
    },
    {
      name: '产品新建弹窗',
      open: async () => {
        await page.goto('/admin/products')
        await page.getByRole('button', { name: 'New product' }).click()
        await expect(page.getByText('Product line', { exact: true }).first()).toBeVisible()
      }
    },
    {
      name: '零件新建弹窗',
      open: async () => {
        await page.goto('/admin/parts')
        // 零件页要先选产品才出列表，但「新增零件」按钮始终在
        await page.getByRole('button', { name: 'New part' }).click()
        await expect(page.getByText('Part number', { exact: true }).first()).toBeVisible()
      }
    },
    {
      name: '产品线新建弹窗',
      open: async () => {
        await page.goto('/admin/product-lines')
        await page.getByRole('button', { name: 'New product line' }).click()
        await expect(page.getByText('Sort order', { exact: true }).first()).toBeVisible()
      }
    },
    {
      name: '工单详情面板',
      open: async () => {
        await page.goto('/admin/tickets')
        await page.locator('.el-table__row').first().click()
        // 面板里最长标签 "Assignee"
        await expect(page.getByText('Assignee', { exact: true }).first()).toBeVisible()
      }
    },
    {
      name: '修改密码弹窗',
      open: async () => {
        await page.goto('/admin/tickets')
        await page.getByRole('button', { name: 'Change password' }).click()
        await expect(page.getByText('Confirm password', { exact: true }).first()).toBeVisible()
      }
    },
    {
      name: '客户侧提交工单',
      open: async () => {
        await page.goto('/en/tickets/new')
        // 最长标签 "On-site service"
        await expect(page.getByText('On-site service', { exact: true }).first()).toBeVisible()
      }
    }
  ]

  const failures = []
  for (const scene of scenes) {
    await scene.open()
    // 等弹窗/面板动画结束再量，否则拿到的是过渡中的宽度
    await page.waitForTimeout(400)
    const bad = await wrappedLabels(page)
    if (bad.length) failures.push(`${scene.name}: ${bad.join(' / ')}`)
  }

  expect(
    failures,
    `以下英文表单标签折行（宽度不够，请调大该页 useFormLabelWidth 的英文宽度）：\n${failures.join('\n')}`
  ).toEqual([])
})

// 英文界面下弹窗不得横向溢出。
//
// 典型事故：中文「删除」只有 2 个字，英文 "Delete" 更宽，固定宽度的行内控件
// 会被挤出弹窗边界（用户报过：新建/编辑用户里"删除产品线"按钮越界）。
// 中文下量不出来，只有切到英文才暴露。
test('@smoke 英文界面弹窗内容不横向溢出', async ({ page }) => {
  await loginEnglish(page)

  const scenes = [
    {
      name: '新建用户（含产品线分配行）',
      path: '/admin/users',
      open: async () => {
        await page.getByRole('button', { name: 'New user' }).click()
        // 分配行是溢出的高发区，必须有一行才量得到
        await page.getByRole('button', { name: 'Add product line' }).click()
      }
    },
    {
      name: '新建产品',
      path: '/admin/products',
      open: async () => {
        await page.getByRole('button', { name: 'New product' }).click()
      }
    },
    {
      name: '新建零件',
      path: '/admin/parts',
      open: async () => {
        await page.getByRole('button', { name: 'New part' }).click()
      }
    },
    {
      name: '新建产品线',
      path: '/admin/product-lines',
      open: async () => {
        await page.getByRole('button', { name: 'New product line' }).click()
      }
    },
    {
      name: '工单详情面板',
      path: '/admin/tickets',
      open: async () => {
        await page.locator('.el-table__row').first().click()
      }
    },
    {
      name: '方案阅读面板',
      path: '/admin/faults',
      open: async () => {
        await page.locator('.el-table__row').first().click()
      }
    }
  ]

  const problems = []
  for (const scene of scenes) {
    await page.goto(scene.path)
    await page.waitForTimeout(1000)
    await scene.open()
    await page.waitForTimeout(600)

    const over = await page.evaluate(() => {
      // 注意：':visible' 是 Playwright 专有伪类，浏览器端 querySelector 不认
      const dialog = [...document.querySelectorAll('.el-dialog')].find(
        (el) => el.offsetParent !== null
      )
      if (!dialog) return null
      const body = dialog.querySelector('.el-dialog__body')
      if (!body) return 0
      return body.scrollWidth - body.clientWidth
    })

    if (over === null) problems.push(`${scene.name}: 没找到弹窗`)
    else if (over > 0) problems.push(`${scene.name}: 横向溢出 ${over}px`)
    await page.keyboard.press('Escape')
    await page.waitForTimeout(300)
  }

  expect(
    problems,
    `英文弹窗内容横向溢出（元素宽度写死，没给英文留余量）：\n${problems.join('\n')}`
  ).toEqual([])
})
