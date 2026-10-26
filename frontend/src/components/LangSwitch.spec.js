// LangSwitch.vue：后台顶栏的语言入口
//
// 核心契约（缺陷回归）：按钮显示的是**目标语言**，不是当前语言。
// 曾经的实现显示"简体中文"，中文界面下英文母语者看不到任何英文线索，
// 根本不认识这是切换入口。所以下面的断言必须"中文界面 → 看到 English"，
// 若有人改回显示当前语言，第一条就会红。
import { describe, expect, it, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import LangSwitch from './LangSwitch.vue'
import { i18n, setLocale } from '../locales'

async function mountSwitch() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/admin/tickets', component: LangSwitch, meta: { titleKey: 'admin.nav.tickets' } }]
  })
  await router.push('/admin/tickets')
  const wrapper = mount(LangSwitch, { global: { plugins: [router] }, attachTo: document.body })
  await flushPromises()
  return { wrapper, router }
}

beforeEach(() => {
  localStorage.clear()
  i18n.global.locale.value = 'zh-CN'
})

describe('LangSwitch', () => {
  it('中文界面显示英文名 English（而不是当前语言的"简体中文"）', async () => {
    const { wrapper } = await mountSwitch()
    expect(wrapper.text()).toBe('English')
    // 悬停与读屏给出完整语义：光看"English"不知道点了是切过去还是当前就是英文
    expect(wrapper.attributes('title')).toBe('切换到 English')
    expect(wrapper.attributes('aria-label')).toBe('切换到 English')
    wrapper.unmount()
  })

  it('英文界面显示简体中文，说明文案跟随界面语言', async () => {
    setLocale('en-US', { persist: false })
    const { wrapper } = await mountSwitch()
    expect(wrapper.text()).toBe('简体中文')
    expect(wrapper.attributes('aria-label')).toBe('Switch to 简体中文')
    wrapper.unmount()
  })

  it('点击切到另一种语言，并持久化到 localStorage、同步 html lang 与标签页标题', async () => {
    const { wrapper } = await mountSwitch()
    await wrapper.trigger('click')
    await flushPromises()

    expect(i18n.global.locale.value).toBe('en-US')
    expect(localStorage.getItem('locale')).toBe('en-US')
    expect(document.documentElement.getAttribute('lang')).toBe('en-US')
    // 切语言不换路由，afterEach 不触发，标题必须在这里补上
    expect(document.title).toContain('Tickets')

    // 切换后按钮自动变成"另一种语言"，形成来回可逆的入口
    expect(wrapper.text()).toBe('简体中文')
    wrapper.unmount()
  })

  it('再点一次切回中文，localStorage 同步回 zh-CN', async () => {
    setLocale('en-US', { persist: false })
    const { wrapper } = await mountSwitch()
    await wrapper.trigger('click')
    await flushPromises()

    expect(i18n.global.locale.value).toBe('zh-CN')
    expect(localStorage.getItem('locale')).toBe('zh-CN')
    wrapper.unmount()
  })

  it('带有地球图标，语言名完全不认识的第三国用户也看得出这是语言入口', async () => {
    const { wrapper } = await mountSwitch()
    // 图标是装饰性的（aria-hidden），语义由按钮的 aria-label 承担
    expect(wrapper.find('svg.globe').exists()).toBe(true)
    expect(wrapper.find('svg.globe').attributes('aria-hidden')).toBe('true')
    wrapper.unmount()
  })
})
