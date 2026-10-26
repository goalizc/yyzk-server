<template>
  <div class="page">
    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>{{ $t('admin.audit.title') }}</span>
          <el-button :loading="exporting" @click="onExport">
            {{ $t('admin.audit.filter.export') }}
          </el-button>
        </div>
      </template>

      <p class="intro">{{ $t('admin.audit.intro') }}</p>

      <!-- 汇总条：先给「谁最活跃、谁在失败、有没有多 IP」，再让人下钻 -->
      <div class="summary">
        <div class="stat">
          <span class="stat-label">{{ $t('admin.audit.summary.title', { days: summary.period_days }) }}</span>
          <span class="stat-value">{{ t('admin.audit.summary.total', summary.total) }}</span>
        </div>
        <div class="stat">
          <span class="stat-label">{{ $t('admin.audit.result.failure') }}</span>
          <span class="stat-value" :class="{ danger: summary.failures > 0 }">
            {{ t('admin.audit.summary.failures', summary.failures) }}
          </span>
        </div>
        <div class="stat">
          <span class="stat-label">{{ $t('admin.audit.col.username') }}</span>
          <span class="stat-value">{{ t('admin.audit.summary.actors', summary.actors.length) }}</span>
        </div>
        <div v-if="topActor" class="stat grow">
          <span class="stat-label">{{ $t('admin.audit.summary.topActor') }}</span>
          <span class="stat-value">
            {{ topActor.username }}
            <el-tag
              v-if="topActor.distinct_ips > 1"
              type="warning"
              size="small"
              class="ip-tag"
            >
              {{ t('admin.audit.summary.multiIp', { count: topActor.distinct_ips }) }}
            </el-tag>
          </span>
        </div>
      </div>

      <el-form :inline="true" class="filters" @submit.prevent>
        <el-form-item :label="$t('admin.audit.filter.username')">
          <el-input
            v-model="filters.username"
            :placeholder="$t('admin.audit.filter.usernamePlaceholder')"
            clearable
            class="w-account"
            @keyup.enter="search"
            @clear="search"
          />
        </el-form-item>
        <el-form-item :label="$t('admin.audit.filter.action')">
          <el-select v-model="filters.action" clearable class="w-action" @change="search">
            <el-option :label="$t('admin.audit.filter.actionAll')" value="" />
            <el-option
              v-for="code in actions"
              :key="code"
              :label="actionLabel(code)"
              :value="code"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('admin.audit.filter.result')">
          <el-select v-model="filters.result" clearable class="w-result" @change="search">
            <el-option :label="$t('admin.audit.filter.resultAll')" value="" />
            <el-option :label="$t('admin.audit.result.success')" value="success" />
            <el-option :label="$t('admin.audit.result.failure')" value="failure" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('admin.audit.filter.dateRange')">
          <el-date-picker
            v-model="filters.range"
            type="daterange"
            value-format="YYYY-MM-DD"
            :start-placeholder="$t('admin.audit.filter.startDate')"
            :end-placeholder="$t('admin.audit.filter.endDate')"
            class="w-date"
            @change="search"
          />
        </el-form-item>
        <el-form-item :label="$t('admin.audit.filter.keyword')">
          <el-input
            v-model="filters.keyword"
            :placeholder="$t('admin.audit.filter.keywordPlaceholder')"
            clearable
            class="w-keyword"
            @keyup.enter="search"
            @clear="search"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="search">{{ $t('admin.audit.filter.search') }}</el-button>
          <el-button @click="onReset">{{ $t('admin.audit.filter.reset') }}</el-button>
        </el-form-item>
      </el-form>

      <ErrorState v-if="loadError" :error="loadError" @retry="load" />
      <el-table
        v-else
        v-loading="loading"
        :data="rows"
        row-key="id"
        border
        class="table"
        @row-click="openDetail"
      >
        <el-table-column :label="$t('admin.audit.col.time')" width="150">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column :label="$t('admin.audit.col.username')" width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ displayUsername(row.username) }}</template>
        </el-table-column>
        <el-table-column :label="$t('admin.audit.col.action')" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ actionLabel(row.action) }}</template>
        </el-table-column>
        <el-table-column :label="$t('admin.audit.col.target')" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ targetText(row) }}</template>
        </el-table-column>
        <el-table-column :label="$t('admin.audit.col.result')" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.result === 'success' ? 'success' : 'danger'" size="small">
              {{ row.result === 'success' ? $t('admin.audit.result.success') : $t('admin.audit.result.failure') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="ip" :label="$t('admin.audit.col.ip')" width="130" />
        <el-table-column prop="status" :label="$t('admin.audit.col.status')" width="90" align="center" />
        <template #empty>
          <el-empty :description="$t('admin.audit.empty')" />
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
        @size-change="search"
      />
    </el-card>

    <DetailPanel
      v-model="panelVisible"
      :title="$t('admin.audit.detail.title')"
      :size="760"
      destroy-on-close
    >
      <template v-if="detail">
        <el-descriptions :column="2" border class="desc">
          <el-descriptions-item :label="$t('admin.audit.detail.time')">
            {{ formatDateTime(detail.created_at) }}
          </el-descriptions-item>
          <el-descriptions-item :label="$t('admin.audit.detail.username')">
            {{ displayUsername(detail.username) }}
          </el-descriptions-item>
          <el-descriptions-item :label="$t('admin.audit.detail.action')">
            {{ actionLabel(detail.action) }}
          </el-descriptions-item>
          <el-descriptions-item :label="$t('admin.audit.detail.result')">
            {{ detail.result === 'success' ? $t('admin.audit.result.success') : $t('admin.audit.result.failure') }}
          </el-descriptions-item>
          <el-descriptions-item :label="$t('admin.audit.detail.target')" :span="2">
            {{ targetText(detail) }}
          </el-descriptions-item>
          <el-descriptions-item :label="$t('admin.audit.detail.ip')">
            {{ detail.ip || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="$t('admin.audit.detail.status')">
            {{ detail.status }}
          </el-descriptions-item>
          <el-descriptions-item :label="$t('admin.audit.detail.path')" :span="2">
            <span class="mono">{{ detail.path }}</span>
          </el-descriptions-item>
          <el-descriptions-item :label="$t('admin.audit.detail.requestId')" :span="2">
            <span class="mono">{{ detail.request_id || '-' }}</span>
          </el-descriptions-item>
          <el-descriptions-item :label="$t('admin.audit.detail.userAgent')" :span="2">
            <span class="ua">{{ detail.user_agent || '-' }}</span>
          </el-descriptions-item>
          <el-descriptions-item v-if="detail.error_code" :label="$t('admin.audit.detail.errorCode')" :span="2">
            <el-tag type="danger" size="small">{{ detail.error_code }}</el-tag>
          </el-descriptions-item>
        </el-descriptions>

        <div class="extra">
          <div class="extra-title">{{ $t('admin.audit.detail.extra') }}</div>
          <el-descriptions v-if="extraFields.length" :column="1" border>
            <el-descriptions-item
              v-for="item in extraFields"
              :key="item.key"
              :label="item.label"
            >
              {{ item.value }}
            </el-descriptions-item>
          </el-descriptions>
          <p v-else class="empty-extra">{{ $t('admin.audit.detail.empty') }}</p>
        </div>
      </template>
    </DetailPanel>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import {
  adminAuditActions,
  adminAuditSummary,
  adminExportAuditLogs,
  adminGetAuditLog,
  adminListAuditLogs
} from '../../../api/audit'
import DetailPanel from '../../../components/DetailPanel.vue'
import ErrorState from '../../../components/ErrorState.vue'
import { errorMessage } from '../../../utils/error'
import { formatDateTime } from '../../../utils/format'

const { t } = useI18n()

const rows = ref([])
const actions = ref([])
const loading = ref(false)
const exporting = ref(false)
const loadError = ref('')
const panelVisible = ref(false)
const detail = ref(null)

const summary = ref({ period_days: 7, total: 0, failures: 0, actors: [] })
const topActor = computed(() => summary.value.actors[0] || null)

const filters = reactive({ username: '', action: '', result: '', keyword: '', range: [] })
const pagination = reactive({ page: 1, pageSize: 20, total: 0 })

// 动作码 → 完整文案 key。用映射表而不是拼 key（拼字符串的 key 扫描脚本抓不到，
// 漏翻译时会直接把 key 显示给用户）
const ACTION_KEYS = {
  'auth.login': 'admin.audit.action.authLogin',
  'auth.password_change': 'admin.audit.action.authPasswordChange',
  'ticket.create': 'admin.audit.action.ticketCreate',
  'ticket.update': 'admin.audit.action.ticketUpdate',
  'product.create': 'admin.audit.action.productCreate',
  'product.update': 'admin.audit.action.productUpdate',
  'product.delete': 'admin.audit.action.productDelete',
  'part.create': 'admin.audit.action.partCreate',
  'part.update': 'admin.audit.action.partUpdate',
  'part.delete': 'admin.audit.action.partDelete',
  'product_line.create': 'admin.audit.action.productLineCreate',
  'product_line.update': 'admin.audit.action.productLineUpdate',
  'product_line.delete': 'admin.audit.action.productLineDelete',
  'fault.create': 'admin.audit.action.faultCreate',
  'fault.update': 'admin.audit.action.faultUpdate',
  'fault.delete': 'admin.audit.action.faultDelete',
  'user.create': 'admin.audit.action.userCreate',
  'user.update': 'admin.audit.action.userUpdate',
  'user.reset_password': 'admin.audit.action.userResetPassword',
  'user.grant': 'admin.audit.action.userGrant',
  'user.revoke_grant': 'admin.audit.action.userRevokeGrant',
  'user.set_product_lines': 'admin.audit.action.userSetProductLines',
  'audit.export': 'admin.audit.action.auditExport',
  'upload.create': 'admin.audit.action.uploadCreate',
  'upload.delete': 'admin.audit.action.uploadDelete'
}

const FIELD_KEYS = {
  reason: 'admin.audit.field.reason',
  identity_verified: 'admin.audit.field.identityVerified',
  error_class: 'admin.audit.field.errorClass',
  title_from: 'admin.audit.field.titleFrom',
  title_to: 'admin.audit.field.titleTo',
  from_status: 'admin.audit.field.fromStatus',
  to_status: 'admin.audit.field.toStatus',
  assignee_from: 'admin.audit.field.assigneeFrom',
  assignee_to: 'admin.audit.field.assigneeTo',
  remark_updated: 'admin.audit.field.remarkUpdated',
  role: 'admin.audit.field.role',
  role_from: 'admin.audit.field.roleFrom',
  role_to: 'admin.audit.field.roleTo',
  is_active_from: 'admin.audit.field.isActiveFrom',
  is_active_to: 'admin.audit.field.isActiveTo',
  username_changed: 'admin.audit.field.usernameChanged',
  permission: 'admin.audit.field.permission',
  expires_at: 'admin.audit.field.expiresAt',
  grant_id: 'admin.audit.field.grantId',
  line_id: 'admin.audit.field.lineId',
  product_id: 'admin.audit.field.productId',
  line_count: 'admin.audit.field.lineCount',
  query: 'admin.audit.field.query',
  error_code: 'admin.audit.field.errorCode'
}

const REASON_KEYS = {
  success: 'admin.audit.reason.success',
  wrong_password: 'admin.audit.reason.wrongPassword',
  user_not_found: 'admin.audit.reason.userNotFound',
  disabled: 'admin.audit.reason.disabled',
  admin_reset: 'admin.audit.reason.adminReset',
  self_change: 'admin.audit.reason.selfChange'
}

const STATUS_KEYS = {
  open: 'admin.audit.status.open',
  processing: 'admin.audit.status.processing',
  resolved: 'admin.audit.status.resolved',
  closed: 'admin.audit.status.closed'
}

function actionLabel(code) {
  const key = ACTION_KEYS[code]
  return key ? t(key) : t('admin.audit.action.unknown')
}

// 未登录的动作（如客户自己提交工单）后端记 "-"，直接展示像数据缺失
function displayUsername(value) {
  return value && value !== '-' ? value : t('admin.audit.anonymous')
}

function targetText(row) {
  if (row.target_name) return row.target_name
  if (row.target_id) return row.target_id
  return t('admin.audit.detail.targetNone')
}

function fieldLabel(key) {
  const mapped = FIELD_KEYS[key]
  return mapped ? t(mapped) : key
}

function fieldValue(key, value) {
  if (value === null || value === undefined || value === '') return '-'
  if (key === 'identity_verified') {
    return value ? t('admin.audit.verified.yes') : t('admin.audit.verified.no')
  }
  if (key === 'reason') {
    const mapped = REASON_KEYS[value]
    return mapped ? t(mapped) : String(value)
  }
  if (key === 'from_status' || key === 'to_status') {
    const mapped = STATUS_KEYS[value]
    return mapped ? t(mapped) : String(value)
  }
  if (typeof value === 'boolean') return value ? '✓' : '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

// JSONB 存储会重排键（PG 按长度+字节序），直接遍历会得到「新标题 / 原标题」这种倒序，
// 所以按业务阅读顺序固定排列；未登记的键排在最后，原样展示便于排查。
const FIELD_ORDER = [
  'reason', 'identity_verified', 'error_class', 'title_from', 'title_to',
  'from_status', 'to_status', 'assignee_from', 'assignee_to', 'remark_updated',
  'role', 'role_from', 'role_to', 'is_active_from', 'is_active_to', 'username_changed',
  'permission', 'expires_at', 'grant_id',
  'line_id', 'product_id', 'line_count', 'query', 'error_code'
]

const extraFields = computed(() => {
  const payload = detail.value?.detail || {}
  return Object.keys(payload)
    .sort((a, b) => {
      const left = FIELD_ORDER.indexOf(a)
      const right = FIELD_ORDER.indexOf(b)
      return (left === -1 ? FIELD_ORDER.length : left) - (right === -1 ? FIELD_ORDER.length : right)
    })
    .map((key) => ({
      key,
      label: fieldLabel(key),
      value: fieldValue(key, payload[key])
    }))
})

function buildParams() {
  const params = { page: pagination.page, page_size: pagination.pageSize }
  if (filters.username.trim()) params.username = filters.username.trim()
  if (filters.action) params.action = filters.action
  if (filters.result) params.result = filters.result
  if (filters.keyword.trim()) params.keyword = filters.keyword.trim()
  const [start, end] = filters.range || []
  if (start) params.start_date = start
  if (end) params.end_date = end
  return params
}

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const [page, summaryData] = await Promise.all([
      adminListAuditLogs(buildParams()),
      adminAuditSummary({ days: 7, limit: 20 })
    ])
    rows.value = page.items
    pagination.total = page.total
    summary.value = summaryData
  } catch (e) {
    rows.value = []
    loadError.value = errorMessage(e, { fallbackKey: 'admin.audit.loadFailed' })
  } finally {
    loading.value = false
  }
}

function search() {
  pagination.page = 1
  load()
}

function onReset() {
  Object.assign(filters, { username: '', action: '', result: '', keyword: '', range: [] })
  search()
}

async function openDetail(row) {
  try {
    detail.value = await adminGetAuditLog(row.id)
    panelVisible.value = true
  } catch (e) {
    ElMessage.error(errorMessage(e, { fallbackKey: 'admin.audit.loadFailed' }))
  }
}

async function onExport() {
  exporting.value = true
  try {
    const blob = await adminExportAuditLogs(buildParams())
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `audit-logs-${new Date().toISOString().slice(0, 10)}.csv`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  } catch (e) {
    ElMessage.error(errorMessage(e, { fallbackKey: 'admin.audit.exportFailed' }))
  } finally {
    exporting.value = false
  }
}

onMounted(async () => {
  await load()
  try {
    actions.value = await adminAuditActions()
  } catch {
    // 动作清单拿不到不影响主列表，筛选下拉留空即可
    actions.value = []
  }
})
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

.intro {
  margin: 0 0 12px;
  color: #909399;
  font-size: 13px;
}

.summary {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}

.stat {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 16px;
  background: #f5f7fa;
  border-radius: 6px;
  min-width: 140px;
}

.stat.grow {
  flex: 1;
}

.stat-label {
  font-size: 12px;
  color: #909399;
}

.stat-value {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.stat-value.danger {
  color: #f56c6c;
}

.ip-tag {
  margin-left: 6px;
}

.filters {
  margin-bottom: 4px;
}

.w-account {
  width: 180px;
}

.w-action {
  width: 190px;
}

.w-result {
  width: 130px;
}

.w-date {
  width: 260px;
}

.w-keyword {
  width: 220px;
}

.table {
  width: 100%;
}

.pager {
  margin-top: 16px;
  justify-content: flex-end;
}

.desc {
  margin-bottom: 16px;
}

.extra-title {
  font-weight: 600;
  font-size: 14px;
  margin: 8px 0 10px;
}

.empty-extra {
  margin: 0;
  color: #909399;
  font-size: 13px;
}

.mono {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 12px;
  word-break: break-all;
}

.ua {
  font-size: 12px;
  color: #606266;
  word-break: break-all;
}
</style>
