// ProductList.vue：新增/编辑、型号撞号内联报错、删除拦截、上下架开关回滚
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import ProductList from './ProductList.vue'
import { setPermissions } from '../../../utils/permissions'

vi.mock('../../../api/admin', () => ({
  adminListProducts: vi.fn(),
  adminListProductLines: vi.fn(),
  adminCreateProduct: vi.fn(),
  adminUpdateProduct: vi.fn(),
  adminDeleteProduct: vi.fn()
}))

import {
  adminCreateProduct,
  adminDeleteProduct,
  adminListProductLines,
  adminListProducts,
  adminUpdateProduct
} from '../../../api/admin'

const ROWS = [
  {
    id: 1,
    name: '扫地机器人',
    model: 'X1',
    line_id: 1,
    line_name: '扫地机',
    description: '',
    is_active: true,
    sort_order: 0,
    fault_count: 0,
    created_at: '2026-10-01T09:00:00+08:00',
    updated_at: '2026-10-01T09:00:00+08:00'
  },
  {
    id: 2,
    name: '净化器',
    model: 'A2',
    line_id: 1,
    line_name: '扫地机',
    description: '',
    is_active: true,
    sort_order: 1,
    fault_count: 4,
    created_at: '2026-10-02T09:00:00+08:00',
    updated_at: '2026-10-02T09:00:00+08:00'
  }
]

function page(items = ROWS) {
  return { total: items.length, page: 1, page_size: 20, items }
}

async function mountList() {
  const wrapper = mount(ProductList, {
    global: { plugins: [ElementPlus] },
    attachTo: document.body
  })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  vi.clearAllMocks()
  setPermissions(['product:read', 'product:write', 'product_line:read'])
  adminListProducts.mockResolvedValue(page())
  adminListProductLines.mockResolvedValue({ items: [{ id: 1, name: '扫地机', is_active: true }] })
  adminCreateProduct.mockResolvedValue({})
  adminUpdateProduct.mockResolvedValue({})
  adminDeleteProduct.mockResolvedValue({ success: true })
})

describe('ProductList', () => {
  it('加载后渲染产品行与故障数', async () => {
    const wrapper = await mountList()
    expect(adminListProducts).toHaveBeenCalledWith(
      expect.objectContaining({ page: 1, page_size: 20 })
    )
    expect(wrapper.text()).toContain('扫地机器人')
    expect(wrapper.text()).toContain('X1')
    expect(wrapper.text()).toContain('4')
  })

  it('关键词输入走 300ms 防抖，只发一次请求', async () => {
    vi.useFakeTimers()
    const wrapper = await mountList()
    adminListProducts.mockClear()

    const input = wrapper.find('input')
    await input.setValue('扫')
    await input.setValue('扫地')
    await input.setValue('扫地机')

    expect(adminListProducts).not.toHaveBeenCalled()
    vi.advanceTimersByTime(300)
    await flushPromises()
    expect(adminListProducts).toHaveBeenCalledTimes(1)
    expect(adminListProducts).toHaveBeenCalledWith(
      expect.objectContaining({ keyword: '扫地机' })
    )
    vi.useRealTimers()
  })

  it('型号重复（409 MODEL_DUPLICATED）只记字段级错误，弹窗保持打开', async () => {
    const wrapper = await mountList()
    adminCreateProduct.mockRejectedValue({
      response: { data: { detail: '型号 X1 已存在', code: 'MODEL_DUPLICATED' } }
    })

    // 打开新增弹窗
    const addBtn = wrapper.findAll('button').find((b) => b.text().includes('新增产品'))
    await addBtn.trigger('click')
    await flushPromises()

    // 按 el-form-item 的 prop 定位输入框：select 内部也有 input，
    // 用索引取会把值填到错误控件上（这里是踩过的坑）
    const items = wrapper.find('.el-dialog').findAll('.el-form-item')
    const nameItem = items.find((el) => el.text().includes('名称') && !el.text().includes('型号'))
    await nameItem.find('input').setValue('新产品')
    const modelItem = items.find((el) => el.text().includes('型号'))
    await modelItem.find('input').setValue('X1')
    wrapper.vm.$.setupState.form.line_id = 1

    const saveBtn = wrapper.findAll('.el-dialog button').find((b) => b.text().includes('保存'))
    await saveBtn.trigger('click')
    await flushPromises()

    expect(adminCreateProduct).toHaveBeenCalledWith(
      expect.objectContaining({ name: '新产品', model: 'X1', line_id: 1 })
    )
    // happy-dom 下 el-form-item 的报错节点不会渲染（error prop 与 validateMessage 都一样），
    // 所以断言状态：文案落在 modelError、弹窗不关闭
    expect(wrapper.vm.$.setupState.modelError).toBe('型号 X1 已存在')
    expect(wrapper.vm.$.setupState.dialogVisible).toBe(true)

    // 一改型号就撤掉撞号提示
    await modelItem.find('input').setValue('X2')
    expect(wrapper.vm.$.setupState.modelError).toBe('')
  })

  it('fault_count > 0 时删除被拦在前端，不发删除请求', async () => {
    const wrapper = await mountList()

    const rows = wrapper.findAll('.el-table__row')
    // 第二行（净化器，fault_count=4）的删除按钮
    const delBtn = rows[1].findAll('button').find((b) => b.text().includes('删除'))
    await delBtn.trigger('click')
    await flushPromises()

    expect(adminDeleteProduct).not.toHaveBeenCalled()
    expect(document.body.textContent).toContain('需先迁移或删除故障')
  })

  it('列表加载失败时进入错误态，点重试重新请求', async () => {
    adminListProducts.mockRejectedValueOnce({
      response: { data: { detail: '数据库不可用', code: 'SERVICE_UNAVAILABLE' } }
    })
    const wrapper = await mountList()

    expect(wrapper.vm.$.setupState.loadError).toBe('数据库不可用')
    // 错误态下表格与分页必须真的卸载，否则"加载失败"和旧数据会同时挂在页面上
    expect(wrapper.find('.el-table').exists()).toBe(false)
    expect(wrapper.find('.el-pagination').exists()).toBe(false)
    expect(wrapper.text()).toContain('重新加载')

    adminListProducts.mockResolvedValue(page())
    const retryBtn = wrapper.findAll('button').find((b) => b.text().includes('重新加载'))
    await retryBtn.trigger('click')
    await flushPromises()

    expect(wrapper.vm.$.setupState.loadError).toBe('')
    expect(wrapper.find('.el-table').exists()).toBe(true)
    expect(wrapper.find('.el-pagination').exists()).toBe(true)
    expect(wrapper.text()).toContain('扫地机器人')
  })

  it('上架开关失败时回滚（重新拉列表保持一致）', async () => {
    const wrapper = await mountList()
    adminUpdateProduct.mockRejectedValue({
      response: { data: { detail: '保存失败', code: 'INTERNAL_ERROR' } }
    })

    const switchEl = wrapper.findAll('.el-table__row')[0].find('.el-switch')
    await switchEl.trigger('click')
    await flushPromises()

    expect(adminUpdateProduct).toHaveBeenCalledWith(1, { is_active: false })
    // 失败后重新拉列表（第一次是挂载时）
    expect(adminListProducts).toHaveBeenCalledTimes(2)
  })

  it('只读角色看不到写入口，状态开关禁用且行点击不打开编辑', async () => {
    setPermissions(['product:read'])
    const wrapper = await mountList()

    expect(wrapper.findAll('button').some((b) => b.text().includes('新增产品'))).toBe(false)
    const firstRow = wrapper.findAll('.el-table__row')[0]
    expect(firstRow.findAll('button').some((b) => b.text().includes('编辑'))).toBe(false)
    expect(firstRow.findAll('button').some((b) => b.text().includes('删除'))).toBe(false)
    expect(firstRow.find('.el-switch').classes()).toContain('is-disabled')

    await firstRow.trigger('click')
    await flushPromises()
    expect(wrapper.vm.$.setupState.dialogVisible).toBe(false)
  })
})
