// StatsDashboard.vue：days 联动三个接口、(未输入关键词) 置底、(未输入关键词) 与真实词不混排
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createRouter, createMemoryHistory } from 'vue-router'
import StatsDashboard from './StatsDashboard.vue'

vi.mock('../../../api/admin', () => ({
  adminStatsOverview: vi.fn(),
  adminStatsTopFaults: vi.fn(),
  adminStatsMissed: vi.fn()
}))

// echarts 在 happy-dom 下没有真实画布，init 会抛错；这里只验证数据编排，图形渲染交给浏览器
const setOption = vi.fn()
const chartOn = vi.fn()
vi.mock('echarts/core', () => ({
  use: vi.fn(),
  init: vi.fn(() => ({
    setOption,
    on: chartOn,
    resize: vi.fn(),
    clear: vi.fn(),
    dispose: vi.fn()
  }))
}))
vi.mock('echarts/charts', () => ({ BarChart: {} }))
vi.mock('echarts/components', () => ({ GridComponent: {}, TooltipComponent: {} }))
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }))

import { adminStatsMissed, adminStatsOverview, adminStatsTopFaults } from '../../../api/admin'

const OVERVIEW = {
  period_days: 30,
  total_queries: 1234,
  view_queries: 1147,
  resolved_queries: 555,
  resolve_rate: 0.484,
  total_tickets: 56,
  open_tickets: 12,
  missed_queries: 87
}

async function mountDash() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/admin/stats', name: 'admin-stats', component: StatsDashboard },
      { path: '/admin/faults/edit/:id?', name: 'admin-fault-edit', component: { template: '<div />' } }
    ]
  })
  await router.push('/admin/stats')
  const wrapper = mount(StatsDashboard, {
    global: { plugins: [ElementPlus, router] },
    attachTo: document.body
  })
  await flushPromises()
  return { wrapper, router }
}

beforeEach(() => {
  vi.clearAllMocks()
  adminStatsOverview.mockResolvedValue(OVERVIEW)
  adminStatsTopFaults.mockResolvedValue([
    {
      fault_id: 21,
      title: '开机无反应',
      product_name: '扫地机器人',
      part_name: '电源模组',
      view_count: 234,
      resolved_count: 180,
      period_views: 68
    }
  ])
  // 故意把 (未输入关键词) 放在第一条：验证前端会把它挪到末尾
  adminStatsMissed.mockResolvedValue([
    { raw_query: '(未输入关键词)', count: 15, sample_product_name: '净化器', sample_part_name: '滤芯', last_seen_at: '2026-10-18T10:00:00+08:00' },
    { raw_query: '漏水', count: 23, sample_product_name: '扫地机器人', sample_part_name: '水箱模组', last_seen_at: '2026-10-19T18:20:00+08:00' }
  ])
})

describe('StatsDashboard', () => {
  it('默认近 30 天，三个接口都带 days=30', async () => {
    await mountDash()
    expect(adminStatsOverview).toHaveBeenCalledWith({ days: 30 })
    expect(adminStatsTopFaults).toHaveBeenCalledWith({ days: 30, limit: 10 })
    expect(adminStatsMissed).toHaveBeenCalledWith({ days: 30, limit: 20 })
  })

  it('四张卡按口径渲染（解决率带百分号）', async () => {
    const { wrapper } = await mountDash()
    expect(wrapper.text()).toContain('1,234')
    expect(wrapper.text()).toContain('48.4%')
    expect(wrapper.text()).toContain('56')
    expect(wrapper.text()).toContain('12')
    // 未命中次数进副标题
    expect(wrapper.text()).toContain('87')
  })

  it('快速切窗口时，旧窗口的响应后到会被丢弃', async () => {
    const { wrapper } = await mountDash()
    const state = wrapper.vm.$.setupState

    let resolveSlow
    const slow = new Promise((resolve) => {
      resolveSlow = resolve
    })
    adminStatsOverview.mockReturnValueOnce(slow)

    state.days = 7
    const first = state.loadAll()
    state.days = 0
    await state.loadAll()
    expect(state.overview.total_queries).toBe(1234)

    // 7 天窗口的响应此刻才回来，不能覆盖"全部"的数据
    resolveSlow({ ...OVERVIEW, total_queries: 999 })
    await first
    await flushPromises()
    expect(state.overview.total_queries).toBe(1234)
    // 且不能把 loading 卡在 true（旧请求的 finally 不该关别人的 loading）
    expect(state.loading.overview).toBe(false)
  })

  it('切到"全部"传 days=0', async () => {
    const { wrapper } = await mountDash()
    wrapper.vm.$.setupState.days = 0
    await wrapper.vm.$.setupState.loadAll()
    await flushPromises()

    expect(adminStatsOverview).toHaveBeenLastCalledWith({ days: 0 })
    expect(adminStatsTopFaults).toHaveBeenLastCalledWith({ days: 0, limit: 10 })
    expect(adminStatsMissed).toHaveBeenLastCalledWith({ days: 0, limit: 20 })
  })

  it('(未输入关键词) 行置底且标记 isBlank', async () => {
    const { wrapper } = await mountDash()
    const rows = wrapper.vm.$.setupState.missedRows

    expect(rows).toHaveLength(2)
    expect(rows[0].raw_query).toBe('漏水')
    expect(rows[0].isBlank).toBe(false)
    expect(rows[1].raw_query).toBe('(未输入关键词)')
    expect(rows[1].isBlank).toBe(true)
  })

  it('无数据时显示各自的空态文案', async () => {
    adminStatsTopFaults.mockResolvedValue([])
    adminStatsMissed.mockResolvedValue([])
    const { wrapper } = await mountDash()

    expect(wrapper.text()).toContain('该时间范围内还没有查看记录')
    expect(wrapper.text()).toContain('暂无未命中记录')
  })

  it('柱子数据里带 fault_id，点击按真实柱子数据拼出的 id 跳转', async () => {
    const { router } = await mountDash()

    const option = setOption.mock.calls.at(-1)[0]
    expect(option.series[0].data).toEqual([{ value: 68, faultId: 21 }])

    // 关键：用 setOption 里真实的柱子对象驱动 click，
    // 手搓一个 { faultId: 21 } 会让"series 里根本没带 faultId"这种回归也能通过
    const clickHandler = chartOn.mock.calls.find(([name]) => name === 'click')[1]
    clickHandler({ data: option.series[0].data[0], dataIndex: 0 })
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/admin/faults/edit/21')
  })

  it('柱子 fault_id 为 0 时也要跳转（0 是合法 id，不能被 when-falsy 丢掉）', async () => {
    adminStatsTopFaults.mockResolvedValue([
      {
        fault_id: 0,
        title: '零号故障',
        product_name: '扫地机器人',
        part_name: '电源模组',
        view_count: 1,
        resolved_count: 0,
        period_views: 1
      }
    ])
    const { router } = await mountDash()

    const option = setOption.mock.calls.at(-1)[0]
    const clickHandler = chartOn.mock.calls.find(([name]) => name === 'click')[1]
    clickHandler({ data: option.series[0].data[0], dataIndex: 0 })
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/admin/faults/edit/0')
  })

  it('点击没有 fault_id 的柱子（空数据）不跳转', async () => {
    const { router } = await mountDash()
    const before = router.currentRoute.value.path
    const clickHandler = chartOn.mock.calls.find(([name]) => name === 'click')[1]
    clickHandler({ data: {}, dataIndex: 0 })
    await flushPromises()
    expect(router.currentRoute.value.path).toBe(before)
  })

  it('解决率分母为 null 时显示占位符而不是 NaN', async () => {
    adminStatsOverview.mockResolvedValue({ ...OVERVIEW, resolve_rate: null, view_queries: 0 })
    const { wrapper } = await mountDash()
    const text = wrapper.findAll('.metric-value')[1].text()
    expect(text).toBe('-')
  })
})
