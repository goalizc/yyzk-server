<template>
  <el-container class="layout">
    <el-aside width="200px" class="aside">
      <div class="brand">售后故障诊断</div>
      <el-menu :default-active="activeMenu" router class="menu">
        <el-menu-item index="/admin/tickets">工单管理</el-menu-item>
        <el-menu-item index="/admin/products">产品管理</el-menu-item>
        <el-menu-item index="/admin/parts">零件管理</el-menu-item>
        <el-menu-item index="/admin/faults">故障知识库</el-menu-item>
        <el-menu-item index="/admin/stats">数据看板</el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header">
        <span class="title">{{ pageTitle }}</span>
        <div class="actions">
          <span class="user">{{ displayName }}</span>
          <el-tag v-if="roleLabel" size="small" type="info">{{ roleLabel }}</el-tag>
          <el-button link type="primary" @click="passwordVisible = true">修改密码</el-button>
          <el-button link type="danger" @click="onLogout">退出登录</el-button>
        </div>
      </el-header>

      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>

    <el-dialog v-model="passwordVisible" title="修改密码" width="420px" @closed="resetForm">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="96px">
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
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { changePassword } from '../../api/auth'
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
  const map = { admin: '管理员', agent: '客服' }
  return map[user.value.role] || ''
})

const pageTitle = computed(() => route.meta?.title || '后台管理')

// /admin/faults/edit/:id? 也要让侧边栏"故障知识库"保持高亮
const activeMenu = computed(() => {
  const path = route.path
  if (path.startsWith('/admin/faults')) return '/admin/faults'
  return path
})

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
</style>
