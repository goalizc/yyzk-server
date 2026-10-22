// FaultEdit.vue：新建默认 3 行步骤、编辑回显与步骤重排、空步骤剔除、切换产品清零件
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createRouter, createMemoryHistory } from 'vue-router'
import FaultEdit from './FaultEdit.vue'
import { setPermissions } from '../../../utils/permissions'

vi.mock('../../../api/admin', () => ({
  adminListProducts: vi.fn(),
  adminListParts: vi.fn(),
  adminGetFault: vi.fn(),
  adminCreateFault: vi.fn(),
  adminUpdateFault: vi.fn(),
  adminUpload: vi.fn()
}))

import {
  adminCreateFault,
  adminGetFault,
  adminListParts,
  adminListProducts,
  adminUpdateFault,
  adminUpload
} from '../../../api/admin'

const PRODUCTS = [{ id: 1, name: '扫地机器人', model: 'X1' }]
const PARTS = [
  { id: 11, name: '电源模组', group_name: '动力系统' },
  { id: 12, name: '主刷模组', group_name: '动力系统' }
]

const DETAIL = {
  id: 21,
  product_id: 1,
  part_id: 12,
  title: '主刷不转',
  symptom: '启动后主刷不转',
  root_cause: '电机损坏',
  // 故意乱序：验证回显按 step 升序
  solution_steps: [
    { step: 2, text: '第二步', image_url: null },
    { step: 1, text: '第一步', image_url: '/uploads/a.jpg' }
  ],
  required_tools: '螺丝刀',
  needs_professional: true,
  attachment_urls: [{ name: '手册.pdf', url: '/uploads/m.pdf', size: 1024 }],
  is_published: false,
  created_by: 1,
  created_at: '2026-10-01T09:00:00+08:00',
  updated_at: '2026-10-05T09:00:00+08:00',
  view_count: 10,
  resolved_count: 3
}

async function mountEdit(path = '/admin/faults/edit') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/admin/faults', name: 'admin-faults', component: { template: '<div />' } },
      { path: '/admin/faults/edit/:id?', name: 'admin-fault-edit', component: FaultEdit }
    ]
  })
  await router.push(path)
  const wrapper = mount(FaultEdit, {
    global: { plugins: [ElementPlus, router] },
    attachTo: document.body
  })
  await flushPromises()
  return { wrapper, router }
}

beforeEach(() => {
  vi.clearAllMocks()
  setPermissions(['fault:read', 'fault:write', 'product:read', 'part:read'])
  adminListProducts.mockResolvedValue({ total: 1, page: 1, page_size: 100, items: PRODUCTS })
  adminListParts.mockResolvedValue({ total: 2, page: 1, page_size: 100, items: PARTS })
  adminGetFault.mockResolvedValue(DETAIL)
  adminCreateFault.mockResolvedValue({})
  adminUpdateFault.mockResolvedValue({})
})

describe('FaultEdit', () => {
  it('新建时默认 3 行解决步骤', async () => {
    const { wrapper } = await mountEdit()
    expect(wrapper.vm.$.setupState.form.solution_steps).toHaveLength(3)
    expect(adminGetFault).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('新增故障')
  })

  it('编辑时回显字段，步骤按 step 升序', async () => {
    const { wrapper } = await mountEdit('/admin/faults/edit/21')
    const state = wrapper.vm.$.setupState

    expect(adminGetFault).toHaveBeenCalledWith('21')
    // 先加载零件再回填 part_id，下拉才能显示名称
    expect(adminListParts).toHaveBeenCalledWith({ product_id: 1, page: 1, page_size: 100 })
    expect(state.form.part_id).toBe(12)
    expect(state.form.solution_steps.map((s) => s.text)).toEqual(['第一步', '第二步'])
    expect(state.form.solution_steps[0].image_url).toBe('/uploads/a.jpg')
    expect(state.form.needs_professional).toBe(true)
    expect(state.form.is_published).toBe(false)
    expect(state.form.attachment_urls).toHaveLength(1)
  })

  it('保存时剔除空步骤并重新编号（step 从 1 连续递增）', async () => {
    const { wrapper } = await mountEdit()
    const state = wrapper.vm.$.setupState
    state.form.product_id = 1
    state.form.part_id = 11
    state.form.title = '新故障'
    // 默认 3 行：第 2 行留空
    state.form.solution_steps[0].text = '断电'
    state.form.solution_steps[2].text = '重启'

    const payload = state.buildPayload()
    expect(payload.solution_steps).toEqual([
      { step: 1, text: '断电', image_url: null },
      { step: 2, text: '重启', image_url: null }
    ])
  })

  it('切换产品清空已选零件（避免 PART_PRODUCT_MISMATCH）', async () => {
    const { wrapper } = await mountEdit('/admin/faults/edit/21')
    const state = wrapper.vm.$.setupState
    expect(state.form.part_id).toBe(12)

    state.onProductChange(1)
    await flushPromises()
    expect(state.form.part_id).toBe(null)
  })

  it('提交成功后跳回列表', async () => {
    const { wrapper, router } = await mountEdit()
    const state = wrapper.vm.$.setupState
    state.form.product_id = 1
    state.form.part_id = 11
    state.form.title = '新故障'
    state.form.solution_steps = []

    await state.onSubmit()
    await flushPromises()

    expect(adminCreateFault).toHaveBeenCalledTimes(1)
    expect(router.currentRoute.value.path).toBe('/admin/faults')
  })

  it('必填缺失时不提交', async () => {
    const { wrapper } = await mountEdit()
    await wrapper.vm.$.setupState.onSubmit()
    await flushPromises()
    expect(adminCreateFault).not.toHaveBeenCalled()
  })

  it('附件 beforeUpload 允许 pdf/mp4，拒绝其它后缀', async () => {
    const { wrapper } = await mountEdit()
    const state = wrapper.vm.$.setupState
    const make = (name, size = 1024) => {
      const f = new File(['x'], name)
      Object.defineProperty(f, 'size', { value: size })
      return f
    }

    expect(state.beforeUploadAttachment(make('手册.pdf'))).toBe(true)
    expect(state.beforeUploadAttachment(make('演示.mp4'))).toBe(true)
    expect(state.beforeUploadAttachment(make('脚本.sh'))).toBe(false)
    await flushPromises()
    expect(document.body.textContent).toContain('仅支持')
    // 超限同样拦在本地，不让用户等上传完才失败
    expect(state.beforeUploadAttachment(make('big.pdf', 20 * 1024 * 1024 + 1))).toBe(false)
  })

  it('附件上传成功后元数据入 attachment_urls，随故障一起提交', async () => {
    adminUpload.mockResolvedValue({ url: '/uploads/2026/10/m.pdf', filename: 'm.pdf', size: 2048 })
    const { wrapper } = await mountEdit()
    const state = wrapper.vm.$.setupState
    const before = state.form.attachment_urls.length

    await state.doUploadAttachment({ file: new File(['x'], 'm.pdf') })
    await flushPromises()

    expect(state.form.attachment_urls).toHaveLength(before + 1)
    // 契约 §4：附件不单独建表，元数据随故障存 attachment_urls
    expect(state.form.attachment_urls.at(-1)).toEqual({
      name: 'm.pdf',
      url: '/uploads/2026/10/m.pdf',
      size: 2048
    })
    expect(state.uploadingAttachment).toBe(false)
  })

  it('附件上传失败不写入列表，并区分超时文案', async () => {
    adminUpload.mockRejectedValue({ code: 'ECONNABORTED' })
    const { wrapper } = await mountEdit()
    const state = wrapper.vm.$.setupState
    const before = state.form.attachment_urls.length

    await state.doUploadAttachment({ file: new File(['x'], 'm.pdf') })
    await flushPromises()

    expect(state.form.attachment_urls).toHaveLength(before)
    expect(document.body.textContent).toContain('上传超时')
    expect(state.uploadingAttachment).toBe(false)
  })

  it('附件 beforeUpload 允许 pdf/mp4，拒绝其它后缀', async () => {
    const { wrapper } = await mountEdit()
    const state = wrapper.vm.$.setupState
    const make = (name, size = 1024) => {
      const f = new File(['x'], name)
      Object.defineProperty(f, 'size', { value: size })
      return f
    }

    expect(state.beforeUploadAttachment(make('手册.pdf'))).toBe(true)
    expect(state.beforeUploadAttachment(make('演示.mp4'))).toBe(true)
    expect(state.beforeUploadAttachment(make('脚本.sh'))).toBe(false)
    await flushPromises()
    expect(document.body.textContent).toContain('仅支持')
    // 超限同样拦在本地，不让用户等上传完才失败
    expect(state.beforeUploadAttachment(make('big.pdf', 20 * 1024 * 1024 + 1))).toBe(false)
  })

  it('附件上传成功后元数据入 attachment_urls，随故障一起提交', async () => {
    adminUpload.mockResolvedValue({ url: '/uploads/2026/10/m.pdf', filename: 'm.pdf', size: 2048 })
    const { wrapper } = await mountEdit()
    const state = wrapper.vm.$.setupState
    const before = state.form.attachment_urls.length

    await state.doUploadAttachment({ file: new File(['x'], 'm.pdf') })
    await flushPromises()

    expect(state.form.attachment_urls).toHaveLength(before + 1)
    // 契约 §4：附件不单独建表，元数据随故障存 attachment_urls
    expect(state.form.attachment_urls.at(-1)).toEqual({
      name: 'm.pdf',
      url: '/uploads/2026/10/m.pdf',
      size: 2048
    })
    expect(state.uploadingAttachment).toBe(false)
  })

  it('附件上传失败不写入列表，并区分超时文案', async () => {
    adminUpload.mockRejectedValue({ code: 'ECONNABORTED' })
    const { wrapper } = await mountEdit()
    const state = wrapper.vm.$.setupState
    const before = state.form.attachment_urls.length

    await state.doUploadAttachment({ file: new File(['x'], 'm.pdf') })
    await flushPromises()

    expect(state.form.attachment_urls).toHaveLength(before)
    expect(document.body.textContent).toContain('上传超时')
    expect(state.uploadingAttachment).toBe(false)
  })
})
