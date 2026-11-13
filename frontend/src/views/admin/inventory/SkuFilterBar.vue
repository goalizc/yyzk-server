<template>
  <div class="sku-filter">
    <span class="bar-label">{{ $t('admin.inventory.common.filter') }}</span>
    <el-input
      :model-value="keyword"
      :placeholder="$t('admin.inventory.common.skuKeywordPlaceholder')"
      clearable
      class="kw"
      @update:model-value="onKeyword"
      @keyup.enter="emit('change')"
      @clear="emit('change')"
    />
    <el-select
      :model-value="categoryId"
      :placeholder="$t('admin.inventory.common.category')"
      :loading="loading"
      clearable
      filterable
      class="sm"
      @update:model-value="onCategory"
    >
      <el-option v-for="c in categories" :key="c.id" :label="c.name" :value="c.id" />
    </el-select>
    <el-select
      :model-value="productId"
      :placeholder="$t('admin.inventory.common.product')"
      :loading="loading"
      clearable
      filterable
      class="md"
      @update:model-value="onProduct"
    >
      <el-option v-for="p in products" :key="p.id" :label="p.name" :value="p.id" />
    </el-select>
    <span class="count" :class="{ warn: truncated }">{{ summary }}</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps({
  keyword: { type: String, default: '' },
  categoryId: { type: Number, default: null },
  productId: { type: Number, default: null },
  categories: { type: Array, default: () => [] },
  products: { type: Array, default: () => [] },
  // 当前候选数量 / 服务端真实总数，用来提示"只列了前 N 个"
  shown: { type: Number, default: 0 },
  total: { type: Number, default: 0 },
  loading: { type: Boolean, default: false }
})
const emit = defineEmits(['update:keyword', 'update:categoryId', 'update:productId', 'change'])

const { t } = useI18n()

const hasFilter = computed(
  () => props.keyword.trim() !== '' || props.categoryId !== null || props.productId !== null
)
const truncated = computed(() => props.total > props.shown)

// 三态：被截断（最需要引导）/ 有筛选 / 无筛选。
// 被截断时必须说清楚"下拉里不全"，否则用户会以为物资没建档。
const summary = computed(() => {
  if (truncated.value) return t('admin.inventory.common.skuTruncated', { total: props.total, n: props.shown })
  if (hasFilter.value) return t('admin.inventory.common.skuFiltered', { n: props.shown })
  return t('admin.inventory.common.skuTotal', { total: props.shown })
})

function onKeyword(value) {
  emit('update:keyword', value ?? '')
}

function onCategory(value) {
  emit('update:categoryId', value ?? null)
  emit('change')
}

function onProduct(value) {
  emit('update:productId', value ?? null)
  emit('change')
}
</script>

<style scoped>
.sku-filter {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
  padding: 8px 10px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
}
.bar-label { font-size: 13px; color: var(--el-text-color-regular); }
/* 780px 弹窗里四个控件一排：关键词 150 + 分类 130 + 产品 160 + 标签，余下给计数 */
.kw { width: 150px; }
.sm { width: 130px; }
/* 产品名普遍长于分类（「植保无人机 16L」），130px 会截断 */
.md { width: 160px; }
.count {
  flex: 1;
  min-width: 120px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.count.warn { color: var(--el-color-warning); }
</style>
