import { computed } from 'vue'
import { currentLocale } from '../locales'

/**
 * 表单标签宽度：按语言给两套值。
 *
 * 中文标签普遍 3–5 个字（「需专业人员」82px），英文是同义短语，长 1.5–2 倍
 * （"Requires a professional" 159px）。沿用中文时代的固定宽度，英文会折行或截断。
 *
 * 为什么不用 `label-width="auto"`：实测它让每个 label 各自等于内容宽度
 * （Product 70px / Part 47px / Requires a professional 159px），
 * **同一表单里标签不再对齐**，值的起始位置参差，比折行更难读。
 * 英文宽度建议按该表单最长标签实测 + 10px 预留。
 */
export function useFormLabelWidth(zhWidth, enWidth) {
  return computed(() => (currentLocale() === 'en-US' ? enWidth : zhWidth))
}
