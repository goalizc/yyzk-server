<template>
  <div class="page">
    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>{{ $t('admin.inventory.category.title') }}</span>
          <el-button v-if="canWrite" type="primary" @click="openCreate">
            {{ $t('admin.inventory.category.newCategory') }}
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
        <el-form-item :label="$t('admin.inventory.common.status')">
          <el-select v-model="filters.is_active" clearable class="sm" @change="reload">
            <el-option :label="$t('admin.inventory.common.active')" :value="true" />
            <el-option :label="$t('admin.inventory.common.inactive')" :value="false" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button @click="onReset">{{ $t('admin.inventory.common.reset') }}</el-button>
        </el-form-item>
      </el-form>

      <ErrorState v-if="loadError" :error="loadError" @retry="load" />
      <el-table v-else v-loading="loading" :data="rows" row-key="id" border>
        <el-table-column
          prop="name"
          :label="$t('admin.inventory.category.colName')"
          min-width="180"
          show-overflow-tooltip
        />
        <el-table-column
          prop="remark"
          :label="$t('admin.inventory.category.colRemark')"
          min-width="240"
          show-overflow-tooltip
        >
          <template #default="{ row }">{{ row.remark || '-' }}</template>
        </el-table-column>
        <el-table-column
          :label="$t('admin.inventory.category.colStatus')"
          width="100"
          align="center"
        >
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
              {{ row.is_active ? $t('admin.inventory.common.active') : $t('admin.inventory.common.inactive') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          v-if="canWrite"
          :label="$t('admin.inventory.category.colActions')"
          width="160"
          align="center"
        >
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">
              {{ $t('common.action.edit') }}
            </el-button>
            <el-button v-if="row.is_active" link type="danger" @click="onToggle(row, false)">
              {{ $t('admin.inventory.common.inactive') }}
            </el-button>
            <el-button v-else link type="primary" @click="onToggle(row, true)">
              {{ $t('admin.inventory.common.active') }}
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
      :title="editingId ? $t('admin.inventory.category.editCategory') : $t('admin.inventory.category.newCategory')"
      :width="isNarrow ? '92%' : '480px'"
      @closed="resetForm"
    >
      <el-form ref="formRef" :model="form" :rules="rules" :label-width="labelWidth">
        <el-form-item :label="$t('admin.inventory.category.fieldName')" prop="name">
          <el-input v-model="form.name" maxlength="50" />
        </el-form-item>
        <el-form-item :label="$t('admin.inventory.category.fieldRemark')">
          <el-input v-model="form.remark" type="textarea" maxlength="200" :rows="2" />
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
  inventoryCategories, inventoryCreateCategory, inventoryUpdateCategory
} from '../../../api/inventory'
import ErrorState from '../../../components/ErrorState.vue'
import { errorMessage } from '../../../utils/error'
import { hasPermission } from '../../../utils/permissions'
import { useNarrow } from '../../../utils/viewport'
import { useFormLabelWidth } from '../../../utils/formLabel'

const { t } = useI18n()
const canWrite = computed(() => hasPermission('inventory:sku:write'))
const labelWidth = useFormLabelWidth('88px', '120px')
const isNarrow = useNarrow()

const rows = ref([])
const loading = ref(false)
const loadError = ref('')
const pagination = reactive({ page: 1, pageSize: 20, total: 0 })
const filters = reactive({ keyword: '', is_active: null })

const dialogVisible = ref(false)
const editingId = ref(null)
const submitting = ref(false)
const formRef = ref()
const emptyForm = () => ({ name: '', remark: '' })
const form = reactive(emptyForm())

const rules = computed(() => ({
  name: [{ required: true, message: t('admin.inventory.category.ruleName'), trigger: 'blur' }]
}))

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const params = {
      page: pagination.page,
      page_size: pagination.pageSize,
      ...(filters.keyword.trim() ? { keyword: filters.keyword.trim() } : {}),
      ...(filters.is_active === null ? {} : { is_active: filters.is_active })
    }
    const data = await inventoryCategories(params)
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
  filters.is_active = null
  reload()
}

function resetForm() {
  editingId.value = null
  Object.assign(form, emptyForm())
  formRef.value?.clearValidate()
}

function openCreate() {
  resetForm()
  dialogVisible.value = true
}

function openEdit(row) {
  resetForm()
  editingId.value = row.id
  Object.assign(form, { name: row.name, remark: row.remark || '' })
  dialogVisible.value = true
}

async function onSubmit() {
  // el-dialog 懒渲染：未打开时 formRef 为 null，validate() 会静默 return
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    const payload = { name: form.name.trim(), remark: form.remark || null }
    if (editingId.value) {
      await inventoryUpdateCategory(editingId.value, payload)
    } else {
      await inventoryCreateCategory(payload)
    }
    ElMessage.success(t('admin.inventory.common.saved'))
    dialogVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error(errorMessage(e, { fallbackKey: 'admin.inventory.common.saveFailed' }))
  } finally {
    submitting.value = false
  }
}

async function onToggle(row, active) {
  try {
    if (active) {
      await ElMessageBox.confirm(
        t('admin.inventory.category.enableConfirm', { name: row.name }),
        t('admin.inventory.category.enableTitle'),
        { type: 'info' }
      )
    } else {
      await ElMessageBox.confirm(
        t('admin.inventory.category.disableConfirm', { name: row.name }),
        t('admin.inventory.category.disableTitle'),
        { type: 'warning' }
      )
    }
  } catch {
    return
  }
  try {
    await inventoryUpdateCategory(row.id, { is_active: active })
    ElMessage.success(
      active
        ? t('admin.inventory.category.enableSuccess')
        : t('admin.inventory.category.disableSuccess')
    )
    await load()
  } catch (e) {
    ElMessage.error(errorMessage(e, { fallbackKey: 'admin.inventory.common.saveFailed' }))
  }
}

onMounted(load)
</script>

<style scoped>
.page { display: flex; flex-direction: column; gap: 16px; }
.head { display: flex; align-items: center; justify-content: space-between; }
.filters { margin-bottom: 4px; }
.pager { margin-top: 16px; justify-content: flex-end; }
.wd { width: 200px; }
.sm { width: 130px; }
</style>
