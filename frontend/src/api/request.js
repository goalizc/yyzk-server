import axios from 'axios'

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
  (response) => response.data,
  (error) => {
    const code = error.response?.data?.code
    // 契约 §0.3：只有 AUTH_TOKEN_EXPIRED 才清 token 跳登录，
    // 登录失败（AUTH_INVALID_CREDENTIALS）必须在表单内提示，不能闪回登录页。
    // AUTH_USER_DISABLED（403）：账号被停用，token 已无意义，同样回登录页
    if (code === 'AUTH_TOKEN_EXPIRED' || code === 'AUTH_USER_DISABLED') {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      if (!location.pathname.endsWith('/admin/login')) {
        location.href = '/admin/login'
      }
    }
    return Promise.reject(error)
  }
)

export default request
