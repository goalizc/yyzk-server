<template>
  <el-container class="layout">
    <el-header class="header">
      <span class="brand">售后故障诊断系统</span>
      <div class="actions">
        <span class="user">{{ displayName }}</span>
        <el-button link type="primary" @click="passwordVisible = true">修改密码</el-button>
        <el-button link type="danger" @click="onLogout">退出登录</el-button>
      </div>
    </el-header>

    <el-main>
      <router-view />
    </el-main>

    <el-dialog v-model="passwordVisible" title="修改密码" width="420px" @closed="resetForm">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="88px">
        <el-form-item label="原密码" prop="oldPassword">
          <el-input v-model="form.oldPassword" type="password" show-password />
        </el-form-item>
        <el-form-item label="新密码" prop="newPassword">
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
import { useRouter } from 'vue-router'
import { changePassword } from '../../api/auth'

const router = useRouter()
const passwordVisible = ref(false)
const submitting = ref(false)
const formRef = ref()

const form = reactive({ oldPassword: '', newPassword: '', confirmPassword: '' })

const displayName = computed(() => {
  try {
    return JSON.parse(localStorage.getItem('user') || '{}').real_name || '已登录'
  } catch {
    return '已登录'
  }
})

const rules = {
  oldPassword: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 8, message: '新密码至少 8 位', trigger: 'blur' }
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
  formRef.value?.clearValidate()
}

async function onSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    await changePassword({ old_password: form.oldPassword, new_password: form.newPassword })
    ElMessage.success('密码已修改')
    passwordVisible.value = false
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '修改失败，请稍后重试')
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
  min-height: 100%;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
}

.brand {
  font-size: 16px;
  font-weight: 600;
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
</style>
