// ImageUpload.vue：beforeUpload 接线（后缀优先于大小）、成功才写回 url、超时与拒绝的文案区分
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import ImageUpload from './ImageUpload.vue'

vi.mock('../api/admin', () => ({ adminUpload: vi.fn() }))

import { adminUpload } from '../api/admin'

function makeFile(name, size = 1024) {
  const file = new File(['x'], name, { type: 'image/jpeg' })
  // happy-dom 下 File.size 只读，用 defineProperty 造不同体积
  Object.defineProperty(file, 'size', { value: size })
  return file
}

function mountUpload(modelValue = null) {
  return mount(ImageUpload, {
    props: { modelValue },
    global: { plugins: [ElementPlus] },
    attachTo: document.body
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  document.body.innerHTML = ''
})

describe('ImageUpload', () => {
  it('beforeUpload 拒绝非图片后缀（走 utils/upload 的白名单镜像）', async () => {
    const wrapper = mountUpload()
    const state = wrapper.vm.$.setupState

    expect(state.beforeUpload(makeFile('说明.pdf'))).toBe(false)
    await flushPromises()
    expect(document.body.textContent).toContain('仅支持 jpg / jpeg / png 格式')
  })

  it('beforeUpload 拒绝超过 20MB 的图片', async () => {
    const wrapper = mountUpload()
    const state = wrapper.vm.$.setupState

    expect(state.beforeUpload(makeFile('big.jpg', 20 * 1024 * 1024 + 1))).toBe(false)
    await flushPromises()
    expect(document.body.textContent).toContain('20MB')
  })

  it('后缀合法且体积合规时放行', () => {
    const wrapper = mountUpload()
    const state = wrapper.vm.$.setupState
    expect(state.beforeUpload(makeFile('ok.png'))).toBe(true)
  })

  it('上传成功才把 url 写回父组件', async () => {
    adminUpload.mockResolvedValue({ url: '/uploads/2026/10/a.png' })
    const wrapper = mountUpload()

    await wrapper.vm.$.setupState.doUpload({ file: makeFile('a.png') })
    await flushPromises()

    expect(adminUpload).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['/uploads/2026/10/a.png'])
  })

  it('上传失败不写回，保持原值', async () => {
    adminUpload.mockRejectedValue({
      response: { data: { detail: '文件类型不支持', code: 'UPLOAD_TYPE_INVALID' } }
    })
    const wrapper = mountUpload('/uploads/old.png')

    await wrapper.vm.$.setupState.doUpload({ file: makeFile('a.png') })
    await flushPromises()

    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    expect(document.body.textContent).toContain('文件类型不支持')
    // loading 必须复位，否则按钮会一直转圈
    expect(wrapper.vm.$.setupState.uploading).toBe(false)
  })

  it('超时与超限的提示文案分开，不笼统说"上传失败"', async () => {
    const wrapper = mountUpload()
    const state = wrapper.vm.$.setupState

    adminUpload.mockRejectedValue({ code: 'ECONNABORTED' })
    await state.doUpload({ file: makeFile('a.png') })
    await flushPromises()
    expect(document.body.textContent).toContain('上传超时')

    adminUpload.mockRejectedValue({
      response: { data: { detail: 'too large', code: 'UPLOAD_TOO_LARGE' } }
    })
    await state.doUpload({ file: makeFile('b.png') })
    await flushPromises()
    expect(document.body.textContent).toContain('20MB')
  })

  it('存储不可写（503）时给出可行动文案，而不是笼统的"上传失败"', async () => {
    // 真实故障：上传目录属主不对，后端返回 503 SERVICE_UNAVAILABLE。
    // 改造前报 500，前端只显示"服务器内部错误"，用户和运维都不知道该做什么。
    adminUpload.mockRejectedValue({
      response: {
        status: 503,
        data: { detail: '服务器暂时无法保存文件，请联系管理员', code: 'SERVICE_UNAVAILABLE' }
      }
    })
    const wrapper = mountUpload()

    await wrapper.vm.$.setupState.doUpload({ file: makeFile('a.png') })
    await flushPromises()

    const text = document.body.textContent
    expect(text).toContain('无法保存文件')
    expect(text).toContain('联系管理员')
    // 不能退化成没有信息量的通用文案
    expect(text).not.toContain('服务器内部错误')
  })

  it('移除按钮清空 url', async () => {
    const wrapper = mountUpload('/uploads/old.png')
    const removeBtn = wrapper.findAll('button').find((b) => b.text().includes('移除'))
    await removeBtn.trigger('click')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([null])
  })
})
