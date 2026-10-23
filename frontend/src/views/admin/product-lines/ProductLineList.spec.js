import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import ProductLineList from './ProductLineList.vue'
import { setPermissions } from '../../../utils/permissions'

vi.mock('../../../api/admin', () => ({
  adminListProductLines: vi.fn(),
  adminCreateProductLine: vi.fn(),
  adminUpdateProductLine: vi.fn(),
  adminDeleteProductLine: vi.fn()
}))

import { adminListProductLines } from '../../../api/admin'

beforeEach(() => {
  vi.clearAllMocks()
  setPermissions(['product_line:read', 'product_line:write'])
  adminListProductLines.mockResolvedValue({
    items: [{ id: 1, name: '扫地机', sort_order: 0, is_active: true, product_count: 3 }]
  })
})

describe('ProductLineList', () => {
  it('渲染产品线与产品数', async () => {
    const wrapper = mount(ProductLineList, { global: { plugins: [ElementPlus] }, attachTo: document.body })
    await flushPromises()
    expect(wrapper.text()).toContain('扫地机')
    expect(wrapper.text()).toContain('3')
  })
})

// 一致性：其它列表（产品/零件/故障/工单）都是"点行即编辑"，产品线此前没有
describe('ProductLineList 行点击', () => {
  it('点击行打开编辑弹窗并带上该行 id', async () => {
    const wrapper = mount(ProductLineList, {
      global: { plugins: [ElementPlus] },
      attachTo: document.body
    })
    await flushPromises()

    await wrapper.findAll('.el-table__row')[0].trigger('click')
    await flushPromises()

    const state = wrapper.vm.$.setupState
    expect(state.dialogVisible).toBe(true)
    expect(state.editingId).toBe(1)
  })

  it('只读角色点行不打开弹窗（与其它列表同规则）', async () => {
    setPermissions(['product_line:read'])
    const wrapper = mount(ProductLineList, {
      global: { plugins: [ElementPlus] },
      attachTo: document.body
    })
    await flushPromises()

    await wrapper.findAll('.el-table__row')[0].trigger('click')
    await flushPromises()

    expect(wrapper.vm.$.setupState.dialogVisible).toBe(false)
  })
})
