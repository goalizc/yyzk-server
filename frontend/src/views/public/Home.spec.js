// Home.vue：产品→故障两级（零件可选过滤）、关键词过滤、未命中上报（600ms 防抖 + 30s 去重）
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
  { id: 21, title: '主刷不转', symptom: '启动后主刷不转', view_count: 10, part_name: '主刷模组' },
  { id: 22, title: '异响', symptom: '工作时异响', view_count: 3, part_name: '水箱模组' }
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

describe('Home 产品优先，零件可选', () => {
  it('挂载时加载产品列表', async () => {
    const { wrapper } = await mountHome()
    expect(listProducts).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('售后自助故障诊断')
    wrapper.unmount()
  })

  it('选产品后加载零件，并立刻加载该产品全部故障（不等零件）', async () => {
    const { wrapper } = await mountHome()
    wrapper.vm.productId = 1 // el-select v-model 先更新，再触发 @change
    await wrapper.vm.onProductChange(1)
    expect(listParts).toHaveBeenCalledWith(1)
    expect(wrapper.vm.partId).toBeNull()
    // 第二参数为空 → api 层不带 part_id，后端返回该产品全部故障
    expect(listFaults).toHaveBeenCalledWith(1, null)
    expect(wrapper.vm.faults).toHaveLength(2)
    wrapper.unmount()
  })

  it('选零件后按零件重新过滤列表', async () => {
    const { wrapper } = await mountHome()
    wrapper.vm.productId = 1
    await wrapper.vm.onProductChange(1)
    wrapper.vm.partId = 11
    await wrapper.vm.onPartChange(11)
    expect(listFaults).toHaveBeenLastCalledWith(1, 11)
    expect(wrapper.vm.faults).toHaveLength(2)
    expect(wrapper.text()).toContain('2 条故障现象')
    wrapper.unmount()
  })

  it('清空零件（查看全部零件）后回到产品全量列表', async () => {
    const { wrapper } = await mountHome()
    wrapper.vm.productId = 1
    await wrapper.vm.onProductChange(1)
    wrapper.vm.partId = 11
    await wrapper.vm.onPartChange(11)
    listFaults.mockClear()

    wrapper.vm.clearPart()
    await flushPromises()

    expect(wrapper.vm.partId).toBeNull()
    expect(listFaults).toHaveBeenCalledWith(1, null)
    wrapper.unmount()
  })

  it('列表项带零件名作为参考信息', async () => {
    // 零件不再是必经步骤，客户要知道"这条大概出在哪个部件"
    const { wrapper } = await mountHome()
    wrapper.vm.productId = 1
    await wrapper.vm.onProductChange(1)
    await flushPromises()
    expect(wrapper.find('.fault-part').text()).toBe('主刷模组')
    wrapper.unmount()
  })

  it('只有产品与零件两个下拉，不再有"选择故障现象"下拉', async () => {
    // 这条锁死设计决定：第三步下拉与下面的列表是同一批数据，且只显示术语标题，
    // 比列表更难选。有人想加回来会先让这条变红（见 docs 页面清单 §客户首页）
    const { wrapper } = await mountHome()
    expect(wrapper.findAll('.field')).toHaveLength(2)
    expect(wrapper.text()).not.toContain('选择故障现象')
    wrapper.unmount()
  })

  it('关键词在客户端过滤标题与现象', async () => {
    const { wrapper } = await mountHome()
    wrapper.vm.productId = 1
    await wrapper.vm.onProductChange(1)
    wrapper.vm.keyword = '异响'
    expect(wrapper.vm.filteredFaults.map((f) => f.id)).toEqual([22])
    wrapper.vm.keyword = '主刷' // 只在标题里
    expect(wrapper.vm.filteredFaults.map((f) => f.id)).toEqual([21])
    wrapper.vm.keyword = 'ZZZZ'
    expect(wrapper.vm.filteredFaults).toEqual([])
    wrapper.unmount()
  })

  it('过滤无结果时出现提交工单入口，并携带产品与零件上下文跳转', async () => {
    const { wrapper, router } = await mountHome()
    wrapper.vm.productId = 1
    await wrapper.vm.onProductChange(1)
    wrapper.vm.partId = 11
    await wrapper.vm.onPartChange(11)
    wrapper.vm.keyword = 'ZZZZ'
    await flushPromises()
    expect(wrapper.text()).toContain('没有找到匹配的解决方案')

    wrapper.vm.goTicket()
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('ticket-new')
    // 已经不存在"选中的故障"，工单只带产品与零件
    expect(router.currentRoute.value.query).toMatchObject({
      product_id: '1',
      part_id: '11'
    })
    wrapper.unmount()
  })

  it('未选零件也能提交工单，只带产品上下文', async () => {
    const { wrapper, router } = await mountHome()
    wrapper.vm.productId = 1
    await wrapper.vm.onProductChange(1)
    await flushPromises()

    wrapper.vm.goTicket()
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('ticket-new')
    expect(router.currentRoute.value.query).toMatchObject({ product_id: '1' })
    expect(router.currentRoute.value.query.part_id).toBeUndefined()
    wrapper.unmount()
  })
})

describe('Home 列表即选择器', () => {
  it('超过一屏时折叠，点「展开更多」再露出剩余条目', async () => {
    listFaults.mockResolvedValue(
      Array.from({ length: 7 }, (_, i) => ({
        id: 100 + i,
        title: `故障 ${i + 1}`,
        symptom: `现象 ${i + 1}`,
        view_count: 7 - i
      }))
    )
    const { wrapper } = await mountHome()
    wrapper.vm.productId = 1
    await wrapper.vm.onProductChange(1)
    wrapper.vm.partId = 11
    await wrapper.vm.onPartChange(11)
    await flushPromises()

    expect(wrapper.findAll('.fault-item')).toHaveLength(5)
    expect(wrapper.text()).toContain('展开更多（还有 2 条）')

    await wrapper.find('.more button').trigger('click')
    expect(wrapper.findAll('.fault-item')).toHaveLength(7)
    expect(wrapper.find('.more').exists()).toBe(false)
    wrapper.unmount()
  })

  it('换关键词时收起回第一屏（避免停在展开很多条的状态）', async () => {
    listFaults.mockResolvedValue(
      Array.from({ length: 7 }, (_, i) => ({ id: 100 + i, title: `故障${i}`, symptom: '', view_count: 0 }))
    )
    const { wrapper } = await mountHome()
    wrapper.vm.productId = 1
    await wrapper.vm.onProductChange(1)
    wrapper.vm.partId = 11
    await wrapper.vm.onPartChange(11)
    await flushPromises()

    wrapper.vm.showMore()
    expect(wrapper.vm.visibleCount).toBe(10)
    wrapper.vm.keyword = '故障'
    await flushPromises()
    expect(wrapper.vm.visibleCount).toBe(5)
    wrapper.unmount()
  })

  it('列表底部给出「都不是我的情况」的提交工单入口', async () => {
    const { wrapper } = await mountHome()
    wrapper.vm.productId = 1
    await wrapper.vm.onProductChange(1)
    wrapper.vm.partId = 11
    await wrapper.vm.onPartChange(11)
    await flushPromises()

    expect(wrapper.find('.list-footer').text()).toContain('都不是我的情况？')
    expect(wrapper.find('.list-footer').text()).toContain('提交工单')
    wrapper.unmount()
  })

  it('该产品没有故障记录时也有提交工单入口，文案区分"没记录"与"搜不到"', async () => {
    listFaults.mockResolvedValue([])
    const { wrapper } = await mountHome()
    wrapper.vm.productId = 1
    await wrapper.vm.onProductChange(1)
    await flushPromises()

    expect(wrapper.text()).toContain('暂时还没有这类故障记录')
    expect(wrapper.text()).toContain('提交工单')
    // 没有关键词时不该出现"清空关键词"
    expect(wrapper.text()).not.toContain('清空关键词')
    wrapper.unmount()
  })

  it('选了零件但该零件没有记录时，给出「查看全部零件」回到产品全量', async () => {
    listFaults.mockResolvedValue([])
    const { wrapper } = await mountHome()
    wrapper.vm.productId = 1
    await wrapper.vm.onProductChange(1)
    wrapper.vm.partId = 11
    await wrapper.vm.onPartChange(11)
    await flushPromises()
    expect(wrapper.text()).toContain('查看全部零件')

    const btn = wrapper.findAll('.empty-actions button').find((b) => b.text() === '查看全部零件')
    await btn.trigger('click')
    await flushPromises()
    expect(wrapper.vm.partId).toBeNull()
    expect(listFaults).toHaveBeenLastCalledWith(1, null)
    wrapper.unmount()
  })

  it('关键词无匹配时可以一键清空关键词回到列表', async () => {
    const { wrapper } = await mountHome()
    wrapper.vm.productId = 1
    await wrapper.vm.onProductChange(1)
    wrapper.vm.partId = 11
    await wrapper.vm.onPartChange(11)
    wrapper.vm.keyword = 'ZZZZ'
    await flushPromises()
    expect(wrapper.text()).toContain('没有找到匹配的解决方案')

    await wrapper.find('.empty-actions button').trigger('click')
    await flushPromises()
    expect(wrapper.vm.keyword).toBe('')
    expect(wrapper.findAll('.fault-item')).toHaveLength(2)
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

  it('未选择产品时不上报（选完产品就能报，不必等零件）', async () => {
    const { wrapper } = await mountHome()
    wrapper.vm.keyword = '随便'
    wrapper.vm.onKeywordInput()
    await vi.advanceTimersByTimeAsync(700)
    expect(reportMiss).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('未选零件时关键词未命中也要上报，part_id 传 null', async () => {
    // 零件是可选过滤器，客户没选零件正是最需要被统计的那批"不知道该搜什么"的人
    listFaults.mockResolvedValue(FAULTS)
    const { wrapper } = await mountHome()
    wrapper.vm.productId = 1
    await wrapper.vm.onProductChange(1)
    expect(wrapper.vm.partId).toBeNull()

    wrapper.vm.keyword = 'ZZZZ'
    wrapper.vm.onKeywordInput()
    await vi.advanceTimersByTimeAsync(700)

    expect(reportMiss).toHaveBeenCalledTimes(1)
    expect(reportMiss).toHaveBeenCalledWith({
      product_id: 1,
      part_id: null,
      raw_query: 'ZZZZ'
    })
    wrapper.unmount()
  })

  it('产品下没有任何故障记录时立即上报 raw_query=null（不必等关键词）', async () => {
    // 契约 §4 要求"未输入关键词"这一桶也要有数据，否则看板里永远空着
    listFaults.mockResolvedValue([])
    const { wrapper } = await mountHome()
    wrapper.vm.productId = 1
    await wrapper.vm.onProductChange(1)

    expect(reportMiss).toHaveBeenCalledTimes(1)
    expect(reportMiss).toHaveBeenCalledWith({ product_id: 1, part_id: null, raw_query: null })
    wrapper.unmount()
  })

  it('选了零件后零件无记录，上报带 part_id', async () => {
    listFaults.mockResolvedValue([])
    const { wrapper } = await mountHome()
    wrapper.vm.productId = 1
    await wrapper.vm.onProductChange(1)
    reportMiss.mockClear()
    wrapper.vm.partId = 11
    await wrapper.vm.onPartChange(11)

    expect(reportMiss).toHaveBeenCalledTimes(1)
    expect(reportMiss).toHaveBeenCalledWith({ product_id: 1, part_id: 11, raw_query: null })
    wrapper.unmount()
  })

  it('空结果 + 关键词都命中同一组合时，只按各自的 key 各报一次', async () => {
    listFaults.mockResolvedValue([])
    const { wrapper } = await mountHome()
    wrapper.vm.productId = 1
    await wrapper.vm.onProductChange(1)
    // 选产品阶段已按 (1, null, null) 报过一次；选零件是另一个 key，会再报一次
    wrapper.vm.partId = 11
    await wrapper.vm.onPartChange(11)
    expect(reportMiss).toHaveBeenCalledTimes(2)
    expect(reportMiss).toHaveBeenLastCalledWith({ product_id: 1, part_id: 11, raw_query: null })

    wrapper.vm.keyword = '不出水'
    wrapper.vm.onKeywordInput()
    await vi.advanceTimersByTimeAsync(700)
    expect(reportMiss).toHaveBeenCalledTimes(3) // 关键词那次是另一个 key
    expect(reportMiss).toHaveBeenLastCalledWith({
      product_id: 1,
      part_id: 11,
      raw_query: '不出水'
    })
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
