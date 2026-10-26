import { describe, expect, it } from 'vitest'
import { PERMISSION_LABEL_KEYS, permissionLabel } from './permissionLabels'

// 与后端 ALL_PERMISSIONS 对齐的 16 个权限码（v1.5 新增 audit:read）
const CODES = [
  'ticket:read', 'ticket:write', 'ticket:assign',
  'product:read', 'product:write',
  'part:read', 'part:write',
  'fault:read', 'fault:write',
  'upload:write', 'stats:read',
  'user:read', 'user:write',
  'product_line:read', 'product_line:write',
  'audit:read'
]

describe('permissionLabels', () => {
  it('16 个权限码都有文案 key，且都翻译得出中文名', () => {
    expect(Object.keys(PERMISSION_LABEL_KEYS)).toHaveLength(16)
    for (const code of CODES) {
      expect(PERMISSION_LABEL_KEYS[code], `缺少 key: ${code}`).toBeTruthy()
      // key 存在但语言包里没有，t() 会原样返回 key —— 这里同时验证了两层
      const label = permissionLabel(code)
      expect(label).toBeTruthy()
      expect(label).not.toBe(code)
      expect(label).not.toMatch(/^permission\./)
    }
  })

  it('未知权限码回退原码', () => {
    expect(permissionLabel('unknown:code')).toBe('unknown:code')
  })
})
