// 组件测试的浏览器环境补齐（happy-dom 未实现的部分）
import { beforeEach } from 'vitest'
import { config } from '@vue/test-utils'
import { i18n } from './locales'

/*
 * i18n 全局安装。
 *
 * 所有页面组件都用 useI18n()，测试挂载时若没有安装 i18n 插件会直接抛
 * "Need to install with `app.use` function"。放在这里一次解决，
 * 不用去每个 spec 的 global.plugins 里补。
 */
config.global.plugins = [i18n]

/*
 * 测试语言固定为中文。
 *
 * 现有 150 条用例大量断言中文文案（toContain('已关闭，不可再流转')），
 * 把它们改写成断 key 收益很低（key 是否正确由 locale.spec.js 的键完整性检查负责），
 * 风险却高（容易把"文案错了"变成"key 存在"的无效断言）。
 *
 * 每个用例前重置：路由守卫会调 setLocale，某个用例切到英文会污染后面所有用例。
 */
beforeEach(() => {
  i18n.global.locale.value = 'zh-CN'
})

class ObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() {
    return []
  }
}

globalThis.ResizeObserver = globalThis.ResizeObserver || ObserverStub
globalThis.IntersectionObserver = globalThis.IntersectionObserver || ObserverStub

if (!window.matchMedia) {
  window.matchMedia = () => ({
    matches: false,
    media: '',
    onchange: null,
    addListener() {},
    removeListener() {},
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent() {
      return false
    }
  })
}
