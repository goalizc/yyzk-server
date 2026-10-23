import { afterEach, describe, expect, it } from 'vitest'
import { setLocale } from '../locales'
import { buildFaultCopyText } from './faultCopy'

const ORIGIN = 'http://192.168.1.2'

const BASE = {
  id: 123,
  title: '开机无反应',
  product_name: '扫地机器人 X1',
  part_name: '电池组',
  symptom: '插电后指示灯不亮',
  root_cause: '电池过放保护',
  required_tools: '十字螺丝刀',
  needs_professional: false,
  is_published: true,
  solution_steps: [
    { step: 2, text: '长按电源键 10 秒', image_url: '/uploads/a.jpg' },
    { step: 1, text: '检查电源适配器指示灯', image_url: null }
  ]
}

describe('buildFaultCopyText', () => {
  it('已发布方案包含文字、图片标注与客户页链接', () => {
    const text = buildFaultCopyText(BASE, ORIGIN)

    expect(text).toContain('【开机无反应】')
    expect(text).toContain('产品：扫地机器人 X1 / 电池组')
    expect(text).toContain('1. 检查电源适配器指示灯')
    expect(text).toContain('2. 长按电源键 10 秒')
    expect(text).toContain('[含示意图]')
    expect(text).toContain(`完整图文方案：${ORIGIN}/faults/123`)
  })

  it('未发布方案不附链接', () => {
    const text = buildFaultCopyText({ ...BASE, is_published: false }, ORIGIN)

    expect(text).not.toContain('完整图文方案')
    expect(text).toContain('该方案尚未发布')
  })

  it('需专业处理时加警示', () => {
    const text = buildFaultCopyText({ ...BASE, needs_professional: true }, ORIGIN)

    expect(text).toContain('该故障建议由专业人员处理')
  })

  it('空字段整行省略', () => {
    const text = buildFaultCopyText(
      { ...BASE, root_cause: null, required_tools: null },
      ORIGIN
    )

    expect(text).not.toContain('可能原因')
    expect(text).not.toContain('所需工具')
  })
})

// 英文模板此前一条用例都没有：词汇对不上、占位符漏了都不会被发现。
// 复制方案文本是英文客服每天要用的动作，必须有覆盖。
describe('buildFaultCopyText（英文）', () => {
  afterEach(() => setLocale('zh-CN'))

  it('模板与图片标注走英文，正文仍是业务数据（不翻译）', () => {
    setLocale('en-US')
    const text = buildFaultCopyText({ ...BASE, needs_professional: true }, ORIGIN)

    expect(text).toContain('should be handled by a professional')
    expect(text).toContain('[开机无反应]')
    expect(text).toContain('Product: 扫地机器人 X1 / 电池组')
    expect(text).toContain('Steps:')
    expect(text).toContain('[with illustration]')
    // 业务数据是运营录入的内容，英文界面下仍是中文（范围决策，不是缺陷）
    expect(text).toContain('1. 检查电源适配器指示灯')
  })

  it('链接必须带 /en 前缀：英文客服复制给英文客户，点开不能是中文页', () => {
    setLocale('en-US')
    const text = buildFaultCopyText(BASE, ORIGIN)

    expect(text).toContain(`${ORIGIN}/en/faults/123`)
    expect(text).not.toContain(`${ORIGIN}/faults/123`)
  })

  it('中文环境的链接不带前缀，且与改造前一致', () => {
    setLocale('zh-CN')
    const text = buildFaultCopyText(BASE, ORIGIN)

    expect(text).toContain(`完整图文方案：${ORIGIN}/faults/123`)
  })
})
