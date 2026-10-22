import { describe, expect, it } from 'vitest'
import { PERMISSION_LABELS, permissionLabel } from './permissionLabels'

// 与后端 ALL_PERMISSIONS 对齐的 15 个权限码
const CODES = [
  'ticket:read', 'ticket:write', 'ticket:assign',
  'product:read', 'product:write',
  'part:read', 'part:write',
  'fault:read', 'fault:write',
  'upload:write', 'stats:read',
  'user:read', 'user:write',
  'product_line:read', 'product_line:write'
]

describe('permissionLabels', () => {
  it('15 个权限码都有中文名', () => {
    expect(Object.keys(PERMISSION_LABELS)).toHaveLength(15)
    for (const code of CODES) {
      expect(PERMISSION_LABELS[code]).toBeTruthy()
      expect(PERMISSION_LABELS[code]).not.toBe(code)
    }
  })

  it('未知权限码回退原码', () => {
    expect(permissionLabel('unknown:code')).toBe('unknown:code')
  })
})
