<template>
  <div class="page">
    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>工单管理</span>
        </div>
      </template>

      <el-form :inline="true" class="filters" @submit.prevent>
        <el-form-item label="状态">
          <el-select v-model="filters.status" placeholder="全部" clearable class="sm" @change="reload">
            <el-option
              v-for="(item, key) in TICKET_STATUS"
              :key="key"
              :label="item.label"
              :value="key"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="创建日期">
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            value-format="YYYY-MM-DD"
            range-separator="~"
            start-placeholder="开始"
            end-placeholder="结束"
            class="range"
            @change="reload"
          />
        </el-form-item>
        <el-form-item label="单号 / 电话">
          <el-input
            v-model="filters.keyword"
            placeholder="工单号或联系方式"
            clearable
            class="wd"
            @input="onKeywordInput"
            @clear="reload"
          />
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
        @row-click="openDetail"
      >
        <el-table-column prop="ticket_no" label="单号" width="160" />
        <el-table-column label="产品" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.product_name">{{ row.product_name }}</span>
            <span v-else class="muted">-</span>
            <span v-if="row.product_model" class="muted"> {{ row.product_model }}</span>
          </template>
        </el-table-column>
        <el-table-column label="故障" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.fault_title || '-' }}</template>
        </el-table-column>
        <el-table-column label="联系人" width="140">
          <template #default="{ row }">
            <div>{{ row.contact }}</div>
            <div v-if="row.contact_name" class="muted">{{ row.contact_name }}</div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="ticketStatusType(row.status)">
              {{ ticketStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="上门" width="70" align="center">
          <template #default="{ row }">{{ row.need_on_site ? '是' : '否' }}</template>
        </el-table-column>
        <el-table-column label="处理人" width="100">
          <template #default="{ row }">
            <span :class="{ muted: !row.assignee_name }">{{ row.assignee_name || '未认领' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="150">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无工单" />
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

    <TicketDrawer v-model="drawerVisible" :ticket-id="currentId" @updated="onDrawerUpdated" />
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import TicketDrawer from './TicketDrawer.vue'
import { adminListTickets } from '../../../api/admin'
import ErrorState from '../../../components/ErrorState.vue'
import { errorText, TICKET_STATUS, ticketStatusLabel, ticketStatusType } from '../../../utils/admin'
import { formatDateTime } from '../../../utils/format'

const rows = ref([])
const loading = ref(false)
const loadError = ref('')
const pagination = reactive({ page: 1, pageSize: 20, total: 0 })
const filters = reactive({ status: null, keyword: '' })
const dateRange = ref([])
const drawerVisible = ref(false)
const currentId = ref(null)

let keywordTimer = null

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const [startDate, endDate] = dateRange.value || []
    const params = {
      page: pagination.page,
      page_size: pagination.pageSize,
      ...(filters.status ? { status: filters.status } : {}),
      ...(filters.keyword.trim() ? { keyword: filters.keyword.trim() } : {}),
      // 契约 §5：end_date 含当日，服务端按半开区间处理，前端原样传 YYYY-MM-DD
      ...(startDate ? { start_date: startDate } : {}),
      ...(endDate ? { end_date: endDate } : {})
    }
    const data = await adminListTickets(params)
    rows.value = data.items
    pagination.total = data.total
    if (!data.items.length && pagination.page > 1) {
      pagination.page -= 1
      return load()
    }
  } catch (e) {
    rows.value = []
    pagination.total = 0
    loadError.value = errorText(e, '工单列表加载失败')
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

function onReset() {
  filters.status = null
  filters.keyword = ''
  dateRange.value = []
  reload()
}

function openDetail(row) {
  // P-12 规则 3：抽屉必须自己请求详情（列表里的 contact 是脱敏的、也没有流转历史）
  currentId.value = row.id
  drawerVisible.value = true
}

function onDrawerUpdated(updated) {
  // 局部刷新该行，不整页重载
  const target = rows.value.find((item) => item.id === updated.id)
  if (target) {
    target.status = updated.status
    target.assignee_name = updated.assignee_name
    target.updated_at = updated.updated_at
  }
}

onMounted(load)
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

.range {
  width: 260px;
}

.muted {
  color: #a8abb2;
}

.pager {
  margin-top: 16px;
  justify-content: flex-end;
}

:deep(.el-table__row) {
  cursor: pointer;
}
</style>
