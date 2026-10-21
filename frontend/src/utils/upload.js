// 上传约束（与契约 §4 POST /api/admin/upload 保持一致）
// 后端仍会二次校验 MIME，这里只是尽早拦住、避免用户等整个文件传完才失败

export const UPLOAD_MAX_SIZE = 20 * 1024 * 1024 // 20MB

/** 图片（解决步骤配图） */
export const IMAGE_EXTS = ['.jpg', '.jpeg', '.png']

/** 附件（故障资料） */
export const ATTACHMENT_EXTS = ['.jpg', '.jpeg', '.png', '.pdf', '.mp4']

export function extOf(filename = '') {
  const index = filename.lastIndexOf('.')
  return index === -1 ? '' : filename.slice(index).toLowerCase()
}

export function isAllowedExt(filename, allowed) {
  return allowed.includes(extOf(filename))
}

/** 后缀不合法时的统一文案 */
export function extHint(allowed) {
  return `仅支持 ${allowed.map((ext) => ext.replace('.', '')).join(' / ')} 格式`
}
