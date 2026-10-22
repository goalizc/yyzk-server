import { onBeforeUnmount, onMounted, ref } from 'vue'

export function useNarrow(query = '(max-width: 768px)') {
  const isNarrow = ref(false)
  let mql = null
  const sync = (event) => { isNarrow.value = event.matches }
  onMounted(() => {
    mql = window.matchMedia?.(query)
    if (!mql) return
    isNarrow.value = mql.matches
    mql.addEventListener?.('change', sync)
  })
  onBeforeUnmount(() => mql?.removeEventListener?.('change', sync))
  return isNarrow
}
