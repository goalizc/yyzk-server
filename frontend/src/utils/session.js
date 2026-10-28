/**
 * 后台会话的本地状态：凭证是否还能用、以及统一的清理。
 *
 * 原来分散在 `utils/token.js`（判凭证）与 `utils/auth.js`（清凭证）两个文件里，
 * 名字都偏泛、职责又相邻，改一处容易漏另一处，所以合到一处。
 *
 * 边界：这里只做**本地时间**判断与本地清理，不做鉴权。
 * 签名、token_version、账号停用一律由后端判定。
 */
import { clearPermissions } from './permissions'
import { clearActivity } from './idle'

/** 解出 JWT 的载荷；格式不对一律返回 null，不抛异常 */
function decodePayload(token) {
  const parts = String(token || '').split('.')
  if (parts.length !== 3) return null
  try {
    // base64url → base64，再补足 4 的倍数
    const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), '=')
    const binary = atob(padded)
    // 载荷里可能有中文（用户名），atob 出来是 latin1，必须按 UTF-8 还原
    const bytes = Uint8Array.from(binary, (ch) => ch.charCodeAt(0))
    return JSON.parse(new TextDecoder().decode(bytes))
  } catch {
    return null
  }
}

/**
 * 本地是否有**未过期**的后台 token。
 *
 * 只用于一个决策：要不要跳过登录页。
 * 不"有 token 就算已登录"：过期残留若放行，用户会看到后台外壳闪一下、
 * 随即被 401 踹回登录页。
 *
 * @param {number} [now] 当前毫秒时间戳（测试注入用）
 */
export function hasValidToken(now = Date.now()) {
  let token
  try {
    token = localStorage.getItem('token')
  } catch {
    // 隐私模式读不了 localStorage：当作未登录
    return false
  }
  if (!token) return false

  const payload = decodePayload(token)
  // 载荷必须是对象：`atob` 出来是合法 JSON 但不一定是对象（如字符串字面量），
  // 这种"能解析但没有 exp 的怪东西"不能当成有效凭证
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return false
  // 没有 exp 的凭证（理论不会出现）不做时间判断，交给后端否掉
  if (typeof payload.exp !== 'number') return true
  return payload.exp * 1000 > now
}

/**
 * 本地登录痕迹的统一清理。
 *
 * 退出登录、空闲超时、守卫里被动失效、401 拦截器都走这里。
 * 早年各处手写 removeItem（曾有三份），漏掉一处就是"token 没了权限还在"的半登出状态。
 */
export function clearAuthLocal() {
  localStorage.removeItem('token')
  localStorage.removeItem('user')
  clearPermissions()
  // 空闲计时也要清：否则下一个登录的人会继承上一个人"已经空闲很久"的状态
  clearActivity()
}
