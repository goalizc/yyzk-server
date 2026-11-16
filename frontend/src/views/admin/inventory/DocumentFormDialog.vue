<template>
  <el-dialog
    v-model="visible"
    :title="title"
    :width="isNarrow ? '94%' : 'min(1000px, 94vw)'"
    @closed="resetForm"
  >
    <el-form ref="formRef" :model="form" :label-width="labelWidth">
      <el-form-item :label="$t('admin.inventory.common.warehouse')">
        <el-select v-model="form.warehouse_id" class="wd">
          <el-option v-for="w in warehouses" :key="w.id" :label="w.name" :value="w.id" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="resource === 'adjustment'" :label="$t('admin.inventory.common.adjustType')">
        <el-radio-group v-model="form.adjust_type">
          <el-radio value="in">{{ $t('admin.inventory.common.adjustIn') }}</el-radio>
          <el-radio value="out">{{ $t('admin.inventory.common.adjustOut') }}</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item :label="$t('admin.inventory.common.remark')">
        <el-input v-model="form.remark" maxlength="500" />
      </el-form-item>
    </el-form>

    <SkuFilterBar
      v-model:keyword="keyword"
      v-model:category-id="categoryId"
      v-model:product-id="productId"
      :categories="categories"
      :products="products"
      :shown="candidates.length"
      :total="totalCount"
      :loading="skuLoading"
      @change="reloadSkus"
    />

    <div class="items-head">
      <span>{{ $t('admin.inventory.common.itemsCount', { n: validItemCount }) }}</span>
      <el-button link type="primary" @click="addItem">{{ $t('admin.inventory.common.addItem') }}</el-button>
    </div>
    <el-table :data="form.items" border size="small">
      <el-table-column :label="$t('admin.inventory.common.sku')" :min-width="isCompact ? 180 : 250">
        <template #default="{ row }">
          <el-select v-model="row.sku_id" filterable class="full" @change="onSkuChange(row)">
            <el-option
              v-for="s in optionsFor(row.sku_id)"
              :key="s.id"
              :label="skuLabel(s)"
              :value="s.id"
            />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column :label="$t('admin.inventory.common.quantity')" :width="isCompact ? 100 : 120">
        <template #default="{ row }">
          <el-input-number v-model="row.quantity" class="full" :min="1" :max="999999" :precision="0" :step-strictly="true" size="small" controls-position="right" />
        </template>
      </el-table-column>
      <el-table-column v-if="showBalance" :label="$t('admin.inventory.common.balance')" :width="isCompact ? 90 : 110" align="center">
        <template #default="{ row }">
          <span :class="{ 'text-danger': balanceInsufficient(row) }">{{ balanceOf(row.sku_id) }}</span>
        </template>
      </el-table-column>
      <!-- 单价只写留档，窄窗口先让位给数量与备注，避免整表横向滚动 -->
      <el-table-column v-if="!isCompact" :label="$t('admin.inventory.common.unitCost')" width="140">
        <template #default="{ row }">
          <el-input-number v-model="row.unit_cost" class="full" :min="0" :precision="2" size="small" controls-position="right" />
        </template>
      </el-table-column>
      <el-table-column :label="$t('admin.inventory.common.remark')" :min-width="isCompact ? 120 : 170">
        <template #default="{ row }">
          <el-input v-model="row.remark" maxlength="200" size="small" />
        </template>
      </el-table-column>
      <el-table-column :label="$t('admin.inventory.common.actions')" :width="isCompact ? 60 : 72" align="center">
        <template #default="{ $index }">
          <el-button link type="danger" @click="removeItem($index)">
            {{ $t('admin.inventory.common.remove') }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>
    <div v-if="hint" class="hint">{{ hint }}</div>
    <div v-else-if="!isCompact" class="hint muted">{{ $t('admin.inventory.common.unitCostHint') }}</div>

    <template #footer>
      <el-button @click="visible = false">{{ $t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="submitting" @click="onSubmit">
        {{ $t('common.action.submit') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import {
  inventoryCreateInbound, inventoryCreateOutbound, inventoryCreateAdjustment
} from '../../../api/inventory'
import { errorMessage } from '../../../utils/error'
import { useNarrow } from '../../../utils/viewport'
import { useFormLabelWidth } from '../../../utils/formLabel'
import SkuFilterBar from './SkuFilterBar.vue'
import { useSkuPicker } from './useSkuPicker'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  // inbound | outbound | adjustment
  resource: { type: String, required: true },
  title: { type: String, default: '' },
  warehouses: { type: Array, default: () => [] },
  // 首屏兜底用的 SKU（父组件已拉的启用中物资），筛选后的候选由 picker 自己拉
  skus: { type: Array, default: () => [] },
  categories: { type: Array, default: () => [] },
  products: { type: Array, default: () => [] }
})
const emit = defineEmits(['update:modelValue', 'created'])

const { t } = useI18n()
// 英文最长标签 "Unit cost (optional, record only)" / "Adjustment direction"
const labelWidth = useFormLabelWidth('88px', '150px')
const isNarrow = useNarrow()
// 窄窗口（≤1000px）切紧凑列宽：隐藏只写留档的单价列，避免明细表横向滚动
const isCompact = useNarrow('(max-width: 1000px)')

// 物资条目可能上千，逐条下拉选不中：分类 / 产品筛选交给后端缩范围
const {
  keyword,
  categoryId,
  productId,
  candidates,
  totalCount,
  loading: skuLoading,
  reload: reloadSkus,
  reset: resetSkus,
  optionsFor,
  balanceOf
} = useSkuPicker(() => props.skus)

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
})
// 出库 / 盘亏会扣减余额，选 SKU 时就要让用户看到可用量
const showBalance = computed(() => props.resource !== 'inbound')
const submitting = ref(false)
const formRef = ref()
const hint = ref('')

// 映射表而不是拼函数名：扫描脚本能抓到，新增资源时改这里一处
const CREATE_FN = {
  inbound: inventoryCreateInbound,
  outbound: inventoryCreateOutbound,
  adjustment: inventoryCreateAdjustment
}

function newItem() {
  return { sku_id: null, quantity: 1, unit_cost: null, remark: '' }
}

const form = ref({ warehouse_id: null, adjust_type: 'in', remark: '', items: [newItem()] })

const validItemCount = computed(() => form.value.items.filter((item) => item.sku_id).length)

function resetForm() {
  form.value = {
    warehouse_id: props.warehouses[0]?.id ?? null,
    adjust_type: 'in',
    remark: '',
    items: [newItem()]
  }
  hint.value = ''
  resetSkus()
  formRef.value?.clearValidate()
}

watch(visible, (value) => {
  if (value) {
    resetForm()
    // 每次打开都按真实 total 拉一次：父组件只拉了前 100 条，不能用来判断"够不够"
    reloadSkus()
  }
})

function addItem() {
  form.value.items.push(newItem())
}

function removeItem(index) {
  form.value.items.splice(index, 1)
  if (!form.value.items.length) addItem()
}

function skuLabel(sku) {
  return `${sku.sku_no} ${sku.name}`
}

function isOutbound() {
  return props.resource === 'outbound' ||
    (props.resource === 'adjustment' && form.value.adjust_type === 'out')
}

function balanceInsufficient(row) {
  return isOutbound() && row.sku_id && Number(row.quantity) > Number(balanceOf(row.sku_id))
}

function onSkuChange() {
  hint.value = ''
}

async function onSubmit() {
  hint.value = ''
  const rows = form.value.items
  const lastFilled = rows.reduce((last, row, idx) => (row.sku_id ? idx : last), -1)
  // 只忽略「末尾空行」；中间空行说明漏填，静默丢弃会让用户
  // 以为两行都提交了（审查 m-10）
  if (rows.some((row, idx) => !row.sku_id && idx < lastFilled)) {
    hint.value = t('admin.inventory.common.itemSkuRequired')
    return
  }
  const items = rows.filter((item) => item.sku_id)
  if (!items.length) {
    hint.value = t('admin.inventory.common.itemEmpty')
    return
  }
  if (items.some((item) => !item.quantity || Number(item.quantity) <= 0)) {
    hint.value = t('admin.inventory.common.itemQtyRequired')
    return
  }
  if (!form.value.warehouse_id) {
    hint.value = t('admin.inventory.sku.ruleWarehouse')
    return
  }
  // 余额不足交给后端整单回滚（DB 层 CHECK 才是权威）；这里提前提示，不硬拦
  const payload = {
    warehouse_id: form.value.warehouse_id,
    remark: form.value.remark || null,
    items: items.map((item) => ({
      sku_id: item.sku_id,
      quantity: Number(item.quantity),
      // unit_cost 只写留档：不展示、不计算（§3.6）
      ...(item.unit_cost != null ? { unit_cost: item.unit_cost } : {}),
      ...(item.remark ? { remark: item.remark } : {})
    }))
  }
  if (props.resource === 'adjustment') payload.adjust_type = form.value.adjust_type

  submitting.value = true
  try {
    await CREATE_FN[props.resource](payload)
    ElMessage.success(t('admin.inventory.common.created'))
    visible.value = false
    emit('created')
  } catch (e) {
    ElMessage.error(errorMessage(e, { fallbackKey: 'admin.inventory.common.saveFailed' }))
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.items-head { display: flex; align-items: center; justify-content: space-between; margin: 8px 0; }
.wd { width: 260px; }
.full { width: 100%; }
.hint { margin-top: 8px; color: var(--el-color-danger); font-size: 12px; }
.hint.muted { color: var(--el-text-color-secondary); }
.text-danger { color: var(--el-color-danger); font-weight: 600; }
</style>
