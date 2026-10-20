// FaultDetail.vue：渲染、反馈交互与错误态
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createRouter, createMemoryHistory } from 'vue-router'
import FaultDetail from './FaultDetail.vue'

vi.mock('../../api/fault', () => ({
  getFault: vi.fn(),
  sendFeedback: vi.fn()
}))

import { getFault, sendFeedback } from '../../api/fault'

const DETAIL = {
  id: 21,
  product_id: 1,
  part_id: 11,
  product_name: '扫地机器人',
  part_name: '主刷模组',
  title: '主刷不转',
  symptom: '启动后主刷不转',
  root_cause: '主刷缠绕异物',
  required_tools: '螺丝刀',
  needs_professional: false,
  solution_steps: [
    { step: 1, text: '翻起机器', image_url: null },
    { step: 2, text: '清理缠绕物', image_url: '/uploads/a.jpg' }
  ],
  attachment_urls: [{ name: '手册.pdf', url: '/uploads/m.pdf', size: 2048 }],
  view_count: 10,
  resolved_count: 3,
  query_log_id: 99
}

function makeRouter() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/faults/:id', name: 'fault-detail', component: FaultDetail },
      { path: '/tickets/new', name: 'ticket-new', component: { template: '<div />' } }
    ]
  })
  return router
}

async function mountDetail(query = {}) {
  const router = makeRouter()
  await router.push({ path: '/faults/21', query })
  const wrapper = mount(FaultDetail, {
    global: { plugins: [ElementPlus, router] },
    attachTo: document.body
  })
  await flushPromises()
  return { wrapper, router }
}

beforeEach(() => {
  vi.clearAllMocks()
  getFault.mockResolvedValue(DETAIL)
  sendFeedback.mockResolvedValue({})
})

describe('FaultDetail', () => {
  it('渲染标题、步骤、附件，并把关键词透传给详情接口', async () => {
    const { wrapper } = await mountDetail({ q: '主刷' })
    expect(getFault).toHaveBeenCalledWith('21', '主刷')
    expect(wrapper.text()).toContain('主刷不转')
    expect(wrapper.text()).toContain('翻起机器')
    expect(wrapper.text()).toContain('清理缠绕物')
    expect(wrapper.text()).toContain('手册.pdf')
    expect(wrapper.text()).not.toContain('请勿自行拆机') // needs_professional=false
    wrapper.unmount()
  })

  it('需要专业处理时展示警示', async () => {
    getFault.mockResolvedValue({ ...DETAIL, needs_professional: true })
    const { wrapper } = await mountDetail()
    expect(wrapper.text()).toContain('请勿自行拆机')
    wrapper.unmount()
  })

  it('点击已解决：携带 query_log_id 反馈，成功后禁用按钮', async () => {
    const { wrapper } = await mountDetail()
    await wrapper.vm.feedback(true)
    await flushPromises()
    expect(sendFeedback).toHaveBeenCalledWith(21, { query_log_id: 99, resolved: true })
    expect(wrapper.vm.feedbackDone).toBe(true)
    expect(wrapper.text()).toContain('很高兴帮到您')
    wrapper.unmount()
  })

  it('未解决反馈展示转工单引导', async () => {
    const { wrapper } = await mountDetail()
    await wrapper.vm.feedback(false)
    await flushPromises()
    expect(sendFeedback).toHaveBeenCalledWith(21, { query_log_id: 99, resolved: false })
    expect(wrapper.text()).toContain('建议提交工单')
    wrapper.unmount()
  })

  it('404 时展示错误态而非白屏', async () => {
    getFault.mockRejectedValue({
      response: { status: 404, data: { detail: '故障不存在', code: 'NOT_FOUND' } }
    })
    const { wrapper } = await mountDetail()
    expect(wrapper.text()).toContain('故障不存在')
    expect(wrapper.text()).toContain('返回首页')
    wrapper.unmount()
  })

  it('仍然不行按钮携带完整上下文跳转工单页', async () => {
    const { wrapper, router } = await mountDetail()
    wrapper.vm.goTicket()
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('ticket-new')
    expect(router.currentRoute.value.query).toMatchObject({
      product_id: '1',
      part_id: '11',
      fault_id: '21',
      fault_title: '主刷不转'
    })
    wrapper.unmount()
  })
})
