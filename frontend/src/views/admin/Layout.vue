<template>
  <el-container class="layout">
    <el-aside v-if="!isNarrow" width="200px" class="aside">
      <div class="brand">售后故障诊断</div>
      <el-menu :default-active="activeMenu" router class="menu">
        <el-menu-item v-for="item in navItems" :key="item.path" :index="item.path">
          {{ item.label }}
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container class="body">
      <el-header class="header">
        <span class="title">{{ pageTitle }}</span>

        <!-- 手机上侧栏收起（固定 200px 会把表格挤成一列并撑出横向滚动），
             导航改放顶栏下拉，路由变化后自动收起 -->
        <el-dropdown v-if="isNarrow" trigger="click" class="nav-dropdown" @command="onNav">
          <el-button text>
            {{ pageTitle }}<span class="caret">▾</span>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item
                v-for="item in navItems"
                :key="item.path"
                :command="item.path"
                :disabled="activeMenu === item.path"
              >
                {{ item.label }}
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>

        <div class="actions">
          <span v-if="!isNarrow" class="user">{{ displayName }}</span>
          <el-tag v-if="!isNarrow && roleLabel" size="small" type="info">{{ roleLabel }}</el-tag>
          <el-button link type="primary" @click="passwordVisible = true">修改密码</el-button>
          <el-button link type="danger" @click="onLogout">退出登录</el-button>
        </div>
      </el-header>

      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>

    <el-dialog v-model="passwordVisible" title="修改密码" :width="dialogWidth" @closed="resetForm">
      <el-form ref="formRef" :model="form" :rules="rules" :label-width="isNarrow ? 'auto' : '96px'" :label-position="isNarrow ? 'top' : 'right'">
        <el-form-item label="原密码" prop="oldPassword" :error="oldPasswordError">
          <el-input v-model="form.oldPassword" type="password" show-password />
        </el-form-item>
        <el-form-item label="新密码" prop="newPassword" :error="newPasswordError">
          <el-input v-model="form.newPassword" type="password" show-password />
        </el-form-item>
        <el-form-item label="确认新密码" prop="confirmPassword">
          <el-input v-model="form.confirmPassword" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="passwordVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="onSubmit">保存</el-button>
      </template>
    </el-dialog>
  </el-container>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { changePassword, fetchMe } from '../../api/auth'
import { clearPermissions, hasPermission, setPermissions } from '../../utils/permissions'
import { errorCode, errorText } from '../../utils/admin'

const route = useRoute()
const router = useRouter()

const passwordVisible = ref(false)
const submitting = ref(false)
const oldPasswordError = ref('')
const newPasswordError = ref('')
const formRef = ref()

const form = reactive({ oldPassword: '', newPassword: '', confirmPassword: '' })

const user = computed(() => {
  try {
    return JSON.parse(localStorage.getItem('user') || '{}')
  } catch {
    return {}
  }
})

const displayName = computed(() => user.value.real_name || user.value.username || '已登录')
const roleLabel = computed(() => {
  const map = {
    super_admin: '超级管理员',
    supervisor: '售后主管',
    agent: '一线客服',
    auditor: '只读审计'
  }
  return map[user.value.role] || ''
})

const pageTitle = computed(() => route.meta?.title || '后台管理')

// /admin/faults/edit/:id? 也要让侧边栏"故障知识库"保持高亮
const activeMenu = computed(() => {
  const path = route.path
  if (path.startsWith('/admin/faults')) return '/admin/faults'
  return path
})

// ---------- 窄屏（手机）布局 ----------
// 侧栏固定 200px，在 390px 屏上会占掉一半宽度，剩下的表格被挤成一列并撑出
// 横向滚动（实测 scrollWidth 473 > clientWidth 390）。窄屏改为顶栏下拉导航。
const NARROW_QUERY = '(max-width: 768px)'
const isNarrow = ref(false)
const dialogWidth = computed(() => (isNarrow.value ? '92%' : '420px'))

const NAV_ITEMS = [
  { path: '/admin/tickets', label: '工单管理', permission: 'ticket:read' },
  { path: '/admin/products', label: '产品管理', permission: 'product:read' },
  { path: '/admin/parts', label: '零件管理', permission: 'part:read' },
  { path: '/admin/faults', label: '故障知识库', permission: 'fault:read' },
  { path: '/admin/stats', label: '数据看板', permission: 'stats:read' }
]

const navItems = computed(() => NAV_ITEMS.filter((item) => hasPermission(item.permission)))

function onNav(path) {
  router.push(path)
}

let narrowMql = null
const syncNarrow = (event) => {
  isNarrow.value = event.matches
}

onMounted(() => {
  narrowMql = window.matchMedia?.(NARROW_QUERY)
  if (!narrowMql) return
  isNarrow.value = narrowMql.matches
  narrowMql.addEventListener?.('change', syncNarrow)
})

onBeforeUnmount(() => narrowMql?.removeEventListener?.('change', syncNarrow))

// 每次后台路由切换刷新权限（管理员可能刚改了授权/角色）
watch(
  () => route.fullPath,
  async () => {
    try {
      const data = await fetchMe()
      setPermissions(data.permissions)
    } catch {
      // 401/403 已由拦截器跳登录；网络错误忽略，避免误退出
    }
  }
)

const rules = {
  oldPassword: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 8, message: '新密码至少 8 位', trigger: 'blur' },
    {
      // P-11 规则 1：新旧密码不能相同，前端先拦，后端用哈希比对兜底（PASSWORD_SAME）。
      // newPasswordError 优先：服务端回文案后再次校验也要保持报错，不能被"本轮通过"清掉。
      // callback 传字符串而不是 Error —— async-validator 收到 Error 只取 .message 存成裸串，
      // Element Plus 读不到 .message 就不渲染。
      validator: (_rule, value, callback) => {
        if (newPasswordError.value) callback(newPasswordError.value)
        else if (value && value === form.oldPassword) callback('新密码不能与原密码相同')
        else callback()
      }
    }
  ],
  confirmPassword: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    {
      // 契约 §1：两次一致由前端校验，后端只信任 new_password
      validator: (_rule, value, callback) => {
        if (value !== form.newPassword) callback(new Error('两次输入的密码不一致'))
        else callback()
      },
      trigger: 'blur'
    }
  ]
}

function resetForm() {
  form.oldPassword = ''
  form.newPassword = ''
  form.confirmPassword = ''
  oldPasswordError.value = ''
  newPasswordError.value = ''
  formRef.value?.clearValidate()
}

async function onSubmit() {
  oldPasswordError.value = ''
  newPasswordError.value = ''
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    await changePassword({ old_password: form.oldPassword, new_password: form.newPassword })
    ElMessage.success('密码已修改')
    passwordVisible.value = false
  } catch (e) {
    // P-11 规则 3：错误内联在对应字段下，不关闭弹窗
    const code = errorCode(e)
    if (code === 'PASSWORD_INVALID') {
      oldPasswordError.value = errorText(e, '原密码不正确')
    } else if (code === 'PASSWORD_SAME') {
      // 前端已拦过一次；能到这里说明字符不同但哈希等价（极罕见），或前端校验被绕过。
      // 校验器的第一优先级就是 newPasswordError，所以这次 validateField 会稳定报错，
      // 不会像"校验通过则清空"那样把服务端文案吞掉
      newPasswordError.value = errorText(e, '新密码不能与原密码相同')
      await formRef.value?.validateField('newPassword').catch(() => {})
    } else {
      ElMessage.error(errorText(e, '修改失败，请稍后重试'))
    }
  } finally {
    submitting.value = false
  }
}

function onLogout() {
  localStorage.removeItem('token')
  localStorage.removeItem('user')
  clearPermissions()
  router.replace('/admin/login')
}
</script>

<style scoped>
.layout {
  min-height: 100vh;
}

.aside {
  background: #fff;
  border-right: 1px solid #e4e7ed;
  display: flex;
  flex-direction: column;
}

.brand {
  height: 56px;
  display: flex;
  align-items: center;
  padding: 0 20px;
  font-size: 15px;
  font-weight: 600;
  border-bottom: 1px solid #e4e7ed;
}

.menu {
  border-right: none;
  flex: 1;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
}

.title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user {
  color: #606266;
  font-size: 13px;
}

.main {
  background: #f5f7fa;
  padding: 16px;
}

.nav-dropdown {
  margin-left: auto;
  margin-right: 8px;
}

.caret {
  margin-left: 4px;
  font-size: 11px;
  color: #909399;
}

/* ---------- 窄屏 ---------- */
@media (max-width: 768px) {
  /* 顶栏 60px 高（默认）+ 安全区，按钮的 44px 命中区才放得下 */
  .header {
    height: auto;
    min-height: 56px;
    padding: 6px 12px;
    padding-top: calc(6px + var(--safe-top));
    gap: 8px;
    flex-wrap: nowrap;
    overflow: hidden;
  }

  /* 标题与下拉里的文字重复，窄屏只留下拉（它本身就是当前页名 + 导航入口） */
  .title {
    display: none;
  }

  .nav-dropdown {
    margin-left: 0;
    margin-right: auto;
    min-width: 0;
    flex: 1;
  }

  .nav-dropdown :deep(.el-button) {
    min-height: var(--tap-min);
    padding: 0 8px;
    font-size: 15px;
    font-weight: 600;
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* 两个文字按钮横排在 390px 屏上会和标题抢空间，
     去掉间距并收到右侧，各自仍有 44px 命中高度 */
  .actions {
    gap: 2px;
    flex-shrink: 0;
  }

  /* 顶栏三个元素（下拉 / 修改密码 / 退出登录）加起来约 300px，
     390px 屏上贴着排会显得拥挤。缩小字号与内边距，保证不相互挤压换行。 */
  .actions :deep(.el-button) {
    font-size: 13px;
    min-height: var(--tap-min);
    padding: 0 6px;
  }

  /* 表格页的内边距在窄屏上是纯浪费，全部让给内容宽度 */
  .main {
    padding: 10px;
  }

  .brand {
    padding: 0 12px;
  }
}
</style>
