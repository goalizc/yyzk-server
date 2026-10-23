// DetailPanel.vue：详情面板容器的形态约定
//
// 这里只测「容器该保证什么」，不测业务内容——业务组件各自有自己的 spec。
// 形态（居中弹窗）是这次改动的核心，所以宽度、居中、footer 条件渲染都要锁住。
//
// 注意：el-dialog 的 rendered 在 onMounted 里置 true，触发的是下一个 tick 的重渲染，
// 所以每个用例都必须 await 一次 flushPromises 才能查到 DOM。
import { afterEach, describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import DetailPanel from './DetailPanel.vue'

const mounted = []

async function mountPanel(props = {}, slots = {}) {
  const wrapper = mount(DetailPanel, {
    props: { modelValue: true, title: '工单详情', ...props },
    slots: { default: '<p class="probe">内容</p>', ...slots },
    global: { plugins: [ElementPlus] },
    attachTo: document.body
  })
  mounted.push(wrapper)
  await flushPromises()
  return wrapper
}

afterEach(() => {
  while (mounted.length) mounted.pop().unmount()
  document.body.innerHTML = ''
})

describe('DetailPanel', () => {
  it('渲染为居中弹窗而不是右侧抽屉', async () => {
    const wrapper = await mountPanel()
    // 容器形态变了要在这里失败：抽屉是 .el-drawer，弹窗是 .el-dialog
    expect(document.querySelector('.el-drawer')).toBeNull()
    expect(document.querySelector('.el-dialog')).not.toBeNull()
    // 容器类名落在 .el-dialog 上，E2E 靠它定位（.detail-panel）
    expect(document.querySelector('.el-dialog.detail-panel')).not.toBeNull()
    expect(wrapper.text()).toContain('内容')
  })

  it('宽度用 min(size, 92vw)，窄屏自动收缩且不需要监听 resize', async () => {
    await mountPanel({ size: 880 })
    const dialog = document.querySelector('.el-dialog')
    // Element Plus 把宽度挂在 CSS 变量上（--el-dialog-width），不是 inline width
    expect(dialog.style.getPropertyValue('--el-dialog-width')).toBe('min(880px, 92vw)')
  })

  it('size 可覆盖默认宽度', async () => {
    await mountPanel({ size: 820 })
    const dialog = document.querySelector('.el-dialog')
    expect(dialog.style.getPropertyValue('--el-dialog-width')).toBe('min(820px, 92vw)')
  })

  it('没有 footer 插槽时不渲染底部栏（不留一条空白）', async () => {
    await mountPanel()
    expect(document.querySelector('.el-dialog__footer')).toBeNull()
  })

  it('传了 footer 插槽才渲染底部栏', async () => {
    await mountPanel({}, { footer: '<button class="probe-btn">保存</button>' })
    expect(document.querySelector('.el-dialog__footer')).not.toBeNull()
    expect(document.querySelector('.probe-btn')).not.toBeNull()
  })

  it('把 el-dialog 的关闭事件转发给父组件', async () => {
    const wrapper = await mountPanel()
    // Element Plus 自己的关闭按钮时序不在本组件职责内，这里只锁「转发」这一层
    wrapper.findComponent({ name: 'ElDialog' }).vm.$emit('update:modelValue', false)
    await flushPromises()
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([false])
  })

  it('默认不允许点遮罩关闭（详情里常有未保存的表单）', async () => {
    const wrapper = await mountPanel()
    expect(wrapper.findComponent({ name: 'ElDialog' }).props('closeOnClickModal')).toBe(false)
  })

  it('需要时可以把 closeOnClickModal 放开', async () => {
    const wrapper = await mountPanel({ closeOnClickModal: true })
    expect(wrapper.findComponent({ name: 'ElDialog' }).props('closeOnClickModal')).toBe(true)
  })
})
