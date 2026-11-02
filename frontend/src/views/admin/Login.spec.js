// Login.vue：空闲超时被踢回来时的提示、登录成功后重置空闲计时
//
// 第二条是防回归的重点：登录页可能开着很久（活动记录是两小时前的），
// 若登录成功后不重置计时，紧接着的路由守卫会把刚登录的人判成超时再踢回去。
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createRouter, createMemoryHistory } from 'vue-router'
import Login from './Login.vue'

vi.mock('../../api/auth', () => ({ login: vi.fn() }))
vi.mock('../../utils/idle', () => ({ resetActivity: vi.fn() }))

import { login } from '../../api/auth'
import { resetActivity } from '../../utils/idle'

async function mountLogin(path = '/admin/login') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/admin/login', component: Login },
      { path: '/admin', component: { template: '<div>后台</div>' } }
    ]
  })
  await router.push(path)
  const wrapper = mount(Login, {
    global: { plugins: [ElementPlus, router] },
    attachTo: document.body
  })
  await flushPromises()
  return { wrapper, router }
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  login.mockResolvedValue({
    access_token: 'token-abc',
    user: { username: 'admin', real_name: '管理员' },
    permissions: ['ticket:read']
  })
})

describe('Login 空闲超时提示', () => {
  it('带 reason=idle 时说明"长时间未操作，已自动退出"', async () => {
    const { wrapper } = await mountLogin('/admin/login?reason=idle')
    expect(wrapper.text()).toContain('长时间未操作，已自动退出')
    wrapper.unmount()
  })

  it('正常进入登录页不出现这条提示', async () => {
    const { wrapper } = await mountLogin()
    expect(wrapper.text()).not.toContain('长时间未操作')
    wrapper.unmount()
  })
})

describe('Login 登录成功', () => {
  it('写入凭证后立刻重置空闲计时，避免刚登录就被判超时', async () => {
    const { wrapper, router } = await mountLogin()
    const state = wrapper.vm.$.setupState
    state.form.username = 'admin'
    state.form.password = 'pass1234'

    await state.onSubmit()
    await flushPromises()

    expect(localStorage.getItem('token')).toBe('token-abc')
    expect(resetActivity).toHaveBeenCalledTimes(1)
    expect(router.currentRoute.value.path).toBe('/admin')
    wrapper.unmount()
  })
})

describe('Login 语言入口', () => {
  it('渲染语言切换按钮（登录页独立于后台 Layout，需自带入口）', async () => {
    const { wrapper } = await mountLogin()
    const sw = wrapper.find('.lang-corner .lang-switch')
    expect(sw.exists()).toBe(true)
    // 默认中文界面下按钮显示目标语言 English，与后台顶栏同一规则
    expect(sw.text()).toBe('English')
    wrapper.unmount()
  })

  it('点击切到英文并持久化到 localStorage、同步 html lang', async () => {
    const { wrapper } = await mountLogin()
    const sw = wrapper.find('.lang-corner .lang-switch')
    await sw.trigger('click')
    await flushPromises()

    expect(localStorage.getItem('locale')).toBe('en-US')
    expect(document.documentElement.getAttribute('lang')).toBe('en-US')
    wrapper.unmount()
  })
})
