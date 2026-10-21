// Playwright 配置
//
// 用系统已安装的 Chrome（channel: 'chrome'）而不是下载 Chromium：
//   1. 环境里已有 Chrome 156，省一份 150MB+ 的浏览器；
//   2. 跑的就是用户真实使用的浏览器，能验出 Chromium 独有的行为差异。
//
// 前置：需要先起 docker 全栈（cd deploy && docker compose up -d && docker compose run --rm init）
// 运行：
//   npm run e2e        桌面主链路冒烟
//   npm run e2e:walk   逐屏人工走查
//   npm run e2e:mobile 移动端适配验收（TC-61）
import { defineConfig, devices } from '@playwright/test'

// 三套用例的标签互斥，靠 E2E_MODE 切换要跑哪一套：
//   walkthrough → 只跑 @walkthrough
//   mobile      → 只跑 @mobile
//   其它/空      → 只跑主链路冒烟（排除上面两类）
const MODE = process.env.E2E_MODE || ''
const TAG_BY_MODE = { walkthrough: /@walkthrough/, mobile: /@mobile/ }
const grep = TAG_BY_MODE[MODE] || /@smoke/
const grepInvert = MODE ? undefined : /@walkthrough|@mobile/

export default defineConfig({
  testDir: './e2e',
  grep,
  grepInvert,
  // 输出目录放仓库内（已 gitignore）：
  // /tmp 是 10MB 的 tmpfs，截图一多就写不进；
  // preserveOutput 关掉"每轮清空"，因为沙箱对单次批量删除有阈值拦截（>50 文件）
  outputDir: process.env.E2E_OUTPUT_DIR || './.e2e-output',
  preserveOutput: 'always',
  // 主链路冒烟是串行的：3 条用例改动同一份数据，并行会互相干扰
  workers: 1,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: [['list']],
  timeout: 45_000,
  expect: { timeout: 10_000 },

  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost',
    // 不用 trace：沙箱里 Playwright 复制 trace 归档会 EPERM，且 trace 在
    // 「断言超时」类失败上帮助有限（截图 + 失败时的 DOM 更直接）
    trace: 'off',
    screenshot: 'only-on-failure',
    video: 'off',
    actionTimeout: 10_000,
    navigationTimeout: 20_000
  },

  projects: [
    {
      name: 'chrome',
      use: {
        ...devices['Desktop Chrome'],
        channel: 'chrome'
      }
    }
  ]
})
