/**
 * 后端错误码 → 文案。key 就是契约里登记的机器码。
 *
 * 两条规则（见 国际化设计 §4.4）：
 *   1. **一码一义**的码在这里给标准文案，前端按 code 直接取。
 *   2. **一码多义 / 动态参数**的码（NOT_FOUND、DELETE_BLOCKED、TICKET_STATUS_INVALID、
 *      VALIDATION_ERROR）服务端 detail 更精确。它们也列在 DETAIL_FIRST 里：
 *      中文环境用服务端原文（保持现有提示不变），其它语言用这里的通用文案。
 *
 * 新增错误码时：先加进 API 契约 §7，再补本文件 + en-US/error.js。
 * `src/locales/locale.spec.js` 会扫描后端的 BusinessError 码与这里比对，漏一个就红。
 */
export default {
  ASSIGNEE_DISABLED: '该账号已停用，不能作为处理人',
  ASSIGNEE_NO_PERMISSION: '该账号没有处理工单的权限',
  ASSIGNEE_OUT_OF_SCOPE: '该账号看不到此工单所属产品线',
  AUTH_INVALID_CREDENTIALS: '用户名或密码错误',
  AUTH_TOKEN_EXPIRED: '登录已过期，请重新登录',
  AUTH_USER_DISABLED: '账号已停用',
  DELETE_BLOCKED: '仍被其它数据引用，请先处理关联数据',
  INTERNAL_ERROR: '服务器内部错误，请稍后重试',
  INVALID_PERMISSION: '该权限不可临时授予',
  LAST_SUPER_ADMIN: '系统至少需要保留一个在用超级管理员',
  LINE_DUPLICATED: '同一产品线不能重复授权',
  LINE_INACTIVE: '产品线已停用，不能新授权',
  LINE_NAME_DUPLICATED: '产品线 {name} 已存在',
  METHOD_NOT_ALLOWED: '接口不支持该请求方法',
  MODEL_DUPLICATED: '型号 {model} 已存在',
  NOT_FOUND: '请求的数据不存在或已被删除',
  PART_PRODUCT_MISMATCH: '零件不属于所选产品',
  PASSWORD_INVALID: '原密码不正确',
  PASSWORD_SAME: '新密码不能与原密码相同',
  PERMISSION_DENIED: '无权限执行此操作',
  QUERY_LOG_MISMATCH: '反馈的日志与故障不匹配',
  RATE_LIMITED: '操作过于频繁，请稍后再试',
  SELF_DISABLE: '不能停用自己',
  SELF_ROLE_CHANGE: '不能修改自己的角色',
  SERVICE_UNAVAILABLE: '服务暂时不可用，请稍后重试',
  TICKET_STATUS_INVALID: '该状态流转不被允许',
  UPLOAD_IN_USE: '该文件正在被方案引用，请先移除引用',
  UPLOAD_TOO_LARGE: '文件超过 20MB 限制',
  UPLOAD_TYPE_NOT_ALLOWED: '不支持的文件类型',
  USERNAME_DUPLICATED: '账号已存在',
  USER_DISABLED: '账号已停用，不能发放临时授权',
  VALIDATION_ERROR: '提交的内容有误，请检查后重试'
}
