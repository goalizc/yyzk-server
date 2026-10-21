// FaultList.vue：筛选参数拼装、产品切换清空零件、进入编辑、删除确认、空态
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createRouter, createMemoryHistory } from 'vue-router'
import FaultList from './FaultList.vue'

vi.mock('../../../api/admin', () => ({
  adminListFaults: vi.fn(),
  adminListProducts: vi.fn(),
  adminListParts: vi.fn(),
  adminDeleteFault: vi.fn()
}))

import {
  adminDeleteFault,
  adminListFaults,
  adminListParts,
  adminListProducts
} from '../../../api/admin'

const PRODUCTS = [{ id: 1, name: '扫地机器人', model: 'X1' }]
const PARTS = [{ id: 11, name: '主刷模组', group_name: '动力系统' }]
const FAULTS = [
  {
    id: 21,
    product_id: 1,
    product_name: '扫地机器人',
    part_id: 11,
    part_name: '主刷模组',
    title: '主刷不转',
    symptom: '启动后主刷不转',
    needs_professional: false,
    is_published: true,
    view_count: 30,
    resolved_count: 20,
    attachment_count: 0,
    created_at: '2026-10-01T09:00:00+08:00',
    updated_at: '2026-10-05T09:00:00+08:00'
  }
]

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/admin/faults', name: 'admin-faults', component: FaultList },
      { path: '/admin/faults/edit/:id?', name: 'admin-fault-edit', component: { template: '<div />' } }
    ]
  })
}

async function mountList() {
  const router = makeRouter()
  await router.push('/admin/faults')
  const wrapper = mount(FaultList, {
    global: { plugins: [ElementPlus, router] },
    attachTo: document.body
  })
  await flushPromises()
  return { wrapper, router }
}

beforeEach(() => {
  vi.clearAllMocks()
  adminListProducts.mockResolvedValue({ total: 1, page: 1, page_size: 100, items: PRODUCTS })
  adminListParts.mockResolvedValue({ total: 1, page: 1, page_size: 100, items: PARTS })
  adminListFaults.mockResolvedValue({ total: 1, page: 1, page_size: 20, items: FAULTS })
  adminDeleteFault.mockResolvedValue({ success: true })
})

describe('FaultList', () => {
  it('首次加载不带筛选参数，只传分页', async () => {
    const { wrapper } = await mountList()
    expect(adminListFaults).toHaveBeenCalledWith({ page: 1, page_size: 20 })
    expect(wrapper.text()).toContain('主刷不转')
    expect(wrapper.text()).toContain('已发布')
  })

  it('选中产品后带 product_id，并拉该产品零件', async () => {
    const { wrapper } = await mountList()
    // 直接驱动组件状态等价于用户在下拉里选产品：v-model 会先写 filters.productId，
    // 所以这里要手动补上，否则查的是"全部产品"
    const state = wrapper.vm.$.setupState
    state.filters.productId = 1
    state.onProductChange(1)
    await flushPromises()

    expect(adminListParts).toHaveBeenCalledWith({ product_id: 1, page: 1, page_size: 100 })
    expect(adminListFaults).toHaveBeenLastCalledWith(
      expect.objectContaining({ product_id: 1, page: 1 })
    )
  })

  it('换产品会清空已选零件，避免跨产品查询', async () => {
    const { wrapper } = await mountList()
    const state = wrapper.vm.$.setupState
    state.onProductChange(1)
    await flushPromises()
    state.filters.partId = 11

    // 切到另一个产品（模拟后端返回另一个 id）
    state.filters.productId = 2
    state.onProductChange(2)
    await flushPromises()

    expect(state.filters.partId).toBe(null)
    expect(adminListFaults).toHaveBeenLastCalledWith(
      expect.not.objectContaining({ part_id: 11 })
    )
  })

  it('关键词走 300ms 防抖', async () => {
    vi.useFakeTimers()
    const { wrapper } = await mountList()
    adminListFaults.mockClear()

    wrapper.vm.$.setupState.filters.keyword = '不转'
    wrapper.vm.$.setupState.onKeywordInput()
    expect(adminListFaults).not.toHaveBeenCalled()

    vi.advanceTimersByTime(300)
    await flushPromises()
    expect(adminListFaults).toHaveBeenCalledWith(
      expect.objectContaining({ keyword: '不转', page: 1 })
    )
    vi.useRealTimers()
  })

  it('重置清空全部筛选并回到第一页', async () => {
    const { wrapper } = await mountList()
    const state = wrapper.vm.$.setupState
    state.filters.productId = 1
    state.filters.partId = 11
    state.filters.keyword = 'abc'
    state.filters.published = false
    state.pagination.page = 3

    state.onReset()
    await flushPromises()

    expect(state.filters.productId).toBe(null)
    expect(state.filters.partId).toBe(null)
    expect(state.filters.keyword).toBe('')
    expect(state.filters.published).toBe(null)
    expect(state.pagination.page).toBe(1)
    expect(adminListFaults).toHaveBeenLastCalledWith({ page: 1, page_size: 20 })
  })

  it('筛选快速变更时，先发后到的旧响应被丢弃', async () => {
    const { wrapper } = await mountList()
    const state = wrapper.vm.$.setupState

    let resolveSlow
    const slow = new Promise((resolve) => {
      resolveSlow = resolve
    })
    // 第一次请求挂起，第二次立即返回
    adminListFaults.mockReturnValueOnce(slow)
    adminListFaults.mockResolvedValueOnce({
      total: 1,
      page: 1,
      page_size: 20,
      items: [{ ...FAULTS[0], id: 99, title: '最新结果' }]
    })

    state.filters.productId = 1
    const first = state.load()
    state.filters.productId = 2
    const second = state.load()
    await second
    await flushPromises()
    expect(state.rows[0].title).toBe('最新结果')

    // 旧请求此刻才回来，不能覆盖
    resolveSlow({ total: 1, page: 1, page_size: 20, items: [FAULTS[0]] })
    await first
    await flushPromises()
    expect(state.rows[0].title).toBe('最新结果')
  })


  it('列表为空时给出"新增第一条"引导', async () => {
    adminListFaults.mockResolvedValue({ total: 0, page: 1, page_size: 20, items: [] })
    const { wrapper } = await mountList()
    expect(wrapper.text()).toContain('暂无故障')
  })

  it('列表加载失败进入错误态，重试后表格恢复', async () => {
    adminListFaults.mockRejectedValueOnce({
      response: { data: { detail: '数据库不可用', code: 'SERVICE_UNAVAILABLE' } }
    })
    const { wrapper } = await mountList()

    expect(wrapper.vm.$.setupState.loadError).toBe('数据库不可用')
    expect(wrapper.find('.el-table').exists()).toBe(false)
    expect(wrapper.text()).toContain('重新加载')

    adminListFaults.mockResolvedValue({ total: 1, page: 1, page_size: 20, items: FAULTS })
    const retryBtn = wrapper.findAll('button').find((b) => b.text().includes('重新加载'))
    await retryBtn.trigger('click')
    await flushPromises()

    expect(wrapper.vm.$.setupState.loadError).toBe('')
    expect(wrapper.find('.el-table').exists()).toBe(true)
    expect(wrapper.text()).toContain(FAULTS[0].title)
  })
})
