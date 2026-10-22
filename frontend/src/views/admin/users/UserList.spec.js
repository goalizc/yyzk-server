import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
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

import { adminListProductLines, adminListUsers } from '../../../api/admin'

beforeEach(() => {
  vi.clearAllMocks()
  setPermissions(['user:read', 'user:write', 'product_line:read'])
  adminListUsers.mockResolvedValue({ total: 1, page: 1, page_size: 20, items: [
    {
      id: 1, username: 'wangwei', real_name: '王伟', role: 'agent', is_active: true,
      last_login_at: null, created_at: '2026-10-01T09:00:00+08:00',
      product_lines: [{ id: 1, name: '扫地机', expires_at: null }]
    }
  ] })
  adminListProductLines.mockResolvedValue({ items: [] })
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
})
