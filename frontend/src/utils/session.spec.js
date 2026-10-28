// utils/session.js：本地凭证"是否还值得进后台"的判断
//
// 这条判断只影响"要不要跳过登录页"，不承担鉴权（签名/账号状态由后端判定）。
// 但边界必须准：说"有效"会让用户进后台被 401 踹回来，说"无效"会让已登录的人白登一次。
import { beforeEach, describe, expect, it } from 'vitest'
import { hasValidToken } from './session'

const b64url = (obj) => Buffer.from(JSON.stringify(obj)).toString('base64url')
const jwt = (payload) => `${b64url({ alg: 'HS256', typ: 'JWT' })}.${b64url(payload)}.sig`
const nowSeconds = () => Math.floor(Date.now() / 1000)

beforeEach(() => localStorage.clear())

describe('hasValidToken', () => {
  it('没有 token 时为 false', () => {
    expect(hasValidToken()).toBe(false)
  })

  it('exp 在未来的 token 为 true', () => {
    localStorage.setItem('token', jwt({ sub: 'admin', exp: nowSeconds() + 3600 }))
    expect(hasValidToken()).toBe(true)
  })

  it('exp 已过去的 token 为 false（过期残留不能放行）', () => {
    localStorage.setItem('token', jwt({ sub: 'admin', exp: nowSeconds() - 1 }))
    expect(hasValidToken()).toBe(false)
  })

  it('exp 正好等于当前时刻算过期（严格大于才有效）', () => {
    const now = 1_700_000_000_000
    localStorage.setItem('token', jwt({ sub: 'admin', exp: now / 1000 }))
    expect(hasValidToken(now)).toBe(false)
  })

  it('载荷没有 exp 时不按时间判断，交给后端', () => {
    localStorage.setItem('token', jwt({ sub: 'admin' }))
    expect(hasValidToken()).toBe(true)
  })

  it('载荷含中文（用户名）也能正确解码', () => {
    localStorage.setItem('token', jwt({ sub: 'admin', name: '张运维', exp: nowSeconds() + 60 }))
    expect(hasValidToken()).toBe(true)
  })

  it('结构不对的 token（段数不足 / 非 JSON / 非 base64）一律为 false', () => {
    for (const bad of ['abc', 'a.b', 'a.@@@.c', `a.${b64url('not-json')}.c`]) {
      localStorage.clear()
      localStorage.setItem('token', bad)
      expect(hasValidToken(), `token=${bad}`).toBe(false)
    }
  })
})
