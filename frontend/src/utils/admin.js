// 后台页面共用的常量与小工具（各页面不重复写一份）
import { i18n } from '../locales'

/**
 * 工单状态：文案 key + 标签色（契约 §5）。
 *
 * 存 key 而不是文案：这份表被列表、详情、看板、客户侧工单页共用，
 * 存中文的话切语言时每个调用点都要自己翻译一遍。
 * 取文案统一走 ticketStatusLabel()。
 */
export const TICKET_STATUS = {
  open: { labelKey: 'common.status.open', type: 'warning' },
  processing: { labelKey: 'common.status.processing', type: 'primary' },
  resolved: { labelKey: 'common.status.resolved', type: 'success' },
  closed: { labelKey: 'common.status.closed', type: 'info' }
}

/** 状态流转约束（契约 §5）：值 = 允许流转到的目标状态 */
export const TICKET_TRANSITIONS = {
  open: ['processing', 'closed'],
  processing: ['resolved', 'closed'],
  resolved: ['closed'],
  closed: []
}

export function ticketStatusLabel(value) {
  const item = TICKET_STATUS[value]
  // 未知状态（后端新增）直接显示原值，不要显示空白
  return item ? i18n.global.t(item.labelKey) : value || '-'
}

export function ticketStatusType(value) {
  return TICKET_STATUS[value]?.type || 'info'
}


export function errorCode(error) {
  return error?.response?.data?.code || ''
}

