<template>
  <el-dialog
    v-model="visible"
    :title="title || $t('admin.inventory.common.editDoc')"
    :width="isNarrow ? '94%' : 'min(900px, 94vw)'"
    @closed="resetForm"
  >
    <el-alert
      :closable="false"
      type="info"
      :title="$t('admin.inventory.common.editDocHint')"
      class="tip"
    />

    <el-form ref="formRef" :label-width="labelWidth">
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
      <el-button link type="primary" @click="addItem">
        {{ $t('admin.inventory.common.addItem') }}
      </el-button>
    </div>
    <el-table :data="form.items" border size="small">
      <el-table-column :label="$t('admin.inventory.common.sku')" :min-width="isCompact ? 180 : 250">
        <template #default="{ row }">
          <el-select v-model="row.sku_id" filterable class="full" @change="hint = ''">
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
          <el-input-number
            v-model="row.quantity"
            class="full"
            :min="1"
            :max="999999"
            :precision="0"
            :step-strictly="true"
            size="small"
            controls-position="right"
          />
        </template>
      </el-table-column>
      <el-table-column
        v-if="isOutbound"
        :label="$t('admin.inventory.common.balance')"
        :width="isCompact ? 90 : 110"
        align="center"
      >
        <template #default="{ row }">
          <span :class="{ 'text-danger': balanceInsufficient(row) }">{{ balanceOf(row.sku_id) }}</span>
        </template>
      </el-table-column>
      <el-table-column :label="$t('admin.inventory.common.remark')" :min-width="isCompact ? 120 : 180">
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

    <template #footer>
      <el-button @click="visible = false">{{ $t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="submitting" @click="onSubmit">
        {{ $t('common.action.save') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { inventoryUpdateDocument } from '../../../api/inventory'
import { errorMessage } from '../../../utils/error'
import { useNarrow } from '../../../utils/viewport'
import { useFormLabelWidth } from '../../../utils/formLabel'
import SkuFilterBar from './SkuFilterBar.vue'
import { useSkuPicker } from './useSkuPicker'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  // 单据详情（含 items: sku_id / sku_no / sku_name / quantity / remark）
  doc: { type: Object, default: null },
  // 首屏兜底用的启用中 SKU；筛选后的候选由 picker 自己拉
  skus: { type: Array, default: () => [] },
  categories: { type: Array, default: () => [] },
  products: { type: Array, default: () => [] },
  title: { type: String, default: '' }
})
const emit = defineEmits(['update:modelValue', 'updated'])

const { t } = useI18n()
const labelWidth = useFormLabelWidth('88px', '120px')
const isNarrow = useNarrow()
// 窄窗口切紧凑列宽，保证改单明细同样不横向滚动
const isCompact = useNarrow('(max-width: 1000px)')

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
  balanceOf,
  remember
} = useSkuPicker(() => props.skus)

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
})
const isOutbound = computed(() => props.doc?.doc_type === 'outbound')
const submitting = ref(false)
const formRef = ref()
const hint = ref('')

function newItem() {
  return { sku_id: null, quantity: 1, remark: '' }
}

const form = ref({ remark: '', items: [newItem()] })

const validItemCount = computed(() => form.value.items.filter((item) => item.sku_id).length)

// 单据里的 SKU 可能已停用（不在启用清单里），先登记进 known，
// 否则下拉里既没有选项、余额也拿不到，用户会看到空白框
function rememberDocItems(doc) {
  remember(
    (doc?.items || []).map((it) => ({
      id: it.sku_id,
      sku_no: it.sku_no,
      name: it.sku_name,
      quantity: 0
    })),
    { keepExisting: true }
  )
}

function resetForm() {
  const doc = props.doc
  resetSkus()
  rememberDocItems(doc)
  form.value = {
    remark: doc?.remark || '',
    items: (doc?.items || []).map((it) => ({
      sku_id: it.sku_id,
      quantity: it.quantity,
      remark: it.remark || ''
    }))
  }
  if (!form.value.items.length) form.value.items.push(newItem())
  hint.value = ''
  formRef.value?.clearValidate()
}

// immediate：父组件若以「已打开」状态挂载（或测试直接传 true），也要按 doc 回填
watch(
  visible,
  (value) => {
    if (value) {
      resetForm()
      reloadSkus()
    }
  },
  { immediate: true }
)

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

function balanceInsufficient(row) {
  return row.sku_id && Number(row.quantity) > Number(balanceOf(row.sku_id))
}

async function onSubmit() {
  hint.value = ''
  const rows = form.value.items
  const lastFilled = rows.reduce((last, row, idx) => (row.sku_id ? idx : last), -1)
  // 与新建单据同规则：中间空行是漏填，不能静默丢
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
  // unit_cost 不在此处提交：后端按 SKU 沿用旧档案，避免把只写留档的成本抹掉
  const payload = {
    remark: form.value.remark || '',
    items: items.map((item) => ({
      sku_id: item.sku_id,
      quantity: Number(item.quantity),
      ...(item.remark ? { remark: item.remark } : {})
    }))
  }
  // 改单会按差额补记更正流水，是权威台账变更：和冲正一样要二次确认，
  // 避免误点「保存」直接改余额（审查 M-04）。
  try {
    await ElMessageBox.confirm(
      t('admin.inventory.common.editConfirm', { docNo: props.doc.doc_no }),
      t('admin.inventory.common.confirmTitle'),
      { type: 'warning' }
    )
  } catch {
    return
  }
  submitting.value = true
  try {
    const updated = await inventoryUpdateDocument(props.doc.id, payload)
    ElMessage.success(t('admin.inventory.common.editSuccess'))
    visible.value = false
    emit('updated', updated)
  } catch (e) {
    ElMessage.error(errorMessage(e, { fallbackKey: 'admin.inventory.common.editFailed' }))
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.tip { margin-bottom: 12px; }
.items-head { display: flex; align-items: center; justify-content: space-between; margin: 8px 0; }
.full { width: 100%; }
.hint { margin-top: 8px; color: var(--el-color-danger); font-size: 12px; }
.text-danger { color: var(--el-color-danger); font-weight: 600; }
</style>
