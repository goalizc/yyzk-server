// 时间与百分比统一格式化（页面不各写一套）

const DATE_TIME = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false
})

const DATE_ONLY = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit'
})

/** ISO 字符串 → 2026/10/20 14:05（固定按 Asia/Shanghai 展示） */
export function formatDateTime(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return DATE_TIME.format(date).replace(/\//g, '-')
}

export function formatDate(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return DATE_ONLY.format(date).replace(/\//g, '-')
}

/** 0.667 → 66.7% */
export function formatPercent(value, digits = 1) {
  if (value === null || value === undefined) return '-'
  return `${(Number(value) * 100).toFixed(digits)}%`
}

/** 大数字加千分位 */
export function formatNumber(value) {
  if (value === null || value === undefined) return '-'
  return Number(value).toLocaleString('zh-CN')
}
