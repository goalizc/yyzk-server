<template>
  <div class="page">
    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>产品管理</span>
          <div class="head-actions">
            <el-input
              v-model="filters.keyword"
              placeholder="搜索名称或型号"
              clearable
              class="kw"
              @input="onKeywordInput"
              @clear="reload"
            />
            <el-select
              v-model="filters.isActive"
              placeholder="全部状态"
              clearable
              class="status"
              @change="reload"
            >
              <el-option label="已上架" :value="true" />
              <el-option label="已下架" :value="false" />
            </el-select>
            <el-button v-if="canWrite" type="primary" @click="openCreate">新增产品</el-button>
          </div>
        </div>
      </template>

      <ErrorState v-if="loadError" :error="loadError" @retry="load" />
      <el-table
        v-else
        v-loading="loading"
        :data="rows"
        row-key="id"
        border
        @row-click="onRowClick"
      >
        <el-table-column label="名称 / 型号" min-width="200">
          <template #default="{ row }">
            <div class="name">{{ row.name }}</div>
            <div class="model">{{ row.model }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="line_name" label="产品线" width="120">
          <template #default="{ row }">{{ row.line_name || '-' }}</template>
        </el-table-column>
        <el-table-column prop="fault_count" label="故障数" width="90" align="center" />
        <el-table-column label="状态" width="110" align="center">
          <template #default="{ row }">
            <!-- 切换即保存；接口失败要把开关拨回去，否则页面状态与库不一致 -->
            <el-switch
              :model-value="row.is_active"
              :disabled="!canWrite"
              :loading="togglingId === row.id"
              inline-prompt
              active-text="上架"
              inactive-text="下架"
              @click.stop
              @change="(value) => onToggleActive(row, value)"
            />
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="120">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column v-if="canWrite" label="操作" width="130" align="center">
          <template #default="{ row }">
            <el-button link type="primary" @click.stop="openEdit(row)">编辑</el-button>
            <el-button link type="danger" @click.stop="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无产品，点击右上角「新增产品」录入第一个" />
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
      :title="editingId ? '编辑产品' : '新增产品'"
      width="520px"
      @closed="resetForm"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="88px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" maxlength="100" placeholder="如：智能扫地机器人" />
        </el-form-item>
        <el-form-item label="型号" prop="model" :error="modelError">
          <!-- 409 MODEL_DUPLICATED 只在这个字段下内联提示，不整页报错 -->
          <el-input v-model="form.model" maxlength="50" placeholder="如：X1" @input="onModelInput" />
        </el-form-item>
        <el-form-item label="产品线" prop="line_id">
          <el-select v-model="form.line_id" placeholder="请选择产品线" class="line-select">
            <el-option
              v-for="line in lines"
              :key="line.id"
              :label="line.is_active ? line.name : `${line.name}（已停用）`"
              :value="line.id"
              :disabled="!line.is_active && line.id !== form.line_id"
            />
          </el-select>
          <el-button v-if="canManageLines" link type="primary" class="manage" @click="$router.push('/admin/product-lines')">
            管理产品线
          </el-button>
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model="form.description" type="textarea" :rows="3" maxlength="500" show-word-limit />
        </el-form-item>
        <el-form-item label="排序" prop="sort_order">
          <el-input-number v-model="form.sort_order" :min="0" :max="9999" controls-position="right" />
          <span class="hint">数字越小越靠前</span>
        </el-form-item>
        <el-form-item label="是否上架" prop="is_active">
          <el-switch v-model="form.is_active" inline-prompt active-text="上架" inactive-text="下架" />
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
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  adminCreateProduct,
  adminDeleteProduct,
  adminListProductLines,
  adminListProducts,
  adminUpdateProduct
} from '../../../api/admin'
import ErrorState from '../../../components/ErrorState.vue'
import { errorCode, errorText } from '../../../utils/admin'
import { formatDate } from '../../../utils/format'
import { hasPermission } from '../../../utils/permissions'

const canWrite = computed(() => hasPermission('product:write'))
const canManageLines = hasPermission('product_line:read')
const lines = ref([])

const rows = ref([])
const loading = ref(false)
const loadError = ref('')
const pagination = reactive({ page: 1, pageSize: 20, total: 0 })
const filters = reactive({ keyword: '', isActive: null })

const dialogVisible = ref(false)
const editingId = ref(null)
const submitting = ref(false)
const togglingId = ref(null)
// 型号撞号的后端文案（409 MODEL_DUPLICATED）：只挂在型号字段下，不弹全局错误
const modelError = ref('')
const formRef = ref()

const form = reactive({
  name: '',
  model: '',
  line_id: null,
  description: '',
  is_active: true,
  sort_order: 0
})

const rules = {
  name: [{ required: true, message: '请输入产品名称', trigger: 'blur' }],
  model: [{ required: true, message: '请输入型号', trigger: 'blur' }],
  line_id: [{ required: true, message: '请选择产品线', trigger: 'change' }]
}

let keywordTimer = null

async function loadLines() {
  try {
    // 拉全量：编辑已停用产品线下的产品时，当前线仍要能回显
    lines.value = (await adminListProductLines()).items
  } catch {
    lines.value = []
  }
}

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const params = {
      page: pagination.page,
      page_size: pagination.pageSize,
      ...(filters.keyword.trim() ? { keyword: filters.keyword.trim() } : {}),
      ...(filters.isActive === null || filters.isActive === undefined
        ? {}
        : { is_active: filters.isActive })
    }
    const data = await adminListProducts(params)
    rows.value = data.items
    pagination.total = data.total
    // 删除最后一页最后一条后当前页可能越界，回退一页重新拉，避免显示空表但 total>0
    if (!data.items.length && pagination.page > 1) {
      pagination.page -= 1
      return load()
    }
  } catch (e) {
    rows.value = []
    pagination.total = 0
    // 首屏/刷新失败给出可重试的错误态，不再只弹一条转瞬即逝的提示
    loadError.value = errorText(e, '产品列表加载失败')
  } finally {
    loading.value = false
  }
}

function reload() {
  pagination.page = 1
  load()
}

function onKeywordInput() {
  clearTimeout(keywordTimer)
  keywordTimer = setTimeout(reload, 300)
}

function onSizeChange() {
  pagination.page = 1
  load()
}

function onModelInput() {
  // 一改型号就撤掉撞号提示
  if (!modelError.value) return
  modelError.value = ''
  formRef.value?.clearValidate(['model'])
}

function resetForm() {
  editingId.value = null
  modelError.value = ''
  Object.assign(form, {
    name: '',
    model: '',
    line_id: null,
    description: '',
    is_active: true,
    sort_order: 0
  })
  formRef.value?.clearValidate()
}

function openCreate() {
  resetForm()
  dialogVisible.value = true
}

function openEdit(row) {
  resetForm()
  editingId.value = row.id
  Object.assign(form, {
    name: row.name,
    model: row.model,
    line_id: row.line_id,
    description: row.description || '',
    is_active: row.is_active,
    sort_order: row.sort_order
  })
  dialogVisible.value = true
}

async function onSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  const payload = {
    name: form.name.trim(),
    model: form.model.trim(),
    line_id: form.line_id,
    description: form.description || null,
    is_active: form.is_active,
    sort_order: form.sort_order
  }
  try {
    if (editingId.value) {
      await adminUpdateProduct(editingId.value, payload)
      ElMessage.success('已保存')
    } else {
      await adminCreateProduct(payload)
      ElMessage.success('已新增')
    }
    dialogVisible.value = false
    // 局部刷新当前页，不整页重载（P-13 规则 5）
    await load()
  } catch (e) {
    if (errorCode(e) === 'MODEL_DUPLICATED') {
      modelError.value = errorText(e, '型号已存在')
      return
    }
    ElMessage.error(errorText(e))
  } finally {
    submitting.value = false
  }
}

async function onToggleActive(row, value) {
  togglingId.value = row.id
  try {
    await adminUpdateProduct(row.id, { is_active: value })
    row.is_active = value
    ElMessage.success(value ? '已上架' : '已下架')
  } catch (e) {
    ElMessage.error(errorText(e, '状态更新失败'))
    // 失败回滚：重新拉一次列表，保证开关与库一致（不算整页重载）
    await load()
  } finally {
    togglingId.value = null
  }
}

async function onDelete(row) {
  // fault_count > 0 说明删除必然被拒：只提示、不发删除请求（省一次必然失败的往返）。
  // 注意仍以后端 DELETE_BLOCKED 为准 —— fault_count 只算故障，零件引用后端也会拦。
  if (row.fault_count > 0) {
    try {
      await ElMessageBox.confirm(
        `该产品下有 ${row.fault_count} 条故障，需先迁移或删除故障后才能删除本产品。`,
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
      `确认删除产品「${row.name}（${row.model}）」？删除后不可恢复。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }

  try {
    await adminDeleteProduct(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    // DELETE_BLOCKED：后端复算的引用统计可能比列表里的 fault_count 更新，原文展示
    ElMessage.error(errorText(e, '删除失败'))
  }
}

function onRowClick(row) {
  if (!canWrite.value) return
  openEdit(row)
}

onMounted(() => {
  load()
  loadLines()
})
onBeforeUnmount(() => clearTimeout(keywordTimer))
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
  flex-wrap: wrap;
}

.kw {
  width: 200px;
}

.status {
  width: 130px;
}

.name {
  font-weight: 600;
}

.model {
  color: #909399;
  font-size: 12px;
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

.line-select {
  width: 240px;
}

.manage {
  margin-left: 8px;
}

/* 整行可点进编辑，但操作列按钮不触发 */
:deep(.el-table__row) {
  cursor: pointer;
}
</style>
