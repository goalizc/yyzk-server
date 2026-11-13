import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
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
  adminListGrantablePermissions: vi.fn(),
  adminCreateGrant: vi.fn(),
  adminRevokeGrant: vi.fn(),
  adminReplaceUserLines: vi.fn()
}))

vi.mock('../../../utils/clipboard', () => ({
  copyText: vi.fn().mockResolvedValue(true)
}))

import {
  adminCreateUser, adminListGrants, adminListGrantablePermissions, adminListProductLines, adminListUsers,
  adminReplaceUserLines, adminResetPassword, adminUpdateUser
} from '../../../api/admin'
import { copyText } from '../../../utils/clipboard'
import { ROLE_VALUES } from '../../../utils/roles'

function makeUser(overrides = {}) {
  const role = overrides.role || 'agent'
  return {
    id: 1, username: 'wangwei', real_name: '王伟', role, roles: [role], is_active: true,
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
  // 授权下拉的唯一来源是后端；测试里给一份最小清单
  adminListGrantablePermissions.mockResolvedValue(['ticket:read', 'inventory:sku:read'])
  adminUpdateUser.mockResolvedValue({})
  adminCreateUser.mockResolvedValue({})
  copyText.mockResolvedValue(true)
})

// el-dialog / ElMessageBox 都 teleport 到 body。挂载后不卸载会逐条堆积，
// DOM 越来越重、渲染越来越慢，最终稳定触发 5s 超时（既有基线失败的根因）。
// 统一从这里挂载，afterEach 里集中卸载并清空 body。
const mountedWrappers = []

function mountUserList() {
  const wrapper = mount(UserList, {
    global: { plugins: [ElementPlus] },
    attachTo: document.body
  })
  mountedWrappers.push(wrapper)
  return wrapper
}

afterEach(() => {
  for (const wrapper of mountedWrappers.splice(0)) {
    try {
      wrapper.unmount()
    } catch {
      // 测试内已卸载过：忽略
    }
  }
  document.body.innerHTML = ''
  // 超时失败的用例可能来不及跑 confirm.mockRestore()，这里兜底防 spy 泄漏
  vi.restoreAllMocks()
})

describe('UserList', () => {
  it('加载并渲染用户、角色与产品线', async () => {
    const wrapper = mountUserList()
    await flushPromises()

    expect(adminListUsers).toHaveBeenCalled()
    expect(wrapper.text()).toContain('wangwei')
    expect(wrapper.text()).toContain('一线客服')
    expect(wrapper.text()).toContain('扫地机')
  })

  it('多角色在列表展示全部中文名，编辑回填并随保存提交 roles 数组', async () => {
    adminListUsers.mockResolvedValue({
      total: 1,
      page: 1,
      page_size: 20,
      items: [makeUser({ roles: ['supervisor', 'warehouse_clerk'] })]
    })
    const wrapper = mountUserList()
    await flushPromises()

    expect(wrapper.text()).toContain('售后主管')
    expect(wrapper.text()).toContain('仓管录入员')

    const state = wrapper.vm.$.setupState
    state.openEdit(state.rows[0])
    await flushPromises()
    expect(state.form.roles).toEqual(['supervisor', 'warehouse_clerk'])
    // 含售后线角色 → 产品线分配保留
    expect(state.showProductLines).toBe(true)

    await state.onSubmit()
    await flushPromises()

    expect(adminUpdateUser).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ roles: ['supervisor', 'warehouse_clerk'] })
    )
  })

  it('新建仓管账号不会默认叠加一线客服角色', async () => {
    const wrapper = mountUserList()
    await flushPromises()
    const btn = wrapper.findAll('button').find((b) => b.text().includes('新建用户'))
    await btn.trigger('click')
    await flushPromises()

    const state = wrapper.vm.$.setupState
    expect(state.form.roles).toEqual([])

    Object.assign(state.form, {
      username: 'clerk1',
      real_name: '仓管一',
      password: 'Init@12345',
      confirm_password: 'Init@12345',
      roles: ['warehouse_clerk']
    })
    await state.onSubmit()
    await flushPromises()

    expect(adminCreateUser).toHaveBeenCalledTimes(1)
    const payload = adminCreateUser.mock.calls[0][0]
    expect(payload.roles).toEqual(['warehouse_clerk'])
    expect(payload.roles).not.toContain('agent')
  })

  it('生效临时授权数量显示在角色下方，点标签打开授权面板', async () => {
    adminListUsers.mockResolvedValue({
      total: 1, page: 1, page_size: 20,
      items: [makeUser({ active_grant_count: 2 })]
    })
    const wrapper = mountUserList()
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
    const wrapper = mountUserList()
    await flushPromises()

    const state = wrapper.vm.$.setupState
    state.openGrants(state.rows[0])
    await state.loadGrants()
    await flushPromises()

    expect(document.body.textContent).toContain('处理工单')
    expect(document.body.textContent).toContain('李工')
  })

  it('新建用户表单包含确认密码字段', async () => {
    const wrapper = mountUserList()
    await flushPromises()

    const addBtn = wrapper.findAll('button').find((b) => b.text().includes('新建用户'))
    await addBtn.trigger('click')
    await flushPromises()

    expect(document.body.textContent).toContain('确认密码')
    expect(wrapper.vm.$.setupState.form.confirm_password).toBe('')
  })

  it('停用账号前二次确认，取消则不发请求', async () => {
    const confirm = vi.spyOn(ElMessageBox, 'confirm').mockRejectedValue(new Error('cancel'))
    const wrapper = mountUserList()
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
    const wrapper = mountUserList()
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
    const wrapper = mountUserList()
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
    const wrapper = mountUserList()
    await flushPromises()

    const state = wrapper.vm.$.setupState
    state.openEdit(state.rows[0])
    await flushPromises()
    state.form.roles = ['auditor']

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

  // 7 个角色平铺时「售后主管 / 仓管主管 / 产品计划」极易选错，按职责分区后一眼可辨。
  // 断言到 value 而不只是组名：分组成员写错会让角色从下拉里"消失"。
  it('角色下拉按系统 / 主数据 / 售后 / 仓管分区，且分组不漏角色', async () => {
    const wrapper = mountUserList()
    await flushPromises()

    const btn = wrapper.findAll('button').find((b) => b.text().includes('新建用户'))
    await btn.trigger('click')
    await flushPromises()

    // 顶部筛选 + 弹窗各一套分组，组件树里先出现的是筛选
    const groups = wrapper.findAllComponents({ name: 'ElOptionGroup' }).map((g) => ({
      label: g.props('label'),
      values: g.findAllComponents({ name: 'ElOption' }).map((o) => o.props('value'))
    }))
    const dialogGroups = groups.slice(0, 4)
    expect(dialogGroups.map((g) => g.label)).toEqual([
      '系统管理',
      '主数据',
      '售后角色',
      '仓管角色'
    ])
    expect(dialogGroups[1].values).toEqual(['product_planner'])
    expect(dialogGroups[2].values).toEqual(['supervisor', 'agent', 'auditor'])
    expect(dialogGroups[3].values).toEqual(['warehouse_clerk', 'warehouse_manager'])
    // 并集必须等于全部角色：漏登记会让该角色彻底选不到
    expect(dialogGroups.flatMap((g) => g.values).sort()).toEqual([...ROLE_VALUES].sort())
  })

  // 产品线只作用于工单数据范围，属售后线概念；仓管、超管、产品计划不该看到这个字段
  it('仓管 / 超管 / 产品计划隐藏产品线分配，售后角色保留', async () => {
    const wrapper = mountUserList()
    await flushPromises()
    const btn = wrapper.findAll('button').find((b) => b.text().includes('新建用户'))
    await btn.trigger('click')
    await flushPromises()

    const state = wrapper.vm.$.setupState
    const formLabels = () =>
      wrapper.findAllComponents({ name: 'ElFormItem' }).map((c) => c.props('label'))
    // 新建默认不预选角色：产品线分配也先隐藏，避免多选叠加出意外的 agent
    expect(state.form.roles).toEqual([])
    expect(formLabels()).not.toContain('产品线')

    state.form.roles = ['agent']
    await flushPromises()
    expect(formLabels()).toContain('产品线')

    for (const role of [
      'warehouse_clerk',
      'warehouse_manager',
      'super_admin',
      'product_planner'
    ]) {
      state.form.roles = [role]
      await flushPromises()
      expect(formLabels(), `${role} 不该显示产品线`).not.toContain('产品线')
    }
    state.form.roles = ['supervisor']
    await flushPromises()
    expect(formLabels()).toContain('产品线')
  })

  // 隐藏字段不能顺手把库里的历史分配清空：仓管被改回售后线时应能复用
  it('编辑仓管用户时不调用产品线替换接口', async () => {
    adminListUsers.mockResolvedValue({
      total: 1,
      page: 1,
      page_size: 20,
      items: [makeUser({ role: 'warehouse_manager', product_lines: [{ id: 1, name: '扫地机', expires_at: null }] })]
    })
    const wrapper = mountUserList()
    await flushPromises()

    const state = wrapper.vm.$.setupState
    state.openEdit(state.rows[0])
    await flushPromises()
    await state.onSubmit()
    await flushPromises()

    expect(adminUpdateUser).toHaveBeenCalled()
    expect(adminReplaceUserLines).not.toHaveBeenCalled()
  })
})

// 一致性：其它列表都是"点行即编辑"，用户管理此前没有。
// 但用户行里有开关、授权标签、三个按钮 —— 这些都不能被行点击抢走，
// 否则"点删除/点授权"会顺带弹出编辑窗。
describe('UserList 行点击', () => {
  function mountList() {
    return mountUserList()
  }

  it('点击行打开编辑弹窗并带上该行 id', async () => {
    const wrapper = mountList()
    await flushPromises()

    await wrapper.findAll('.el-table__row')[0].trigger('click')
    await flushPromises()

    const state = wrapper.vm.$.setupState
    expect(state.dialogVisible).toBe(true)
    expect(state.editingId).toBe(1)
  })

  it('点状态开关不打开编辑弹窗', async () => {
    const wrapper = mountList()
    await flushPromises()

    // 只断言"没被行点击抢走"：停用本身要过二次确认，请求不在这一步发出。
    // 若开关上的 @click.stop 被删掉，这次点击会冒泡到 tr 打开编辑弹窗，用例即红
    await wrapper.findAll('.el-table__row')[0].find('.el-switch').trigger('click')
    await flushPromises()

    expect(wrapper.vm.$.setupState.dialogVisible).toBe(false)
  })

  it('点「临时授权 N」标签只开授权面板，不打开编辑弹窗', async () => {
    adminListUsers.mockResolvedValue({
      total: 1, page: 1, page_size: 20,
      items: [makeUser({ active_grant_count: 2 })]
    })
    const wrapper = mountList()
    await flushPromises()

    const tag = wrapper.findAll('.el-tag').find((el) => el.text().includes('临时授权 2'))
    await tag.trigger('click')
    await flushPromises()

    const state = wrapper.vm.$.setupState
    expect(state.grantsVisible).toBe(true)
    expect(state.dialogVisible).toBe(false)
    // 可授予清单必须来自后端（S3：不再前端硬编码，避免与 grantable_permissions 漂移）
    expect(adminListGrantablePermissions).toHaveBeenCalled()
    expect(state.grantableOptions).toEqual(['ticket:read', 'inventory:sku:read'])
  })

  it('新建用户弹窗的角色下拉有 7 个选项（曾因模板引用已删除的常量而变成空列表）', async () => {
    const wrapper = mountList()
    await flushPromises()

    const btn = wrapper.findAll('button').find((b) => b.text().includes('新建用户'))
    await btn.trigger('click')
    await flushPromises()

    // 七角色：super_admin / supervisor / product_planner / agent / auditor / warehouse_clerk / warehouse_manager
    // 「仓管」限定词不可省：supervisor 是售后主管，裸写「主管」两者分不清
    const roles = ['超级管理员', '产品计划', '售后主管', '一线客服', '只读审计', '仓管录入员', '仓管主管']
    const labels = wrapper
      .findAllComponents({ name: 'ElOption' })
      .map((c) => c.props('label'))
      .filter((l) => roles.includes(l))
    // 顶部筛选 + 弹窗各 7 个；弹窗为空列表时这里只有 7 → 立刻红
    expect(labels.length).toBe(14)
  })

  // 回归：ROLE_KEYS 曾写成 warehouseClerk / warehouseManager 驼峰，
  // 与后端 ROLE_VALUES 的 snake_case 对不上 —— 列表里显示英文原文，
  // 且把驼峰值提交给 POST /users 会 422。断言 value 而不只是 label 才能拦住。
  it('角色下拉的 value 就是后端 users.role 的取值（snake_case）', async () => {
    const wrapper = mountUserList()
    await flushPromises()

    const btn = wrapper.findAll('button').find((b) => b.text().includes('新建用户'))
    await btn.trigger('click')
    await flushPromises()

    const values = new Set(
      wrapper.findAllComponents({ name: 'ElOption' }).map((c) => c.props('value'))
    )
    for (const role of ['warehouse_clerk', 'warehouse_manager']) {
      expect(values.has(role), `缺少角色 ${role}`).toBe(true)
    }
    expect(values.has('warehouseClerk')).toBe(false)
    expect(values.has('warehouseManager')).toBe(false)
  })

  it('列表里仓管角色显示中文名，不把 role 原值泄给用户', async () => {
    adminListUsers.mockResolvedValue({
      total: 2,
      page: 1,
      page_size: 20,
      items: [
        makeUser({ id: 1, username: 'clerk', role: 'warehouse_clerk' }),
        makeUser({ id: 2, username: 'manager', role: 'warehouse_manager' })
      ]
    })
    const wrapper = mountUserList()
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('仓管录入员')
    expect(text).toContain('仓管主管')
    expect(text).not.toContain('warehouse_clerk')
    expect(text).not.toContain('warehouse_manager')
  })

  it('只读角色点行不打开弹窗', async () => {
    setPermissions(['user:read'])
    const wrapper = mountList()
    await flushPromises()

    await wrapper.findAll('.el-table__row')[0].trigger('click')
    await flushPromises()

    expect(wrapper.vm.$.setupState.dialogVisible).toBe(false)
  })
})
