// 后台角色：英文键 ↔ 中文名
//
// **key 必须与后端 `user_roles.role` 的取值逐字一致**（`ROLE_VALUES` /
// `user_roles.role` CHECK 白名单，均为 snake_case）。这些 key 同时被当作
// POST/PUT /api/admin/users 的 `roles` 数组元素提交，写成驼峰会导致：
//   ① 查不到中文名，界面把 warehouse_clerk 原样显示给用户；
//   ② 建号 / 改角色被后端校验拒掉（422 VALIDATION_ERROR）。
//
// value 用字面量而不是 `common.role.${role}` 拼接：check_i18n.py 与键完整性
// 检查都依赖字面量才能扫到。
export const ROLE_KEYS = {
  super_admin: 'common.role.super_admin',
  supervisor: 'common.role.supervisor',
  product_planner: 'common.role.product_planner',
  warehouse_clerk: 'common.role.warehouse_clerk',
  warehouse_manager: 'common.role.warehouse_manager',
  agent: 'common.role.agent',
  auditor: 'common.role.auditor'
}

export const ROLE_VALUES = Object.keys(ROLE_KEYS)

// 下拉分区：系统 / 主数据 / 售后 / 仓管是四条独立职责，混在一个平铺列表里容易选错。
// 超管不属任何业务线（全局账号），单独成组放在最前。
// 分组成员合计必须等于 ROLE_VALUES，漏掉的角色会在下拉里"消失"——
// frontend/src/utils/roles.spec.js 有断言兜底。
export const ROLE_GROUPS = [
  { key: 'common.roleGroup.system', roles: ['super_admin'] },
  { key: 'common.roleGroup.master', roles: ['product_planner'] },
  { key: 'common.roleGroup.service', roles: ['supervisor', 'agent', 'auditor'] },
  { key: 'common.roleGroup.warehouse', roles: ['warehouse_clerk', 'warehouse_manager'] }
]

// 产品线（user_product_lines）只用于**工单**数据范围，属于售后线概念。
// 仓管两个角色、超管与产品计划不看工单范围，产品线分配对这些角色是噪音，
// 表单里直接隐藏，避免管理员误以为"没选产品线就没权限"。
// 注意：仅隐藏与不写，**不主动清空**库里已有的分配（改角色回售后线时应能复用）。
const LINE_ROLES = new Set(['supervisor', 'agent', 'auditor'])

// 支持单角色与多角色：一人多岗时只要有任一角色属于售后线，就需要分配产品线
export function usesProductLines(roleOrRoles) {
  const values = Array.isArray(roleOrRoles) ? roleOrRoles : [roleOrRoles]
  return values.some((role) => LINE_ROLES.has(role))
}

/**
 * 角色值 → 中文名。传 t（vue-i18n 的翻译函数）而不在模块里取，
 * 这样调用方可以自由切换语言。
 *
 * 未登记的角色原样返回：宁可露出原始值，也不要显示成空，便于发现漏登记。
 */
export function roleLabel(t, value) {
  if (!value) return ''
  const key = ROLE_KEYS[value]
  return key ? t(key) : String(value)
}
