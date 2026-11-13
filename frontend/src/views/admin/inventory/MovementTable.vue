<template>
  <el-card shadow="never">
    <template #header>
      <div class="head">
        <span>{{ t(headerKey) }}</span>
      </div>
    </template>

    <el-form :inline="true" class="filters" @submit.prevent>
      <el-form-item :label="t('admin.inventory.movement.filterSku')">
        <el-select
          v-model="filters.sku_id"
          clearable
          filterable
          class="wd"
          :placeholder="t('admin.inventory.movement.allSku')"
          @change="reload"
        >
          <el-option v-for="s in skus" :key="s.id" :label="`${s.sku_no} ${s.name}`" :value="s.id" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('admin.inventory.common.docNo')">
        <el-input
          v-model="filters.doc_no"
          :placeholder="t('admin.inventory.common.keywordPlaceholder')"
          clearable
          class="wd"
          @keyup.enter="reload"
          @clear="reload"
        />
      </el-form-item>
      <el-form-item :label="t('admin.inventory.common.dateRange')">
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          value-format="YYYY-MM-DD"
          range-separator="~"
          :start-placeholder="t('admin.inventory.common.start')"
          :end-placeholder="t('admin.inventory.common.end')"
          class="range"
          @change="reload"
        />
      </el-form-item>
      <el-form-item>
        <el-button @click="onReset">{{ t('admin.inventory.common.reset') }}</el-button>
      </el-form-item>
    </el-form>

    <el-alert
      v-if="reversible"
      :closable="false"
      type="info"
      :title="t('admin.inventory.movement.appendOnlyHint')"
      class="hint"
    />

    <ErrorState v-if="loadError" :error="loadError" @retry="load" />
    <el-table v-else v-loading="loading" :data="rows" row-key="id" border>
      <el-table-column :label="t('admin.inventory.movement.colCreatedAt')" width="170">
        <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column :label="t('admin.inventory.movement.colSku')" min-width="200" show-overflow-tooltip>
        <template #default="{ row }">{{ row.sku_no }} {{ row.sku_name }}</template>
      </el-table-column>
      <el-table-column prop="doc_no" :label="t('admin.inventory.movement.colDocNo')" width="170" show-overflow-tooltip />
      <el-table-column :label="t('admin.inventory.movement.colDelta')" width="100" align="center">
        <template #default="{ row }">
          <span :class="row.delta >= 0 ? 'text-in' : 'text-out'">
            {{ row.delta > 0 ? '+' : '' }}{{ row.delta }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="balance_after" :label="t('admin.inventory.movement.colBalanceAfter')" width="120" align="center" />
      <el-table-column prop="operator_id" :label="t('admin.inventory.movement.colOperator')" width="100" align="center" />
      <el-table-column v-if="reversible" :label="t('admin.inventory.common.actions')" width="100" align="center">
        <template #default="{ row }">
          <!-- 已冲正单据的流水不能再冲正一次；没有关联单据的流水也不显示 -->
          <el-button
            v-if="row.document_id && row.doc_status !== 'void'"
            link
            type="danger"
            @click="emit('reverse', row.document_id, row.doc_no)"
          >
            {{ t('admin.inventory.common.reverse') }}
          </el-button>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty :description="t('admin.inventory.common.empty')" />
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
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { inventoryMovements, inventorySkus } from '../../../api/inventory'
import ErrorState from '../../../components/ErrorState.vue'
import { errorMessage } from '../../../utils/error'
import { formatDateTime } from '../../../utils/format'

const { reversible = false, headerKey = 'admin.inventory.movement.title' } = defineProps({
  // 是否显示行内「冲正」按钮（调整页开启，只读流水页关闭）
  reversible: { type: Boolean, default: false },
  headerKey: { type: String, default: 'admin.inventory.movement.title' }
})
const emit = defineEmits(['reverse'])
const { t } = useI18n()

const rows = ref([])
const loading = ref(false)
const loadError = ref('')
const pagination = reactive({ page: 1, pageSize: 20, total: 0 })
const filters = reactive({ sku_id: null, doc_no: '' })
const dateRange = ref([])
const skus = ref([])

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const [startDate, endDate] = dateRange.value || []
    const params = {
      page: pagination.page,
      page_size: pagination.pageSize,
      ...(filters.sku_id ? { sku_id: filters.sku_id } : {}),
      ...(filters.doc_no.trim() ? { doc_no: filters.doc_no.trim() } : {}),
      ...(startDate ? { start_date: startDate } : {}),
      ...(endDate ? { end_date: endDate } : {})
    }
    const data = await inventoryMovements(params)
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

async function loadSkus() {
  try {
    const data = await inventorySkus({ page: 1, page_size: 100, is_active: true })
    skus.value = data.items || []
  } catch {
    skus.value = []
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
  filters.sku_id = null
  filters.doc_no = ''
  dateRange.value = []
  reload()
}

onMounted(() => {
  loadSkus()
  load()
})

// 父级（调整页）建单/冲正后调用以刷新流水
defineExpose({ reload })
</script>

<style scoped>
.head { display: flex; align-items: center; justify-content: space-between; }
.filters { margin-bottom: 4px; }
.pager { margin-top: 16px; justify-content: flex-end; }
.wd { width: 220px; }
.range { width: 260px; }
.hint { margin-bottom: 12px; }
.text-in { color: var(--el-color-success); font-weight: 600; }
.text-out { color: var(--el-color-danger); font-weight: 600; }
</style>
