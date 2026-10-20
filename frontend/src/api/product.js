import request from './request'

export function listProducts() {
  return request.get('/products')
}

export function listParts(productId) {
  return request.get(`/products/${productId}/parts`)
}
