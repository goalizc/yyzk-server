import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import FaultReaderDrawer from './FaultReaderDrawer.vue'
import { setPermissions } from '../../../utils/permissions'

vi.mock('../../../api/admin', () => ({
  adminGetFault: vi.fn()
}))
vi.mock('../../../utils/clipboard', () => ({
  copyText: vi.fn().mockResolvedValue(true)
}))

import { adminGetFault } from '../../../api/admin'
import { copyText } from '../../../utils/clipboard'

const DETAIL = {
  id: 21,
  title: '主刷不转',
  product_id: 1,
  product_name: '扫地机器人',
  part_id: 11,
  part_name: '主刷模组',
  symptom: '启动后主刷不转',
  root_cause: '毛发缠绕',
  required_tools: null,
  solution_steps: [{ step: 1, text: '拆下主刷', image_url: null }],
  attachment_urls: [],
  needs_professional: false,
  is_published: true,
  created_at: '2026-10-01T09:00:00+08:00',
  updated_at: '2026-10-05T09:00:00+08:00',
  view_count: 30,
  resolved_count: 20
}

async function mountDrawer(props = {}) {
  const wrapper = mount(FaultReaderDrawer, {
    props: { modelValue: true, faultId: 21, ...props },
    global: { plugins: [ElementPlus] },
    attachTo: document.body
  })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  vi.clearAllMocks()
  setPermissions(['fault:read', 'fault:write'])
  adminGetFault.mockResolvedValue(DETAIL)
  copyText.mockResolvedValue(true)
})

describe('FaultReaderDrawer', () => {
  it('打开时加载并渲染方案', async () => {
    const wrapper = await mountDrawer()

    expect(adminGetFault).toHaveBeenCalledWith(21)
    expect(wrapper.text()).toContain('主刷不转')
    expect(wrapper.text()).toContain('拆下主刷')
  })

  it('有 fault:write 时显示编辑入口', async () => {
    const wrapper = await mountDrawer()
    expect(wrapper.text()).toContain('编辑')
  })

  it('无 fault:write 时隐藏编辑入口', async () => {
    setPermissions(['fault:read'])
    const wrapper = await mountDrawer()
    expect(wrapper.text()).not.toContain('编辑')
  })

  it('只有已发布方案显示打开客户页', async () => {
    const published = await mountDrawer()
    expect(published.text()).toContain('打开客户页')

    adminGetFault.mockResolvedValue({ ...DETAIL, is_published: false })
    const draft = await mountDrawer()
    expect(draft.text()).not.toContain('打开客户页')
  })

  it('复制调用 copyText 并包含客户页链接', async () => {
    const wrapper = await mountDrawer()

    const button = wrapper.findAll('button').find((node) => node.text() === '复制方案文本')
    await button.trigger('click')
    await flushPromises()

    expect(copyText).toHaveBeenCalledTimes(1)
    expect(copyText.mock.calls[0][0]).toContain('/faults/21')
  })
})
