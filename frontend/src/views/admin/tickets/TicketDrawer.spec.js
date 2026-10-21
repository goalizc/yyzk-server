// TicketDrawer.vue：状态流转可选项、状态变更强制备注、不传处理人时的 payload 形状
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import TicketDrawer from './TicketDrawer.vue'

vi.mock('../../../api/admin', () => ({
  adminGetTicket: vi.fn(),
  adminUpdateTicket: vi.fn()
}))

import { adminGetTicket, adminUpdateTicket } from '../../../api/admin'

function makeDetail(overrides = {}) {
  return {
    id: 1,
    ticket_no: 'TK202610190001',
    status: 'open',
    contact: '13800138000',
    contact_name: '张先生',
    need_on_site: false,
    description: '按步骤试了还是不行',
    remark: null,
    assignee_id: null,
    assignee_name: null,
    product: { id: 1, name: '扫地机器人', model: 'X1' },
    part: { id: 11, name: '电源模组' },
    fault: { id: 21, title: '开机无反应', needs_professional: true },
    created_at: '2026-10-19T10:30:00+08:00',
    updated_at: '2026-10-19T10:30:00+08:00',
    history: [
      { from_status: null, to_status: 'open', operator_name: null, remark: null, created_at: '2026-10-19T10:30:00+08:00' }
    ],
    ...overrides
  }
}

async function mountDrawer(ticketId = 1) {
  const wrapper = mount(TicketDrawer, {
    props: { modelValue: true, ticketId },
    global: { plugins: [ElementPlus] },
    attachTo: document.body
  })
  // el-drawer 的内容是 teleport 到 body 的，wrapper 自己卸不掉这段 DOM，
  // 必须在 afterEach 里显式 unmount，否则残留节点会跨用例互相踩，报
  // "Cannot read properties of null (reading 'nextSibling')" 的 unhandled rejection。
  mounted.push(wrapper)
  // el-drawer 的 @open 在 happy-dom 下不一定触发，直接调一次 load 等价
  await wrapper.vm.refresh()
  await flushPromises()
  return wrapper
}

// 每个用例创建的 wrapper，afterEach 统一卸载
const mounted = []

beforeEach(() => {
  vi.clearAllMocks()
  adminGetTicket.mockResolvedValue(makeDetail())
  adminUpdateTicket.mockResolvedValue(makeDetail())
})

afterEach(() => {
  // 倒序卸载：后挂载的先拆，与 Vue 的挂载顺序相反才符合 DOM 栈
  while (mounted.length) mounted.pop().unmount()
})

describe('TicketDrawer', () => {
  it('打开时请求详情（不用列表行数据凑）', async () => {
    const wrapper = await mountDrawer(7)
    expect(adminGetTicket).toHaveBeenCalledWith(7)
    expect(wrapper.text()).toContain('TK202610190001')
    // 详情返回完整联系方式，未脱敏
    expect(wrapper.text()).toContain('13800138000')
    expect(wrapper.text()).toContain('需专业维修')
  })

  it('状态可选项按合法路径约束：open → processing/closed', async () => {
    const wrapper = await mountDrawer()
    expect(wrapper.vm.$.setupState.nextStatuses).toEqual(['processing', 'closed'])
  })

  it('closed 为终态，没有可流转目标', async () => {
    adminGetTicket.mockResolvedValue(makeDetail({ status: 'closed' }))
    const wrapper = await mountDrawer()
    expect(wrapper.vm.$.setupState.nextStatuses).toEqual([])
    expect(wrapper.text()).toContain('已关闭，不可再流转')
  })

  it('状态变更但备注为空时拒绝提交，不发请求', async () => {
    const wrapper = await mountDrawer()
    const state = wrapper.vm.$.setupState
    state.form.status = 'processing'
    state.form.remark = '   '

    await state.onSave()
    await flushPromises()

    expect(adminUpdateTicket).not.toHaveBeenCalled()
    expect(state.remarkError).toBe('变更状态必须填写备注')
  })

  it('状态变更带备注：payload 不含 assignee_id（未传由后端自动认领）', async () => {
    const wrapper = await mountDrawer()
    const state = wrapper.vm.$.setupState
    state.form.status = 'processing'
    state.form.remark = '已电话联系用户'

    await state.onSave()
    await flushPromises()

    expect(adminUpdateTicket).toHaveBeenCalledWith(1, {
      status: 'processing',
      remark: '已电话联系用户'
    })
  })

  it('无任何修改时不发请求', async () => {
    const wrapper = await mountDrawer()
    await wrapper.vm.$.setupState.onSave()
    await flushPromises()
    expect(adminUpdateTicket).not.toHaveBeenCalled()
  })

  it('只改上门意愿不强制备注', async () => {
    const wrapper = await mountDrawer()
    const state = wrapper.vm.$.setupState
    state.form.need_on_site = true

    await state.onSave()
    await flushPromises()

    expect(adminUpdateTicket).toHaveBeenCalledWith(1, { need_on_site: true })
  })

  it('保存成功后向上抛出 updated 事件并同步详情', async () => {
    const updated = makeDetail({ status: 'processing', assignee_name: '李工' })
    adminUpdateTicket.mockResolvedValue(updated)
    const wrapper = await mountDrawer()
    const state = wrapper.vm.$.setupState
    state.form.status = 'processing'
    state.form.remark = '处理中'

    await state.onSave()
    await flushPromises()

    expect(wrapper.emitted('updated')?.[0]?.[0]).toMatchObject({
      id: 1,
      status: 'processing',
      assignee_name: '李工'
    })
    expect(state.detail.status).toBe('processing')
  })

  it('已有处理人时提示文案不同，且保存不改处理人', async () => {
    adminGetTicket.mockResolvedValue(
      makeDetail({ status: 'processing', assignee_id: 7, assignee_name: '李工' })
    )
    adminUpdateTicket.mockResolvedValue(
      makeDetail({ status: 'resolved', assignee_id: 7, assignee_name: '李工' })
    )
    const wrapper = await mountDrawer()
    const state = wrapper.vm.$.setupState

    // 三分支文案：已有人 → "保存不会改变处理人"；无人 → "由你认领"
    expect(state.assigneeHint).toContain('李工')
    expect(state.assigneeHint).toContain('不会改变处理人')

    state.form.status = 'resolved'
    state.form.remark = '已远程指导解决'
    await state.onSave()
    await flushPromises()

    // payload 里不能出现 assignee_id：不传才会"保持原处理人"
    const payload = adminUpdateTicket.mock.calls.at(-1)[1]
    expect(payload).toEqual({ status: 'resolved', remark: '已远程指导解决' })
    expect('assignee_id' in payload).toBe(false)
  })

  it('TICKET_STATUS_INVALID（他人已改动）时重新拉详情，不吃着旧状态继续', async () => {
    const wrapper = await mountDrawer()
    const state = wrapper.vm.$.setupState
    adminUpdateTicket.mockRejectedValue({
      response: { data: { detail: '该状态流转不被允许', code: 'TICKET_STATUS_INVALID' } }
    })
    // 重新拉回来的是别人改过的状态
    adminGetTicket.mockResolvedValue(makeDetail({ status: 'processing' }))

    state.form.status = 'closed'
    state.form.remark = '客户取消'
    await state.onSave()
    await flushPromises()

    expect(adminGetTicket).toHaveBeenCalledTimes(2)
    expect(state.detail.status).toBe('processing')
    // 重新加载后表单复位，避免用户对着过期状态再点一次保存
    expect(state.form.status).toBe(null)
  })

  it('刷新详情期间不把 detail 清空（否则抽屉内容闪一下、滚动跳回顶部）', async () => {
    const wrapper = await mountDrawer()
    const state = wrapper.vm.$.setupState
    expect(state.detail).not.toBeNull()

    // 让第二次请求挂起，观察"加载中"这一瞬间的 detail
    let release
    adminGetTicket.mockReturnValue(new Promise((r) => (release = r)))
    // refresh 是 defineExpose 出来的，在 vm 上而不在 setupState 上
    const pending = wrapper.vm.refresh()
    await Promise.resolve()

    // 关键：请求在途时旧内容仍然在，用户不会看到内容消失再出现
    expect(state.detail).not.toBeNull()
    expect(state.detail.ticket_no).toBe('TK202610190001')
    expect(state.loading).toBe(true)

    release(makeDetail({ status: 'processing' }))
    await pending
    await flushPromises()
    expect(state.detail.status).toBe('processing')
  })

  it('备注 placeholder 与报错文案不重复（避免同一句话灰红并排出现两遍）', async () => {
    const wrapper = await mountDrawer()
    const state = wrapper.vm.$.setupState

    // 未选状态时：说明"可留空"
    expect(state.remarkPlaceholder).toContain('可留空')

    // 选了状态后：应当是"该写什么"的示例，而不是直接把报错文案当 placeholder
    state.form.status = 'processing'
    await flushPromises()
    expect(state.remarkPlaceholder).not.toBe('变更状态必须填写备注')
    expect(state.remarkPlaceholder).toContain('如：')

    // 报错触发后，placeholder 与报错文案仍然不同
    await state.onSave()
    expect(state.remarkError).toBe('变更状态必须填写备注')
    expect(state.remarkPlaceholder).not.toBe(state.remarkError)
  })
})
