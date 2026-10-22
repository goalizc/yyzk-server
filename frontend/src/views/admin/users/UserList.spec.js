import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessageBox } from 'element-plus'
import UserList from './UserList.vue'
import { setPermissions } from '../../../utils/permissions'

vi.mock('../../../api/admin', () => ({
  adminListUsers: vi.fn(),
  adminListProductLines: vi.fn(),
  adminCreateUser: vi.fn(),
  adminUpdateUser: vi.fn(),
  adminResetPassword: vi.fn(),
  adminListGrants: vi.fn(),
  adminCreateGrant: vi.fn(),
  adminRevokeGrant: vi.fn(),
  adminReplaceUserLines: vi.fn()
}))

vi.mock('../../../utils/clipboard', () => ({
  copyText: vi.fn().mockResolvedValue(true)
}))

import {
  adminListGrants, adminListProductLines, adminListUsers, adminResetPassword, adminUpdateUser
} from '../../../api/admin'
import { copyText } from '../../../utils/clipboard'

function makeUser(overrides = {}) {
  return {
    id: 1, username: 'wangwei', real_name: '王伟', role: 'agent', is_active: true,
    last_login_at: null, created_at: '2026-10-01T09:00:00+08:00',
    active_grant_count: 0,
    product_lines: [{ id: 1, name: '扫地机', expires_at: null }],
    ...overrides
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  setPermissions(['user:read', 'user:write', 'product_line:read'])
  adminListUsers.mockResolvedValue({ total: 1, page: 1, page_size: 20, items: [makeUser()] })
  adminListProductLines.mockResolvedValue({ items: [] })
  adminListGrants.mockResolvedValue([])
  adminUpdateUser.mockResolvedValue({})
  copyText.mockResolvedValue(true)
})

describe('UserList', () => {
  it('加载并渲染用户、角色与产品线', async () => {
    const wrapper = mount(UserList, { global: { plugins: [ElementPlus] }, attachTo: document.body })
    await flushPromises()

    expect(adminListUsers).toHaveBeenCalled()
    expect(wrapper.text()).toContain('wangwei')
    expect(wrapper.text()).toContain('一线客服')
    expect(wrapper.text()).toContain('扫地机')
  })

  it('生效临时授权数量显示在角色下方，点标签打开授权抽屉', async () => {
    adminListUsers.mockResolvedValue({
      total: 1, page: 1, page_size: 20,
      items: [makeUser({ active_grant_count: 2 })]
    })
    const wrapper = mount(UserList, { global: { plugins: [ElementPlus] }, attachTo: document.body })
    await flushPromises()

    expect(wrapper.text()).toContain('临时授权 2')
    const tag = wrapper.findAll('.el-tag').find((el) => el.text().includes('临时授权 2'))
    await tag.trigger('click')
    await flushPromises()

    expect(wrapper.vm.$.setupState.grantsVisible).toBe(true)
    expect(adminListGrants).toHaveBeenCalledWith(1)
  })

  it('授权记录显示权限中文名与授予人', async () => {
    adminListGrants.mockResolvedValue([
      {
        id: 9, permission: 'ticket:write', reason: '代班',
        expires_at: '2026-11-01T23:59:59+08:00', is_active: true,
        granted_by_name: '李工'
      }
    ])
    const wrapper = mount(UserList, { global: { plugins: [ElementPlus] }, attachTo: document.body })
    await flushPromises()

    const state = wrapper.vm.$.setupState
    state.openGrants(state.rows[0])
    await state.loadGrants()
    await flushPromises()

    expect(document.body.textContent).toContain('处理工单')
    expect(document.body.textContent).toContain('李工')
  })

  it('新建用户表单包含确认密码字段', async () => {
    const wrapper = mount(UserList, { global: { plugins: [ElementPlus] }, attachTo: document.body })
    await flushPromises()

    const addBtn = wrapper.findAll('button').find((b) => b.text().includes('新建用户'))
    await addBtn.trigger('click')
    await flushPromises()

    expect(document.body.textContent).toContain('确认密码')
    expect(wrapper.vm.$.setupState.form.confirm_password).toBe('')
  })

  it('停用账号前二次确认，取消则不发请求', async () => {
    const confirm = vi.spyOn(ElMessageBox, 'confirm').mockRejectedValue(new Error('cancel'))
    const wrapper = mount(UserList, { global: { plugins: [ElementPlus] }, attachTo: document.body })
    await flushPromises()

    const state = wrapper.vm.$.setupState
    await state.onToggleActive(state.rows[0], false)

    expect(confirm).toHaveBeenCalledWith(
      expect.stringContaining('停用后该账号将立即无法登录'),
      '停用确认',
      expect.anything()
    )
    expect(adminUpdateUser).not.toHaveBeenCalled()
    expect(state.rows[0].is_active).toBe(true)
    confirm.mockRestore()
  })

  it('重置密码后点击复制调用 copyText 并传入新密码', async () => {
    const password = 'Xy9#password'
    adminResetPassword.mockResolvedValue({ password })
    const confirm = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
    const wrapper = mount(UserList, { global: { plugins: [ElementPlus] }, attachTo: document.body })
    await flushPromises()

    const state = wrapper.vm.$.setupState
    await state.onResetPassword(state.rows[0])
    await flushPromises()

    expect(state.passwordVisible).toBe(true)
    const copyBtn = [...document.querySelectorAll('.password-row button')]
      .find((node) => node.textContent.includes('复制'))
    expect(copyBtn).toBeTruthy()
    copyBtn.click()
    await flushPromises()

    expect(copyText).toHaveBeenCalledTimes(1)
    expect(copyText).toHaveBeenCalledWith(password)
    confirm.mockRestore()
  })

  it('编辑用户时可修改账号并随保存提交', async () => {
    const wrapper = mount(UserList, { global: { plugins: [ElementPlus] }, attachTo: document.body })
    await flushPromises()

    const state = wrapper.vm.$.setupState
    state.openEdit(state.rows[0])
    await flushPromises()
    state.form.username = '  wangwei2  '

    await state.onSubmit()
    await flushPromises()

    expect(adminUpdateUser).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ username: 'wangwei2' })
    )
  })

  it('角色变更保存前二次确认，取消则不提交', async () => {
    const wrapper = mount(UserList, { global: { plugins: [ElementPlus] }, attachTo: document.body })
    await flushPromises()

    const state = wrapper.vm.$.setupState
    state.openEdit(state.rows[0])
    await flushPromises()
    state.form.role = 'auditor'

    const confirm = vi.spyOn(ElMessageBox, 'confirm').mockRejectedValue(new Error('cancel'))
    await state.onSubmit()
    await flushPromises()

    expect(confirm).toHaveBeenCalledWith(
      expect.stringContaining('其权限会立即变化'),
      '角色变更确认',
      expect.anything()
    )
    expect(adminUpdateUser).not.toHaveBeenCalled()
    confirm.mockRestore()
  })
})
