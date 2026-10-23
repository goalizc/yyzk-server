/**
 * 浏览器标签页标题。
 *
 * 国际化改造前 `document.title` 只在 index.html 里写死过一次，
 * 进任何页面都显示同一个中文标题。这里按路由的 `titleKey` 生成，
 * 语言切换时也要手动调一次（切语言不换路由，afterEach 不会跑）。
 */
import { i18n } from '../locales'

export function applyPageTitle(meta = {}) {
  if (typeof document === 'undefined') return
  const appName = i18n.global.t('common.appName')
  const key = meta.titleKey
  const pageName = key ? i18n.global.t(key) : ''
  // 首页没有 titleKey：直接用品名，避免"售后故障诊断系统 · 售后故障诊断系统"
  document.title = pageName && pageName !== appName ? `${pageName} · ${appName}` : appName
}
