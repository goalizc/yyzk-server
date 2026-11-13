<template>
  <div class="page">
    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>{{ t(I18N[resource].title) }}</span>
          <el-button v-if="canWrite" type="primary" @click="formVisible = true">
            {{ t(I18N[resource].newDoc) }}
          </el-button>
        </div>
      </template>

      <el-form :inline="true" class="filters" @submit.prevent>
        <el-form-item :label="$t('admin.inventory.common.docNo')">
          <el-input
            v-model="filters.doc_no"
            :placeholder="$t('admin.inventory.common.keywordPlaceholder')"
            clearable
            class="wd"
            @keyup.enter="reload"
            @clear="reload"
          />
        </el-form-item>
        <el-form-item :label="$t('admin.inventory.common.category')">
          <el-select v-model="filters.category_id" clearable filterable class="sm" @change="reload">
            <el-option v-for="c in categoryOptions" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('admin.inventory.common.product')">
          <el-select v-model="filters.product_id" clearable filterable class="md" @change="reload">
            <el-option v-for="p in productOptions" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('admin.inventory.common.dateRange')">
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            value-format="YYYY-MM-DD"
            range-separator="~"
            :start-placeholder="$t('admin.inventory.common.start')"
            :end-placeholder="$t('admin.inventory.common.end')"
            class="range"
            @change="reload"
          />
        </el-form-item>
        <el-form-item :label="$t('admin.inventory.common.status')">
          <el-select v-model="filters.status" clearable class="sm" @change="reload">
            <el-option :label="$t('admin.inventory.common.statusConfirmed')" value="confirmed" />
            <el-option :label="$t('admin.inventory.common.statusVoid')" value="void" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button @click="onReset">{{ $t('admin.inventory.common.reset') }}</el-button>
        </el-form-item>
      </el-form>

      <ErrorState v-if="loadError" :error="loadError" @retry="load" />
      <el-table v-else v-loading="loading" :data="rows" row-key="id" border @row-click="openDetail">
        <el-table-column prop="doc_no" :label="t(I18N[resource].colDocNo)" width="200" />
        <el-table-column :label="$t('admin.inventory.common.status')" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="row.status === 'void' ? 'info' : 'success'" size="small">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="remark" :label="$t('admin.inventory.common.remark')" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.remark || '-' }}</template>
        </el-table-column>
        <el-table-column :label="t(I18N[resource].colCreatedAt)" width="170">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column :label="t(I18N[resource].colActions)" width="110" align="center">
          <template #default="{ row }">
            <el-button link type="primary" @click.stop="openDetail(row)">
              {{ $t('admin.inventory.common.detail') }}
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

    <DocumentFormDialog
      v-model="formVisible"
      :resource="resource"
      :title="t(I18N[resource].newDoc)"
      :warehouses="warehouses"
      :skus="skus"
      :categories="categoryOptions"
      :products="productOptions"
      @created="onCreated"
    />
    <DocumentDetailPanel
      v-model="detailVisible"
      :title="t(I18N[resource].detailTitle)"
      :doc="detail"
      @reversed="onReversed"
      @edit="onEditRequested"
    />
    <EditDocumentDialog
      v-model="editVisible"
      :doc="editDoc"
      :skus="skus"
      :categories="categoryOptions"
      :products="productOptions"
      :title="$t('admin.inventory.common.editDoc')"
      @updated="onEdited"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import {
  inventoryInboundOrders, inventoryOutboundOrders,
  inventoryGetInbound, inventoryGetOutbound,
  inventorySkus, inventoryWarehouses, inventoryCategories, inventoryRefProducts
} from '../../../api/inventory'
import ErrorState from '../../../components/ErrorState.vue'
import { errorMessage } from '../../../utils/error'
import { formatDateTime } from '../../../utils/format'
import { hasPermission } from '../../../utils/permissions'
import DocumentFormDialog from './DocumentFormDialog.vue'
import DocumentDetailPanel from './DocumentDetailPanel.vue'
import EditDocumentDialog from './EditDocumentDialog.vue'

const props = defineProps({
  // inbound | outbound
  resource: { type: String, required: true }
})

const { t } = useI18n()

// 全部走映射表，禁拼 i18n key（扫描脚本抓不到拼出来的 key）
const I18N = {
  inbound: {
    title: 'admin.inventory.inbound.title',
    newDoc: 'admin.inventory.inbound.newDoc',
    detailTitle: 'admin.inventory.inbound.detailTitle',
    colDocNo: 'admin.inventory.inbound.colDocNo',
    colCreatedAt: 'admin.inventory.inbound.colCreatedAt',
    colActions: 'admin.inventory.inbound.colActions'
  },
  outbound: {
    title: 'admin.inventory.outbound.title',
    newDoc: 'admin.inventory.outbound.newDoc',
    detailTitle: 'admin.inventory.outbound.detailTitle',
    colDocNo: 'admin.inventory.outbound.colDocNo',
    colCreatedAt: 'admin.inventory.outbound.colCreatedAt',
    colActions: 'admin.inventory.outbound.colActions'
  }
}
const LIST_FN = { inbound: inventoryInboundOrders, outbound: inventoryOutboundOrders }
const GET_FN = { inbound: inventoryGetInbound, outbound: inventoryGetOutbound }
const WRITE_PERM = { inbound: 'inventory:inbound:write', outbound: 'inventory:outbound:write' }
const STATUS_KEYS = {
  confirmed: 'admin.inventory.common.statusConfirmed',
  void: 'admin.inventory.common.statusVoid'
}

const canWrite = computed(() => hasPermission(WRITE_PERM[props.resource]))
const rows = ref([])
const loading = ref(false)
const loadError = ref('')
const pagination = reactive({ page: 1, pageSize: 20, total: 0 })
const filters = reactive({ doc_no: '', category_id: null, product_id: null, status: null })
const dateRange = ref([])
const warehouses = ref([])
const skus = ref([])
const categoryOptions = ref([])
const productOptions = ref([])
const formVisible = ref(false)
const detailVisible = ref(false)
const detail = ref(null)
const editVisible = ref(false)
const editDoc = ref(null)

function statusLabel(status) {
  const key = STATUS_KEYS[status]
  return key ? t(key) : status
}

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const [startDate, endDate] = dateRange.value || []
    const params = {
      page: pagination.page,
      page_size: pagination.pageSize,
      ...(filters.doc_no.trim() ? { doc_no: filters.doc_no.trim() } : {}),
      ...(filters.category_id === null ? {} : { category_id: filters.category_id }),
      ...(filters.product_id === null ? {} : { product_id: filters.product_id }),
      ...(filters.status ? { status: filters.status } : {}),
      ...(startDate ? { start_date: startDate } : {}),
      ...(endDate ? { end_date: endDate } : {})
    }
    const data = await LIST_FN[props.resource](params)
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

async function loadRefs() {
  try {
    const [wh, sku, cat, prod] = await Promise.all([
      inventoryWarehouses({ page: 1, page_size: 100 }),
      inventorySkus({ page: 1, page_size: 100, is_active: true }),
      inventoryCategories({ page: 1, page_size: 100, is_active: true }).catch(() => ({ items: [] })),
      // 产品引用走库存域端点：仓管没有 product:read，用 /admin/products 会被 403 成空列表
      inventoryRefProducts().catch(() => [])
    ])
    warehouses.value = wh.items || []
    skus.value = sku.items || []
    categoryOptions.value = cat.items || []
    productOptions.value = prod || []
  } catch {
    warehouses.value = []
    skus.value = []
    categoryOptions.value = []
    productOptions.value = []
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
  filters.doc_no = ''
  filters.category_id = null
  filters.product_id = null
  filters.status = null
  dateRange.value = []
  reload()
}

async function openDetail(row) {
  detail.value = null
  detailVisible.value = true
  try {
    detail.value = await GET_FN[props.resource](row.id)
  } catch (e) {
    detailVisible.value = false
    ElMessage.error(errorMessage(e, { fallbackKey: 'admin.inventory.common.loadFailed' }))
  }
}

async function onCreated() {
  await Promise.all([load(), loadRefs()])
}

async function onReversed() {
  // 详情面板冲正成功：原单变 void、生成反向单，刷新列表与引用数据
  await Promise.all([load(), loadRefs()])
}

function onEditRequested(doc) {
  // 详情面板已关闭（避免叠加两层居中弹窗），这里打开改单弹窗
  editDoc.value = doc
  editVisible.value = true
}

async function onEdited() {
  // 改单会按差额补更正流水，余额与流水都可能变化：列表与引用数据一起刷新
  await Promise.all([load(), loadRefs()])
}

onMounted(() => {
  loadRefs()
  load()
})
</script>

<style scoped>
.page { display: flex; flex-direction: column; gap: 16px; }
.head { display: flex; align-items: center; justify-content: space-between; }
.filters { margin-bottom: 4px; }
.pager { margin-top: 16px; justify-content: flex-end; }
.wd { width: 200px; }
.sm { width: 140px; }
/* 产品名普遍长于分类（「植保无人机 16L」），140px 会截成「植保无人机 1…」 */
.md { width: 170px; }
.range { width: 260px; }
</style>
