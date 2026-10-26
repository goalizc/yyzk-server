import { i18n } from '../locales'

/**
 * 权限码 → 文案 key。
 *
 * 存 key 而不是文案：这份表同时用于授权的下拉选项和授权记录表格，
 * 切语言时两处要一起变；存中文的话每个调用点都得自己翻译。
 */
export const PERMISSION_LABEL_KEYS = {
  'ticket:read': 'permission.ticketRead',
  'ticket:write': 'permission.ticketWrite',
  'ticket:assign': 'permission.ticketAssign',
  'product:read': 'permission.productRead',
  'product:write': 'permission.productWrite',
  'part:read': 'permission.partRead',
  'part:write': 'permission.partWrite',
  'fault:read': 'permission.faultRead',
  'fault:write': 'permission.faultWrite',
  'upload:write': 'permission.uploadWrite',
  'stats:read': 'permission.statsRead',
  'user:read': 'permission.userRead',
  'user:write': 'permission.userWrite',
  'product_line:read': 'permission.productLineRead',
  'product_line:write': 'permission.productLineWrite',
  'audit:read': 'permission.auditRead'
}

export function permissionLabel(code) {
  const key = PERMISSION_LABEL_KEYS[code]
  // 未登记的权限码直接显示原码：比显示空白更容易排查
  return key ? i18n.global.t(key) : code
}
