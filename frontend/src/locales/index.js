/**
 * i18n 入口：语言包、语言解析、切换与持久化。
 *
 * 设计要点（见 docs/02-技术设计/国际化设计.md）：
 *   1. 默认语言 zh-CN **不加 URL 前缀**，保证既有链接、书签、已发出的工单短信不变；
 *      英文走 `/en/...`，外文客户可以直接分享/收藏一条英文链接。
 *   2. 后台不加前缀，语言跟随本地偏好（内部员工使用，无分享需求）。
 *   3. 启动时直接从 location.pathname 解析前缀，而不是等 router.beforeEach —
 *      否则首屏会先用中文渲染再闪成英文。
 */
import { createI18n } from 'vue-i18n'
import zhCN from './zh-CN'
import enUS from './en-US'

export const DEFAULT_LOCALE = 'zh-CN'
export const SUPPORTED_LOCALES = ['zh-CN', 'en-US']
export const LOCALE_STORAGE_KEY = 'locale'

/** URL 前缀 ↔ 语言。只列需要前缀的语言，默认语言不占前缀 */
export const LOCALE_PREFIX = { 'en-US': 'en' }
const PREFIX_LOCALE = { en: 'en-US' }

/**
 * 把任意来源的语言值收敛到受支持的两个。
 * 浏览器可能给 `zh-Hans-CN`、`en-GB`、`fr-FR`；没有语言包的一律返回 ''，
 * 交给下一级兜底，避免 i18n 拿到不存在的 locale 后整片显示 key。
 */
export function normalizeLocale(value) {
  if (!value) return ''
  const raw = String(value).toLowerCase()
  if (raw.startsWith('zh')) return 'zh-CN'
  if (raw.startsWith('en')) return 'en-US'
  return ''
}

/** 从路径里取语言前缀：`/en/faults/21` → 'en-US'；`/faults/21` → '' */
export function localeFromPath(pathname = '') {
  const first = String(pathname).split('/')[1] || ''
  return PREFIX_LOCALE[first] || ''
}

function readStored() {
  try {
    return normalizeLocale(localStorage.getItem(LOCALE_STORAGE_KEY))
  } catch {
    // 隐私模式下 localStorage 可能抛异常，不能因此白屏
    return ''
  }
}

/**
 * 启动时的语言判定。
 *
 * 客户侧以 **URL 为唯一权威**：`/en/...` 是英文，无前缀一律中文。
 * 不读 localStorage —— 否则同一条分享出去的链接，在别人机器上会显示成另一种语言，
 * 链接就不再"所见即所分享"了。
 *
 * 后台没有前缀，只看本地偏好；**不跟随 navigator.language**。
 * 原因：内网机器的浏览器语言不可控（英文版 Chrome 的 navigator.language 就是 en-US），
 * 一旦跟随，中文运营打开后台会突然看到英文外壳 + 中文页面内容的混杂状态。
 * 需要英文的人自己切换一次，之后由 localStorage 记住。
 */
export function resolveInitialLocale(pathname = globalThis.location?.pathname || '') {
  const fromPath = localeFromPath(pathname)
  if (fromPath) return fromPath
  if (!String(pathname).startsWith('/admin')) return DEFAULT_LOCALE
  return readStored() || DEFAULT_LOCALE
}

export const i18n = createI18n({
  // legacy: false 才能在 setup 里用 useI18n()
  legacy: false,
  locale: resolveInitialLocale(),
  fallbackLocale: DEFAULT_LOCALE,
  // 缺翻译时直接回退到默认语言，生产环境不要往控制台刷 warning
  missingWarn: false,
  fallbackWarn: false,
  messages: { 'zh-CN': zhCN, 'en-US': enUS }
})

export function currentLocale() {
  return i18n.global.locale.value
}

// 首屏就把 <html lang> 设对。
// 直链 /en/... 时若等到 setLocale 才设置，屏幕阅读器和浏览器翻译会先按 zh-CN 处理，
// 表现为"英文页面被提示翻译成中文"。
if (typeof document !== 'undefined') {
  document.documentElement.setAttribute('lang', i18n.global.locale.value)
}

/**
 * 切换语言。
 * @param {string} locale 目标语言
 * @param {{persist?: boolean}} options persist=false 用于客户侧——那里 URL 已经是权威，
 *        写 localStorage 反而会污染后台的语言偏好。
 */
export function setLocale(locale, { persist = true } = {}) {
  const next = normalizeLocale(locale) || DEFAULT_LOCALE
  i18n.global.locale.value = next
  if (persist) {
    try {
      localStorage.setItem(LOCALE_STORAGE_KEY, next)
    } catch {
      // 存不进去不影响本次会话的语言
    }
  }
  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute('lang', next)
  }
  return next
}

/** 当前语言对应的 URL 前缀段；默认语言返回 undefined（路由参数留空） */
export function currentLocaleParam() {
  return LOCALE_PREFIX[currentLocale()]
}

/**
 * 生成带语言前缀的路由对象，页面跳转统一用它。
 * 手写 `params: { locale: ... }` 容易在某处漏掉，导致英文页面里点一下就跳回中文。
 */
export function localeRoute(name, params = {}, query = undefined) {
  const prefix = currentLocaleParam()
  const result = { name, params: prefix ? { locale: prefix, ...params } : { ...params } }
  if (query && Object.keys(query).length) result.query = query
  return result
}

/**
 * 生成带语言前缀的站内绝对路径，用于「拼成字符串的 URL」。
 *
 * 与 `localeRoute` 的分工：路由跳转用前者（要 params 对象）；
 * 写进剪贴板、`window.open`、分享出去的链接用这个（要字符串）。
 * 漏了前缀的后果很直接——英文客服复制的方案文本里带一条中文页面的链接，
 * 客户点开看到中文。
 */
export function localeHref(path) {
  const prefix = currentLocaleParam()
  const clean = String(path || '/').startsWith('/') ? String(path) : `/${path}`
  return prefix ? `/${prefix}${clean === '/' ? '' : clean}` : clean
}
