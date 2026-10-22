export const PERMISSION_LABELS = {
  'ticket:read': '查看工单', 'ticket:write': '处理工单', 'ticket:assign': '改派工单',
  'product:read': '查看产品', 'product:write': '维护产品',
  'part:read': '查看零件', 'part:write': '维护零件',
  'fault:read': '查看知识库', 'fault:write': '维护知识库',
  'upload:write': '上传附件', 'stats:read': '查看数据看板',
  'user:read': '查看用户', 'user:write': '维护用户',
  'product_line:read': '查看产品线', 'product_line:write': '维护产品线'
}

export function permissionLabel(code) {
  return PERMISSION_LABELS[code] || code
}
