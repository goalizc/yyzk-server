// router/index.js 的「已登录不该看登录页」规则
//
// 为什么单独测这个纯函数：真实导航会连带加载 Layout 等懒加载组件、发请求，
// 单测里既慢又容易被网络层干扰。函数本身是纯的，规则错了这里就会红；
// 接入点是否正确由 e2e/admin-entry.spec.js 端到端兜住。
import { beforeEach, describe, expect, it } from 'vitest'
import { loggedInRedirect } from './index'

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
