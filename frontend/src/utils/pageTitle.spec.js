// 浏览器标签页标题：按 meta.titleKey 取词，随语言变化
import { afterEach, describe, expect, it } from 'vitest'
import { applyPageTitle } from './pageTitle'
import { setLocale } from '../locales'

afterEach(() => {
  // 语言是全局状态，改完必须还原，否则污染同文件后续用例
  setLocale('zh-CN')
})

describe('applyPageTitle', () => {
  it('有 titleKey 时拼成「页面名 · 品名」', () => {
    setLocale('zh-CN')
    applyPageTitle({ titleKey: 'admin.page.tickets' })
    expect(document.title).toBe('工单管理 · 售后故障诊断系统')
  })

  it('没有 titleKey（首页）只用品名，不重复两遍', () => {
    setLocale('zh-CN')
    applyPageTitle({})
    expect(document.title).toBe('售后故障诊断系统')
  })

  it('英文环境用英文标题', () => {
    setLocale('en-US')
    applyPageTitle({ titleKey: 'admin.page.tickets' })
    expect(document.title).toBe('Tickets · Fault Diagnosis System')
  })

  it('客户侧页面也有标题（不再是所有页面同一个中文名）', () => {
    setLocale('en-US')
    applyPageTitle({ titleKey: 'public.faultDetail.pageTitle' })
    expect(document.title).toBe('Solution · Fault Diagnosis System')
  })
})
