// i18n 骨架的契约测试：键完整性、错误码覆盖、语言解析与路由前缀
//
// 这些用例保护的是「以后加文案/加错误码时不会悄悄漏掉一边」，
// 而不是某句具体翻译对不对（翻译质量靠人工校对）。
import { describe, expect, it } from 'vitest'
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'
import zhCN from './zh-CN'
import enUS from './en-US'
import {
  DEFAULT_LOCALE,
  i18n,
  localeFromPath,
  localeRoute,
  normalizeLocale,
  resolveInitialLocale,
  setLocale
} from './index'

/** 把嵌套语言包拍平成 `a.b.c` → 文案 */
function flatten(node, prefix = '', out = {}) {
  for (const [key, value] of Object.entries(node)) {
    const path = prefix ? `${prefix}.${key}` : key
    if (value && typeof value === 'object') flatten(value, path, out)
    else out[path] = value
  }
  return out
}

const zh = flatten(zhCN)
const en = flatten(enUS)

/** 扫描后端源码里所有 BusinessError 的错误码 */
function backendErrorCodes() {
  const root = resolve(process.cwd(), '../backend/app')
  if (!existsSync(root)) return []
  const codes = new Set()
  const walk = (dir) => {
    for (const name of readdirSync(dir)) {
      const full = join(dir, name)
      if (statSync(full).isDirectory()) {
        if (name !== '__pycache__') walk(full)
        continue
      }
      if (!name.endsWith('.py')) continue
      const src = readFileSync(full, 'utf-8')
      for (const m of src.matchAll(/BusinessError\(\s*"([A-Z_]+)"/g)) codes.add(m[1])
      // exceptions.py 里的状态码映射与默认文案字典也登记了码
      for (const m of src.matchAll(/"([A-Z_]{4,})":/g)) codes.add(m[1])
    }
  }
  walk(root)
  return [...codes].sort()
}

describe('语言包键完整性', () => {
  it('zh-CN 与 en-US 的键集合完全一致', () => {
    const zhKeys = Object.keys(zh).sort()
    const enKeys = Object.keys(en).sort()

    // 分开断言，失败时能直接看出是"少译"还是"多译"
    expect(enKeys.filter((k) => !zhKeys.includes(k))).toEqual([])
    expect(zhKeys.filter((k) => !enKeys.includes(k))).toEqual([])
  })

  it('没有空文案（空串会让界面出现空白按钮或标签）', () => {
    for (const [key, value] of Object.entries(zh)) {
      expect(String(value).trim(), `zh-CN 缺文案: ${key}`).not.toBe('')
    }
    for (const [key, value] of Object.entries(en)) {
      expect(String(value).trim(), `en-US 缺文案: ${key}`).not.toBe('')
    }
  })

  it('同一 key 的插值占位符在两种语言里一致', () => {
    // 中文用 {count} 而英文忘了写，运行时会显示"30"却丢掉单位语义。
    //
    // 按「集合」比较而不是数组：英文复数用 `单数 | 复数` 两段，{count} 会出现两次，
    // 而中文只有一段。去重后仍是同一个占位符集合，语义上等价。
    const placeholders = (text) => [...new Set([...String(text).matchAll(/\{(\w+)\}/g)].map((m) => m[1]))].sort()
    for (const key of Object.keys(zh)) {
      expect(placeholders(en[key]), `占位符不一致: ${key}`).toEqual(placeholders(zh[key]))
    }
  })

  it('英文复数变体不得引入中文没有的占位符', () => {
    // 每段可以有也可以没有 {count}（"no items | one item | {count} items" 是合法的），
    // 但不能出现别的变量名——那样第二段会渲染出字面量 {total}
    const names = (text) => [...String(text).matchAll(/\{(\w+)\}/g)].map((m) => m[1])
    for (const key of Object.keys(en)) {
      const parts = String(en[key]).split('|')
      if (parts.length < 2) continue
      const allowed = new Set(names(zh[key]))
      for (const [index, part] of parts.entries()) {
        for (const name of names(part)) {
          expect(allowed.has(name), `${key} 第 ${index + 1} 段出现中文没有的 {${name}}`).toBe(true)
        }
      }
    }
  })
})

describe('后端错误码覆盖', () => {
  it('每个后端错误码在前端字典里都有文案', () => {
    const codes = backendErrorCodes()
    // 后端目录不可用时跳过（例如只 checkout 了 frontend），而不是让用例假绿
    if (!codes.length) {
      console.warn('未找到后端源码，跳过错误码覆盖检查')
      return
    }
    const missing = codes.filter((code) => !(code in zhCN.error))
    expect(missing, `以下错误码缺少前端文案: ${missing.join(', ')}`).toEqual([])
  })

  it('前端字典里没有后端已经不用的码', () => {
    const codes = backendErrorCodes()
    if (!codes.length) return
    const extra = Object.keys(zhCN.error).filter((code) => !codes.includes(code))
    expect(extra, `以下错误码后端已不存在: ${extra.join(', ')}`).toEqual([])
  })
})

describe('英文单复数', () => {
  // 中文没有单复数，英文有。`{count} people viewed` 在 count=1 时是语法错误，
  // 而这类文案正好出现在客户侧方案页顶部，属于"外行一眼看出没做本地化"的地方。
  it('count=1 走单数、其余走复数', () => {
    setLocale('en-US')
    const { t } = i18n.global

    expect(t('common.count.viewed', 1)).toBe('1 person viewed')
    expect(t('common.count.viewed', 2)).toBe('2 people viewed')
    expect(t('common.count.viewed', 0)).toBe('0 people viewed')

    expect(t('public.home.foundCount', 1)).toContain('1 possible fault found')
    expect(t('public.home.foundCount', 3)).toContain('3 possible faults found')

    // 带命名参数 + 复数：t(key, 数量, { 其它变量 })
    expect(t('admin.product.deleteBlocked', 1)).toContain('has 1 fault.')
    expect(t('admin.product.deleteBlocked', 3)).toContain('has 3 faults.')

    setLocale('zh-CN')
  })

  it('中文不受复数语法影响（没有 | 分段时任何数量都返回单段）', () => {
    setLocale('zh-CN')
    const { t } = i18n.global
    expect(t('common.count.viewed', 1)).toBe('1 人看过')
    expect(t('common.count.viewed', 30)).toBe('30 人看过')
    expect(t('admin.product.deleteBlocked', 1)).toBe(
      '该产品下有 1 条故障，需先迁移或删除故障后才能删除本产品。'
    )
  })
})

describe('语言解析', () => {
  it('normalizeLocale 只认两个受支持的语言', () => {
    expect(normalizeLocale('en-GB')).toBe('en-US')
    expect(normalizeLocale('zh-Hans-CN')).toBe('zh-CN')
    // 没有语言包的不能透传，否则整页显示 key
    expect(normalizeLocale('fr-FR')).toBe('')
    expect(normalizeLocale('')).toBe('')
  })

  it('localeFromPath 只匹配字面量 en，不会把 /admin 当语言段', () => {
    expect(localeFromPath('/en')).toBe('en-US')
    expect(localeFromPath('/en/faults/21')).toBe('en-US')
    expect(localeFromPath('/faults/21')).toBe('')
    expect(localeFromPath('/admin/tickets')).toBe('')
    expect(localeFromPath('/')).toBe('')
  })

  it('客户侧以 URL 为权威：无前缀就是中文，不受本地偏好影响', () => {
    localStorage.setItem('locale', 'en-US')
    expect(resolveInitialLocale('/faults/21')).toBe(DEFAULT_LOCALE)
    expect(resolveInitialLocale('/en/faults/21')).toBe('en-US')
    localStorage.removeItem('locale')
  })

  it('后台没有前缀，回退到本地偏好', () => {
    localStorage.setItem('locale', 'en-US')
    expect(resolveInitialLocale('/admin/tickets')).toBe('en-US')
    localStorage.removeItem('locale')
  })

  it('后台不跟随浏览器语言（英文版浏览器的内网机器不能自动变英文）', () => {
    // 测试环境的 navigator.language 是 en-US：若实现里回退到它，这条就会失败。
    // 中英混杂（英文外壳 + 中文页面内容）比全中文更难用。
    localStorage.removeItem('locale')
    expect(resolveInitialLocale('/admin/tickets')).toBe(DEFAULT_LOCALE)
  })
})

describe('localeRoute', () => {
  it('中文环境不生成前缀参数，英文环境带 locale=en', () => {
    setLocale('zh-CN')
    expect(localeRoute('fault-detail', { id: 21 }).params).toEqual({ id: 21 })

    setLocale('en-US')
    expect(localeRoute('fault-detail', { id: 21 }).params).toEqual({ locale: 'en', id: 21 })
    setLocale('zh-CN')
  })

  it('查询参数只在有内容时才挂上去', () => {
    setLocale('zh-CN')
    expect(localeRoute('ticket-new', {}, {})).not.toHaveProperty('query')
    expect(localeRoute('ticket-new', {}, { a: 1 }).query).toEqual({ a: 1 })
  })

  it('setLocale 会把选择写进 localStorage 并同步 html lang', () => {
    setLocale('en-US', { persist: true })
    expect(localStorage.getItem('locale')).toBe('en-US')
    expect(document.documentElement.getAttribute('lang')).toBe('en-US')

    // 客户侧传 persist=false：URL 才是权威，不能污染后台偏好
    setLocale('zh-CN', { persist: false })
    expect(localStorage.getItem('locale')).toBe('en-US')

    localStorage.removeItem('locale')
    setLocale('zh-CN')
  })
})
