// ESLint flat config（ESLint 10）
// 只做静态检查，不参与构建。`npm run lint` 调用。
import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'
import globals from 'globals'
import { readFileSync } from 'node:fs'

// unplugin-auto-import 注入的全局符号（ElMessage 等）不是 import 进来的，
// ESLint 会误报 no-undef。这里从自动生成的 d.ts 里读 const 声明，
// 这样 lint 认的全局与构建期真实注入的始终一致，不用手写白名单维护。
function autoImportGlobals() {
  let dts
  try {
    dts = readFileSync(new URL('./auto-imports.d.ts', import.meta.url), 'utf-8')
  } catch {
    // 首次 clone 还没跑过 dev/build 时没有该文件，退回手写的最小集合
    return { ElMessage: 'readonly', ElMessageBox: 'readonly', ElNotification: 'readonly' }
  }
  const out = {}
  for (const m of dts.matchAll(/^\s*const\s+([A-Za-z_$][\w$]*)\s*:/gm)) out[m[1]] = 'readonly'
  return out
}

export default [
  {
    // 构建产物、依赖、vite/playwright 的缓存目录都不检查
    ignores: [
      'dist/**',
      'dist-verify/**',
      'node_modules/**',
      'test-results/**',
      'playwright-report/**',
      // TMPDIR 指向仓库内时 Playwright 的转换缓存会落在这里
      '.tmp/**',
      '**/vite.config.js.timestamp-*.mjs'
    ]
  },

  js.configs.recommended,
  ...pluginVue.configs['flat/recommended'],

  {
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: 'module',
      globals: {
        ...globals.browser,
        ...globals.es2021,
        ...autoImportGlobals()
      }
    },
    rules: {
      // ---- 项目约定（见 MEMORY.md 编码约定）----
      // 禁止 v-html：全仓红线，用自定义规则守住
      'vue/no-v-html': 'error',

      // ---- 收紧到"能发现真问题"的水位，不做风格整齐 ----
      // 未使用变量只警告：存在故意的占位与解构忽略，报错会淹没真问题
      'no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
      'no-empty': ['error', { allowEmptyCatch: true }],
      'no-console': ['warn', { allow: ['warn', 'error'] }],
      'no-debugger': 'error',
      eqeqeq: ['warn', 'smart'],

      // 组件命名与项目现状一致（PascalCase 多词）
      'vue/multi-word-component-names': 'off',
      // 属性换行顺序属风格，项目现状不统一，不强求
      'vue/attributes-order': 'off',
      'vue/max-attributes-per-line': 'off',
      'vue/singleline-html-element-content-newline': 'off',
      'vue/html-self-closing': 'off',
      'vue/html-indent': 'off',
      'vue/html-closing-bracket-newline': 'off'
    }
  },

  {
    // 测试文件：vitest 全局
    files: ['**/*.spec.js', '**/*.test.js', '**/tests/**/*.js'],
    languageOptions: {
      globals: {
        ...globals.node,
        describe: 'readonly',
        it: 'readonly',
        expect: 'readonly',
        vi: 'readonly',
        beforeEach: 'readonly',
        afterEach: 'readonly',
        beforeAll: 'readonly',
        afterAll: 'readonly'
      }
    }
  },

  {
    // 配置文件在 node 环境跑
    files: ['*.config.js', '**/playwright.config.js', 'scripts/**/*.js'],
    languageOptions: { globals: { ...globals.node } }
  },

  {
    // 逐屏走查脚本的产物就是控制台读数（分辨率、行数、错误字段数……），
    // console.log 是它的输出通道，不是遗留调试代码，此处豁免。
    // 其余测试文件仍受 no-console 约束。
    files: ['e2e/screen-walkthrough.spec.js'],
    rules: { 'no-console': 'off' }
  }
]
