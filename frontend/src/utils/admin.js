// 后台页面共用的常量与小工具（各页面不重复写一份）

/** 工单状态：文案 + 标签色（契约 §5） */
export const TICKET_STATUS = {
  open: { label: '待处理', type: 'warning' },
  processing: { label: '处理中', type: 'primary' },
  resolved: { label: '已解决', type: 'success' },
  closed: { label: '已关闭', type: 'info' }
}

/** 状态流转约束（契约 §5）：值 = 允许流转到的目标状态 */
export const TICKET_TRANSITIONS = {
  open: ['processing', 'closed'],
  processing: ['resolved', 'closed'],
  resolved: ['closed'],
  closed: []
}

export function ticketStatusLabel(value) {
  return TICKET_STATUS[value]?.label || value || '-'
}

export function ticketStatusType(value) {
  return TICKET_STATUS[value]?.type || 'info'
}

/**
 * 从 axios 错误里取后端 detail（中文可读，可直接展示）。
 * 网络层失败没有 response，给一句兜底文案而不是 "Request failed with status code 500"。
 */
export function errorText(error, fallback = '操作失败，请稍后重试') {
  return error?.response?.data?.detail || fallback
}

export function errorCode(error) {
  return error?.response?.data?.code || ''
}

