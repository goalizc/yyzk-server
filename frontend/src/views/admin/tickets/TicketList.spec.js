// TicketList.vue：筛选参数拼装（日期区间透传）、脱敏列渲染、抽屉局部刷新
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import TicketList from './TicketList.vue'

vi.mock('../../../api/admin', () => ({
  adminListTickets: vi.fn(),
  adminGetTicket: vi.fn(),
  adminUpdateTicket: vi.fn()
}))

import { adminListTickets } from '../../../api/admin'

const ROWS = [
  {
    id: 1,
    ticket_no: 'TK202610190001',
    product_name: '扫地机器人',
    product_model: 'X1',
    part_name: '电源模组',
    fault_title: '开机无反应',
    contact: '138****8000',
    contact_name: '张先生',
    need_on_site: true,
    status: 'open',
    assignee_name: null,
    created_at: '2026-10-19T10:30:00+08:00',
    updated_at: '2026-10-19T10:30:00+08:00'
  }
]

async function mountList() {
  const wrapper = mount(TicketList, {
    global: { plugins: [ElementPlus] },
    attachTo: document.body
  })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  vi.clearAllMocks()
  adminListTickets.mockResolvedValue({ total: 1, page: 1, page_size: 20, items: ROWS })
})

describe('TicketList', () => {
  it('首次加载只传分页', async () => {
    await mountList()
    expect(adminListTickets).toHaveBeenCalledWith({ page: 1, page_size: 20 })
  })

  it('列表展示脱敏联系方式与状态文案', async () => {
    const wrapper = await mountList()
    expect(wrapper.text()).toContain('TK202610190001')
    expect(wrapper.text()).toContain('138****8000')
    expect(wrapper.text()).toContain('待处理')
    expect(wrapper.text()).toContain('未认领')
  })

  it('日期区间按 YYYY-MM-DD 原样透传 start_date / end_date', async () => {
    const wrapper = await mountList()
    wrapper.vm.$.setupState.dateRange = ['2026-10-01', '2026-10-19']
    wrapper.vm.$.setupState.reload()
    await flushPromises()

    expect(adminListTickets).toHaveBeenLastCalledWith({
      page: 1,
      page_size: 20,
      start_date: '2026-10-01',
      end_date: '2026-10-19'
    })
  })

  it('状态 + 关键词 + 日期可叠加', async () => {
    const wrapper = await mountList()
    const state = wrapper.vm.$.setupState
    state.filters.status = 'processing'
    state.filters.keyword = 'TK2026'
    state.dateRange = ['2026-10-01', '2026-10-19']
    state.reload()
    await flushPromises()

    expect(adminListTickets).toHaveBeenLastCalledWith({
      page: 1,
      page_size: 20,
      status: 'processing',
      keyword: 'TK2026',
      start_date: '2026-10-01',
      end_date: '2026-10-19'
    })
  })

  it('重置清空三个条件', async () => {
    const wrapper = await mountList()
    const state = wrapper.vm.$.setupState
    state.filters.status = 'closed'
    state.filters.keyword = 'x'
    state.dateRange = ['2026-10-01', '2026-10-02']

    state.onReset()
    await flushPromises()

    expect(state.filters.status).toBe(null)
    expect(state.filters.keyword).toBe('')
    expect(state.dateRange).toEqual([])
    expect(adminListTickets).toHaveBeenLastCalledWith({ page: 1, page_size: 20 })
  })

  it('点击行打开抽屉并带上 id', async () => {
    const wrapper = await mountList()
    await wrapper.findAll('.el-table__row')[0].trigger('click')

    expect(wrapper.vm.$.setupState.currentId).toBe(1)
    expect(wrapper.vm.$.setupState.drawerVisible).toBe(true)
  })

  it('抽屉保存后局部刷新该行状态，不重拉列表', async () => {
    const wrapper = await mountList()
    adminListTickets.mockClear()
    const state = wrapper.vm.$.setupState
    state.rows = ROWS.map((row) => ({ ...row }))

    state.onDrawerUpdated({ id: 1, status: 'processing', assignee_name: '李工' })

    expect(state.rows[0].status).toBe('processing')
    expect(state.rows[0].assignee_name).toBe('李工')
    expect(adminListTickets).not.toHaveBeenCalled()
  })

  it('列表加载失败进入错误态，重试后表格恢复', async () => {
    adminListTickets.mockRejectedValueOnce({
      response: { data: { detail: '数据库不可用', code: 'SERVICE_UNAVAILABLE' } }
    })
    const wrapper = await mountList()

    expect(wrapper.vm.$.setupState.loadError).toBe('数据库不可用')
    expect(wrapper.find('.el-table').exists()).toBe(false)
    expect(wrapper.text()).toContain('重新加载')

    adminListTickets.mockResolvedValue({ total: 1, page: 1, page_size: 20, items: ROWS })
    const retryBtn = wrapper.findAll('button').find((b) => b.text().includes('重新加载'))
    await retryBtn.trigger('click')
    await flushPromises()

    expect(wrapper.vm.$.setupState.loadError).toBe('')
    expect(wrapper.find('.el-table').exists()).toBe(true)
    expect(wrapper.text()).toContain(ROWS[0].ticket_no)
  })
})
