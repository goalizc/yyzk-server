<template>
  <div class="page">
    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>故障知识库</span>
          <el-button v-if="canWrite" type="primary" @click="goCreate">新增故障</el-button>
        </div>
      </template>

      <el-form :inline="true" class="filters" @submit.prevent>
        <el-form-item label="产品">
          <el-select
            v-model="filters.productId"
            placeholder="全部产品"
            filterable
            clearable
            class="wd"
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
        </el-form-item>
        <el-form-item label="零件">
          <el-select
            v-model="filters.partId"
            placeholder="全部零件"
            filterable
            clearable
            class="wd"
            :disabled="!filters.productId"
            :loading="loadingParts"
            @change="reload"
          >
            <el-option
              v-for="item in parts"
              :key="item.id"
              :label="item.group_name ? `${item.group_name} / ${item.name}` : item.name"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="关键词">
          <el-input
            v-model="filters.keyword"
            placeholder="标题或现象"
            clearable
            class="wd"
            @input="onKeywordInput"
            @clear="reload"
          />
        </el-form-item>
        <el-form-item label="发布状态">
          <el-select v-model="filters.published" placeholder="全部" clearable class="sm" @change="reload">
            <el-option label="已发布" :value="true" />
            <el-option label="未发布" :value="false" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button @click="onReset">重置</el-button>
        </el-form-item>
      </el-form>

      <ErrorState v-if="loadError" :error="loadError" @retry="load" />
      <el-table
        v-else
        v-loading="loading"
        :data="rows"
        row-key="id"
        border
        @row-click="onRowClick"
      >
        <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
        <el-table-column label="所属产品" width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.product_name }}</template>
        </el-table-column>
        <el-table-column label="所属零件" width="130" show-overflow-tooltip>
          <template #default="{ row }">{{ row.part_name }}</template>
        </el-table-column>
        <el-table-column prop="view_count" label="查看次数" width="90" align="center" />
        <el-table-column prop="resolved_count" label="解决次数" width="90" align="center" />
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.is_published" size="small" type="success">已发布</el-tag>
            <el-tag v-else size="small" type="info">未发布</el-tag>
            <el-tag
              v-if="row.needs_professional"
              size="small"
              type="warning"
              class="tag-gap"
            >
              需专业
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="120">
          <template #default="{ row }">{{ formatDate(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column v-if="canWrite" label="操作" width="130" align="center">
          <template #default="{ row }">
            <el-button link type="primary" @click.stop="goEdit(row)">编辑</el-button>
            <el-button link type="danger" @click.stop="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无故障，点击「新增故障」录入第一条" />
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
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminDeleteFault, adminListFaults, adminListParts, adminListProducts } from '../../../api/admin'
import ErrorState from '../../../components/ErrorState.vue'
import { errorText } from '../../../utils/admin'
import { formatDate } from '../../../utils/format'
import { hasPermission } from '../../../utils/permissions'

const canWrite = computed(() => hasPermission('fault:write'))
// 只读用户也能打开详情：编辑页会按自己的权限降级为只读视图
const canOpen = computed(() => hasPermission('fault:read'))

const router = useRouter()

const products = ref([])
const parts = ref([])
const loadingProducts = ref(false)
const loadingParts = ref(false)

const rows = ref([])
const loading = ref(false)
const loadError = ref('')
const pagination = reactive({ page: 1, pageSize: 20, total: 0 })

const filters = reactive({ productId: null, partId: null, keyword: '', published: null })

let keywordTimer = null

async function loadProducts() {
  loadingProducts.value = true
  try {
    const data = await adminListProducts({ page: 1, page_size: 100 })
    products.value = data.items
  } catch (e) {
    ElMessage.error(errorText(e, '产品列表加载失败'))
  } finally {
    loadingProducts.value = false
  }
}

// 换产品时旧的零件请求可能晚到，把下拉填成上一家的零件
let partsSeq = 0

async function loadParts(productId) {
  const my = (partsSeq += 1)
  if (!productId) {
    parts.value = []
    return
  }
  loadingParts.value = true
  try {
    const data = await adminListParts({ product_id: productId, page: 1, page_size: 100 })
    if (my !== partsSeq) return
    parts.value = data.items
  } catch (e) {
    if (my !== partsSeq) return
    parts.value = []
    ElMessage.error(errorText(e, '零件列表加载失败'))
  } finally {
    if (my === partsSeq) loadingParts.value = false
  }
}

// 关键词防抖 + 筛选切换都可能让两次请求交叉返回
let listSeq = 0

async function load() {
  const my = (listSeq += 1)
  loading.value = true
  loadError.value = ''
  try {
    const params = {
      page: pagination.page,
      page_size: pagination.pageSize,
      ...(filters.productId ? { product_id: filters.productId } : {}),
      ...(filters.partId ? { part_id: filters.partId } : {}),
      ...(filters.keyword.trim() ? { keyword: filters.keyword.trim() } : {}),
      ...(filters.published === null || filters.published === undefined
        ? {}
        : { is_published: filters.published })
    }
    const data = await adminListFaults(params)
    if (my !== listSeq) return
    rows.value = data.items
    pagination.total = data.total
    if (!data.items.length && pagination.page > 1) {
      pagination.page -= 1
      return load()
    }
  } catch (e) {
    if (my !== listSeq) return
    rows.value = []
    pagination.total = 0
    loadError.value = errorText(e, '故障列表加载失败')
  } finally {
    if (my === listSeq) loading.value = false
  }
}

function reload() {
  pagination.page = 1
  load()
}

function onProductChange(value) {
  // 换产品必须清零件，否则会带着别家的 part_id 查询（后端 part 与 product 不匹配）
  filters.partId = null
  parts.value = []
  if (value) loadParts(value)
  reload()
}

function onKeywordInput() {
  clearTimeout(keywordTimer)
  keywordTimer = setTimeout(reload, 300)
}

function onSizeChange() {
  pagination.page = 1
  load()
}

function onReset() {
  filters.productId = null
  filters.partId = null
  filters.keyword = ''
  filters.published = null
  parts.value = []
  reload()
}

function goCreate() {
  router.push({ name: 'admin-fault-edit' })
}

function goEdit(row) {
  router.push({ name: 'admin-fault-edit', params: { id: row.id } })
}

function onRowClick(row) {
  if (!canOpen.value) return
  goEdit(row)
}

async function onDelete(row) {
  try {
    // 契约 §4：被工单引用时不阻止删除（引用置 NULL），但要明确告知不可恢复
    await ElMessageBox.confirm(
      `确认删除故障「${row.title}」？删除后不可恢复，相关工单会保留但不再关联该故障。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }

  try {
    await adminDeleteFault(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    ElMessage.error(errorText(e, '删除失败'))
  }
}

onMounted(async () => {
  await loadProducts()
  await load()
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
}

.filters {
  margin-bottom: 8px;
}

.wd {
  width: 200px;
}

.sm {
  width: 120px;
}

.pager {
  margin-top: 16px;
  justify-content: flex-end;
}

.tag-gap {
  margin-left: 4px;
}

:deep(.el-table__row) {
  cursor: pointer;
}
</style>
