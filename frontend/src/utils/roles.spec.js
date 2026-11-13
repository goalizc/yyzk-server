import { describe, expect, it } from 'vitest'
import { ROLE_GROUPS, ROLE_KEYS, ROLE_VALUES, usesProductLines } from './roles'

describe('roles', () => {
  it('product_planner 是主数据角色，且分组不漏角色', () => {
    expect(ROLE_KEYS.product_planner).toBe('common.role.product_planner')
    const flattened = ROLE_GROUPS.flatMap((group) => group.roles)
    expect(flattened.sort()).toEqual([...ROLE_VALUES].sort())
    const master = ROLE_GROUPS.find((group) => group.key === 'common.roleGroup.master')
    expect(master.roles).toEqual(['product_planner'])
  })

  it('product_planner 不参与产品线分配', () => {
    expect(usesProductLines('product_planner')).toBe(false)
    expect(usesProductLines('supervisor')).toBe(true)
  })

  it('多角色只要有售后线角色就需要产品线分配', () => {
    expect(usesProductLines(['warehouse_manager', 'supervisor'])).toBe(true)
    expect(usesProductLines(['warehouse_manager', 'agent'])).toBe(true)
    expect(usesProductLines(['warehouse_manager', 'product_planner'])).toBe(false)
    expect(usesProductLines([])).toBe(false)
  })
})
