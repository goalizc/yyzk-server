import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import SkuList from './SkuList.vue'
import InboundList from './InboundList.vue'
import DocumentList from './DocumentList.vue'
import OutboundList from './OutboundList.vue'
import MovementList from './MovementList.vue'
import AdjustmentList from './AdjustmentList.vue'
import ReverseDialog from './ReverseDialog.vue'
import CategoryList from './CategoryList.vue'
import EditDocumentDialog from './EditDocumentDialog.vue'
import DocumentFormDialog from './DocumentFormDialog.vue'
import SkuFilterBar from './SkuFilterBar.vue'
import { setPermissions } from '../../../utils/permissions'

// 把整条 api 层替成桩，页面只验证"能挂载、文案能解析、按钮按权限出现"
vi.mock('../../../api/inventory', () => ({
  inventoryWarehouses: vi.fn(),
  inventorySkus: vi.fn(),
  inventoryCreateSku: vi.fn(),
  inventoryUpdateSku: vi.fn(),
  inventoryDisableSku: vi.fn(),
  inventoryCategories: vi.fn(),
  inventoryRefProducts: vi.fn(),
  inventoryRefParts: vi.fn(),
  inventoryCreateCategory: vi.fn(),
  inventoryUpdateCategory: vi.fn(),
  inventorySummary: vi.fn(),
  inventoryInboundOrders: vi.fn(),
  inventoryGetInbound: vi.fn(),
  inventoryCreateInbound: vi.fn(),
  inventoryOutboundOrders: vi.fn(),
  inventoryGetOutbound: vi.fn(),
  inventoryCreateOutbound: vi.fn(),
  inventoryCreateAdjustment: vi.fn(),
  inventoryReverseDocument: vi.fn(),
  inventoryUpdateDocument: vi.fn(),
  inventoryMovements: vi.fn(),
  inventoryExport: vi.fn()
}))

import * as inv from '../../../api/inventory'

let wrapper
afterEach(() => {
  wrapper?.unmount()
  wrapper = null
})

beforeEach(() => {
  vi.clearAllMocks()
  setPermissions([
    'inventory:sku:read', 'inventory:sku:write',
    'inventory:inbound:read', 'inventory:inbound:write',
    'inventory:outbound:read', 'inventory:outbound:write',
    'inventory:movement:read', 'inventory:adjust:write', 'inventory:export'
  ])
  const sku = {
    id: 1, sku_no: 'A1', name: '螺丝', warehouse_id: 1, spec: '', unit: '件',
    categories: [], products: [], part_id: null, min_stock: 0, is_active: true,
    quantity: 5, part_name: null
  }
  inv.inventoryWarehouses.mockResolvedValue({ items: [{ id: 1, code: 'WH', name: '默认仓', is_active: true }] })
  inv.inventorySkus.mockResolvedValue({ items: [sku], total: 1 })
  inv.inventoryCategories.mockResolvedValue({ items: [], total: 0 })
  inv.inventorySummary.mockResolvedValue({ sku_count: 1, low_stock_count: 0 })
  // 产品 / 零件引用走库存域端点，仓管没有 product:read / part:read
  inv.inventoryRefProducts.mockResolvedValue([])
  inv.inventoryRefParts.mockResolvedValue([])
  inv.inventoryInboundOrders.mockResolvedValue({ items: [], total: 0 })
  inv.inventoryOutboundOrders.mockResolvedValue({ items: [], total: 0 })
  inv.inventoryMovements.mockResolvedValue({ items: [], total: 0 })
  inv.inventoryExport.mockResolvedValue({ data: new Blob(['x']), headers: {} })
})

describe('进销存 5 个页面冒烟', () => {
  it('SkuList 渲染标题与新建按钮', async () => {
    wrapper = mount(SkuList, { global: { plugins: [ElementPlus] }, attachTo: document.body })
    await flushPromises()
    expect(wrapper.find('.page').exists()).toBe(true)
    expect(wrapper.text()).toContain('物资 SKU')
    expect(wrapper.text()).toContain('新建 SKU')
  })

  it('产品档案为空时提示联系产品计划岗', async () => {
    inv.inventoryRefProducts.mockResolvedValue([])
    wrapper = mount(SkuList, { global: { plugins: [ElementPlus] }, attachTo: document.body })
    await flushPromises()

    const create = wrapper.findAll('button').find((b) => b.text().includes('新建 SKU'))
    await create.trigger('click')
    await flushPromises()

    expect(document.body.textContent).toContain('请联系产品/计划岗')
  })

  it('产品列表加载失败时提示重试，不误报档案为空', async () => {
    inv.inventoryRefProducts.mockRejectedValue(new Error('network'))
    wrapper = mount(SkuList, { global: { plugins: [ElementPlus] }, attachTo: document.body })
    await flushPromises()

    const create = wrapper.findAll('button').find((b) => b.text().includes('新建 SKU'))
    await create.trigger('click')
    await flushPromises()

    expect(document.body.textContent).toContain('产品列表加载失败')
    expect(document.body.textContent).not.toContain('暂无产品档案')
  })

  it('InboundList 渲染标题', async () => {
    wrapper = mount(InboundList, { global: { plugins: [ElementPlus] }, attachTo: document.body })
    await flushPromises()
    expect(wrapper.find('.page').exists()).toBe(true)
    expect(wrapper.text()).toContain('入库单')
    expect(wrapper.text()).toContain('登记入库')
  })

  it('OutboundList 渲染标题', async () => {
    wrapper = mount(OutboundList, { global: { plugins: [ElementPlus] }, attachTo: document.body })
    await flushPromises()
    expect(wrapper.find('.page').exists()).toBe(true)
    expect(wrapper.text()).toContain('出库单')
    expect(wrapper.text()).toContain('登记出库')
  })

  it('MovementList 渲染标题与两个导出按钮', async () => {
    wrapper = mount(MovementList, { global: { plugins: [ElementPlus] }, attachTo: document.body })
    await flushPromises()
    expect(wrapper.find('.page').exists()).toBe(true)
    expect(wrapper.text()).toContain('库存流水')
    expect(wrapper.text()).toContain('导出余额')
    expect(wrapper.text()).toContain('导出流水')
  })

  it('AdjustmentList 渲染标题与登记按钮', async () => {
    wrapper = mount(AdjustmentList, { global: { plugins: [ElementPlus] }, attachTo: document.body })
    await flushPromises()
    expect(wrapper.find('.page').exists()).toBe(true)
    expect(wrapper.text()).toContain('盘点调整')
    expect(wrapper.text()).toContain('登记调整')
  })

  it('CategoryList 渲染标题与新建按钮', async () => {
    wrapper = mount(CategoryList, { global: { plugins: [ElementPlus] }, attachTo: document.body })
    await flushPromises()
    expect(wrapper.find('.page').exists()).toBe(true)
    expect(wrapper.text()).toContain('物资分类')
    expect(wrapper.text()).toContain('新建分类')
    expect(inv.inventoryCategories).toHaveBeenCalled()
  })
})

describe('单据列表筛选', () => {
  // 单据明细里只有 sku_id，产品要靠 SKU 的关联表反查，故参数必须原样传给后端
  it('入库单按产品筛选时把 product_id 带进查询参数', async () => {
    // 直接挂 DocumentList：InboundList 只是包了一层 resource 的壳
    wrapper = mount(DocumentList, {
      props: { resource: 'inbound' },
      global: { plugins: [ElementPlus] },
      attachTo: document.body
    })
    await flushPromises()
    // 产品下拉走库存域引用端点（仓管没有 product:read）
    expect(inv.inventoryRefProducts).toHaveBeenCalled()

    const state = wrapper.vm.$.setupState
    state.filters.product_id = 7
    state.reload()
    await flushPromises()
    expect(inv.inventoryInboundOrders).toHaveBeenCalledWith(
      expect.objectContaining({ product_id: 7 })
    )
  })
})

describe('冲正弹窗：原因必填', () => {
  it('不填原因点确认被校验拦下，填了才调用后端', async () => {
    wrapper = mount(ReverseDialog, {
      props: { modelValue: true, docId: 1, docNo: 'RK20261112-0001' },
      global: { plugins: [ElementPlus] },
      attachTo: document.body
    })
    await flushPromises()

    const confirmBtn = wrapper
      .findAll('button')
      .find((b) => b.text() === '冲正')
    expect(confirmBtn.exists()).toBe(true)

    // 空原因：validate 失败，不应调用后端
    await confirmBtn.trigger('click')
    await flushPromises()
    expect(inv.inventoryReverseDocument).not.toHaveBeenCalled()

    // 输入原因后再提交
    await wrapper.find('textarea').setValue('盘亏登记错误')
    await confirmBtn.trigger('click')
    await flushPromises()
    expect(inv.inventoryReverseDocument).toHaveBeenCalledWith(1, { remark: '盘亏登记错误' })
  })
})

describe('单据弹窗：物资条数多时用分类 / 产品缩范围', () => {
  const skuA = {
    id: 1, sku_no: 'A1', name: '螺丝', spec: '', unit: '件', warehouse_id: 1,
    quantity: 5, is_active: true, categories: [{ id: 3, name: '紧固件' }],
    products: [{ id: 7, name: '植保无人机 16L' }]
  }
  const skuB = {
    id: 2, sku_no: 'B1', name: '喷嘴', spec: '', unit: '件', warehouse_id: 1,
    quantity: 9, is_active: true, categories: [], products: []
  }

  async function mountForm() {
    wrapper = mount(DocumentFormDialog, {
      props: {
        modelValue: false,
        resource: 'inbound',
        warehouses: [{ id: 1, name: '默认仓' }],
        skus: [skuA, skuB],
        categories: [{ id: 3, name: '紧固件' }],
        products: [{ id: 7, name: '植保无人机 16L' }]
      },
      global: { plugins: [ElementPlus] },
      attachTo: document.body
    })
    await flushPromises()
    // 走真实的打开路径：v-model 由 false → true 才会触发 reload
    await wrapper.setProps({ modelValue: true })
    await flushPromises()
    return wrapper.vm.$.setupState
  }

  it('打开即按 is_active 拉一次，选分类 / 产品后带上筛选参数重拉', async () => {
    inv.inventorySkus.mockResolvedValue({ items: [skuA, skuB], total: 2 })
    await mountForm()

    // 父组件只拉了前 100 条，不能拿它当"够不够"的依据，故打开时自己拉一次
    expect(inv.inventorySkus).toHaveBeenCalledWith(
      expect.objectContaining({ is_active: true, page_size: 100 })
    )

    inv.inventorySkus.mockClear()
    inv.inventorySkus.mockResolvedValue({ items: [skuA], total: 1 })
    const bar = wrapper.findComponent(SkuFilterBar)
    // 先写回 v-model，再触发 change——与组件内部 emit 顺序一致
    bar.vm.$emit('update:categoryId', 3)
    await flushPromises()
    bar.vm.$emit('change')
    await flushPromises()
    expect(inv.inventorySkus).toHaveBeenLastCalledWith(
      expect.objectContaining({ category_id: 3 })
    )

    bar.vm.$emit('update:productId', 7)
    await flushPromises()
    bar.vm.$emit('change')
    await flushPromises()
    // 三个条件可叠加，与列表页一致
    expect(inv.inventorySkus).toHaveBeenLastCalledWith(
      expect.objectContaining({ category_id: 3, product_id: 7 })
    )

    // 分类 / 产品只能缩到某一类，某类下就有上百条时还得靠关键词兜底
    bar.vm.$emit('update:keyword', ' 电机 ')
    await flushPromises()
    bar.vm.$emit('change')
    await flushPromises()
    expect(inv.inventorySkus).toHaveBeenLastCalledWith(
      expect.objectContaining({ keyword: '电机', category_id: 3, product_id: 7 })
    )
  })

  it('换筛选后已选中的物资仍留在该行候选里', async () => {
    inv.inventorySkus.mockResolvedValue({ items: [skuA, skuB], total: 2 })
    const state = await mountForm()

    state.form.items[0].sku_id = 1
    await flushPromises()

    // 筛选后只剩 B，但第 1 行选的是 A —— 不兜住就会变成空白框
    inv.inventorySkus.mockResolvedValue({ items: [skuB], total: 1 })
    await state.reloadSkus()
    expect(state.optionsFor(1).map((s) => s.id)).toContain(1)
  })

  it('候选被 page_size 截断时提示用筛选缩小范围', async () => {
    inv.inventorySkus.mockResolvedValue({ items: [skuA], total: 320 })
    await mountForm()
    expect(wrapper.find('.count').text()).toContain('共 320 个物资')
    expect(wrapper.find('.count').text()).toContain('仅列出前 1 个')
  })

  it('改单时已停用的物资仍显示编码与名称', async () => {
    const doc = {
      id: 9,
      doc_type: 'inbound',
      items: [
        { sku_id: 1, sku_no: 'A1', sku_name: '螺丝', quantity: 5, remark: '' },
        { sku_id: 88, sku_no: 'OLD1', sku_name: '停产件', quantity: 2, remark: '' }
      ]
    }
    // 接口返回空 = 停产件不在启用清单里，只能靠明细兜底
    inv.inventorySkus.mockResolvedValue({ items: [], total: 0 })
    wrapper = mount(EditDocumentDialog, {
      props: { modelValue: true, doc, skus: [skuA] },
      global: { plugins: [ElementPlus] },
      attachTo: document.body
    })
    await flushPromises()

    const state = wrapper.vm.$.setupState
    expect(state.optionsFor(88).map((s) => s.id)).toContain(88)
    // 明细补进来的兜底项 quantity 是 0，不能盖掉启用清单里真实的余额
    expect(state.balanceOf(1)).toBe(5)
  })
})

describe('改单弹窗：回填明细并按新数量提交', () => {
  it('预填原明细，保存时走 PUT 且 quantity 为新值', async () => {

    const doc = {
      id: 9,
      doc_type: 'inbound',
      remark: '原备注',
      items: [{ sku_id: 1, sku_no: 'A1', sku_name: '螺丝', quantity: 5, remark: '' }]
    }
    wrapper = mount(EditDocumentDialog, {
      props: {
        modelValue: true,
        doc,
        skus: [{ id: 1, sku_no: 'A1', name: '螺丝', quantity: 100 }]
      },
      global: { plugins: [ElementPlus] },
      attachTo: document.body
    })
    await flushPromises()

    const state = wrapper.vm.$.setupState
    expect(state.form.items).toHaveLength(1)
    expect(state.form.items[0].quantity).toBe(5)

    state.form.items[0].quantity = 7
    await flushPromises()

    const saveBtn = wrapper.findAll('button').find((b) => b.text() === '保存')
    expect(saveBtn.exists()).toBe(true)
    await saveBtn.trigger('click')
    await flushPromises()

    expect(inv.inventoryUpdateDocument).toHaveBeenCalledWith(
      9,
      expect.objectContaining({
        items: [expect.objectContaining({ sku_id: 1, quantity: 7 })]
      })
    )
  })
})
