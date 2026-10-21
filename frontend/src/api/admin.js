import request from './request'

// 后台接口封装（契约 §2 / §3 / §4 / §5 / §6）。
// 注意：错误由调用方按 `error.response.data.code` 分支处理，
// 这里不做统一的弹窗，避免"接口报错 + 表单内联提示"重复打扰。

// ---------------------------------------------------------------- 产品

export function adminListProducts(params) {
  return request.get('/admin/products', { params })
}

export function adminCreateProduct(payload) {
  return request.post('/admin/products', payload)
}

export function adminUpdateProduct(id, payload) {
  return request.put(`/admin/products/${id}`, payload)
}

export function adminDeleteProduct(id) {
  return request.delete(`/admin/products/${id}`)
}

// ---------------------------------------------------------------- 零件

export function adminListParts(params) {
  return request.get('/admin/parts', { params })
}

export function adminCreatePart(payload) {
  return request.post('/admin/parts', payload)
}

export function adminUpdatePart(id, payload) {
  return request.put(`/admin/parts/${id}`, payload)
}

export function adminDeletePart(id) {
  return request.delete(`/admin/parts/${id}`)
}

// ---------------------------------------------------------------- 故障

export function adminListFaults(params) {
  return request.get('/admin/faults', { params })
}

export function adminGetFault(id) {
  return request.get(`/admin/faults/${id}`)
}

export function adminCreateFault(payload) {
  return request.post('/admin/faults', payload)
}

export function adminUpdateFault(id, payload) {
  return request.put(`/admin/faults/${id}`, payload)
}

export function adminDeleteFault(id) {
  return request.delete(`/admin/faults/${id}`)
}

// ---------------------------------------------------------------- 工单

export function adminListTickets(params) {
  return request.get('/admin/tickets', { params })
}

export function adminGetTicket(id) {
  return request.get(`/admin/tickets/${id}`)
}

export function adminUpdateTicket(id, payload) {
  return request.put(`/admin/tickets/${id}`, payload)
}

// ---------------------------------------------------------------- 统计

export function adminStatsOverview(params) {
  return request.get('/admin/stats/overview', { params })
}

export function adminStatsTopFaults(params) {
  return request.get('/admin/stats/top-faults', { params })
}

export function adminStatsMissed(params) {
  return request.get('/admin/stats/missed', { params })
}

// ---------------------------------------------------------------- 上传

/**
 * 上传单个文件（契约 §4 POST /api/admin/upload）。
 * 大文件上限 20MB，axios 全局 timeout 10s 对 20MB 偏紧，这里单独放宽。
 */
export function adminUpload(file, onProgress) {
  const form = new FormData()
  form.append('file', file)
  return request.post('/admin/upload', form, {
    timeout: 60000,
    onUploadProgress: onProgress
  })
}

/**
 * 删除一个未被引用的上传文件。
 *
 * 用于"上传后又点了移除"的场景——不调用它，文件会永久留在服务器上。
 * 后端对两种情况都按成功处理：文件已不存在（幂等）、文件仍在被引用（409）。
 * 后者说明这张图被别的方案用着，删不得，前端也不该报错打扰用户。
 */
export function adminDeleteUpload(url) {
  return request.delete('/admin/upload', { params: { url } })
}
