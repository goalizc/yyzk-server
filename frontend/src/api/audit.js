import request from './request'

/** 操作日志列表（筛选参数见后端契约 §6） */
export function adminListAuditLogs(params) {
  return request.get('/admin/audit-logs', { params })
}

export function adminGetAuditLog(id) {
  return request.get(`/admin/audit-logs/${id}`)
}

/** 可选动作清单：与后端规则表同源，前端不维护第二份 */
export function adminAuditActions() {
  return request.get('/admin/audit-logs/actions')
}

/** 近 N 天按人聚合 */
export function adminAuditSummary(params) {
  return request.get('/admin/audit-logs/summary', { params })
}

/** 按当前筛选导出 CSV（后端带 BOM，Excel 直接打开不乱码） */
export function adminExportAuditLogs(params) {
  return request.get('/admin/audit-logs/export', { params, responseType: 'blob' })
}
