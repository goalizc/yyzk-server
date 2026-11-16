<template>
  <div class="page">
    <el-card shadow="never">
      <template #header>
        <div class="head">
          <div class="head-left">
            <span>{{ $t('admin.inventory.sku.title') }}</span>
            <!-- 低库存待办：点一下直接筛出低于阈值的物资（PRD §2.4 的首页待办数落点） -->
            <el-tag
              v-if="lowStockCount > 0"
              type="danger"
              effect="plain"
              class="low-tag"
              @click="showLowStock"
            >
              {{ $t('admin.inventory.sku.lowStockSummary', { n: lowStockCount }) }}
            </el-tag>
          </div>
          <el-button v-if="canWrite" type="primary" @click="openCreate">
            {{ $t('admin.inventory.sku.newSku') }}
          </el-button>
        </div>
      </template>

      <el-form :inline="true" class="filters" @submit.prevent>
        <el-form-item :label="$t('admin.inventory.common.keyword')">
          <el-input
            v-model="filters.keyword"
            :placeholder="$t('admin.inventory.common.keywordPlaceholder')"
            clearable
            class="wd"
            @keyup.enter="reload"
            @clear="reload"
          />
        </el-form-item>
        <el-form-item :label="$t('admin.inventory.sku.filterCategory')">
          <el-select v-model="filters.category_id" clearable filterable class="sm" @change="reload">
            <el-option v-for="c in categoryOptions" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('admin.inventory.sku.filterProduct')">
          <el-select v-model="filters.product_id" clearable filterable class="sm" @change="reload">
            <el-option v-for="p in productOptions" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('admin.inventory.common.status')">
          <el-select v-model="filters.is_active" clearable class="sm" @change="reload">
            <el-option :label="$t('admin.inventory.common.active')" :value="true" />
            <el-option :label="$t('admin.inventory.common.inactive')" :value="false" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-checkbox v-model="filters.low_stock" @change="reload">
            {{ $t('admin.inventory.common.lowStockOnly') }}
          </el-checkbox>
        </el-form-item>
        <el-form-item>
          <el-button @click="onReset">{{ $t('admin.inventory.common.reset') }}</el-button>
        </el-form-item>
      </el-form>

      <ErrorState v-if="loadError" :error="loadError" @retry="load" />
      <el-table v-else v-loading="loading" :data="rows" row-key="id" border>
        <el-table-column prop="sku_no" :label="$t('admin.inventory.sku.colSkuNo')" width="116" />
        <el-table-column prop="name" :label="$t('admin.inventory.sku.colName')" min-width="150" show-overflow-tooltip />
        <el-table-column :label="$t('admin.inventory.sku.colSpec')" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">
            <span :class="{ muted: !row.spec && !row.unit }">{{ specText(row) || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('admin.inventory.sku.colCategories')" min-width="105" show-overflow-tooltip>
          <template #default="{ row }">
            <span :class="{ muted: !row.categories || !row.categories.length }">
              {{ categoriesText(row.categories) || $t('admin.inventory.common.uncategorized') }}
            </span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('admin.inventory.sku.colProducts')" min-width="105" show-overflow-tooltip>
          <template #default="{ row }">
            <span :class="{ muted: !row.products || !row.products.length }">
              {{ productsText(row.products) || $t('admin.inventory.common.noPart') }}
            </span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('admin.inventory.sku.colPart')" min-width="100" show-overflow-tooltip>
          <template #default="{ row }">
            <span :class="{ muted: !row.part_name }">{{ row.part_name || $t('admin.inventory.common.noPart') }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('admin.inventory.sku.colQty')" width="110" align="center">
          <template #default="{ row }">
            <span :class="{ 'text-danger': isLow(row) }">{{ row.quantity }}</span>
            <el-tag v-if="isLow(row)" type="danger" size="small" class="tag">
              {{ $t('admin.inventory.sku.lowStockTag') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="min_stock" :label="$t('admin.inventory.sku.colMinStock')" width="72" align="center" />
        <el-table-column :label="$t('admin.inventory.sku.colStatus')" width="70" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
              {{ row.is_active ? $t('admin.inventory.common.active') : $t('admin.inventory.common.inactive') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="canWrite" :label="$t('admin.inventory.sku.colActions')" width="112" align="center">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">{{ $t('common.action.edit') }}</el-button>
            <el-button v-if="row.is_active" link type="danger" @click="onDisable(row)">
              {{ $t('admin.inventory.common.inactive') }}
            </el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty :description="$t('admin.inventory.common.empty')" />
        </template>
      </el-table>

      <el-pagination
        v-if="!loadError"
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.pageSize"
        class="pager"
        layout="total, sizes, prev, pager, next"
        :page-sizes="[10, 20, 50]"
        :total="pagination.total"
        @current-change="load"
        @size-change="onSizeChange"
      />
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? $t('admin.inventory.sku.editSku') : $t('admin.inventory.sku.newSku')"
      :width="isNarrow ? '92%' : '560px'"
      @closed="resetForm"
    >
      <el-form ref="formRef" :model="form" :rules="rules" :label-width="labelWidth">
        <el-form-item :label="$t('admin.inventory.sku.fieldSkuNo')" prop="sku_no">
          <el-input v-model="form.sku_no" maxlength="50" :disabled="Boolean(editingId)" />
        </el-form-item>
        <el-form-item :label="$t('admin.inventory.sku.fieldName')" prop="name">
          <el-input v-model="form.name" maxlength="100" />
        </el-form-item>
        <el-form-item :label="$t('admin.inventory.sku.fieldWarehouse')" prop="warehouse_id">
          <el-select
            v-model="form.warehouse_id"
            :disabled="Boolean(editingId)"
            :no-data-text="$t('admin.inventory.common.noWarehouse')"
            class="full"
          >
            <el-option v-for="w in warehouses" :key="w.id" :label="w.name" :value="w.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('admin.inventory.sku.fieldSpec')">
          <el-input v-model="form.spec" maxlength="100" />
        </el-form-item>
        <el-form-item :label="$t('admin.inventory.sku.fieldUnit')">
          <el-input v-model="form.unit" maxlength="20" />
        </el-form-item>
        <el-form-item :label="$t('admin.inventory.sku.fieldCategories')">
          <el-select
            v-model="form.category_ids"
            multiple
            clearable
            filterable
            collapse-tags
            collapse-tags-tooltip
            class="full"
            :placeholder="$t('admin.inventory.sku.fieldCategories')"
          >
            <el-option v-for="c in categoryOptions" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('admin.inventory.sku.fieldProducts')">
          <el-select
            v-model="form.product_ids"
            multiple
            clearable
            filterable
            collapse-tags
            collapse-tags-tooltip
            class="full"
            :placeholder="$t('admin.inventory.sku.fieldProducts')"
          >
            <el-option v-for="p in productOptions" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
          <div v-if="productLoaded && !productOptions.length && !productLoadError" class="field-hint">
            {{ $t('admin.inventory.sku.productMissingHint') }}
          </div>
          <div v-else-if="productLoadError" class="field-hint">
            {{ $t('admin.inventory.sku.productsLoadFailed') }}
          </div>
        </el-form-item>
        <el-form-item :label="$t('admin.inventory.sku.fieldPart')">
          <el-select
            v-model="form.part_id"
            clearable
            filterable
            class="full"
            :loading="partLoading"
            :placeholder="$t('admin.inventory.common.partOptional')"
            @visible-change="onPartVisibleChange"
          >
            <el-option v-for="p in partOptions" :key="p.id" :label="p.label" :value="p.id" />
          </el-select>
          <div v-if="partOptionsLoaded && !partOptions.length && !partLoadError" class="field-hint">
            {{ $t('admin.inventory.sku.partMissingHint') }}
          </div>
          <div v-else-if="partLoadError" class="field-hint">
            {{ $t('admin.inventory.sku.partsLoadFailed') }}
          </div>
        </el-form-item>
        <el-form-item :label="$t('admin.inventory.sku.fieldMinStock')">
          <el-input-number v-model="form.min_stock" :min="0" :max="999999" :precision="0" :step-strictly="true" controls-position="right" />
        </el-form-item>
        <el-form-item :label="$t('admin.inventory.common.unitCost')">
          <el-input-number v-model="form.unit_cost" :min="0" :precision="2" controls-position="right" />
          <div class="field-hint">{{ $t('admin.inventory.common.unitCostHint') }}</div>
        </el-form-item>
        <el-form-item :label="$t('admin.inventory.sku.fieldIsActive')">
          <el-switch v-model="form.is_active" />
        </el-form-item>
        <el-form-item :label="$t('admin.inventory.sku.fieldRemark')">
          <el-input v-model="form.remark" type="textarea" maxlength="500" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ $t('common.action.cancel') }}</el-button>
        <el-button type="primary" :loading="submitting" @click="onSubmit">
          {{ $t('common.action.save') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  inventorySkus, inventoryCreateSku, inventoryUpdateSku, inventoryDisableSku, inventoryWarehouses,
  inventoryCategories, inventoryRefProducts, inventoryRefParts, inventorySummary
} from '../../../api/inventory'
import ErrorState from '../../../components/ErrorState.vue'
import { errorMessage } from '../../../utils/error'
import { hasPermission } from '../../../utils/permissions'
import { useNarrow } from '../../../utils/viewport'
import { useFormLabelWidth } from '../../../utils/formLabel'

const { t } = useI18n()
const canWrite = computed(() => hasPermission('inventory:sku:write'))
// 最长标签「关联产品（可多选）」/ "Low-stock threshold"，给足宽度避免折行
// 最长中文标签「关联产品（可多选）」9 个全角字约 126px，加 label 右内边距留到 160px；
// 英文 "Low-stock threshold" 实测约 150px，留到 190px。
const labelWidth = useFormLabelWidth('160px', '190px')
const isNarrow = useNarrow()

const rows = ref([])
const loading = ref(false)
const loadError = ref('')
const lowStockCount = ref(0)
const pagination = reactive({ page: 1, pageSize: 20, total: 0 })
const filters = reactive({
  keyword: '', category_id: null, product_id: null, is_active: null, low_stock: false
})
const warehouses = ref([])
const partOptions = ref([])
const categoryOptions = ref([])
const productOptions = ref([])

const dialogVisible = ref(false)
const editingId = ref(null)
// 打开编辑弹窗时的原始启用状态：用于判断「这次保存是否在停用」
const editingActive = ref(true)
const submitting = ref(false)
const formRef = ref()
const emptyForm = () => ({
  sku_no: '', name: '', warehouse_id: null, spec: '', unit: '件', // i18n-ignore 单位是与后端约定的数据字段默认值（可被用户改成英文单位），非界面文案
  category_ids: [], product_ids: [],
  part_id: null, min_stock: 0, unit_cost: null, is_active: true, remark: ''
})
const form = reactive(emptyForm())

const rules = computed(() => ({
  sku_no: [{ required: true, message: t('admin.inventory.sku.ruleSkuNo'), trigger: 'blur' }],
  name: [{ required: true, message: t('admin.inventory.sku.ruleName'), trigger: 'blur' }],
  warehouse_id: [{ required: true, message: t('admin.inventory.sku.ruleWarehouse'), trigger: 'change' }]
}))

function isLow(row) {
  // 停用 SKU 不再标红：与后端 /skus/low-stock 和 /summary 的口径保持一致
  return row.is_active !== false && row.min_stock > 0 && row.quantity < row.min_stock
}

function categoriesText(categories) {
  return (categories || []).map((c) => c.name).join(' / ')
}

/** 规格列合并了单位（「40×30 热敏 · 卷」）：单位单列信息量低且挤占宽度。 */
function specText(row) {
  return [row.spec, row.unit].filter(Boolean).join(' · ')
}

function productsText(products) {
  return (products || []).map((p) => p.name).join(' / ')
}

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const params = {
      page: pagination.page,
      page_size: pagination.pageSize,
      ...(filters.keyword.trim() ? { keyword: filters.keyword.trim() } : {}),
      ...(filters.category_id === null ? {} : { category_id: filters.category_id }),
      ...(filters.product_id === null ? {} : { product_id: filters.product_id }),
      ...(filters.is_active === null ? {} : { is_active: filters.is_active }),
      ...(filters.low_stock ? { low_stock: true } : {})
    }
    const data = await inventorySkus(params)
    rows.value = data.items
    pagination.total = data.total
    if (!data.items.length && pagination.page > 1) {
      pagination.page -= 1
      return load()
    }
  } catch (e) {
    rows.value = []
    pagination.total = 0
    loadError.value = errorMessage(e, { fallbackKey: 'admin.inventory.common.loadFailed' })
  } finally {
    loading.value = false
  }
}

function reload() {
  pagination.page = 1
  load()
}

function onSizeChange() {
  pagination.page = 1
  load()
}

function onReset() {
  filters.keyword = ''
  filters.category_id = null
  filters.product_id = null
  filters.is_active = null
  filters.low_stock = false
  reload()
}

async function loadSummary() {
  try {
    const data = await inventorySummary()
    lowStockCount.value = data.low_stock_count || 0
  } catch {
    lowStockCount.value = 0
  }
}

function showLowStock() {
  filters.low_stock = true
  reload()
}

async function loadWarehouses() {
  try {
    const data = await inventoryWarehouses({ page: 1, page_size: 100 })
    warehouses.value = data.items || []
  } catch (e) {
    // 静默清空会让「新建 SKU」弹窗里没有仓库可选，用户只能提交后才看到
    // 「请选择仓库」，错误原因完全看不到
    warehouses.value = []
    ElMessage.error(errorMessage(e, { fallbackKey: 'admin.inventory.common.loadFailed' }))
  }
}

/** 分类下拉：只取启用的分类用于录入与筛选（停用分类仍保留在历史 SKU 上）。 */
async function loadCategoryOptions() {
  try {
    const data = await inventoryCategories({ page: 1, page_size: 100, is_active: true })
    categoryOptions.value = data.items || []
  } catch (e) {
    categoryOptions.value = []
    ElMessage.error(errorMessage(e, { fallbackKey: 'admin.inventory.common.loadFailed' }))
  }
}

/** 产品下拉：库存域引用端点（只读），仓管也有权限；关联可选、不强制。
 *  不能改用 `/admin/products`——那要 product:read，仓管没有，下拉会恒为空。 */
async function loadProductOptions() {
  productLoadError.value = false
  try {
    productOptions.value = (await inventoryRefProducts()) || []
  } catch {
    productOptions.value = []
    productLoadError.value = true
  } finally {
    productLoaded.value = true
  }
}

/** 零件下拉：省略 product_id 一次取回全部零件（含产品名），避免按产品 N+1 请求。
 *  首次展开下拉时再加载，挂载即拉会拖慢首屏。 */
const partLoading = ref(false)
const partOptionsLoaded = ref(false)
const partLoadError = ref(false)
const productLoaded = ref(false)
const productLoadError = ref(false)

async function loadPartOptions() {
  if (partLoading.value) return
  partLoading.value = true
  partLoadError.value = false
  try {
    const parts = (await inventoryRefParts()) || []
    partOptions.value = parts.map((part) => ({
      id: part.id,
      label: `${part.product_name || ''} / ${part.name}`
    }))
    partOptionsLoaded.value = true
  } catch {
    partOptions.value = []
    partLoadError.value = true
  } finally {
    partLoading.value = false
  }
}

function onPartVisibleChange(visible) {
  if (visible && !partOptionsLoaded.value) loadPartOptions()
}

function resetForm() {
  editingId.value = null
  editingActive.value = true
  Object.assign(form, emptyForm(), { warehouse_id: warehouses.value[0]?.id ?? null })
  formRef.value?.clearValidate()
}

function openCreate() {
  resetForm()
  dialogVisible.value = true
}

function openEdit(row) {
  resetForm()
  editingId.value = row.id
  editingActive.value = row.is_active
  Object.assign(form, {
    sku_no: row.sku_no,
    name: row.name,
    warehouse_id: row.warehouse_id,
    spec: row.spec || '',
    unit: row.unit || '件', // i18n-ignore 数据字段默认值，非界面文案
    category_ids: (row.categories || []).map((c) => c.id),
    product_ids: (row.products || []).map((p) => p.id),
    part_id: row.part_id ?? null,
    min_stock: row.min_stock,
    unit_cost: null, // 只写不留档：编辑时不回显，避免误以为能改价
    is_active: row.is_active,
    remark: row.remark || ''
  })
  dialogVisible.value = true
}

function payloadFromForm() {
  const base = {
    name: form.name.trim(),
    spec: form.spec || null,
    unit: form.unit || '件', // i18n-ignore 数据字段默认值，非界面文案
    category_ids: [...form.category_ids],
    product_ids: [...form.product_ids],
    part_id: form.part_id ?? null,
    min_stock: form.min_stock,
    is_active: form.is_active,
    remark: form.remark || null
  }
  // unit_cost 为 null 时创建也要带上（可选写入留档），编辑时同理不清除旧值
  if (form.unit_cost != null) base.unit_cost = form.unit_cost
  if (!editingId.value) {
    base.sku_no = form.sku_no.trim()
    base.warehouse_id = form.warehouse_id
    base.min_stock = form.min_stock
  }
  return base
}

async function onSubmit() {
  // el-dialog 懒渲染：未打开时 formRef 为 null，validate() 会静默 return
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  // 编辑弹窗里的停用开关与列表「停用」是同一件事（后端同样校验 SKU_IN_USE），
  // 但这里原本没有二次确认，误关就再也建不了单（审查 m-09）。
  if (editingId.value && editingActive.value && !form.is_active) {
    try {
      await ElMessageBox.confirm(
        t('admin.inventory.sku.disableConfirm', { name: form.name }),
        t('admin.inventory.sku.disableTitle'),
        { type: 'warning' }
      )
    } catch {
      return
    }
  }
  submitting.value = true
  try {
    const payload = payloadFromForm()
    if (editingId.value) {
      await inventoryUpdateSku(editingId.value, payload)
      ElMessage.success(t('admin.inventory.common.saved'))
    } else {
      await inventoryCreateSku(payload)
      ElMessage.success(t('admin.inventory.common.saved'))
    }
    dialogVisible.value = false
    await Promise.all([load(), loadSummary()])
  } catch (e) {
    ElMessage.error(errorMessage(e, { fallbackKey: 'admin.inventory.common.saveFailed' }))
  } finally {
    submitting.value = false
  }
}

async function onDisable(row) {
  try {
    await ElMessageBox.confirm(
      t('admin.inventory.sku.disableConfirm', { name: row.name }),
      t('admin.inventory.sku.disableTitle'),
      { type: 'warning' }
    )
  } catch {
    return
  }
  try {
    await inventoryDisableSku(row.id)
    ElMessage.success(t('admin.inventory.sku.disableSuccess'))
    await Promise.all([load(), loadSummary()])
  } catch (e) {
    ElMessage.error(errorMessage(e, { fallbackKey: 'admin.inventory.sku.disableFailed' }))
  }
}

onMounted(() => {
  loadWarehouses()
  loadCategoryOptions()
  loadProductOptions()
  loadSummary()
  load()
})
</script>

<style scoped>
.page { display: flex; flex-direction: column; gap: 16px; }
.head { display: flex; align-items: center; justify-content: space-between; }
.head-left { display: flex; align-items: center; gap: 8px; }
.low-tag { cursor: pointer; }
.filters { margin-bottom: 4px; }
.pager { margin-top: 16px; justify-content: flex-end; }
.wd { width: 200px; }
.sm { width: 130px; }
.full { width: 100%; }
.tag { margin-left: 6px; }
.muted { color: var(--el-text-color-secondary); }
.text-danger { color: var(--el-color-danger); font-weight: 600; }
.field-hint { font-size: 12px; color: var(--el-text-color-secondary); line-height: 1.4; margin-top: 2px; }
</style>
