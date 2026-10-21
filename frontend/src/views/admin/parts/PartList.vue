<template>
  <div class="page">
    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>零件管理</span>
          <div class="head-actions">
            <el-select
              v-model="productId"
              placeholder="请选择产品"
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
            <el-button type="primary" :disabled="!productId" @click="openCreate">新增零件</el-button>
          </div>
        </div>
      </template>

      <el-alert
        v-if="!loadingProducts && !products.length"
        type="info"
        :closable="false"
        show-icon
        title="还没有产品，请先到「产品管理」新增产品，再录入零件。"
      />

      <ErrorState v-if="loadError" :error="loadError" @retry="loadParts" />
      <el-table
        v-else
        v-loading="loading"
        :data="rows"
        row-key="id"
        border
        @row-click="openEdit"
      >
        <el-table-column prop="part_no" label="编号" width="150">
          <template #default="{ row }">
            <span :class="{ muted: !row.part_no }">{{ row.part_no || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="名称" min-width="160" />
        <el-table-column label="分组" width="140">
          <template #default="{ row }">
            <el-tag v-if="row.group_name" size="small" type="info">{{ row.group_name }}</el-tag>
            <span v-else class="muted">未分组</span>
          </template>
        </el-table-column>
        <el-table-column prop="sort_order" label="排序" width="80" align="center" />
        <el-table-column prop="fault_count" label="故障数" width="90" align="center" />
        <el-table-column label="操作" width="130" align="center">
          <template #default="{ row }">
            <el-button link type="primary" @click.stop="openEdit(row)">编辑</el-button>
            <el-button link type="danger" @click.stop="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty :description="productId ? '该产品下暂无零件' : '请先选择产品'" />
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
      :title="editingId ? '编辑零件' : '新增零件'"
      width="480px"
      @closed="resetForm"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="88px">
        <el-form-item label="所属产品">
          <!-- 零件不可跨产品：产品由页面带入，弹窗内只读展示 -->
          <span class="readonly">{{ currentProductLabel }}</span>
        </el-form-item>
        <el-form-item label="零件编号" prop="part_no">
          <el-input v-model="form.part_no" maxlength="50" placeholder="如：P-X1-001" />
        </el-form-item>
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" maxlength="100" placeholder="如：主刷模组" />
        </el-form-item>
        <el-form-item label="分组" prop="group_name">
          <el-input v-model="form.group_name" maxlength="50" placeholder="如：动力系统（可自由输入）" />
        </el-form-item>
        <el-form-item label="排序" prop="sort_order">
          <el-input-number v-model="form.sort_order" :min="0" :max="9999" controls-position="right" />
          <span class="hint">数字越小越靠前</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="onSubmit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  adminCreatePart,
  adminDeletePart,
  adminListParts,
  adminListProducts,
  adminUpdatePart
} from '../../../api/admin'
import ErrorState from '../../../components/ErrorState.vue'
import { errorText } from '../../../utils/admin'

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

const rules = {
  name: [{ required: true, message: '请输入零件名称', trigger: 'blur' }]
}

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
    ElMessage.error(errorText(e, '产品列表加载失败'))
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
    loadError.value = errorText(e, '零件列表加载失败')
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
    ElMessage.warning('请先选择产品')
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
      ElMessage.success('已保存')
    } else {
      await adminCreatePart({ ...payload, product_id: productId.value })
      ElMessage.success('已新增')
    }
    dialogVisible.value = false
    await loadParts()
  } catch (e) {
    ElMessage.error(errorText(e))
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
        `零件「${row.name}」下有 ${row.fault_count} 条故障，需先迁移或删除故障后才能删除本零件。`,
        '无法删除',
        { type: 'warning', confirmButtonText: '知道了', showCancelButton: false }
      )
    } catch {
      // 关闭弹窗，无需处理
    }
    return
  }

  try {
    await ElMessageBox.confirm(
      `确认删除零件「${row.name}」？删除后不可恢复。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }

  try {
    await adminDeletePart(row.id)
    ElMessage.success('已删除')
    await loadParts()
  } catch (e) {
    // DELETE_BLOCKED 的 detail 带故障条数，原文展示
    ElMessage.error(errorText(e, '删除失败'))
  }
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
