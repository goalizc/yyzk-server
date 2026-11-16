import axios from 'axios'
import { clearAuthLocal } from '../utils/session'

const request = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '/api',
  timeout: 10000
})

request.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

request.interceptors.response.use(
  // fullResponse：下载类接口需要读响应头（如导出截断标记），其余仍只返回 data
  (response) => (response.config?.fullResponse ? response : response.data),
  async (error) => {
    const data = error.response?.data
    // 下载类接口（responseType: 'blob'，如 CSV 导出）失败时，后端返回的仍是
    // JSON 错误体，但浏览器按 Blob 交给前端：不解析就既读不到 code（token 过期
    // 不会跳登录），也读不到 detail（只能显示「导出失败，请重试」）。
    if (data instanceof Blob && (data.type || '').includes('json')) {
      try {
        error.response.data = JSON.parse(await data.text())
      } catch {
        // 不是合法 JSON 就保持原样，交给调用方的兜底文案
      }
    }
    const code = error.response?.data?.code
    // 契约 §0.3：只有 AUTH_TOKEN_EXPIRED 才清 token 跳登录，
    // 登录失败（AUTH_INVALID_CREDENTIALS）必须在表单内提示，不能闪回登录页。
    // AUTH_USER_DISABLED（403）：账号被停用，token 已无意义，同样回登录页
    if (code === 'AUTH_TOKEN_EXPIRED' || code === 'AUTH_USER_DISABLED') {
      clearAuthLocal()
      // 这里是整页跳转而不是 router.push：拦截器可能在 router 初始化之前被调用
      // （守卫里的 fetchMe 失败就走这条路），import router 会形成循环依赖。
      // 整页刷新正好把内存里的旧状态一并清掉，代价可以接受。
      if (!location.pathname.endsWith('/admin/login')) {
        location.href = '/admin/login'
      }
    }
    return Promise.reject(error)
  }
)

export default request
