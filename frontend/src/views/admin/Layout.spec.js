// Layout.vue：侧边栏高亮归并、改密规则（新旧相同 / 两次不一致 / 服务端字段错误不吞）
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createRouter, createMemoryHistory } from 'vue-router'
import Layout from './Layout.vue'

vi.mock('../../api/auth', () => ({
  changePassword: vi.fn(),
  fetchMe: vi.fn().mockResolvedValue({ permissions: ['ticket:read'] })
}))

import { changePassword, fetchMe } from '../../api/auth'
import { setPermissions } from '../../utils/permissions'

async function mountLayout(path = '/admin/tickets') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/admin',
        component: Layout,
        children: [
          { path: 'tickets', name: 'admin-tickets', component: { template: '<div>工单页</div>' }, meta: { title: '工单管理' } },
          { path: 'faults', name: 'admin-faults', component: { template: '<div>故障页</div>' }, meta: { title: '故障知识库' } },
          { path: 'faults/edit/:id?', name: 'admin-fault-edit', component: { template: '<div>编辑页</div>' }, meta: { titleKey: 'admin.page.faultEdit' } }
        ]
      },
      { path: '/admin/login', name: 'admin-login', component: { template: '<div>登录</div>' } }
    ]
  })
  await router.push(path)
  const wrapper = mount(Layout, {
    global: { plugins: [ElementPlus, router] },
    attachTo: document.body
  })
  await flushPromises()
  return { wrapper, router }
}

// el-dialog 是懒渲染的：不先打开弹窗，formRef 为 null，validate() 拿不到实例
async function fillForm(state, { oldPassword, newPassword, confirmPassword }) {
  state.passwordVisible = true
  await flushPromises()
  state.form.oldPassword = oldPassword
  state.form.newPassword = newPassword
  state.form.confirmPassword = confirmPassword
  await flushPromises()
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  localStorage.setItem('user', JSON.stringify({ username: 'admin', real_name: '超级管理员', role: 'super_admin' }))
  setPermissions(['ticket:read'])
  changePassword.mockResolvedValue({})
})

describe('Layout', () => {
  it('侧栏菜单按「作业 → 分析 → 配置 → 管理」排序，基础数据三项连续', async () => {
    // 全权限账号：顺序断言必须看到全部项，缺一项就说明被权限过滤干扰了
    const ALL = [
      'ticket:read', 'fault:read', 'stats:read', 'product_line:read',
      'product:read', 'part:read', 'user:read', 'audit:read'
    ]
    setPermissions(ALL)
    fetchMe.mockResolvedValue({ permissions: ALL })

    const { wrapper } = await mountLayout()
    const labels = wrapper.vm.$.setupState.navItems.map((item) => item.label)

    // 顺序被锁死是故意的：新增菜单要落到正确的分区，而不是往数组尾部追加
    expect(labels).toEqual([
      '工单管理',
      '故障知识库',
      '数据看板',
      '产品线',
      '产品管理',
      '零件管理',
      '用户管理',
      '操作日志'
    ])
    // 产品线 → 产品 → 零件 是数据层级（从粗到细），中间不许插别的项
    const start = labels.indexOf('产品线')
    expect(labels.slice(start, start + 3)).toEqual(['产品线', '产品管理', '零件管理'])
  })

  it('编辑故障页仍高亮侧边栏"故障知识库"', async () => {
    const { wrapper } = await mountLayout('/admin/faults/edit/21')
    expect(wrapper.vm.$.setupState.activeMenu).toBe('/admin/faults')
    // 顶栏标题取当前路由 meta.title
    expect(wrapper.text()).toContain('故障编辑')
  })

  it('进入后台立即刷新权限，不必等路由切换', async () => {
    // 独立路由：Layout 不作为匹配到的路由组件，避免测试里出现自嵌套的两份实例
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/admin/tickets', component: { template: '<div>工单页</div>' }, meta: { title: '工单管理' } }
      ]
    })
    await router.push('/admin/tickets')
    const wrapper = mount(Layout, {
      global: { plugins: [ElementPlus, router] },
      attachTo: document.body
    })
    await flushPromises()

    expect(fetchMe).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('顶栏展示用户名与角色中文名', async () => {
    const { wrapper } = await mountLayout()
    expect(wrapper.text()).toContain('超级管理员')
    expect(wrapper.text()).toContain('管理员')
  })

  it('新旧密码相同时前端拦下，不发请求', async () => {
    const { wrapper } = await mountLayout()
    const state = wrapper.vm.$.setupState
    await fillForm(state, { oldPassword: 'Passw0rd!', newPassword: 'Passw0rd!', confirmPassword: 'Passw0rd!' })

    await state.onSubmit()
    await flushPromises()

    expect(changePassword).not.toHaveBeenCalled()
    // happy-dom 下 el-form-item 的报错节点不渲染，断言状态
    expect(state.passwordVisible).toBe(true)
  })

  it('两次输入不一致时不发请求', async () => {
    const { wrapper } = await mountLayout()
    const state = wrapper.vm.$.setupState
    await fillForm(state, { oldPassword: 'OldPass123', newPassword: 'NewPass123', confirmPassword: 'NewPass124' })

    await state.onSubmit()
    await flushPromises()

    expect(changePassword).not.toHaveBeenCalled()
    expect(state.passwordVisible).toBe(true)
  })

  it('新密码不足 8 位不发请求', async () => {
    const { wrapper } = await mountLayout()
    const state = wrapper.vm.$.setupState
    await fillForm(state, { oldPassword: 'OldPass123', newPassword: 'short', confirmPassword: 'short' })

    await state.onSubmit()
    await flushPromises()

    expect(changePassword).not.toHaveBeenCalled()
  })

  it('校验通过后按契约字段名提交，成功后关闭弹窗', async () => {
    const { wrapper } = await mountLayout()
    const state = wrapper.vm.$.setupState
    await fillForm(state, { oldPassword: 'OldPass123', newPassword: 'NewPass456', confirmPassword: 'NewPass456' })

    await state.onSubmit()
    await flushPromises()

    expect(changePassword).toHaveBeenCalledWith({
      old_password: 'OldPass123',
      new_password: 'NewPass456'
    })
    expect(state.passwordVisible).toBe(false)
  })

  it('PASSWORD_INVALID 落在原密码字段，弹窗不关', async () => {
    changePassword.mockRejectedValue({
      response: { data: { detail: '原密码不正确', code: 'PASSWORD_INVALID' } }
    })
    const { wrapper } = await mountLayout()
    const state = wrapper.vm.$.setupState
    await fillForm(state, { oldPassword: 'WrongPass1', newPassword: 'NewPass456', confirmPassword: 'NewPass456' })

    await state.onSubmit()
    await flushPromises()

    expect(state.oldPasswordError).toBe('原密码不正确')
    expect(state.passwordVisible).toBe(true)
  })

  it('PASSWORD_SAME 的文案要留在新密码字段上，不被二次校验清掉', async () => {
    changePassword.mockRejectedValue({
      response: { data: { detail: '新密码不能与原密码相同', code: 'PASSWORD_SAME' } }
    })
    const { wrapper } = await mountLayout()
    const state = wrapper.vm.$.setupState
    await fillForm(state, { oldPassword: 'OldPass123', newPassword: 'NewPass456', confirmPassword: 'NewPass456' })

    await state.onSubmit()
    await flushPromises()

    // 服务端回来后会再跑一次 validateField('newPassword')；
    // 校验器若"通过就清空"，服务端文案会立刻消失（这是修过的回归）
    expect(state.newPasswordError).toBe('新密码不能与原密码相同')
    const formItems = wrapper.findAll('.el-dialog .el-form-item')
    const newItem = formItems.find((el) => el.text().includes('新密码') && !el.text().includes('确认'))
    expect(newItem.classes()).toContain('is-error')
    expect(state.passwordVisible).toBe(true)
  })

  it('其他错误走全局提示，弹窗保持打开', async () => {
    changePassword.mockRejectedValue({
      response: { data: { detail: '服务暂时不可用', code: 'SERVICE_UNAVAILABLE' } }
    })
    const { wrapper } = await mountLayout()
    const state = wrapper.vm.$.setupState
    await fillForm(state, { oldPassword: 'OldPass123', newPassword: 'NewPass456', confirmPassword: 'NewPass456' })

    await state.onSubmit()
    await flushPromises()

    expect(state.oldPasswordError).toBe('')
    expect(state.newPasswordError).toBe('')
    expect(document.body.textContent).toContain('服务暂时不可用')
    expect(state.passwordVisible).toBe(true)
  })

  it('退出登录清掉本地凭证并跳登录页', async () => {
    const { wrapper, router } = await mountLayout()
    wrapper.vm.$.setupState.onLogout()
    await flushPromises()

    expect(localStorage.getItem('token')).toBe(null)
    expect(localStorage.getItem('user')).toBe(null)
    expect(router.currentRoute.value.path).toBe('/admin/login')
  })
})
