/**
 * 本地登录凭证的"是否还值得进后台"判断。
 *
 * 只用于一个决策：**要不要跳过登录页**。
 * 真正的鉴权永远在后端（token 签名、token_version、账号状态都由服务端判定），
 * 这里只按 JWT 的 `exp` 看时间是否已经过去，不做任何安全判断。
 *
 * 为什么不"有 token 就算已登录"：token 过期后仍有残留值时，
 * 直接放行会让用户看到后台外壳闪一下、随即被 401 踹回登录页。
 * 本地时间过期就直接当未登录，体验更稳。
 */

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
