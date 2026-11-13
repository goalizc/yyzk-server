import request from './request'

// 进销存 24 个端点（PRD §4，统一前缀 /api/admin/inventory）。
// 与售后业务完全独立：单独一个 api 文件，不往 admin.js 里塞。
const BASE = '/admin/inventory'

// ---------------------------------------------------------------- 仓库 / SKU

export function inventoryWarehouses(params) {
  return request.get(`${BASE}/warehouses`, { params })
}

// 库存域只读引用：仓管没有 product:read / part:read（售后域），
// 建 SKU 的「关联产品 / 零件」下拉与单据列表的产品筛选都走这两个端点。
export function inventoryRefProducts() {
  return request.get(`${BASE}/refs/products`)
}

export function inventoryRefParts(productId) {
  // product_id 可选：省略时一次返回全部零件（含 product_name），避免按产品逐个请求
  return request.get(`${BASE}/refs/parts`, {
    params: productId ? { product_id: productId } : {}
  })
}

export function inventorySkus(params) {
  return request.get(`${BASE}/skus`, { params })
}

export function inventoryCreateSku(payload) {
  return request.post(`${BASE}/skus`, payload)
}

export function inventoryUpdateSku(id, payload) {
  return request.put(`${BASE}/skus/${id}`, payload)
}

/** 软删置 is_active=false；已被单据引用时后端返回 409 SKU_IN_USE */
export function inventoryDisableSku(id) {
  return request.delete(`${BASE}/skus/${id}`)
}

// ---------------------------------------------------------------- 分类主数据

export function inventoryCategories(params) {
  return request.get(`${BASE}/categories`, { params })
}

export function inventoryCreateCategory(payload) {
  return request.post(`${BASE}/categories`, payload)
}

export function inventoryUpdateCategory(id, payload) {
  return request.put(`${BASE}/categories/${id}`, payload)
}

/** 后台汇总：SKU 数、低库存数、本月出入库笔数 */
export function inventorySummary() {
  return request.get(`${BASE}/summary`)
}

// ---------------------------------------------------------------- 单据

export function inventoryInboundOrders(params) {
  return request.get(`${BASE}/inbound-orders`, { params })
}

export function inventoryGetInbound(id) {
  return request.get(`${BASE}/inbound-orders/${id}`)
}

export function inventoryCreateInbound(payload) {
  return request.post(`${BASE}/inbound-orders`, payload)
}

export function inventoryOutboundOrders(params) {
  return request.get(`${BASE}/outbound-orders`, { params })
}

export function inventoryGetOutbound(id) {
  return request.get(`${BASE}/outbound-orders/${id}`)
}

export function inventoryCreateOutbound(payload) {
  return request.post(`${BASE}/outbound-orders`, payload)
}

/** adjust_type: 'in' | 'out' */
export function inventoryCreateAdjustment(payload) {
  return request.post(`${BASE}/adjustments`, payload)
}

/** 冲正：生成反向单 + 原单置 void；remark 必填 */
export function inventoryReverseDocument(id, payload) {
  return request.post(`${BASE}/documents/${id}/reverse`, payload)
}

/** 主管修改已生效入库 / 出库单：净更正流水 + 改写明细；需 inventory:doc:edit */
export function inventoryUpdateDocument(id, payload) {
  return request.put(`${BASE}/documents/${id}`, payload)
}

// ---------------------------------------------------------------- 流水 / 导出

export function inventoryMovements(params) {
  return request.get(`${BASE}/movements`, { params })
}

/** CSV 后端带 UTF-8 BOM，Excel 直接打开中文不乱码；
 *  fullResponse 用于读取 X-Export-Truncated 头，提示"只导出了前 N 行" */
export function inventoryExport(params) {
  return request.get(`${BASE}/export`, { params, responseType: 'blob', fullResponse: true })
}
