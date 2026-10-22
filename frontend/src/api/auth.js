import request from './request'

export function login(payload) {
  return request.post('/auth/login', payload)
}

export function changePassword(payload) {
  return request.put('/auth/password', payload)
}

export function fetchMe() {
  return request.get('/auth/me')
}
