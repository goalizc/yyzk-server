// TicketNew.vue：表单校验、payload 组装、429 提示、成功跳转
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createRouter, createMemoryHistory } from 'vue-router'
import TicketNew from './TicketNew.vue'

vi.mock('../../api/ticket', () => ({
  submitTicket: vi.fn()
}))

import { submitTicket } from '../../api/ticket'

// query 不在这里拼：调用方用 router.push 带上，避免两处各算一次
function makeRouter() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/tickets/new', name: 'ticket-new', component: TicketNew },
      { path: '/tickets/success', name: 'ticket-success', component: { template: '<div />' } }
    ]
  })
  return router
}

async function mountTicket(query = {}) {
  const router = makeRouter()
  await router.push({ path: '/tickets/new', query })
  const wrapper = mount(TicketNew, {
    global: { plugins: [ElementPlus, router] },
    attachTo: document.body
  })
  await flushPromises()
  return { wrapper, router }
}

beforeEach(() => {
  vi.clearAllMocks()
  submitTicket.mockResolvedValue({
    ticket_no: 'TK202610210001',
    created_at: '2026-10-21T10:00:00+08:00'
  })
})

describe('TicketNew', () => {
  it('联系方式与描述通过校验后提交，query 上下文转数字', async () => {
    const { wrapper, router } = await mountTicket({
      product_id: '1',
      part_id: '11',
      fault_id: '21',
      fault_title: '主刷不转'
    })
    expect(wrapper.text()).toContain('已关联的问题')
    expect(wrapper.text()).toContain('主刷不转')

    wrapper.vm.form.contact = '  13800138000  '
    wrapper.vm.form.contact_name = ' 张先生 '
    wrapper.vm.form.description = ' 按方案清理后仍不转 '
    wrapper.vm.form.need_on_site = true
    await wrapper.vm.onSubmit()
    await flushPromises()

    expect(submitTicket).toHaveBeenCalledTimes(1)
    expect(submitTicket).toHaveBeenCalledWith({
      contact: '13800138000', // trim
      contact_name: '张先生',
      description: '按方案清理后仍不转',
      need_on_site: true,
      product_id: 1, // 字符串 → 数字
      part_id: 11,
      fault_id: 21
    })
    expect(router.currentRoute.value.name).toBe('ticket-success')
    expect(router.currentRoute.value.query.ticket_no).toBe('TK202610210001')
    wrapper.unmount()
  })

  it('联系方式或描述太短时不发请求', async () => {
    const { wrapper } = await mountTicket()
    wrapper.vm.form.contact = '123'
    wrapper.vm.form.description = '短'
    await wrapper.vm.onSubmit()
    await flushPromises()
    expect(submitTicket).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('429 时提示稍后再试', async () => {
    submitTicket.mockRejectedValue({
      response: { status: 429, data: { detail: '操作过于频繁', code: 'RATE_LIMITED' } }
    })
    const { wrapper } = await mountTicket()
    wrapper.vm.form.contact = '13800138000'
    wrapper.vm.form.description = '描述足够长的一段话'
    await wrapper.vm.onSubmit()
    await flushPromises()
    expect(document.querySelector('.el-message--warning')).toBeTruthy()
    wrapper.unmount()
  })

  it('其他错误展示后端 detail', async () => {
    submitTicket.mockRejectedValue({
      response: { status: 400, data: { detail: '请描述故障情况', code: 'VALIDATION_ERROR' } }
    })
    const { wrapper } = await mountTicket()
    wrapper.vm.form.contact = '13800138000'
    wrapper.vm.form.description = '描述足够长的一段话'
    await wrapper.vm.onSubmit()
    await flushPromises()
    expect(document.querySelector('.el-message--error')).toBeTruthy()
    expect(document.body.textContent).toContain('请描述故障情况')
    wrapper.unmount()
  })
})
