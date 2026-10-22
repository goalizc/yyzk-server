export async function copyText(text) {
  if (!text) return false

  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // 继续走 textarea 兜底：HTTP 内网或权限被拒时 Clipboard API 会抛错
  }

  let area
  try {
    area = document.createElement('textarea')
    area.value = text
    area.setAttribute('readonly', '')
    area.style.position = 'fixed'
    area.style.top = '-1000px'
    area.style.opacity = '0'
    document.body.appendChild(area)
    area.select()
    return document.execCommand('copy')
  } catch {
    return false
  } finally {
    // 无论 execCommand 返回 false 还是抛错，都不把临时节点留在页面上
    if (area?.parentNode) area.parentNode.removeChild(area)
  }
}
