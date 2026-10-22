import { afterEach, describe, expect, it, vi } from 'vitest'
import { copyText } from './clipboard'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('copyText', () => {
  it('优先使用 Clipboard API', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText } })

    await expect(copyText('hello')).resolves.toBe(true)
    expect(writeText).toHaveBeenCalledWith('hello')
  })

  it('API 不可用时走 textarea 兜底', async () => {
    vi.stubGlobal('navigator', {})
    document.execCommand = vi.fn().mockReturnValue(true)

    await expect(copyText('fallback')).resolves.toBe(true)
    expect(document.execCommand).toHaveBeenCalledWith('copy')
    expect(document.querySelector('textarea')).toBeNull()
  })

  it('execCommand 抛错时返回 false 且清理 textarea', async () => {
    vi.stubGlobal('navigator', {})
    document.execCommand = vi.fn().mockImplementation(() => {
      throw new Error('copy denied')
    })

    await expect(copyText('boom')).resolves.toBe(false)
    expect(document.querySelector('textarea')).toBeNull()
  })
})
