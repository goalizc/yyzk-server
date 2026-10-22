<template>
  <div class="page">
    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>用户管理</span>
          <div class="head-actions">
            <el-input v-model="filters.keyword" placeholder="搜索账号或姓名" clearable class="kw" @input="onKeywordInput" @clear="reload" />
            <el-select v-model="filters.role" placeholder="全部角色" clearable class="role" @change="reload">
              <el-option v-for="item in ROLE_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
            <el-select v-model="filters.isActive" placeholder="全部状态" clearable class="status" @change="reload">
              <el-option label="启用" :value="true" />
              <el-option label="停用" :value="false" />
            </el-select>
            <el-button v-if="canWrite" type="primary" @click="openCreate">新建用户</el-button>
          </div>
        </div>
      </template>

      <ErrorState v-if="loadError" :error="loadError" @retry="load" />
      <el-table v-else v-loading="loading" :data="rows" row-key="id" border>
        <el-table-column label="账号 / 姓名" min-width="180">
          <template #default="{ row }">
            <div class="name">{{ row.username }}</div>
            <div class="sub">{{ row.real_name }}</div>
          </template>
        </el-table-column>
        <el-table-column label="角色" width="140">
          <template #default="{ row }">
            <div>{{ roleLabel(row.role) }}</div>
            <el-tag
              v-if="row.active_grant_count > 0"
              type="warning"
              size="small"
              class="grant-tag"
              @click="openGrants(row)"
            >
              临时授权 {{ row.active_grant_count }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="产品线" min-width="180">
          <template #default="{ row }">
            <el-tag v-for="line in row.product_lines" :key="line.id" size="small" class="tag">
              {{ line.name }}{{ line.expires_at ? '（临时）' : '' }}
            </el-tag>
            <span v-if="!row.product_lines.length" class="sub">未分配</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110" align="center">
          <template #default="{ row }">
            <el-switch
              v-if="canWrite && row.id !== currentUserId"
              :model-value="row.is_active"
              :loading="togglingId === row.id"
              inline-prompt
              active-text="启用"
              inactive-text="停用"
              @change="(value) => onToggleActive(row, value)"
            />
            <span v-else>{{ row.is_active ? '启用' : '停用' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="最近登录" width="140">
          <template #default="{ row }">{{ row.last_login_at ? formatDateTime(row.last_login_at) : '从未登录' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="220" align="center">
          <template #default="{ row }">
            <el-button v-if="canWrite" link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="canWrite" link type="warning" @click="onResetPassword(row)">重置密码</el-button>
            <el-button link type="info" @click="openGrants(row)">临时授权</el-button>
          </template>
        </el-table-column>
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
      :title="editingId ? '编辑用户' : '新建用户'"
      :width="isNarrow ? '92%' : '620px'"
      @closed="resetForm"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="账号" prop="username">
          <el-input v-model="form.username" maxlength="50" :disabled="Boolean(editingId)" />
        </el-form-item>
        <el-form-item label="姓名" prop="real_name">
          <el-input v-model="form.real_name" maxlength="50" />
        </el-form-item>
        <el-form-item v-if="!editingId" label="初始密码" prop="password">
          <el-input v-model="form.password" type="password" show-password />
        </el-form-item>
        <el-form-item v-if="!editingId" label="确认密码" prop="confirm_password">
          <el-input v-model="form.confirm_password" type="password" show-password />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="form.role">
            <el-option v-for="item in ROLE_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="产品线">
          <div class="assignments">
            <div v-for="(item, index) in form.product_lines" :key="index" class="assignment-row">
              <el-select v-model="item.line_id" placeholder="选择产品线" class="line-select">
                <el-option
                  v-for="line in lines"
                  :key="line.id"
                  :label="line.is_active ? line.name : `${line.name}（已停用）`"
                  :value="line.id"
                  :disabled="!line.is_active && line.id !== item.line_id"
                />
              </el-select>
              <el-date-picker v-model="item.expires_at" type="date" placeholder="长期（留空）" class="date" value-format="YYYY-MM-DD" />
              <el-button link type="danger" @click="form.product_lines.splice(index, 1)">删除</el-button>
            </div>
            <el-button link type="primary" @click="addAssignment">添加产品线</el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="onSubmit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="passwordVisible" title="密码已重置" :width="isNarrow ? '92%' : '420px'">
      <el-alert type="success" :closable="false" title="请立即复制并通过安全渠道交给本人，关闭后无法再次查看" />
      <div class="password-row">
        <span class="password">{{ resetPassword }}</span>
        <el-button size="small" @click="copyPassword">复制</el-button>
      </div>
      <template #footer>
        <el-button @click="passwordVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="grantsVisible" :title="`临时授权 — ${grantUser?.real_name || ''}`" :size="isNarrow ? '100%' : '560px'" @open="loadGrants">
      <el-table :data="grants" size="small" border>
        <el-table-column label="权限" width="150">
          <template #default="{ row }">
            <el-tooltip :content="row.permission" placement="top">
              <span>{{ permissionLabel(row.permission) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column prop="reason" label="事由" min-width="120" />
        <el-table-column label="授予人" width="110">
          <template #default="{ row }">{{ row.granted_by_name || '系统' }}</template>
        </el-table-column>
        <el-table-column label="到期" width="130">
          <template #default="{ row }">{{ formatDateTime(row.expires_at) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '生效' : '失效' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="canWrite" label="操作" width="80">
          <template #default="{ row }">
            <el-button v-if="row.is_active" link type="danger" @click="onRevoke(row)">收回</el-button>
          </template>
        </el-table-column>
      </el-table>

      <template v-if="canWrite">
        <el-divider>发放新授权</el-divider>
        <el-form ref="grantFormRef" :model="grantForm" :rules="grantRules" label-width="80px">
          <el-form-item label="权限" prop="permission">
            <el-select v-model="grantForm.permission">
              <el-option v-for="item in grantableOptions" :key="item" :label="permissionLabel(item)" :value="item" />
            </el-select>
          </el-form-item>
          <el-form-item label="到期" prop="expires_at">
            <el-date-picker v-model="grantForm.expires_at" type="datetime" value-format="YYYY-MM-DDTHH:mm:ssZ" />
          </el-form-item>
          <el-form-item label="事由" prop="reason">
            <el-input v-model="grantForm.reason" maxlength="200" />
          </el-form-item>
          <el-button type="primary" :loading="grantSubmitting" @click="onCreateGrant">发放</el-button>
        </el-form>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  adminCreateGrant, adminCreateUser, adminListGrants, adminListProductLines,
  adminListUsers, adminReplaceUserLines, adminResetPassword, adminRevokeGrant, adminUpdateUser
} from '../../../api/admin'
import ErrorState from '../../../components/ErrorState.vue'
import { errorCode, errorText } from '../../../utils/admin'
import { copyText } from '../../../utils/clipboard'
import { formatDateTime } from '../../../utils/format'
import { permissionLabel } from '../../../utils/permissionLabels'
import { hasPermission } from '../../../utils/permissions'
import { useNarrow } from '../../../utils/viewport'

const ROLE_OPTIONS = [
  { value: 'super_admin', label: '超级管理员' },
  { value: 'supervisor', label: '售后主管' },
  { value: 'agent', label: '一线客服' },
  { value: 'auditor', label: '只读审计' }
]
// 可临时发放的权限码：不包含 user:write，避免通过临时授权绕过用户管理
const GRANTABLE = [
  'ticket:read', 'ticket:write', 'ticket:assign',
  'product:read', 'product:write', 'part:read', 'part:write',
  'fault:read', 'fault:write', 'upload:write', 'stats:read',
  'user:read', 'product_line:read', 'product_line:write'
]

const canWrite = computed(() => hasPermission('user:write'))
const isNarrow = useNarrow()
const currentUserId = computed(() => {
  try {
    return JSON.parse(localStorage.getItem('user') || '{}').id
  } catch {
    return null
  }
})

const rows = ref([])
const lines = ref([])
const loading = ref(false)
const loadError = ref('')
const pagination = reactive({ page: 1, pageSize: 20, total: 0 })
const filters = reactive({ keyword: '', role: '', isActive: null })
const togglingId = ref(null)

const dialogVisible = ref(false)
const editingId = ref(null)
const submitting = ref(false)
const formRef = ref()
// 编辑前的角色快照：保存时若发生变化要二次确认（权限立即生效）
const originalRole = ref('')
const form = reactive({
  username: '',
  real_name: '',
  password: '',
  confirm_password: '',
  role: 'agent',
  product_lines: []
})

const passwordVisible = ref(false)
const resetPassword = ref('')

const grantsVisible = ref(false)
const grantUser = ref(null)
const grants = ref([])
const grantSubmitting = ref(false)
const grantFormRef = ref()
const grantForm = reactive({ permission: '', expires_at: '', reason: '' })

const rules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  real_name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入初始密码', trigger: 'blur' },
    { min: 8, message: '密码至少 8 位', trigger: 'blur' }
  ],
  confirm_password: [
    { required: true, message: '请再次输入初始密码', trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (value !== form.password) callback(new Error('两次输入的密码不一致'))
        else callback()
      },
      trigger: 'blur'
    }
  ],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }]
}
const grantRules = {
  permission: [{ required: true, message: '请选择权限', trigger: 'change' }],
  expires_at: [{ required: true, message: '请选择到期时间', trigger: 'change' }],
  reason: [{ required: true, message: '请填写事由', trigger: 'blur' }]
}

const grantableOptions = computed(() => GRANTABLE)

function roleLabel(value) {
  return ROLE_OPTIONS.find((item) => item.value === value)?.label || value
}

let keywordTimer = null

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const params = {
      page: pagination.page,
      page_size: pagination.pageSize,
      ...(filters.keyword.trim() ? { keyword: filters.keyword.trim() } : {}),
      ...(filters.role ? { role: filters.role } : {}),
      ...(filters.isActive === null || filters.isActive === undefined ? {} : { is_active: filters.isActive })
    }
    const data = await adminListUsers(params)
    rows.value = data.items
    pagination.total = data.total
  } catch (e) {
    rows.value = []
    pagination.total = 0
    loadError.value = errorText(e, '用户列表加载失败')
  } finally {
    loading.value = false
  }
}

async function loadLines() {
  try {
    // 拉全量：已停用的产品线也要显示（用户当前已分配的仍可保留）
    const data = await adminListProductLines()
    lines.value = data.items
  } catch {
    lines.value = []
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

function resetForm() {
  editingId.value = null
  originalRole.value = ''
  Object.assign(form, {
    username: '',
    real_name: '',
    password: '',
    confirm_password: '',
    role: 'agent',
    product_lines: []
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
  originalRole.value = row.role
  Object.assign(form, {
    username: row.username,
    real_name: row.real_name,
    role: row.role,
    product_lines: row.product_lines.map((line) => ({
      line_id: line.id,
      expires_at: line.expires_at ? line.expires_at.slice(0, 10) : ''
    }))
  })
  dialogVisible.value = true
}

function addAssignment() {
  form.product_lines.push({ line_id: null, expires_at: '' })
}

function toExpiresAt(value) {
  return value ? `${value}T23:59:59+08:00` : null
}

async function onSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  // 角色变更会立即改变对方权限：保存前明确确认一次
  if (editingId.value && form.role !== originalRole.value) {
    try {
      await ElMessageBox.confirm(
        `将「${form.real_name}」的角色从「${roleLabel(originalRole.value)}」改为「${roleLabel(form.role)}」？其权限会立即变化。`,
        '角色变更确认',
        { type: 'warning', confirmButtonText: '确认变更', cancelButtonText: '取消' }
      )
    } catch {
      return
    }
  }

  const assignments = form.product_lines
    .filter((item) => item.line_id)
    .map((item) => ({ line_id: item.line_id, expires_at: toExpiresAt(item.expires_at) }))

  submitting.value = true
  try {
    if (editingId.value) {
      await adminUpdateUser(editingId.value, {
        real_name: form.real_name.trim(),
        role: form.role
      })
      await adminReplaceUserLines(editingId.value, assignments)
    } else {
      await adminCreateUser({
        username: form.username.trim(),
        real_name: form.real_name.trim(),
        password: form.password,
        role: form.role,
        product_lines: assignments
      })
    }
    ElMessage.success('已保存')
    dialogVisible.value = false
    await load()
  } catch (e) {
    if (errorCode(e) === 'USERNAME_DUPLICATED') {
      ElMessage.error('账号已存在')
      return
    }
    ElMessage.error(errorText(e))
  } finally {
    submitting.value = false
  }
}

async function onToggleActive(row, value) {
  // 停用是破坏性操作：开关用 :model-value，取消后不会自己变
  if (value === false) {
    try {
      await ElMessageBox.confirm(
        `停用后该账号将立即无法登录，确认停用「${row.real_name}」？`,
        '停用确认',
        { type: 'warning', confirmButtonText: '确认停用', cancelButtonText: '取消' }
      )
    } catch {
      return
    }
  }
  togglingId.value = row.id
  try {
    await adminUpdateUser(row.id, { is_active: value })
    row.is_active = value
    ElMessage.success(value ? '已启用' : '已停用')
  } catch (e) {
    ElMessage.error(errorText(e, '状态更新失败'))
    await load()
  } finally {
    togglingId.value = null
  }
}

async function onResetPassword(row) {
  try {
    await ElMessageBox.confirm(`确认重置「${row.real_name}」的密码？`, '重置密码', { type: 'warning' })
  } catch {
    return
  }
  try {
    const data = await adminResetPassword(row.id)
    resetPassword.value = data.password
    passwordVisible.value = true
  } catch (e) {
    ElMessage.error(errorText(e, '重置失败'))
  }
}

async function copyPassword() {
  const ok = await copyText(resetPassword.value)
  if (ok) ElMessage.success('已复制')
  else ElMessage.warning('复制失败，请手动选中密码复制')
}

function openGrants(row) {
  grantUser.value = row
  grantsVisible.value = true
}

async function loadGrants() {
  if (!grantUser.value) return
  try {
    grants.value = await adminListGrants(grantUser.value.id)
  } catch (e) {
    ElMessage.error(errorText(e, '授权记录加载失败'))
  }
}

async function onCreateGrant() {
  const valid = await grantFormRef.value?.validate().catch(() => false)
  if (!valid) return
  grantSubmitting.value = true
  try {
    await adminCreateGrant(grantUser.value.id, { ...grantForm })
    ElMessage.success('已发放')
    Object.assign(grantForm, { permission: '', expires_at: '', reason: '' })
    await loadGrants()
  } catch (e) {
    ElMessage.error(errorText(e))
  } finally {
    grantSubmitting.value = false
  }
}

async function onRevoke(row) {
  try {
    await adminRevokeGrant(grantUser.value.id, row.id)
    ElMessage.success('已收回')
    await loadGrants()
  } catch (e) {
    ElMessage.error(errorText(e, '收回失败'))
  }
}

onMounted(async () => {
  await Promise.all([load(), loadLines()])
})
onBeforeUnmount(() => clearTimeout(keywordTimer))
</script>

<style scoped>
.page { display: flex; flex-direction: column; gap: 16px; }
.head { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.head-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.kw { width: 200px; }
.role { width: 140px; }
.status { width: 120px; }
.name { font-weight: 600; }
.sub { color: #909399; font-size: 12px; }
.tag { margin-right: 4px; }
.pager { margin-top: 16px; justify-content: flex-end; }
.assignments { display: flex; flex-direction: column; gap: 8px; }
.assignment-row { display: flex; gap: 8px; align-items: center; }
.line-select { width: 180px; }
.date { width: 160px; }
.password-row { margin-top: 16px; display: flex; align-items: center; gap: 12px; }
.password { font-family: monospace; font-size: 18px; letter-spacing: 1px; word-break: break-all; }
.grant-tag { margin-top: 4px; cursor: pointer; }
</style>
