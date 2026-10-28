// utils/idle.js：空闲自动登出的计时逻辑
//
// 场景：下班直接关机，第二天开机浏览器恢复标签页，JWT 还在 24 小时内，
// 任何人打开电脑都能直接进后台。这里锁死的是"空闲多久算过期"与"触发几次"。
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  clearActivity,
  isIdleExpired,
  readLastActive,
  resetActivity,
  startIdleWatch,
  touchActivity
} from './idle'

const MINUTE = 60 * 1000

beforeEach(() => {
  localStorage.clear()
  // clearActivity 同时把模块内的"上次写盘时间"重置为 0：
  // 只清 localStorage 的话，上一个用例的节流窗口会延续过来，touchActivity 被整段跳过
  clearActivity()
  vi.useFakeTimers()
  // 固定一个时间点，避免跨午休/跨天跑测试时出现"刚好卡在边界"的偶发
  vi.setSystemTime(new Date('2026-10-28T09:00:00+08:00'))
})

afterEach(() => {
  vi.useRealTimers()
})

describe('isIdleExpired', () => {
  it('没有活动记录时为 false（不能把"从没登录过"判成超时）', () => {
    expect(readLastActive()).toBe(0)
    expect(isIdleExpired()).toBe(false)
  })

  it('刚操作过为 false，超过 60 分钟为 true', () => {
    resetActivity()
    expect(isIdleExpired()).toBe(false)

    vi.advanceTimersByTime(59 * MINUTE)
    expect(isIdleExpired()).toBe(false)

    vi.advanceTimersByTime(2 * MINUTE)
    expect(isIdleExpired()).toBe(true)
  })

  it('clearActivity 之后不再算超时（退出登录要清，别让下一个人继承）', () => {
    resetActivity()
    vi.advanceTimersByTime(61 * MINUTE)
    expect(isIdleExpired()).toBe(true)

    clearActivity()
    expect(readLastActive()).toBe(0)
    expect(isIdleExpired()).toBe(false)
  })
})

describe('touchActivity', () => {
  it('15 秒内只写一次盘（mousemove 很密集，不能每个事件都写）', () => {
    resetActivity(0)
    localStorage.setItem('lastActiveAt', '0')

    touchActivity()
    const first = readLastActive()
    expect(first).toBe(Date.now())

    vi.advanceTimersByTime(5 * 1000)
    touchActivity()
    expect(readLastActive()).toBe(first)

    vi.advanceTimersByTime(15 * 1000)
    touchActivity()
    expect(readLastActive()).toBe(Date.now())
  })
})

describe('startIdleWatch', () => {
  it('没有记录时启动即写一次，避免"等第一次鼠标移动才开始计时"', () => {
    const stop = startIdleWatch({ onIdle: vi.fn() })
    expect(readLastActive()).toBe(Date.now())
    stop()
  })

  it('上个会话已经空闲超时：启动时立刻触发一次，且不会重复触发', () => {
    localStorage.setItem('lastActiveAt', String(Date.now() - 61 * MINUTE))
    const onIdle = vi.fn()

    const stop = startIdleWatch({ onIdle })
    expect(onIdle).toHaveBeenCalledTimes(1)

    // 触发后自动停止，不能再被定时器打一遍
    vi.advanceTimersByTime(120 * MINUTE)
    expect(onIdle).toHaveBeenCalledTimes(1)
    stop()
  })

  it('持续操作就一直不触发', () => {
    const onIdle = vi.fn()
    const stop = startIdleWatch({ onIdle })

    // 每 10 分钟动一下鼠标，连续 2 小时
    for (let i = 0; i < 12; i += 1) {
      vi.advanceTimersByTime(10 * MINUTE)
      window.dispatchEvent(new Event('mousemove'))
    }

    expect(onIdle).not.toHaveBeenCalled()
    stop()
  })

  it('闲置到点触发，并在最后 2 分钟只提醒一次', () => {
    const onIdle = vi.fn()
    const onWarn = vi.fn()
    const stop = startIdleWatch({ onIdle, onWarn })

    vi.advanceTimersByTime(57 * MINUTE)
    expect(onWarn).not.toHaveBeenCalled()
    expect(onIdle).not.toHaveBeenCalled()

    vi.advanceTimersByTime(2 * MINUTE) // 59 分钟：进入预警区
    expect(onWarn).toHaveBeenCalledTimes(1)
    expect(onIdle).not.toHaveBeenCalled()

    vi.advanceTimersByTime(2 * MINUTE) // 61 分钟：超时
    expect(onWarn).toHaveBeenCalledTimes(1)
    expect(onIdle).toHaveBeenCalledTimes(1)
    stop()
  })

  it('活动记录被清空后不判定超时（否则 Date.now() 减 0 会立刻误触发）', () => {
    // 触发路径：另一个标签登出、401 拦截器清理都会清掉 lastActiveAt，
    // 而本标签的 Layout 还没卸载，定时器仍会跑一次
    const onIdle = vi.fn()
    const stop = startIdleWatch({ onIdle })

    localStorage.removeItem('lastActiveAt')
    vi.advanceTimersByTime(31 * 1000)

    expect(onIdle).not.toHaveBeenCalled()
    stop()
  })

  it('stop 之后定时器与事件监听都不再生效', () => {
    const onIdle = vi.fn()
    const stop = startIdleWatch({ onIdle })
    stop()

    vi.advanceTimersByTime(120 * MINUTE)
    window.dispatchEvent(new Event('mousemove'))
    expect(onIdle).not.toHaveBeenCalled()
  })
})
