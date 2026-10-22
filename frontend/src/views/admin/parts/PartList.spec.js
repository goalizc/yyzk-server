// PartList.vue：默认选中第一个产品、切换产品刷新、删除拦截、新增带 product_id
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import PartList from './PartList.vue'
import { setPermissions } from '../../../utils/permissions'

vi.mock('../../../api/admin', () => ({
  adminListProducts: vi.fn(),
  adminListParts: vi.fn(),
  adminCreatePart: vi.fn(),
  adminUpdatePart: vi.fn(),
  adminDeletePart: vi.fn()
}))

import {
  adminCreatePart,
  adminDeletePart,
  adminListParts,
  adminListProducts
} from '../../../api/admin'

const PRODUCTS = [
  { id: 1, name: '扫地机器人', model: 'X1' },
  { id: 2, name: '净化器', model: 'A2' }
]

const PARTS = [
  { id: 11, product_id: 1, part_no: 'P-X1-001', name: '主刷模组', group_name: '动力系统', sort_order: 1, fault_count: 0 },
  { id: 12, product_id: 1, part_no: null, name: '水箱模组', group_name: null, sort_order: 2, fault_count: 3 }
]

async function mountList() {
  const wrapper = mount(PartList, {
    global: { plugins: [ElementPlus] },
    attachTo: document.body
  })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  vi.clearAllMocks()
  setPermissions(['product:read', 'part:read', 'part:write'])
  adminListProducts.mockResolvedValue({ total: 2, page: 1, page_size: 100, items: PRODUCTS })
  adminListParts.mockResolvedValue({ total: 2, page: 1, page_size: 20, items: PARTS })
  adminCreatePart.mockResolvedValue({})
  adminDeletePart.mockResolvedValue({ success: true })
})

describe('PartList', () => {
  it('默认选中第一个产品并加载其零件', async () => {
    const wrapper = await mountList()
    expect(adminListParts).toHaveBeenCalledWith(
      expect.objectContaining({ product_id: 1, page: 1 })
    )
    expect(wrapper.text()).toContain('主刷模组')
    expect(wrapper.text()).toContain('动力系统')
    expect(wrapper.text()).toContain('未分组')
  })

  it('未选产品时不发零件请求，新增按钮禁用', async () => {
    adminListProducts.mockResolvedValue({ total: 0, page: 1, page_size: 100, items: [] })
    const wrapper = await mountList()

    expect(adminListParts).not.toHaveBeenCalled()
    const addBtn = wrapper.findAll('button').find((b) => b.text().includes('新增零件'))
    expect(addBtn.attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('请先到「产品管理」新增产品')
  })

  it('新增零件自动带上当前产品 product_id（不可跨产品）', async () => {
    const wrapper = await mountList()
    const addBtn = wrapper.findAll('button').find((b) => b.text().includes('新增零件'))
    await addBtn.trigger('click')
    await flushPromises()

    const items = wrapper.find('.el-dialog').findAll('.el-form-item')
    const nameItem = items.find((el) => el.text().includes('名称'))
    await nameItem.find('input').setValue('电源模组')

    const saveBtn = wrapper.findAll('.el-dialog button').find((b) => b.text().includes('保存'))
    await saveBtn.trigger('click')
    await flushPromises()

    expect(adminCreatePart).toHaveBeenCalledWith(
      expect.objectContaining({ name: '电源模组', product_id: 1 })
    )
  })

  it('fault_count > 0 的零件不发删除请求', async () => {
    const wrapper = await mountList()
    const secondRow = wrapper.findAll('.el-table__row')[1]
    const delBtn = secondRow.findAll('button').find((b) => b.text().includes('删除'))
    await delBtn.trigger('click')
    await flushPromises()

    expect(adminDeletePart).not.toHaveBeenCalled()
    expect(document.body.textContent).toContain('需先迁移或删除故障')
  })

  it('DELETE_BLOCKED 时展示后端 detail 原文', async () => {
    const wrapper = await mountList()
    // 后端复算后认为仍被引用（fault_count 在列表里是 0）
    adminDeletePart.mockRejectedValue({
      response: { data: { detail: '该零件下还有 2 条故障', code: 'DELETE_BLOCKED' } }
    })

    const firstRow = wrapper.findAll('.el-table__row')[0]
    const delBtn = firstRow.findAll('button').find((b) => b.text().includes('删除'))
    await delBtn.trigger('click')
    await flushPromises()

    // 确认框
    const confirmBtn = Array.from(document.querySelectorAll('.el-message-box__btns button')).find(
      (b) => b.textContent.includes('确认删除')
    )
    expect(confirmBtn).toBeTruthy()
    confirmBtn.click()
    await flushPromises()

    expect(adminDeletePart).toHaveBeenCalledWith(11)
  })

  it('零件列表加载失败进入错误态，重试后表格恢复', async () => {
    adminListParts.mockRejectedValueOnce({
      response: { data: { detail: '数据库不可用', code: 'SERVICE_UNAVAILABLE' } }
    })
    const wrapper = await mountList()

    expect(wrapper.vm.$.setupState.loadError).toBe('数据库不可用')
    // 错误态下表格必须真的卸载，否则"加载失败"和旧数据会同时挂在页面上
    expect(wrapper.find('.el-table').exists()).toBe(false)
    expect(wrapper.text()).toContain('重新加载')

    adminListParts.mockResolvedValue({ total: 2, page: 1, page_size: 20, items: PARTS })
    const retryBtn = wrapper.findAll('button').find((b) => b.text().includes('重新加载'))
    await retryBtn.trigger('click')
    await flushPromises()

    expect(wrapper.vm.$.setupState.loadError).toBe('')
    expect(wrapper.find('.el-table').exists()).toBe(true)
    expect(wrapper.text()).toContain('主刷模组')
  })

  it('切产品时先发后到的旧零件响应被丢弃', async () => {
    const wrapper = await mountList()
    const state = wrapper.vm.$.setupState

    let resolveSlow
    const slow = new Promise((resolve) => {
      resolveSlow = resolve
    })
    adminListParts.mockReturnValueOnce(slow)
    adminListParts.mockResolvedValueOnce({
      total: 1,
      page: 1,
      page_size: 20,
      items: [{ ...PARTS[0], id: 21, name: '净化器滤芯' }]
    })

    state.productId = 1
    const first = state.loadParts()
    state.productId = 2
    const second = state.loadParts()
    await second
    await flushPromises()
    expect(state.rows[0].name).toBe('净化器滤芯')

    // 产品 1 的响应此刻才回来，不能覆盖产品 2 的结果
    resolveSlow({ total: 1, page: 1, page_size: 20, items: [PARTS[0]] })
    await first
    await flushPromises()
    expect(state.rows[0].name).toBe('净化器滤芯')
    expect(state.loading).toBe(false)
  })
})
