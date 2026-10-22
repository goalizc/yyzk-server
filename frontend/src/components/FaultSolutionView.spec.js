import { describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import FaultSolutionView from './FaultSolutionView.vue'

const FAULT = {
  id: 21,
  title: '主刷不转',
  product_name: '扫地机器人',
  part_name: '主刷模组',
  symptom: '启动后主刷不转',
  root_cause: '主刷被毛发缠绕',
  required_tools: '十字螺丝刀',
  needs_professional: false,
  is_published: true,
  solution_steps: [
    { step: 1, text: '关闭电源', image_url: null },
    { step: 2, text: '拆下主刷', image_url: '/uploads/a.jpg' }
  ],
  attachment_urls: [{ name: '说明书.pdf', url: '/uploads/b.pdf', size: 2048 }],
  view_count: 30,
  resolved_count: 20
}

function mountView(props = {}) {
  return mount(FaultSolutionView, {
    props: { fault: FAULT, ...props },
    global: { plugins: [ElementPlus] }
  })
}

describe('FaultSolutionView', () => {
  it('渲染标题、描述、步骤、图片与附件', async () => {
    const wrapper = mountView()
    await nextTick() // el-image 在 mounted 后才写入 src

    expect(wrapper.text()).toContain('主刷不转')
    expect(wrapper.text()).toContain('主刷被毛发缠绕')
    expect(wrapper.text()).toContain('拆下主刷')
    expect(wrapper.find('img').attributes('src')).toContain('/uploads/a.jpg')
    expect(wrapper.text()).toContain('说明书.pdf')
  })

  it('showStats 控制查看/解决次数', () => {
    expect(mountView({ showStats: true }).text()).toContain('30 人看过')
    expect(mountView().text()).not.toContain('人看过')
  })

  it('showStatus 控制发布与需专业标签', () => {
    const published = mountView({ showStatus: true })
    expect(published.text()).toContain('已发布')

    const unpublished = mountView({
      showStatus: true,
      fault: { ...FAULT, is_published: false, needs_professional: true }
    })
    expect(unpublished.text()).toContain('未发布')
    expect(unpublished.text()).toContain('需专业')
  })
})
