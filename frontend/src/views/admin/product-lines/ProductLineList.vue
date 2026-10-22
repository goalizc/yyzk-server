<template>
  <div class="page">
    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>产品线管理</span>
          <el-button v-if="canWrite" type="primary" @click="openCreate">新增产品线</el-button>
        </div>
      </template>

      <ErrorState v-if="loadError" :error="loadError" @retry="load" />
      <el-table v-else v-loading="loading" :data="rows" row-key="id" border>
        <el-table-column prop="name" label="名称" min-width="200" />
        <el-table-column prop="product_count" label="产品数" width="100" align="center" />
        <el-table-column prop="sort_order" label="排序" width="100" align="center" />
        <el-table-column label="状态" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
              {{ row.is_active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="canWrite" label="操作" width="160" align="center">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑产品线' : '新增产品线'" width="420px" @closed="resetForm">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" maxlength="50" />
        </el-form-item>
        <el-form-item label="排序" prop="sort_order">
          <el-input-number v-model="form.sort_order" :min="0" :max="9999" controls-position="right" />
        </el-form-item>
        <el-form-item label="启用" prop="is_active">
          <el-switch v-model="form.is_active" />
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
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  adminCreateProductLine, adminDeleteProductLine, adminListProductLines, adminUpdateProductLine
} from '../../../api/admin'
import ErrorState from '../../../components/ErrorState.vue'
import { errorText } from '../../../utils/admin'
import { hasPermission } from '../../../utils/permissions'

const canWrite = hasPermission('product_line:write')
const rows = ref([])
const loading = ref(false)
const loadError = ref('')
const dialogVisible = ref(false)
const editingId = ref(null)
const submitting = ref(false)
const formRef = ref()
const form = reactive({ name: '', sort_order: 0, is_active: true })
const rules = { name: [{ required: true, message: '请输入名称', trigger: 'blur' }] }

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    rows.value = (await adminListProductLines()).items
  } catch (e) {
    rows.value = []
    loadError.value = errorText(e, '产品线加载失败')
  } finally {
    loading.value = false
  }
}

function resetForm() {
  editingId.value = null
  Object.assign(form, { name: '', sort_order: 0, is_active: true })
  formRef.value?.clearValidate()
}

function openCreate() {
  resetForm()
  dialogVisible.value = true
}

function openEdit(row) {
  resetForm()
  editingId.value = row.id
  Object.assign(form, { name: row.name, sort_order: row.sort_order, is_active: row.is_active })
  dialogVisible.value = true
}

async function onSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    if (editingId.value) {
      await adminUpdateProductLine(editingId.value, { ...form, name: form.name.trim() })
    } else {
      await adminCreateProductLine({ ...form, name: form.name.trim() })
    }
    ElMessage.success('已保存')
    dialogVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error(errorText(e))
  } finally {
    submitting.value = false
  }
}

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(`确认删除产品线「${row.name}」？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await adminDeleteProductLine(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    ElMessage.error(errorText(e, '删除失败'))
  }
}

onMounted(load)
</script>

<style scoped>
.page { display: flex; flex-direction: column; gap: 16px; }
.head { display: flex; align-items: center; justify-content: space-between; }
</style>
