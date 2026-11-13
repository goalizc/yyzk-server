// 中英排版守卫：表单标签不得折行、列表不得横向溢出
//
// 为什么需要这条：中文标签短（「零件编号」4 字），英文长 1.5–2 倍
// （"Part number" / "Confirm password" / "Requires a professional"）。
// 写死 label-width 时中文正好、英文折行。
//
// 但反过来也成立：中文一旦写成「单价（选填，仅留档）」这种 10 字标签，
// 150px 的 label-width 连中文都装不下——只测英文会漏掉这类（用户报过折行）。
// 故英文场景全量扫一遍，中文场景补扫标签最长的进销存弹窗。
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

/** 登录并强制中文 */
async function loginChinese(page) {
  await page.goto('/admin/login')
  await page.evaluate(() => localStorage.setItem('locale', 'zh-CN'))
  await page.reload()
  await page.getByPlaceholder('请输入用户名').fill(ADMIN_USER)
  await page.getByPlaceholder('请输入密码').fill(ADMIN_PASS)
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

/** 当前可见弹窗内 el-table 的横向溢出像素；找不到弹窗/表格返回 null。 */
function dialogTableOverflow(page) {
  return page.evaluate(() => {
    const dialog = [...document.querySelectorAll('.el-dialog')].find(
      (el) => el.offsetParent !== null
    )
    if (!dialog) return null
    const table = dialog.querySelector('.el-table')
    if (!table) return null
    const wrap =
      table.querySelector('.el-scrollbar__wrap') || table.querySelector('.el-table__body-wrapper')
    return wrap ? wrap.scrollWidth - wrap.clientWidth : null
  })
}

/** 数量列 el-input-number 右边界相对单元格内容区的溢出像素（>0 即被裁切）。 */
function quantityControlOverflow(page) {
  return page.evaluate(() => {
    const dialog = [...document.querySelectorAll('.el-dialog')].find(
      (el) => el.offsetParent !== null
    )
    if (!dialog) return null
    const row = dialog.querySelector('.el-table__body tbody tr') || dialog.querySelector('.el-table__row')
    const cell = row?.querySelectorAll('td')[1]
    const content = cell?.querySelector('.cell')
    const input = cell?.querySelector('.el-input-number')
    if (!content || !input) return null
    const contentRect = content.getBoundingClientRect()
    const inputRect = input.getBoundingClientRect()
    const increase = cell.querySelector('.el-input-number__increase')
    const controlRect = increase ? increase.getBoundingClientRect() : null
    return {
      input: Math.round(inputRect.right - contentRect.right),
      control: controlRect ? Math.round(controlRect.right - contentRect.right) : null
    }
  })
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
      name: '物资 SKU 新建弹窗',
      open: async () => {
        await page.goto('/admin/inventory/skus')
        await page.getByRole('button', { name: 'New SKU' }).click()
        // 最长标签 "Low-stock threshold" / "Unit cost (optional)"
        await expect(page.getByText('Low-stock threshold', { exact: true }).first()).toBeVisible()
      }
    },
    {
      name: '物资分类新建弹窗',
      open: async () => {
        await page.goto('/admin/inventory/categories')
        await page.getByRole('button', { name: 'New category' }).click()
        await expect(page.getByText('Category name', { exact: true }).first()).toBeVisible()
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
      name: '新建 SKU',
      path: '/admin/inventory/skus',
      open: async () => {
        await page.getByRole('button', { name: 'New SKU' }).click()
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

// 中文界面同样会折行：标签写长了（「单价（选填，仅留档）」10 个全角字）150px 装不下。
// 只扫进销存这几个弹窗——其余页面中文标签都是 3–5 字，英文用例已覆盖。
test('@smoke 中文界面表单标签不折行（标签最长的进销存弹窗）', async ({ page }) => {
  await loginChinese(page)

  const scenes = [
    {
      name: '物资 SKU 新建弹窗',
      path: '/admin/inventory/skus',
      open: async () => {
        await page.getByRole('button', { name: '新建 SKU', exact: true }).click()
      }
    },
    {
      name: '物资分类新建弹窗',
      path: '/admin/inventory/categories',
      open: async () => {
        await page.getByRole('button', { name: '新建分类', exact: true }).click()
      }
    },
    {
      name: '登记入库弹窗',
      path: '/admin/inventory/inbound',
      open: async () => {
        await page.getByRole('button', { name: '登记入库', exact: true }).first().click()
      }
    },
    {
      name: '登记出库弹窗',
      path: '/admin/inventory/outbound',
      open: async () => {
        await page.getByRole('button', { name: '登记出库', exact: true }).first().click()
      }
    }
  ]

  const failures = []
  for (const scene of scenes) {
    await page.goto(scene.path)
    await page.waitForTimeout(1000)
    await scene.open()
    await page.waitForTimeout(600)
    const bad = await wrappedLabels(page)
    if (bad.length) failures.push(`${scene.name}: ${bad.join(' / ')}`)
    await page.keyboard.press('Escape')
    await page.waitForTimeout(300)
  }

  expect(
    failures,
    `以下中文表单标签折行（文案偏长或 label-width 偏窄，改标签文案或调大 useFormLabelWidth 的中文宽度）：\n${failures.join('\n')}`
  ).toEqual([])
})

// 列表页表格不得横向溢出（1440 桌面宽度）。
//
// 典型事故：给 SKU 列表加了「分类」「关联产品」两列固定 min-width 后，
// 总宽 1330 > 可用 1166，整张表被迫横向滚动——而这一页本来是用来"扫一眼"的，
// 一滚动就看不全。加了新列必须在这一页重新配平宽度。
test('@smoke 桌面宽度下列表表格不横向溢出', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await loginChinese(page)

  const routes = [
    { path: '/admin/inventory/skus', name: '物资列表' },
    { path: '/admin/inventory/categories', name: '物资分类' },
    { path: '/admin/inventory/inbound', name: '入库单列表' },
    { path: '/admin/inventory/outbound', name: '出库单列表' },
    { path: '/admin/inventory/movements', name: '库存流水' }
  ]

  const problems = []
  for (const route of routes) {
    await page.goto(route.path)
    await page.waitForTimeout(1200)
    const over = await page.evaluate(() => {
      const table = document.querySelector('.el-table')
      if (!table) return null
      const wrap = table.querySelector('.el-scrollbar__wrap') || table.querySelector('.el-table__body-wrapper')
      return wrap ? wrap.scrollWidth - wrap.clientWidth : 0
    })
    if (over === null) problems.push(`${route.name}: 没找到表格`)
    else if (over > 0) problems.push(`${route.name}: 横向溢出 ${over}px`)
  }

  expect(
    problems,
    `列表表格在 1440 宽下横向溢出（列宽总和超了可用宽度，请压缩固定列或改用 min-width 让列自适应）：\n${problems.join('\n')}`
  ).toEqual([])
})

// 出库登记弹窗的明细行最长（SKU / 数量 / 余额 / 单价 / 备注 / 操作六列）。
// 用户反馈"明细编辑行显示不全、需要拖动"，故单独锁一条：表格容器不得出现横向滚动。
test('@smoke 出库登记弹窗明细表不横向滚动', async ({ page }) => {
  await loginChinese(page)

  // 覆盖常见桌面宽度 + 窄窗口：1440 / 1366 / 1280 / 1024 / 900 / 800
  for (const width of [1440, 1366, 1280, 1024, 900, 800]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/admin/inventory/outbound')
    await page.waitForTimeout(1000)
    await page.getByRole('button', { name: '登记出库', exact: true }).first().click()
    await page.waitForTimeout(600)

    const over = await dialogTableOverflow(page)

    expect(over, `${width}px 宽下没找到出库登记弹窗里的明细表格`).not.toBeNull()
    expect(
      over,
      `${width}px 宽下出库登记弹窗明细表横向溢出 ${over}px（列宽总和超过弹窗宽度）`
    ).toBeLessThanOrEqual(0)

    // 数量列：input-number 默认 120px，窄列会被裁掉右侧 spin 按钮
    const clip = await quantityControlOverflow(page)
    expect(clip, `${width}px 宽下没找到数量输入框`).not.toBeNull()
    expect(clip.input, `${width}px 宽下数量输入框超出单元格 ${clip.input}px`).toBeLessThanOrEqual(0)
    expect(
      clip.control,
      `${width}px 宽下数量 spin 按钮超出单元格 ${clip.control}px`
    ).toBeLessThanOrEqual(0)
  }
})

// 编辑出库单弹窗（详情 → 编辑）：同样不得横向滚动。
test('@smoke 编辑出库弹窗明细表不横向滚动', async ({ page }) => {
  await loginChinese(page)
  await page.setViewportSize({ width: 1280, height: 900 })
  await page.goto('/admin/inventory/outbound')
  await page.waitForTimeout(1000)

  const rows = page.locator('.el-table__row')
  if ((await rows.count()) === 0) {
    test.skip(true, '当前环境没有出库单，跳过改单弹窗布局检查')
  }

  for (const width of [1440, 1366, 1280, 1024, 900, 800]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/admin/inventory/outbound')
    await page.waitForTimeout(1000)
    await page.locator('.el-table__row').first().click()
    await page.waitForTimeout(500)
    await page.getByRole('button', { name: '编辑', exact: true }).click()
    await page.waitForTimeout(500)

    const over = await dialogTableOverflow(page)
    expect(over, `${width}px 宽下没找到改单弹窗里的明细表格`).not.toBeNull()
    expect(
      over,
      `${width}px 宽下改单弹窗明细表横向溢出 ${over}px（列宽总和超过弹窗宽度）`
    ).toBeLessThanOrEqual(0)

    const clip = await quantityControlOverflow(page)
    expect(clip, `${width}px 宽下没找到改单弹窗的数量输入框`).not.toBeNull()
    expect(clip.input, `${width}px 宽下改单数量输入框超出单元格 ${clip.input}px`).toBeLessThanOrEqual(0)
    expect(
      clip.control,
      `${width}px 宽下改单数量 spin 按钮超出单元格 ${clip.control}px`
    ).toBeLessThanOrEqual(0)
  }
})
