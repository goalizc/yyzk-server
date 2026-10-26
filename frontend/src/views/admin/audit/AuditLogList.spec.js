// AuditLogList.vue：筛选参数拼装、动作文案翻译、详情面板、失败标记、导出
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import AuditLogList from './AuditLogList.vue'
import { setPermissions } from '../../../utils/permissions'

vi.mock('../../../api/audit', () => ({
  adminListAuditLogs: vi.fn(),
  adminGetAuditLog: vi.fn(),
  adminAuditActions: vi.fn(),
  adminAuditSummary: vi.fn(),
  adminExportAuditLogs: vi.fn()
}))

import {
  adminAuditActions,
  adminAuditSummary,
  adminExportAuditLogs,
  adminGetAuditLog,
  adminListAuditLogs
} from '../../../api/audit'

const LOGS = [
  {
    id: 31,
    created_at: '2026-10-26T09:00:00+08:00',
    username: 'kefu01',
    action: 'fault.update',
    target_type: 'fault',
    target_id: '7',
    target_name: '喷洒不出水',
    method: 'PUT',
    path: '/api/admin/faults/7',
    status: 200,
    result: 'success',
    ip: '203.0.113.9',
    request_id: 'abc123'
  },
  {
    id: 30,
    created_at: '2026-10-26T08:58:00+08:00',
    username: 'nobody',
    action: 'auth.login',
    target_type: 'user',
    target_id: null,
    target_name: null,
    method: 'POST',
    path: '/api/auth/login',
    status: 401,
    result: 'failure',
    ip: '198.51.100.3',
    request_id: 'def456'
  }
]

const mountedWrappers = []

async function mountPage() {
  const wrapper = mount(AuditLogList, {
    global: { plugins: [ElementPlus] },
    attachTo: document.body
  })
  mountedWrappers.push(wrapper)
  await flushPromises()
  return wrapper
}

afterEach(() => {
  for (const wrapper of mountedWrappers) wrapper.unmount()
  mountedWrappers.length = 0
})

beforeEach(() => {
  vi.clearAllMocks()
  setPermissions(['audit:read'])
  adminListAuditLogs.mockResolvedValue({ total: 2, page: 1, page_size: 20, items: LOGS })
  adminAuditSummary.mockResolvedValue({
    period_days: 7,
    total: 12,
    failures: 3,
    actors: [
      { user_id: 1, username: 'kefu01', total: 9, failures: 2, distinct_ips: 3, last_at: '2026-10-26T09:00:00+08:00' }
    ]
  })
  adminAuditActions.mockResolvedValue(['auth.login', 'fault.update', 'user.reset_password'])
  adminGetAuditLog.mockResolvedValue({
    ...LOGS[0],
    user_id: 2,
    error_code: null,
    user_agent: 'Chrome/156',
    detail: { from_status: 'open', to_status: 'processing', remark_updated: true }
  })
  adminExportAuditLogs.mockResolvedValue(new Blob(['\ufeffa'], { type: 'text/csv' }))
})

describe('AuditLogList', () => {
  it('首次加载只传分页参数，并把动作码翻译成文案', async () => {
    const wrapper = await mountPage()

    expect(adminListAuditLogs).toHaveBeenCalledWith({ page: 1, page_size: 20 })
    expect(wrapper.text()).toContain('修改故障方案')
    // 没有 target_name 的记录退回对象 ID，不能显示空白
    expect(wrapper.text()).toContain('喷洒不出水')
    expect(wrapper.text()).toContain('kefu01')
  })

  it('失败记录带失败标记，成功记录带成功标记', async () => {
    const wrapper = await mountPage()

    const text = wrapper.text()
    expect(text).toContain('成功')
    expect(text).toContain('失败')
    expect(wrapper.findAll('.el-tag--danger').length).toBeGreaterThan(0)
  })

  it('账号 + 结果筛选会带进查询参数并重置到第 1 页', async () => {
    const wrapper = await mountPage()
    const state = wrapper.vm.$.setupState

    state.filters.username = 'kefu'
    state.filters.result = 'failure'
    state.pagination.page = 3
    state.search()
    await flushPromises()

    expect(adminListAuditLogs).toHaveBeenLastCalledWith({
      page: 1,
      page_size: 20,
      username: 'kefu',
      result: 'failure'
    })
  })

  it('时间范围按 YYYY-MM-DD 传给后端', async () => {
    const wrapper = await mountPage()
    const state = wrapper.vm.$.setupState

    state.filters.range = ['2026-10-01', '2026-10-26']
    state.search()
    await flushPromises()

    expect(adminListAuditLogs).toHaveBeenLastCalledWith({
      page: 1,
      page_size: 20,
      start_date: '2026-10-01',
      end_date: '2026-10-26'
    })
  })

  it('重置会清空全部筛选条件', async () => {
    const wrapper = await mountPage()
    const state = wrapper.vm.$.setupState

    state.filters.username = 'kefu'
    state.filters.action = 'fault.update'
    state.filters.keyword = '喷洒'
    state.filters.range = ['2026-10-01', '2026-10-26']
    state.onReset()
    await flushPromises()

    expect(state.filters.username).toBe('')
    expect(state.filters.action).toBe('')
    expect(state.filters.keyword).toBe('')
    expect(state.filters.range).toEqual([])
    expect(adminListAuditLogs).toHaveBeenLastCalledWith({ page: 1, page_size: 20 })
  })

  it('点击行拉详情并把变更字段翻译成人话', async () => {
    const wrapper = await mountPage()

    await wrapper.find('.el-table__row').trigger('click')
    await flushPromises()

    expect(adminGetAuditLog).toHaveBeenCalledWith(31)
    const state = wrapper.vm.$.setupState
    expect(state.panelVisible).toBe(true)
    const labels = state.extraFields.map((item) => item.label)
    expect(labels).toContain('原状态')
    expect(labels).toContain('新状态')
    // 状态码也要翻译，不能把 open/processing 直接丢给用户
    const values = state.extraFields.map((item) => item.value)
    expect(values).toContain('待处理')
    expect(values).toContain('处理中')
  })

  it('汇总条展示近 7 天失败数与多 IP 提示', async () => {
    const wrapper = await mountPage()

    const text = wrapper.text()
    expect(text).toContain('12')
    expect(text).toContain('3')
    expect(text).toContain('3 个 IP')
  })

  it('导出调用处按当前筛选拉 CSV', async () => {
    const wrapper = await mountPage()
    const state = wrapper.vm.$.setupState

    state.filters.action = 'fault.update'
    state.search()
    await flushPromises()
    await state.onExport()
    await flushPromises()

    expect(adminExportAuditLogs).toHaveBeenLastCalledWith({
      page: 1,
      page_size: 20,
      action: 'fault.update'
    })
  })

  it('未登录的动作显示「匿名」，不能把 i18n key 直接泄给用户', async () => {
    adminListAuditLogs.mockResolvedValue({
      total: 1,
      page: 1,
      page_size: 20,
      items: [{ ...LOGS[1], id: 40, username: '-' }]
    })

    const wrapper = await mountPage()

    expect(wrapper.text()).toContain('匿名')
    expect(wrapper.text()).not.toContain('admin.audit.anonymous')
  })

  it('加载失败时展示错误态而不是空表格', async () => {
    adminListAuditLogs.mockRejectedValue({ response: { data: { detail: '服务暂时不可用', code: 'SERVICE_UNAVAILABLE' } } })

    const wrapper = await mountPage()

    expect(wrapper.vm.$.setupState.loadError).toBe('服务暂时不可用')
  })
})
