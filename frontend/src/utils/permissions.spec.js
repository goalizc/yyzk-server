import { beforeEach, describe, expect, it } from 'vitest'
import { hasPermission, loadPermissions, setPermissions } from './permissions'

beforeEach(() => localStorage.clear())

describe('permissions', () => {
  it('默认没有任何权限', () => {
    expect(loadPermissions()).toEqual([])
    expect(hasPermission('ticket:read')).toBe(false)
  })

  it('写入后按权限码判断，去重', () => {
    setPermissions(['ticket:read', 'ticket:read', 'stats:read'])
    expect(loadPermissions()).toEqual(['ticket:read', 'stats:read'])
    expect(hasPermission('ticket:read')).toBe(true)
    expect(hasPermission('user:write')).toBe(false)
  })
})
