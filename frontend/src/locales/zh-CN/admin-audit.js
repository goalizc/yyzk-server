export default {
  title: '操作日志',
  intro: '记录谁在什么时候做了什么。排查问题时按账号或对象查，追责时按人或 IP 查。',

  filter: {
    username: '账号',
    usernamePlaceholder: '输入账号名，支持模糊匹配',
    action: '动作',
    actionAll: '全部动作',
    result: '结果',
    resultAll: '全部结果',
    dateRange: '时间范围',
    startDate: '开始日期',
    endDate: '结束日期',
    keyword: '关键词',
    keywordPlaceholder: '对象名称 / 请求路径 / 账号',
    search: '查询',
    reset: '重置',
    export: '导出 CSV'
  },

  summary: {
    title: '近 {days} 天',
    total: '共 {count} 次操作',
    failures: '失败 {count} 次',
    actors: '涉及 {count} 个账号',
    topActor: '操作最多',
    multiIp: '{count} 个 IP',
    multiIpHint: '同一账号从多个 IP 操作，值得留意'
  },

  col: {
    time: '时间',
    username: '账号',
    action: '动作',
    target: '操作对象',
    result: '结果',
    ip: '来源 IP',
    status: '状态码'
  },

  result: {
    success: '成功',
    failure: '失败'
  },

  action: {
    authLogin: '登录',
    authPasswordChange: '修改自己的密码',
    ticketCreate: '客户提交工单',
    ticketUpdate: '处理工单',
    productCreate: '新建产品',
    productUpdate: '修改产品',
    productDelete: '删除产品',
    partCreate: '新建零件',
    partUpdate: '修改零件',
    partDelete: '删除零件',
    productLineCreate: '新建产品线',
    productLineUpdate: '修改产品线',
    productLineDelete: '删除产品线',
    faultCreate: '新建故障方案',
    faultUpdate: '修改故障方案',
    faultDelete: '删除故障方案',
    userCreate: '新建账号',
    userUpdate: '修改账号',
    userResetPassword: '重置密码',
    userGrant: '发放临时授权',
    userRevokeGrant: '收回临时授权',
    userSetProductLines: '调整数据范围',
    auditExport: '导出审计日志',
    uploadCreate: '上传文件',
    uploadDelete: '删除上传文件',
    unknown: '其他操作'
  },

  detail: {
    title: '操作详情',
    basic: '基本信息',
    time: '时间',
    username: '操作人',
    action: '动作',
    target: '操作对象',
    targetNone: '无具体对象',
    result: '结果',
    ip: '来源 IP',
    path: '请求路径',
    status: '状态码',
    requestId: '请求 ID',
    userAgent: '浏览器',
    errorCode: '错误码',
    extra: '附加信息',
    empty: '无附加信息'
  },

  field: {
    reason: '原因',
    identityVerified: '账号名已验证',
    errorClass: '异常类型',
    titleFrom: '原标题',
    titleTo: '新标题',
    fromStatus: '原状态',
    toStatus: '新状态',
    assigneeFrom: '原处理人',
    assigneeTo: '新处理人',
    remarkUpdated: '备注已更新',
    role: '角色',
    roleFrom: '原角色',
    roleTo: '新角色',
    isActiveFrom: '原状态',
    isActiveTo: '新状态',
    usernameChanged: '改了用户名',
    permission: '权限',
    expiresAt: '有效期至',
    grantId: '授权 ID',
    lineId: '产品线 ID',
    productId: '产品 ID',
    lineCount: '产品线数量',
    query: '查询参数',
    errorCode: '错误码'
  },

  verified: {
    yes: '已验证',
    no: '未验证（来自输入）'
  },

  reason: {
    success: '登录成功',
    wrongPassword: '密码错误',
    userNotFound: '账号不存在',
    disabled: '账号已停用',
    adminReset: '管理员重置',
    selfChange: '本人修改'
  },

  status: {
    open: '待处理',
    processing: '处理中',
    resolved: '已解决',
    closed: '已关闭'
  },

  anonymous: '匿名',
  empty: '没有符合条件的记录',
  total: '共 {count} 条',
  loadFailed: '操作日志加载失败',
  exportFailed: '导出失败'
}
