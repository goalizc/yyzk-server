import request from './request'

/**
 * 客户侧故障列表：一次拉全量，前端本地过滤（契约 §4）。
 * partId 选填 —— 不传则返回该产品下全部故障（零件是可选过滤器）。
 */
export function listFaults(productId, partId) {
  const params = { product_id: productId }
  if (partId) params.part_id = partId
  return request.get('/faults', { params })
}

/**
 * 故障详情：服务端会自增浏览数并写查询日志，返回 query_log_id。
 * 该 id 必须保存，反馈时回传。
 */
export function getFault(faultId, query) {
  return request.get(`/faults/${faultId}`, { params: query ? { q: query } : {} })
}

export function sendFeedback(faultId, payload) {
  return request.post(`/faults/${faultId}/feedback`, payload)
}

/** 未命中检索上报（hit=false），同一组合+关键词 30 秒内只报一次由调用方保证 */
export function reportMiss(payload) {
  return request.post('/query-logs', payload)
}
