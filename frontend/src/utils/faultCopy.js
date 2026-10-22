const PROFESSIONAL_WARNING = '⚠️ 该故障建议由专业人员处理，请勿自行拆机'

export function buildFaultCopyText(fault, origin = window.location.origin) {
  const lines = []

  if (fault.needs_professional) {
    lines.push(PROFESSIONAL_WARNING)
  }

  lines.push(`【${fault.title}】`)
  lines.push(`产品：${fault.product_name || '—'} / ${fault.part_name || '—'}`)

  if (fault.symptom) lines.push('', `现象：${fault.symptom}`)
  if (fault.root_cause) lines.push(`可能原因：${fault.root_cause}`)
  if (fault.required_tools) lines.push(`所需工具：${fault.required_tools}`)

  const steps = [...(fault.solution_steps || [])].sort((a, b) => a.step - b.step)
  if (steps.length) {
    lines.push('', '处理步骤：')
    for (const step of steps) {
      lines.push(`${step.step}. ${step.text}`)
      if (step.image_url) lines.push('   [含示意图]')
    }
  }

  lines.push('')
  if (fault.is_published) {
    lines.push(`完整图文方案：${origin}/faults/${fault.id}`)
  } else {
    lines.push('（该方案尚未发布，配图请在系统内查看）')
  }

  return lines.join('\n')
}
