<template>
  <div class="page">
    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>{{ $t('admin.page.parts') }}</span>
          <div class="head-actions">
            <el-select
              v-model="productId"
              :placeholder="$t('admin.part.selectProduct')"
              filterable
              class="product"
              :loading="loadingProducts"
              @change="onProductChange"
            >
              <el-option
                v-for="item in products"
                :key="item.id"
                :label="`${item.name}（${item.model}）`"
                :value="item.id"
              />
            </el-select>
            <el-button v-if="canWrite" type="primary" :disabled="!productId" @click="openCreate">{{ $t('admin.part.newPart') }}</el-button>
          </div>
        </div>
      </template>

      <el-alert
        v-if="!loadingProducts && !products.length"
        type="info"
        :closable="false"
        show-icon
        :title="$t('admin.part.noProductsAlert')"
      />

      <ErrorState v-if="loadError" :error="loadError" @retry="loadParts" />
      <el-table
        v-else
        v-loading="loading"
        :data="rows"
        row-key="id"
        border
        @row-click="onRowClick"
      >
        <el-table-column prop="part_no" :label="$t('admin.part.colPartNo')" width="150">
          <template #default="{ row }">
            <span :class="{ muted: !row.part_no }">{{ row.part_no || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="name" :label="$t('admin.part.colName')" min-width="160" />
        <el-table-column :label="$t('admin.part.colGroup')" width="140">
          <template #default="{ row }">
            <el-tag v-if="row.group_name" size="small" type="info">{{ row.group_name }}</el-tag>
            <span v-else class="muted">{{ $t('admin.part.ungrouped') }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="sort_order" :label="$t('admin.part.colSort')" width="80" align="center" />
        <el-table-column prop="fault_count" :label="$t('admin.part.colFaultCount')" width="90" align="center" />
        <el-table-column v-if="canWrite" :label="$t('admin.part.colActions')" width="130" align="center">
          <template #default="{ row }">
            <el-button link type="primary" @click.stop="openEdit(row)">{{ $t('common.action.edit') }}</el-button>
            <el-button link type="danger" @click.stop="onDelete(row)">{{ $t('common.action.delete') }}</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty :description="productId ? $t('admin.part.emptyWithProduct') : $t('admin.part.emptyNoProduct')" />
        </template>
      </el-table>

      <el-pagination
        v-if="!loadError && pagination.total > pagination.pageSize"
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.pageSize"
        class="pager"
        layout="total, sizes, prev, pager, next"
        :page-sizes="[20, 50]"
        :total="pagination.total"
        @current-change="loadParts"
        @size-change="onSizeChange"
      />
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? $t('admin.part.dialogEdit') : $t('admin.part.dialogCreate')"
      width="480px"
      @closed="resetForm"
    >
      <el-form ref="formRef" :model="form" :rules="rules" :label-width="labelWidth">
        <el-form-item :label="$t('admin.part.product')">
          <!-- 零件不可跨产品：产品由页面带入，弹窗内只读展示 -->
          <span class="readonly">{{ currentProductLabel }}</span>
        </el-form-item>
        <el-form-item :label="$t('admin.part.partNo')" prop="part_no">
          <el-input v-model="form.part_no" maxlength="50" :placeholder="$t('admin.part.partNoPlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('admin.part.name')" prop="name">
          <el-input v-model="form.name" maxlength="100" :placeholder="$t('admin.part.namePlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('admin.part.group')" prop="group_name">
          <el-input v-model="form.group_name" maxlength="50" :placeholder="$t('admin.part.groupPlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('admin.part.sortOrder')" prop="sort_order">
          <el-input-number v-model="form.sort_order" :min="0" :max="9999" controls-position="right" />
          <span class="hint">{{ $t('admin.part.sortHint') }}</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ $t('common.action.cancel') }}</el-button>
        <el-button type="primary" :loading="submitting" @click="onSubmit">{{ $t('common.action.save') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  adminCreatePart,
  adminDeletePart,
  adminListParts,
  adminListProducts,
  adminUpdatePart
} from '../../../api/admin'
import ErrorState from '../../../components/ErrorState.vue'
import { errorMessage } from '../../../utils/error'
import { hasPermission } from '../../../utils/permissions'
import { useFormLabelWidth } from '../../../utils/formLabel'

const { t } = useI18n()
const canWrite = computed(() => hasPermission('part:write'))
const labelWidth = useFormLabelWidth('88px', '120px')

const products = ref([])
const loadingProducts = ref(false)
const productId = ref(null)

const rows = ref([])
const loading = ref(false)
const loadError = ref('')
const pagination = reactive({ page: 1, pageSize: 20, total: 0 })

const dialogVisible = ref(false)
const editingId = ref(null)
const submitting = ref(false)
const formRef = ref()

const form = reactive({ part_no: '', name: '', group_name: '', sort_order: 0 })

// computed：语言切换后校验文案跟着变
const rules = computed(() => ({
  name: [{ required: true, message: t('admin.part.ruleName'), trigger: 'blur' }]
}))

const currentProductLabel = computed(() => {
  const item = products.value.find((p) => p.id === productId.value)
  return item ? `${item.name}（${item.model}）` : '-'
})

async function loadProducts() {
  loadingProducts.value = true
  try {
    // 后台接口含已下架产品：下架产品下的零件仍需维护
    const data = await adminListProducts({ page: 1, page_size: 100 })
    products.value = data.items
    if (!productId.value && data.items.length) {
      productId.value = data.items[0].id
      await loadParts()
    }
  } catch (e) {
    ElMessage.error(errorMessage(e, { fallbackKey: 'admin.part.productLoadFailed' }))
  } finally {
    loadingProducts.value = false
  }
}

// 请求序号：快速连续切换产品时，先发的请求可能后到并覆盖新结果
let partsSeq = 0

async function loadParts() {
  if (!productId.value) return
  const my = (partsSeq += 1)
  loading.value = true
  loadError.value = ''
  try {
    const data = await adminListParts({
      product_id: productId.value,
      page: pagination.page,
      page_size: pagination.pageSize
    })
    if (my !== partsSeq) return // 已有更新的请求，丢弃本次结果
    rows.value = data.items
    pagination.total = data.total
    if (!data.items.length && pagination.page > 1) {
      pagination.page -= 1
      return loadParts()
    }
  } catch (e) {
    if (my !== partsSeq) return
    rows.value = []
    pagination.total = 0
    loadError.value = errorMessage(e, { fallbackKey: 'admin.part.loadFailed' })
  } finally {
    if (my === partsSeq) loading.value = false
  }
}

function onProductChange() {
  pagination.page = 1
  rows.value = []
  loadParts()
}

function onSizeChange() {
  pagination.page = 1
  loadParts()
}

function resetForm() {
  editingId.value = null
  Object.assign(form, { part_no: '', name: '', group_name: '', sort_order: 0 })
  formRef.value?.clearValidate()
}

function openCreate() {
  if (!productId.value) {
    ElMessage.warning(t('admin.part.selectProductFirst'))
    return
  }
  resetForm()
  dialogVisible.value = true
}

function openEdit(row) {
  resetForm()
  editingId.value = row.id
  Object.assign(form, {
    part_no: row.part_no || '',
    name: row.name,
    group_name: row.group_name || '',
    sort_order: row.sort_order
  })
  dialogVisible.value = true
}

async function onSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  const payload = {
    part_no: form.part_no.trim() || null,
    name: form.name.trim(),
    group_name: form.group_name.trim() || null,
    sort_order: form.sort_order
  }
  try {
    if (editingId.value) {
      await adminUpdatePart(editingId.value, payload)
      ElMessage.success(t('admin.part.saved'))
    } else {
      await adminCreatePart({ ...payload, product_id: productId.value })
      ElMessage.success(t('admin.part.created'))
    }
    dialogVisible.value = false
    await loadParts()
  } catch (e) {
    ElMessage.error(errorMessage(e))
  } finally {
    submitting.value = false
  }
}

async function onDelete(row) {
  // 与产品页保持一致的顺序：先判拦截（只提示、不发请求），再让用户确认删除。
  // 反过来的话用户要先点"确认删除"才被告知不能删，白白多一次交互。
  // 仍以后端 DELETE_BLOCKED 为准（fault_count 可能已过期）。
  if (row.fault_count > 0) {
    try {
      await ElMessageBox.confirm(
        t('admin.part.deleteBlocked', row.fault_count, { name: row.name }),
        t('admin.part.cannotDelete'),
        { type: 'warning', confirmButtonText: t('admin.part.gotIt'), showCancelButton: false }
      )
    } catch {
      // 关闭弹窗，无需处理
    }
    return
  }

  try {
    await ElMessageBox.confirm(
      t('admin.part.deleteConfirm', { name: row.name }),
      t('common.confirm.deleteTitle'),
      { type: 'warning', confirmButtonText: t('common.confirm.delete'), cancelButtonText: t('common.action.cancel') }
    )
  } catch {
    return
  }

  try {
    await adminDeletePart(row.id)
    ElMessage.success(t('admin.part.deleted'))
    await loadParts()
  } catch (e) {
    // DELETE_BLOCKED 的 detail 带故障条数，原文展示
    ElMessage.error(errorMessage(e, { fallbackKey: 'admin.part.deleteFailed' }))
  }
}

function onRowClick(row) {
  if (!canWrite.value) return
  openEdit(row)
}

onMounted(loadProducts)
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.head-actions {
  display: flex;
  gap: 8px;
}

.product {
  width: 240px;
}

.muted {
  color: #a8abb2;
}

.readonly {
  color: #606266;
}

.pager {
  margin-top: 16px;
  justify-content: flex-end;
}

.hint {
  margin-left: 8px;
  color: #a8abb2;
  font-size: 12px;
}

:deep(.el-table__row) {
  cursor: pointer;
}
</style>
