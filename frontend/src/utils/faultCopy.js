import { i18n, localeHref } from '../locales'

/**
 * 生成「复制方案文本」的内容。
 *
 * 模板必须跟界面语言一致：英文客服复制给英文客户，拿到中文模板会很割裂。
 * 注意这里用的是消息模板（含 {title} 等占位符），不要改回字符串拼接。
 */
export function buildFaultCopyText(fault, origin = window.location.origin) {
  const { t } = i18n.global
  const lines = []

  if (fault.needs_professional) {
    lines.push(t('fault.copy.warning'))
  }

  lines.push(t('fault.copy.title', { title: fault.title }))
  lines.push(
    t('fault.copy.meta', {
      product: fault.product_name || '—',
      part: fault.part_name || '—'
    })
  )

  if (fault.symptom) lines.push('', t('fault.copy.symptom', { text: fault.symptom }))
  if (fault.root_cause) lines.push(t('fault.copy.rootCause', { text: fault.root_cause }))
  if (fault.required_tools) lines.push(t('fault.copy.tools', { text: fault.required_tools }))

  const steps = [...(fault.solution_steps || [])].sort((a, b) => a.step - b.step)
  if (steps.length) {
    lines.push('', t('fault.copy.steps'))
    for (const step of steps) {
      lines.push(`${step.step}. ${step.text}`)
      if (step.image_url) lines.push(t('fault.copy.imageMarker'))
    }
  }

  lines.push('')
  if (fault.is_published) {
    // 链接必须带语言前缀：英文界面复制出去的文本是给英文客户看的，
    // 若拼成 /faults/9，客户点开是中文页（审查发现，见 18-国际化全量审查）
    lines.push(t('fault.copy.link', { url: `${origin}${localeHref(`/faults/${fault.id}`)}` }))
  } else {
    lines.push(t('fault.copy.notPublished'))
  }

  return lines.join('\n')
}
