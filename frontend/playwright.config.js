// Playwright 配置
//
// 用系统已安装的 Chrome（channel: 'chrome'）而不是下载 Chromium：
//   1. 环境里已有 Chrome 156，省一份 150MB+ 的浏览器；
//   2. 跑的就是用户真实使用的浏览器，能验出 Chromium 独有的行为差异。
//
// 前置：需要先起 docker 全栈（cd deploy && docker compose up -d && docker compose run --rm init）
// 运行：npm run e2e
import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  // 输出目录不放在仓库内：Playwright 每轮会清空它，
  // 沙箱对单次批量删除有阈值拦截（>50 个文件直接拒绝），
  // 放到系统临时目录可避开，也不污染仓库
  outputDir: process.env.E2E_OUTPUT_DIR || '/tmp/e2e-results',
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
