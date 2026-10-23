<template>
  <div class="page">
    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>{{ $t('admin.page.users') }}</span>
          <div class="head-actions">
            <el-input v-model="filters.keyword" :placeholder="$t('admin.user.list.searchPlaceholder')" clearable class="kw" @input="onKeywordInput" @clear="reload" />
            <el-select v-model="filters.role" :placeholder="$t('admin.user.list.allRoles')" clearable class="role" @change="reload">
              <el-option v-for="item in roleOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
            <el-select v-model="filters.isActive" :placeholder="$t('admin.user.list.allStatuses')" clearable class="status" @change="reload">
              <el-option :label="$t('admin.user.list.enabled')" :value="true" />
              <el-option :label="$t('admin.user.list.disabled')" :value="false" />
            </el-select>
            <el-button v-if="canWrite" type="primary" @click="openCreate">{{ $t('admin.user.list.newUser') }}</el-button>
          </div>
        </div>
      </template>

      <ErrorState v-if="loadError" :error="loadError" @retry="load" />
      <el-table v-else v-loading="loading" :data="rows" row-key="id" border @row-click="onRowClick">
        <el-table-column :label="$t('admin.user.list.colUser')" min-width="180">
          <template #default="{ row }">
            <div class="name">{{ row.username }}</div>
            <div class="sub">{{ row.real_name }}</div>
          </template>
        </el-table-column>
        <el-table-column :label="$t('admin.user.list.colRole')" width="140">
          <template #default="{ row }">
            <div>{{ roleLabel(row.role) }}</div>
            <el-tag
              v-if="row.active_grant_count > 0"
              type="warning"
              size="small"
              class="grant-tag"
              @click.stop="openGrants(row)"
            >
              {{ $t('admin.user.list.activeGrants', { count: row.active_grant_count }) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="$t('admin.user.list.colLines')" min-width="180">
          <template #default="{ row }">
            <el-tag v-for="line in row.product_lines" :key="line.id" size="small" class="tag">
              {{ line.name }}{{ line.expires_at ? $t('admin.user.list.temporary') : '' }}
            </el-tag>
            <span v-if="!row.product_lines.length" class="sub">{{ $t('admin.user.list.noLines') }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('admin.user.list.colStatus')" width="110" align="center">
          <template #default="{ row }">
            <el-switch
              v-if="canWrite && row.id !== currentUserId"
              :model-value="row.is_active"
              :loading="togglingId === row.id"
              inline-prompt
              :active-text="$t('admin.user.list.enabled')"
              :inactive-text="$t('admin.user.list.disabled')"
              @click.stop
              @change="(value) => onToggleActive(row, value)"
            />
            <span v-else>{{ row.is_active ? $t('admin.user.list.enabled') : $t('admin.user.list.disabled') }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('admin.user.list.colLastLogin')" width="140">
          <template #default="{ row }">{{ row.last_login_at ? formatDateTime(row.last_login_at) : $t('admin.user.list.neverLoggedIn') }}</template>
        </el-table-column>
        <el-table-column :label="$t('admin.user.list.colActions')" width="270" align="center">
          <template #default="{ row }">
            <el-button v-if="canWrite" link type="primary" @click.stop="openEdit(row)">{{ $t('common.action.edit') }}</el-button>
            <el-button v-if="canWrite" link type="warning" @click.stop="onResetPassword(row)">{{ $t('admin.user.list.resetPassword') }}</el-button>
            <el-button link type="info" @click.stop="openGrants(row)">{{ $t('admin.user.list.grant') }}</el-button>
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
      :title="editingId ? $t('admin.user.form.editTitle') : $t('admin.user.form.createTitle')"
      :width="isNarrow ? '92%' : '620px'"
      @closed="resetForm"
    >
      <el-form ref="formRef" :model="form" :rules="rules" :label-width="formLabelWidth">
        <el-form-item :label="$t('admin.user.form.username')" prop="username">
          <el-input v-model="form.username" maxlength="50" />
          <div v-if="editingId" class="hint">{{ $t('admin.user.form.renameHint') }}</div>
        </el-form-item>
        <el-form-item :label="$t('admin.user.form.realName')" prop="real_name">
          <el-input v-model="form.real_name" maxlength="50" />
        </el-form-item>
        <el-form-item v-if="!editingId" :label="$t('admin.user.form.password')" prop="password">
          <el-input v-model="form.password" type="password" show-password />
        </el-form-item>
        <el-form-item v-if="!editingId" :label="$t('admin.user.form.confirmPassword')" prop="confirm_password">
          <el-input v-model="form.confirm_password" type="password" show-password />
        </el-form-item>
        <el-form-item :label="$t('admin.user.form.role')" prop="role">
          <el-select v-model="form.role">
            <el-option v-for="item in roleOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('admin.user.form.productLines')">
          <div class="assignments">
            <div v-for="(item, index) in form.product_lines" :key="index" class="assignment-row">
              <el-select v-model="item.line_id" :placeholder="$t('admin.user.form.selectLine')" class="line-select">
                <el-option
                  v-for="line in lines"
                  :key="line.id"
                  :label="line.is_active ? line.name : $t('admin.user.form.lineInactive', { name: line.name })"
                  :value="line.id"
                  :disabled="!line.is_active && line.id !== item.line_id"
                />
              </el-select>
              <el-date-picker v-model="item.expires_at" type="date" :placeholder="$t('admin.user.form.longTerm')" class="date" value-format="YYYY-MM-DD" />
              <el-button link type="danger" @click="form.product_lines.splice(index, 1)">{{ $t('common.action.delete') }}</el-button>
            </div>
            <el-button link type="primary" @click="addAssignment">{{ $t('admin.user.form.addLine') }}</el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ $t('common.action.cancel') }}</el-button>
        <el-button type="primary" :loading="submitting" @click="onSubmit">{{ $t('common.action.save') }}</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="passwordVisible" :title="$t('admin.user.reset.doneTitle')" :width="isNarrow ? '92%' : '420px'">
      <el-alert type="success" :closable="false" :title="$t('admin.user.reset.alert')" />
      <div class="password-row">
        <span class="password">{{ resetPassword }}</span>
        <el-button size="small" @click="copyPassword">{{ $t('common.action.copy') }}</el-button>
      </div>
      <template #footer>
        <el-button @click="passwordVisible = false">{{ $t('common.action.close') }}</el-button>
      </template>
    </el-dialog>

    <DetailPanel v-model="grantsVisible" :title="$t('admin.user.grant.title', { name: grantUser?.real_name || '' })" :size="820" @open="loadGrants">
      <el-table :data="grants" size="small" border>
        <el-table-column :label="$t('admin.user.grant.colPermission')" width="150">
          <template #default="{ row }">
            <el-tooltip :content="row.permission" placement="top">
              <span>{{ permissionLabel(row.permission) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column prop="reason" :label="$t('admin.user.grant.colReason')" min-width="120" />
        <el-table-column :label="$t('admin.user.grant.colGrantedBy')" width="110">
          <template #default="{ row }">{{ row.granted_by_name || $t('admin.user.grant.grantedBySystem') }}</template>
        </el-table-column>
        <el-table-column :label="$t('admin.user.grant.colExpiresAt')" width="130">
          <template #default="{ row }">{{ formatDateTime(row.expires_at) }}</template>
        </el-table-column>
        <el-table-column :label="$t('admin.user.grant.colStatus')" width="80">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? $t('admin.user.grant.active') : $t('admin.user.grant.inactive') }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="canWrite" :label="$t('admin.user.grant.colActions')" width="80">
          <template #default="{ row }">
            <el-button v-if="row.is_active" link type="danger" @click="onRevoke(row)">{{ $t('admin.user.grant.revoke') }}</el-button>
          </template>
        </el-table-column>
      </el-table>

      <template v-if="canWrite">
        <el-divider>{{ $t('admin.user.grant.issueTitle') }}</el-divider>
        <el-form ref="grantFormRef" :model="grantForm" :rules="grantRules" :label-width="grantLabelWidth">
          <el-form-item :label="$t('admin.user.grant.permission')" prop="permission">
            <el-select v-model="grantForm.permission">
              <el-option v-for="item in grantableOptions" :key="item" :label="permissionLabel(item)" :value="item" />
            </el-select>
          </el-form-item>
          <el-form-item :label="$t('admin.user.grant.expiresAt')" prop="expires_at">
            <el-date-picker v-model="grantForm.expires_at" type="datetime" value-format="YYYY-MM-DDTHH:mm:ssZ" />
          </el-form-item>
          <el-form-item :label="$t('admin.user.grant.reason')" prop="reason">
            <el-input v-model="grantForm.reason" maxlength="200" />
          </el-form-item>
          <el-button type="primary" :loading="grantSubmitting" @click="onCreateGrant">{{ $t('admin.user.grant.issue') }}</el-button>
        </el-form>
      </template>
    </DetailPanel>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  adminCreateGrant, adminCreateUser, adminListGrants, adminListProductLines,
  adminListUsers, adminReplaceUserLines, adminResetPassword, adminRevokeGrant, adminUpdateUser
} from '../../../api/admin'
import DetailPanel from '../../../components/DetailPanel.vue'
import ErrorState from '../../../components/ErrorState.vue'
import { errorCode } from '../../../utils/admin'
import { errorMessage } from '../../../utils/error'
import { copyText } from '../../../utils/clipboard'
import { formatDateTime } from '../../../utils/format'
import { permissionLabel } from '../../../utils/permissionLabels'
import { hasPermission } from '../../../utils/permissions'
import { useNarrow } from '../../../utils/viewport'
import { useFormLabelWidth } from '../../../utils/formLabel'

// key 用字面量而不是 `common.role.${value}` 拼接：扫描脚本与键完整性检查都依赖字面量
const ROLE_KEYS = {
  super_admin: 'common.role.super_admin',
  supervisor: 'common.role.supervisor',
  agent: 'common.role.agent',
  auditor: 'common.role.auditor'
}
const ROLE_VALUES = Object.keys(ROLE_KEYS)
// 可临时发放的权限码：不包含 user:write，避免通过临时授权绕过用户管理
const GRANTABLE = [
  'ticket:read', 'ticket:write', 'ticket:assign',
  'product:read', 'product:write', 'part:read', 'part:write',
  'fault:read', 'fault:write', 'upload:write', 'stats:read',
  'user:read', 'product_line:read', 'product_line:write'
]

const { t } = useI18n()
const roleOptions = computed(() =>
  ROLE_VALUES.map((value) => ({ value, label: t(ROLE_KEYS[value]) }))
)

// 英文最长标签 "Confirm password"，130px 实测折行
const formLabelWidth = useFormLabelWidth('90px', '150px')
const grantLabelWidth = useFormLabelWidth('80px', '110px')

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

// computed：语言切换后校验文案跟着变
const rules = computed(() => ({
  username: [{ required: true, message: t('admin.user.form.ruleUsername'), trigger: 'blur' }],
  real_name: [{ required: true, message: t('admin.user.form.ruleRealName'), trigger: 'blur' }],
  password: [
    { required: true, message: t('admin.user.form.rulePassword'), trigger: 'blur' },
    { min: 8, message: t('admin.user.form.rulePasswordMin'), trigger: 'blur' }
  ],
  confirm_password: [
    { required: true, message: t('admin.user.form.ruleConfirmRequired'), trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (value !== form.password) callback(new Error(t('admin.user.form.ruleConfirmMismatch')))
        else callback()
      },
      trigger: 'blur'
    }
  ],
  role: [{ required: true, message: t('admin.user.form.ruleRole'), trigger: 'change' }]
}))
const grantRules = computed(() => ({
  permission: [{ required: true, message: t('admin.user.grant.rulePermission'), trigger: 'change' }],
  expires_at: [{ required: true, message: t('admin.user.grant.ruleExpiresAt'), trigger: 'change' }],
  reason: [{ required: true, message: t('admin.user.grant.ruleReason'), trigger: 'blur' }]
}))

const grantableOptions = computed(() => GRANTABLE)

function roleLabel(value) {
  const key = ROLE_KEYS[value]
  return key ? t(key) : value
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
    loadError.value = errorMessage(e, { fallbackKey: 'admin.user.list.loadFailed' })
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

// 与其它列表一致：点行即编辑；只读角色不弹窗
function onRowClick(row) {
  if (!canWrite.value) return
  openEdit(row)
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
        t('admin.user.role.changeConfirm', {
          name: form.real_name,
          from: roleLabel(originalRole.value),
          to: roleLabel(form.role)
        }),
        t('admin.user.role.changeTitle'),
        { type: 'warning', confirmButtonText: t('admin.user.role.confirmChange'), cancelButtonText: t('common.action.cancel') }
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
        username: form.username.trim(),
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
    ElMessage.success(t('admin.user.form.saved'))
    dialogVisible.value = false
    await load()
  } catch (e) {
    if (errorCode(e) === 'USERNAME_DUPLICATED') {
      ElMessage.error(t('admin.user.form.usernameDuplicated'))
      return
    }
    ElMessage.error(errorMessage(e))
  } finally {
    submitting.value = false
  }
}

async function onToggleActive(row, value) {
  // 停用是破坏性操作：开关用 :model-value，取消后不会自己变
  if (value === false) {
    try {
      await ElMessageBox.confirm(
        t('admin.user.toggle.disableConfirm', { name: row.real_name }),
        t('admin.user.toggle.disableTitle'),
        { type: 'warning', confirmButtonText: t('admin.user.toggle.confirmDisable'), cancelButtonText: t('common.action.cancel') }
      )
    } catch {
      return
    }
  }
  togglingId.value = row.id
  try {
    await adminUpdateUser(row.id, { is_active: value })
    row.is_active = value
    ElMessage.success(value ? t('admin.user.toggle.enabled') : t('admin.user.toggle.disabled'))
  } catch (e) {
    ElMessage.error(errorMessage(e, { fallbackKey: 'admin.user.toggle.failed' }))
    await load()
  } finally {
    togglingId.value = null
  }
}

async function onResetPassword(row) {
  try {
    await ElMessageBox.confirm(t('admin.user.reset.confirm', { name: row.real_name }), t('admin.user.reset.title'), { type: 'warning' })
  } catch {
    return
  }
  try {
    const data = await adminResetPassword(row.id)
    resetPassword.value = data.password
    passwordVisible.value = true
  } catch (e) {
    ElMessage.error(errorMessage(e, { fallbackKey: 'admin.user.reset.failed' }))
  }
}

async function copyPassword() {
  const ok = await copyText(resetPassword.value)
  if (ok) ElMessage.success(t('admin.user.grant.copied'))
  else ElMessage.warning(t('admin.user.reset.copyFailedLong'))
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
    ElMessage.error(errorMessage(e, { fallbackKey: 'admin.user.grant.loadFailed' }))
  }
}

async function onCreateGrant() {
  const valid = await grantFormRef.value?.validate().catch(() => false)
  if (!valid) return
  grantSubmitting.value = true
  try {
    await adminCreateGrant(grantUser.value.id, { ...grantForm })
    ElMessage.success(t('admin.user.grant.issued'))
    Object.assign(grantForm, { permission: '', expires_at: '', reason: '' })
    await loadGrants()
  } catch (e) {
    ElMessage.error(errorMessage(e))
  } finally {
    grantSubmitting.value = false
  }
}

async function onRevoke(row) {
  try {
    await adminRevokeGrant(grantUser.value.id, row.id)
    ElMessage.success(t('admin.user.grant.revoked'))
    await loadGrants()
  } catch (e) {
    ElMessage.error(errorMessage(e, { fallbackKey: 'admin.user.grant.revokeFailed' }))
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
.kw { width: 250px; }
.role { width: 140px; }
.status { width: 120px; }
.name { font-weight: 600; }
.sub { color: #909399; font-size: 12px; }
.hint { color: #909399; font-size: 12px; line-height: 1.6; }
.tag { margin-right: 4px; }
.pager { margin-top: 16px; justify-content: flex-end; }
.assignments { display: flex; flex-direction: column; gap: 8px; }
/* 英文「Delete」比中文「删除」宽，三件套写死宽度会把按钮挤出弹窗；
   下拉改为可伸缩、日期固定、允许换行，任何语言都不溢出。
   日期必须带 .assignment-row 前缀：Element 的 .el-date-editor.el-input{width:220px}
   与单独 .date 同权重，靠多一级选择器压过它（实测原先被撑到 220px） */
.assignment-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.line-select { flex: 1 1 140px; min-width: 0; }
.assignment-row .date { flex: 0 0 150px; width: 150px; }
.password-row { margin-top: 16px; display: flex; align-items: center; gap: 12px; }
.password { font-family: monospace; font-size: 18px; letter-spacing: 1px; word-break: break-all; }
.grant-tag { margin-top: 4px; cursor: pointer; }
</style>
