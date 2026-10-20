import request from './request'

export function submitTicket(payload) {
  return request.post('/tickets', payload)
}
