// 用户管理（P-18）与临时授权
export default {
  list: {
    searchPlaceholder: '搜索账号或姓名',
    allRoles: '全部角色',
    allStatuses: '全部状态',
    enabled: '启用',
    disabled: '停用',
    newUser: '新建用户',
    colUser: '账号 / 姓名',
    colRole: '角色',
    activeGrants: '临时授权 {count}',
    colLines: '产品线',
    noLines: '未分配',
    colStatus: '状态',
    colLastLogin: '最近登录',
    neverLoggedIn: '从未登录',
    colActions: '操作',
    resetPassword: '重置密码',
    grant: '临时授权',
    loadFailed: '用户列表加载失败',
    temporary: '（临时）'
  },

  form: {
    createTitle: '新建用户',
    editTitle: '编辑用户',
    username: '账号',
    realName: '姓名',
    password: '初始密码',
    confirmPassword: '确认密码',
    role: '角色',
    productLines: '产品线',
    addLine: '添加产品线',
    selectLine: '选择产品线',
    lineInactive: '{name}（已停用）',
    longTerm: '长期（留空）',
    renameHint: '改名后请使用新账号登录',
    ruleUsername: '请输入账号',
    ruleRealName: '请输入姓名',
    rulePassword: '请输入初始密码',
    rulePasswordMin: '密码至少 8 位',
    ruleConfirmRequired: '请再次输入初始密码',
    ruleConfirmMismatch: '两次输入的密码不一致',
    ruleRole: '请选择角色',
    saved: '已保存',
    usernameDuplicated: '账号已存在'
  },

  toggle: {
    disableConfirm: '停用后该账号将立即无法登录，确认停用「{name}」？',
    disableTitle: '停用确认',
    confirmDisable: '确认停用',
    enabled: '已启用',
    disabled: '已停用',
    failed: '状态更新失败'
  },

  role: {
    changeTitle: '角色变更确认',
    changeConfirm: '将「{name}」的角色从「{from}」改为「{to}」？其权限会立即变化。',
    confirmChange: '确认变更'
  },

  reset: {
    confirm: '确认重置「{name}」的密码？',
    title: '重置密码',
    doneTitle: '密码已重置',
    alert: '请立即复制并通过安全渠道交给本人，关闭后无法再次查看',
    copyFailedLong: '复制失败，请手动选中密码复制',
    failed: '重置失败'
  },

  grant: {
    title: '临时授权 — {name}',
    colPermission: '权限',
    colReason: '事由',
    colGrantedBy: '授予人',
    colExpiresAt: '到期',
    colStatus: '状态',
    colActions: '操作',
    active: '生效',
    inactive: '失效',
    revoke: '收回',
    issueTitle: '发放新授权',
    permission: '权限',
    expiresAt: '到期',
    reason: '事由',
    issue: '发放',
    issued: '已发放',
    revoked: '已收回',
    revokeFailed: '收回失败',
    loadFailed: '授权记录加载失败',
    grantedBySystem: '系统',
    copy: '复制',
    copied: '已复制',
    rulePermission: '请选择权限',
    ruleExpiresAt: '请选择到期时间',
    ruleReason: '请填写事由'
  }
}
