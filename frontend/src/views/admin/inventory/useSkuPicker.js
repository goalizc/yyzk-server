/**
 * 单据弹窗（新建 / 改单）的 SKU 选择器：分类 / 产品筛选 + 已选项保留。
 *
 * 为什么筛选走服务端而不是前端过滤：
 * `GET /inventory/skus` 的 page_size 上限是 100，父组件进页面时只拉了前 100 条。
 * SKU 上千时纯前端过滤等于在残缺集合里搜，会出现「明明有这个物资却找不到」。
 * 所以筛选参数一律交给后端，前端只缓存「见过的」SKU，用来兜住已选项的
 * label 与余额——切换筛选后已选项可能不在新候选里，但下拉不能显示成空白。
 */
import { computed, ref, watch } from 'vue'
import { inventorySkus } from '../../../api/inventory'

// 后端 page_size 上限（le=100）；一次拉满，减少二次请求
export const SKU_PAGE_SIZE = 100

/**
 * @param {() => Array} getInitial 父组件已拉到的 SKU（可含当前单据里已停用的）
 */
export function useSkuPicker(getInitial) {
  const keyword = ref('')
  const categoryId = ref(null)
  const productId = ref(null)
  // 当前候选（服务端筛选结果）
  const candidates = ref([])
  // 服务端 total，用于判断候选是否被 page_size 截断
  const totalCount = ref(0)
  const loading = ref(false)
  // 是否已经按筛选条件拉过一次（未拉过时 candidates 用父组件的 initial 兜底）
  const loaded = ref(false)
  // id -> sku。已选项可能不在候选里，label / 余额都从这里取
  const known = ref(new Map())

  function remember(list, { keepExisting = false } = {}) {
    if (!list || !list.length) return
    const next = new Map(known.value)
    for (const sku of list) {
      // 单据明细补进来的停用 SKU 只带编码/名称（quantity 缺省 0），
      // 不能覆盖启用清单里已有的余额，否则出库单会误报余额为 0
      if (keepExisting && next.has(sku.id)) continue
      next.set(sku.id, sku)
    }
    known.value = next
  }

  function applyInitial(list) {
    remember(list)
    if (loaded.value) return
    candidates.value = list || []
    totalCount.value = candidates.value.length
  }

  watch(getInitial, applyInitial, { immediate: true })

  const hasFilter = computed(
    () => keyword.value.trim() !== '' || categoryId.value !== null || productId.value !== null
  )
  // 真实总数比候选多 = 还有更多物资没进下拉，必须提示用户缩小范围
  const truncated = computed(() => totalCount.value > candidates.value.length)

  async function reload() {
    loading.value = true
    const trimmed = keyword.value.trim()
    try {
      const data = await inventorySkus({
        page: 1,
        page_size: SKU_PAGE_SIZE,
        is_active: true,
        ...(trimmed ? { keyword: trimmed } : {}),
        ...(categoryId.value === null ? {} : { category_id: categoryId.value }),
        ...(productId.value === null ? {} : { product_id: productId.value })
      })
      candidates.value = data.items || []
      totalCount.value = data.total ?? candidates.value.length
      loaded.value = true
      remember(candidates.value)
    } catch {
      // 拉取失败不该挡住录入：保留上一次候选，用户仍可凭编码搜索
    } finally {
      loading.value = false
    }
  }

  /** 关闭弹窗时清筛选，避免上一单的条件影响下一单 */
  function reset() {
    keyword.value = ''
    categoryId.value = null
    productId.value = null
    loaded.value = false
    candidates.value = getInitial() || []
    totalCount.value = candidates.value.length
  }

  /**
   * 某一行的候选 = 当前筛选结果 + 该行已选中的 SKU。
   * 少了后半句，用户换一次筛选，已经选好的行就变成空白框。
   */
  function optionsFor(selectedId) {
    const list = candidates.value
    if (!selectedId || list.some((sku) => sku.id === selectedId)) return list
    const extra = known.value.get(selectedId)
    return extra ? [extra, ...list] : list
  }

  function skuOf(skuId) {
    return known.value.get(skuId) || null
  }

  function balanceOf(skuId) {
    if (!skuId) return '-'
    return skuOf(skuId)?.quantity ?? 0
  }

  return {
    keyword,
    categoryId,
    productId,
    candidates,
    totalCount,
    loading,
    hasFilter,
    truncated,
    reload,
    reset,
    optionsFor,
    skuOf,
    balanceOf,
    remember
  }
}
