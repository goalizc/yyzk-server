/**
 * 本地登录痕迹的统一清理。
 *
 * 退出登录、会话超时、守卫里被动失效，三处都要清同样几样东西：
 * token / 用户信息 / 权限缓存 / 空闲计时。
 * 早期各写各的（request.js 拦截器也有一份），漏掉一处就会出现
 * "token 没了但权限还在"这类半登出状态，所以收口到这里。
 */
import { clearPermissions } from './permissions'
import { clearActivity } from './idle'

export function clearAuthLocal() {
  localStorage.removeItem('token')
  localStorage.removeItem('user')
  clearPermissions()
  // 空闲计时也要清：否则下一个登录的人会继承上一个人"已经空闲很久"的状态
  clearActivity()
}
