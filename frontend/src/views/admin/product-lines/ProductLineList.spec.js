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
