<template>
  <div class="page">
    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>{{ $t('admin.page.productLines') }}</span>
          <el-button v-if="canWrite" type="primary" @click="openCreate">{{ $t('admin.line.newLine') }}</el-button>
        </div>
      </template>

      <ErrorState v-if="loadError" :error="loadError" @retry="load" />
      <el-table v-else v-loading="loading" :data="rows" row-key="id" border>
        <el-table-column prop="name" :label="$t('admin.line.colName')" min-width="200" />
        <el-table-column prop="product_count" :label="$t('admin.line.colProductCount')" width="100" align="center" />
        <el-table-column prop="sort_order" :label="$t('admin.line.colSort')" width="100" align="center" />
        <el-table-column :label="$t('admin.line.colStatus')" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
              {{ row.is_active ? $t('admin.line.enabled') : $t('admin.line.disabled') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="canWrite" :label="$t('admin.line.colActions')" width="160" align="center">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">{{ $t('common.action.edit') }}</el-button>
            <el-button link type="danger" @click="onDelete(row)">{{ $t('common.action.delete') }}</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? $t('admin.line.dialogEdit') : $t('admin.line.dialogCreate')"
      :width="isNarrow ? '92%' : '420px'"
      @closed="resetForm"
    >
      <el-form ref="formRef" :model="form" :rules="rules" :label-width="labelWidth">
        <el-form-item :label="$t('admin.line.name')" prop="name">
          <el-input v-model="form.name" maxlength="50" />
        </el-form-item>
        <el-form-item :label="$t('admin.line.sortOrder')" prop="sort_order">
          <el-input-number v-model="form.sort_order" :min="0" :max="9999" controls-position="right" />
        </el-form-item>
        <el-form-item :label="$t('admin.line.isActive')" prop="is_active">
          <el-switch v-model="form.is_active" />
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
  adminCreateProductLine, adminDeleteProductLine, adminListProductLines, adminUpdateProductLine
} from '../../../api/admin'
import ErrorState from '../../../components/ErrorState.vue'
import { errorMessage } from '../../../utils/error'
import { hasPermission } from '../../../utils/permissions'
import { useNarrow } from '../../../utils/viewport'
import { useFormLabelWidth } from '../../../utils/formLabel'

const { t } = useI18n()
const canWrite = computed(() => hasPermission('product_line:write'))
const labelWidth = useFormLabelWidth('80px', '110px')
const isNarrow = useNarrow()
const rows = ref([])
const loading = ref(false)
const loadError = ref('')
const dialogVisible = ref(false)
const editingId = ref(null)
const submitting = ref(false)
const formRef = ref()
const form = reactive({ name: '', sort_order: 0, is_active: true })
// computed：语言切换后校验文案跟着变
const rules = computed(() => ({ name: [{ required: true, message: t('admin.line.ruleName'), trigger: 'blur' }] }))

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    rows.value = (await adminListProductLines()).items
  } catch (e) {
    rows.value = []
    loadError.value = errorMessage(e, { fallbackKey: 'admin.line.loadFailed' })
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
    ElMessage.success(t('admin.line.saved'))
    dialogVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error(errorMessage(e))
  } finally {
    submitting.value = false
  }
}

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(t('admin.line.deleteConfirm', { name: row.name }), t('common.confirm.deleteTitle'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await adminDeleteProductLine(row.id)
    ElMessage.success(t('admin.line.deleted'))
    await load()
  } catch (e) {
    ElMessage.error(errorMessage(e, { fallbackKey: 'admin.line.deleteFailed' }))
  }
}

onMounted(load)
</script>

<style scoped>
.page { display: flex; flex-direction: column; gap: 16px; }
.head { display: flex; align-items: center; justify-content: space-between; }
</style>
