import { ref } from 'vue'

const STORAGE_KEY = 'permissions'

export function loadPermissions() {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

const current = ref(loadPermissions())

export function setPermissions(list) {
  current.value = [...new Set(Array.isArray(list) ? list : [])]
  localStorage.setItem(STORAGE_KEY, JSON.stringify(current.value))
}

export function clearPermissions() {
  current.value = []
  localStorage.removeItem(STORAGE_KEY)
}

export function hasPermission(code) {
  return current.value.includes(code)
}

export const permissions = current
