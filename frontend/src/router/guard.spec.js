// router/index.js 的「已登录不该看登录页」规则
//
// 为什么单独测这个纯函数：真实导航会连带加载 Layout 等懒加载组件、发请求，
// 单测里既慢又容易被网络层干扰。函数本身是纯的，规则错了这里就会红；
// 接入点是否正确由 e2e/admin-entry.spec.js 端到端兜住。
import { beforeEach, describe, expect, it } from 'vitest'
import { idleRedirect, loggedInRedirect } from './index'

const b64url = (obj) => Buffer.from(JSON.stringify(obj)).toString('base64url')
const jwt = (payload) => `${b64url({ alg: 'HS256', typ: 'JWT' })}.${b64url(payload)}.sig`
const nowSeconds = () => Math.floor(Date.now() / 1000)

function loginWith(exp) {
  localStorage.setItem('token', jwt({ sub: 'admin', exp }))
}

const loginPage = (query = {}) => ({ path: '/admin/login', query })

beforeEach(() => localStorage.clear())

describe('loggedInRedirect', () => {
  it('已登录访问登录页 → 送进后台首页', () => {
    loginWith(nowSeconds() + 3600)
    expect(loggedInRedirect(loginPage())).toEqual({ path: '/admin' })
  })

  it('带 redirect 时回原页面（登录超时被踢出来的场景）', () => {
    loginWith(nowSeconds() + 3600)
    expect(loggedInRedirect(loginPage({ redirect: '/admin/faults' }))).toEqual({ path: '/admin/faults' })
  })

  it('redirect 指向站外地址时忽略，只回后台首页（防开放重定向）', () => {
    loginWith(nowSeconds() + 3600)
    expect(loggedInRedirect(loginPage({ redirect: 'https://evil.example.com' }))).toEqual({ path: '/admin' })
    expect(loggedInRedirect(loginPage({ redirect: '//evil.example.com' }))).toEqual({ path: '/admin' })
  })

  it('未登录不动，交给 public 放行（照常显示登录页）', () => {
    expect(loggedInRedirect(loginPage())).toBeNull()
  })

  it('token 已过期也不动（不能让后台闪一下再被 401 踹回）', () => {
    loginWith(nowSeconds() - 10)
    expect(loggedInRedirect(loginPage())).toBeNull()
  })

  it('后台其他页面不受影响', () => {
    loginWith(nowSeconds() + 3600)
    expect(loggedInRedirect({ path: '/admin/tickets', query: {} })).toBeNull()
    expect(loggedInRedirect({ path: '/', query: {} })).toBeNull()
  })
})

describe('idleRedirect', () => {
  const idleMinutesAgo = (minutes) =>
    localStorage.setItem('lastActiveAt', String(Date.now() - minutes * 60 * 1000))

  it('最近有操作：放行', () => {
    loginWith(nowSeconds() + 3600)
    idleMinutesAgo(5)
    expect(idleRedirect({ path: '/admin/tickets', query: {} })).toBeNull()
  })

  it('没有 token 时不动（未登录访客不受影响）', () => {
    idleMinutesAgo(120)
    expect(idleRedirect({ path: '/', query: {} })).toBeNull()
  })

  it('客户侧页面不受影响：即使已登录且空闲超时，也不清凭证不跳转', () => {
    // 回归：曾经漏了这个路径判断，同一浏览器登录过后台的人，
    // 空闲超时后打开客户首页会被弹到 /admin/login，自助查询直接不可用
    loginWith(nowSeconds() + 3600)
    idleMinutesAgo(120)

    expect(idleRedirect({ path: '/', query: {} })).toBeNull()
    expect(idleRedirect({ path: '/faults/9', query: {} })).toBeNull()
    expect(idleRedirect({ path: '/en', query: {} })).toBeNull()
    // 客户侧不该动后台凭证：那是后台的会话，与客户页面无关
    expect(localStorage.getItem('token')).not.toBeNull()
  })

  it('空闲超过 60 分钟：清凭证并带 reason=idle 回登录页', () => {
    loginWith(nowSeconds() + 3600)
    localStorage.setItem('permissions', '["ticket:read"]')
    idleMinutesAgo(61)

    expect(idleRedirect({ path: '/admin/tickets', query: {} })).toEqual({
      path: '/admin/login',
      query: { reason: 'idle' }
    })
    // 凭证必须一起清掉，否则"看似已登录"会让后续判断继续放行
    expect(localStorage.getItem('token')).toBeNull()
    expect(localStorage.getItem('permissions')).toBeNull()
    expect(localStorage.getItem('lastActiveAt')).toBeNull()
  })

  it('目标本来就是登录页：清凭证但不再跳自己一次', () => {
    loginWith(nowSeconds() + 3600)
    idleMinutesAgo(61)

    expect(idleRedirect({ path: '/admin/login', query: {} })).toBeNull()
    expect(localStorage.getItem('token')).toBeNull()
  })

  it('恰好 60 分钟算超时（与阈值同口径）', () => {
    loginWith(nowSeconds() + 3600)
    idleMinutesAgo(60)
    expect(idleRedirect({ path: '/admin/tickets', query: {} })).not.toBeNull()
  })
})
