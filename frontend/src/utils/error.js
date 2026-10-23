/**
 * 错误文案统一出口。
 *
 * 契约：后端错误体固定 `{detail, code, params?}`。
 * 顺序如下（见 docs/02-技术设计/国际化设计.md §4）：
 *   1. 中文环境 + 后端给了 detail → 直接用 detail
 *   2. code 在本地字典里 → 按当前语言取词，params 做插值
 *   3. 都取不到 → 后端 detail（可能是新增码，前端未同步）
 *   4. 最后才是兜底文案
 *
 * 为什么中文环境优先 detail：
 * 后端很多码的 detail 比通用文案精确得多（`SERVICE_UNAVAILABLE` 会具体到"数据库不可用"，
 * `MODEL_DUPLICATED` 会带上型号）。字典里的通用文案只在非中文环境才用得上，
 * 这样中文行为与国际化改造前 **完全一致**，零回归。
 */
import { i18n, currentLocale, DEFAULT_LOCALE } from '../locales'

/**
 * @param {unknown} error axios 错误对象
 * @param {{fallbackKey?: string, fallbackText?: string}} options
 *        fallbackText 用于兼容历史调用（第二参数是中文文案而不是 key）
 */
export function errorMessage(error, { fallbackKey, fallbackText } = {}) {
  const body = error?.response?.data
  const code = body?.code
  const detail = body?.detail
  const { t, te } = i18n.global

  // 中文环境保持现状：detail 是后端按具体场景写的，比字典通用文案更准确
  if (currentLocale() === DEFAULT_LOCALE && detail) return detail

  if (code) {
    const key = `error.${code}`
    if (te(key)) return t(key, body.params || {})
  }

  // 前端字典里没有这个码（后端新增但前端未同步）：退回原文，不要显示空提示
  if (detail) return detail
  if (fallbackKey) return t(fallbackKey)
  if (fallbackText) return fallbackText
  return t('common.error.generic')
}
