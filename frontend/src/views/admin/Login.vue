<template>
  <div class="login-page">
    <el-card class="login-card" shadow="always">
      <h1 class="title">{{ $t('common.appName') }}</h1>
      <p class="subtitle">{{ $t('admin.login.subtitle') }}</p>

      <!-- 空闲超时被踢回来时给个说明，否则用户以为自己点错了 -->
      <el-alert
        v-if="idleNotice"
        type="info"
        show-icon
        :closable="false"
        :title="$t('admin.login.idleLogout')"
        class="error"
      />

      <el-alert
        v-if="formError"
        :title="formError"
        type="error"
        :closable="false"
        show-icon
        class="error"
      />

      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent>
        <el-form-item :label="$t('admin.login.username')" prop="username">
          <el-input
            v-model="form.username"
            :placeholder="$t('admin.login.usernamePlaceholder')"
            autocomplete="username"
          />
        </el-form-item>
        <el-form-item :label="$t('admin.login.password')" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            :placeholder="$t('admin.login.passwordPlaceholder')"
            autocomplete="current-password"
            @keyup.enter="onSubmit"
          />
        </el-form-item>
        <el-button type="primary" class="submit" :loading="loading" @click="onSubmit">
          {{ $t('admin.login.submit') }}
        </el-button>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { login } from '../../api/auth'
import { setPermissions } from '../../utils/permissions'
import { resetActivity } from '../../utils/idle'
import { errorMessage } from '../../utils/error'

const router = useRouter()
const route = useRoute()
const { t } = useI18n()
const formRef = ref()
const loading = ref(false)
// 原名 errorText，与 utils/error 导出的 errorText 概念撞车，改为 formError
const formError = ref('')
// 守卫因空闲超时把用户踢回来时会带 reason=idle
const idleNotice = computed(() => route.query.reason === 'idle')

const form = reactive({ username: '', password: '' })
// computed：语言切换后校验文案跟着变
const rules = computed(() => ({
  username: [{ required: true, message: t('admin.login.usernameRequired'), trigger: 'blur' }],
  password: [{ required: true, message: t('admin.login.passwordRequired'), trigger: 'blur' }]
}))

async function onSubmit() {
  formError.value = ''
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    const data = await login({ username: form.username, password: form.password })
    localStorage.setItem('token', data.access_token)
    localStorage.setItem('user', JSON.stringify(data.user))
    setPermissions(data.permissions)
    // 立刻重置空闲计时：登录页可能开着很久，不重置会被紧接着的路由守卫判成超时，
    // 表现为"刚登录成功又被踢回登录页"
    resetActivity()
    ElMessage.success(t('admin.login.success'))
    router.replace(typeof route.query.redirect === 'string' ? route.query.redirect : '/admin')
  } catch (error) {
    // 契约 §0.3：登录失败在表单内提示，不跳转
    formError.value = errorMessage(error, { fallbackKey: 'admin.login.failed' })
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100%;
  padding: 24px;
}

.login-card {
  width: 360px;
  padding: 8px 8px 16px;
}

.title {
  margin: 8px 0 4px;
  font-size: 20px;
  text-align: center;
}

.subtitle {
  margin: 0 0 20px;
  color: #909399;
  font-size: 13px;
  text-align: center;
}

.error {
  margin-bottom: 16px;
}

.submit {
  width: 100%;
  margin-top: 4px;
}
</style>
