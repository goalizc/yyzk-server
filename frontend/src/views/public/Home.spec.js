// Home.vue：三级级联、关键词过滤、未命中上报（600ms 防抖 + 30s 去重）
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createRouter, createMemoryHistory } from 'vue-router'
import Home from './Home.vue'

vi.mock('../../api/product', () => ({
  listProducts: vi.fn(),
  listParts: vi.fn()
}))
vi.mock('../../api/fault', () => ({
  listFaults: vi.fn(),
  reportMiss: vi.fn()
}))

import { listProducts, listParts } from '../../api/product'
import { listFaults, reportMiss } from '../../api/fault'

const PRODUCTS = [
  { id: 1, name: '扫地机器人', model: 'X1' },
  { id: 2, name: '空气净化器', model: 'A2' }
]
const PARTS = [
  { id: 11, name: '主刷模组', group_name: '动力系统' },
  { id: 12, name: '水箱模组', group_name: '清洁系统' }
]
const FAULTS = [
  { id: 21, title: '主刷不转', symptom: '启动后主刷不转', view_count: 10 },
  { id: 22, title: '异响', symptom: '工作时异响', view_count: 3 }
]

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: Home },
      { path: '/faults/:id', name: 'fault-detail', component: { template: '<div />' } },
      { path: '/tickets/new', name: 'ticket-new', component: { template: '<div />' } }
    ]
  })
}

async function mountHome() {
  const router = makeRouter()
  await router.push('/')
  const wrapper = mount(Home, {
    global: { plugins: [ElementPlus, router] },
    attachTo: document.body
  })
  await flushPromises()
  return { wrapper, router }
}

beforeEach(() => {
  vi.clearAllMocks()
  listProducts.mockResolvedValue(PRODUCTS)
  listParts.mockResolvedValue(PARTS)
  listFaults.mockResolvedValue(FAULTS)
  reportMiss.mockResolvedValue({ id: 1 })
})

afterEach(() => {
  document.body.innerHTML = ''
})

describe('Home 三级级联', () => {
  it('挂载时加载产品列表', async () => {
    const { wrapper } = await mountHome()
    expect(listProducts).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('售后自助故障诊断')
    wrapper.unmount()
  })

  it('选产品后加载零件并清空下级', async () => {
    const { wrapper } = await mountHome()
    wrapper.vm.productId = 1 // el-select v-model 先更新，再触发 @change
    await wrapper.vm.onProductChange(1)
    expect(listParts).toHaveBeenCalledWith(1)
    expect(wrapper.vm.partId).toBeNull()
    expect(wrapper.vm.faults).toEqual([])
    wrapper.unmount()
  })

  it('选零件后加载故障列表', async () => {
    const { wrapper } = await mountHome()
    wrapper.vm.productId = 1
    await wrapper.vm.onProductChange(1)
    wrapper.vm.partId = 11
    await wrapper.vm.onPartChange(11)
    expect(listFaults).toHaveBeenCalledWith(1, 11)
    expect(wrapper.vm.faults).toHaveLength(2)
    expect(wrapper.text()).toContain('找到 2 条可能的故障')
    wrapper.unmount()
  })

  it('关键词在客户端过滤标题与现象', async () => {
    const { wrapper } = await mountHome()
    wrapper.vm.productId = 1
    await wrapper.vm.onProductChange(1)
    wrapper.vm.partId = 11
    await wrapper.vm.onPartChange(11)
    wrapper.vm.keyword = '异响'
    expect(wrapper.vm.filteredFaults.map((f) => f.id)).toEqual([22])
    wrapper.vm.keyword = '主刷' // 只在标题里
    expect(wrapper.vm.filteredFaults.map((f) => f.id)).toEqual([21])
    wrapper.vm.keyword = 'ZZZZ'
    expect(wrapper.vm.filteredFaults).toEqual([])
    wrapper.unmount()
  })

  it('过滤无结果时出现提交工单入口，并携带上下文跳转', async () => {
    const { wrapper, router } = await mountHome()
    wrapper.vm.productId = 1
    await wrapper.vm.onProductChange(1)
    wrapper.vm.partId = 11
    await wrapper.vm.onPartChange(11)
    wrapper.vm.faultId = 21
    wrapper.vm.keyword = 'ZZZZ'
    await flushPromises()
    expect(wrapper.text()).toContain('没有找到匹配的解决方案')

    wrapper.vm.goTicket()
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('ticket-new')
    // vue-router 会把 query 序列化成字符串，TicketNew.payload() 再转数字
    expect(router.currentRoute.value.query).toMatchObject({
      product_id: '1',
      part_id: '11',
      fault_id: '21'
    })
    wrapper.unmount()
  })
})

describe('Home 未命中上报', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('过滤结果为 0 时防抖 600ms 后上报，同 key 30 秒内不重复', async () => {
    const { wrapper } = await mountHome()
    wrapper.vm.productId = 1
    await wrapper.vm.onProductChange(1)
    wrapper.vm.partId = 11
    await wrapper.vm.onPartChange(11)

    // 命中时不上报
    wrapper.vm.keyword = '异响'
    wrapper.vm.onKeywordInput()
    await vi.advanceTimersByTimeAsync(700)
    expect(reportMiss).not.toHaveBeenCalled()

    // 未命中 → 600ms 后上报一次
    wrapper.vm.keyword = 'ZZZZ'
    wrapper.vm.onKeywordInput()
    await vi.advanceTimersByTimeAsync(700)
    expect(reportMiss).toHaveBeenCalledTimes(1)
    expect(reportMiss).toHaveBeenCalledWith({
      product_id: 1,
      part_id: 11,
      raw_query: 'ZZZZ'
    })

    // 同 key 30 秒内不重复
    wrapper.vm.keyword = 'ZZZ1'
    wrapper.vm.onKeywordInput()
    await vi.advanceTimersByTimeAsync(700)
    wrapper.vm.keyword = 'ZZZZ' // 回到同一个 key
    wrapper.vm.onKeywordInput()
    await vi.advanceTimersByTimeAsync(700)
    expect(reportMiss).toHaveBeenCalledTimes(2) // ZZZ1 一次 + ZZZZ 因 key 不同
    wrapper.vm.keyword = 'ZZZZ'
    wrapper.vm.onKeywordInput()
    await vi.advanceTimersByTimeAsync(700)
    expect(reportMiss).toHaveBeenCalledTimes(2) // 30 秒窗口内被去重
    wrapper.unmount()
  })

  it('未选择零件时不上报', async () => {
    const { wrapper } = await mountHome()
    wrapper.vm.keyword = '随便'
    wrapper.vm.onKeywordInput()
    await vi.advanceTimersByTimeAsync(700)
    expect(reportMiss).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})

describe('Home 卸载清理', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('卸载后防抖定时器不触发未命中上报（review R3 回归）', async () => {
    const { wrapper } = await mountHome()
    wrapper.vm.productId = 1
    await wrapper.vm.onProductChange(1)
    wrapper.vm.partId = 11
    await wrapper.vm.onPartChange(11)

    wrapper.vm.keyword = 'ZZZZ'
    wrapper.vm.onKeywordInput()
    wrapper.unmount() // 600ms 内离开页面
    await vi.advanceTimersByTimeAsync(700)
    expect(reportMiss).not.toHaveBeenCalled()
  })
})
