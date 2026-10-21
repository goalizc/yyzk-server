// utils/upload.js：后缀白名单与大小上限必须与契约 §4 一致
import { describe, expect, it } from 'vitest'
import {
  ATTACHMENT_EXTS,
  extHint,
  extOf,
  IMAGE_EXTS,
  isAllowedExt,
  UPLOAD_MAX_SIZE
} from './upload'

describe('utils/upload', () => {
  it('大小上限为 20MB', () => {
    expect(UPLOAD_MAX_SIZE).toBe(20 * 1024 * 1024)
  })

  it('图片白名单为 jpg/jpeg/png', () => {
    expect(IMAGE_EXTS).toEqual(['.jpg', '.jpeg', '.png'])
  })

  it('附件白名单在图片基础上加 pdf/mp4', () => {
    expect(ATTACHMENT_EXTS).toEqual(['.jpg', '.jpeg', '.png', '.pdf', '.mp4'])
  })

  it('后缀提取大小写不敏感', () => {
    expect(extOf('A.JPG')).toBe('.jpg')
    expect(extOf('manual.PDF')).toBe('.pdf')
    expect(extOf('noext')).toBe('')
    expect(extOf('')).toBe('')
  })

  it('白名单校验：拒绝可执行文件与超长伪装后缀', () => {
    expect(isAllowedExt('a.png', IMAGE_EXTS)).toBe(true)
    expect(isAllowedExt('a.svg', IMAGE_EXTS)).toBe(false)
    expect(isAllowedExt('a.exe', ATTACHMENT_EXTS)).toBe(false)
    // 只取最后一段后缀，"a.png.exe" 不能被当成 png 放行
    expect(isAllowedExt('a.png.exe', IMAGE_EXTS)).toBe(false)
  })

  it('提示文案去掉点号', () => {
    expect(extHint(IMAGE_EXTS)).toBe('仅支持 jpg / jpeg / png 格式')
    expect(extHint(ATTACHMENT_EXTS)).toBe('仅支持 jpg / jpeg / png / pdf / mp4 格式')
  })
})
