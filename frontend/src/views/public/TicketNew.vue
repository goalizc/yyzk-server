<template>
  <div class="ticket-new">
    <el-page-header content="提交工单" @back="router.back()" class="page-header" />

    <el-card v-if="contextTitle" shadow="never" class="block">
      <template #header>已关联的问题</template>
      <p class="context">
        {{ contextTitle }}
      </p>
      <p v-if="contextParts" class="muted">{{ contextParts }}</p>
    </el-card>

    <el-card shadow="never" class="block">
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="96px"
        @submit.prevent="onSubmit"
      >
        <el-form-item label="联系方式" prop="contact">
          <el-input v-model="form.contact" placeholder="手机号或邮箱，便于工程师联系您" maxlength="100" />
        </el-form-item>

        <el-form-item label="称呼" prop="contact_name">
          <el-input v-model="form.contact_name" placeholder="选填，如：张先生" maxlength="50" />
        </el-form-item>

        <el-form-item label="问题描述" prop="description">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="5"
            maxlength="2000"
            show-word-limit
            placeholder="请描述故障现象、已尝试的步骤、机器型号等信息（至少 5 个字）"
          />
        </el-form-item>

        <el-form-item label="需要上门">
          <el-switch v-model="form.need_on_site" active-text="需要工程师上门" />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="submitting" @click="onSubmit">提交工单</el-button>
          <el-button @click="router.back()">返回</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { submitTicket } from '../../api/ticket'

const route = useRoute()
const router = useRouter()

const formRef = ref()
const submitting = ref(false)

const form = reactive({
  contact: '',
  contact_name: '',
  description: '',
  need_on_site: false
})

const rules = {
  contact: [
    { required: true, message: '请填写联系方式', trigger: 'blur' },
    { min: 5, max: 100, message: '联系方式长度需在 5–100 之间', trigger: 'blur' }
  ],
  description: [
    { required: true, message: '请描述故障情况', trigger: 'blur' },
    { min: 5, max: 2000, message: '问题描述需在 5–2000 字之间', trigger: 'blur' }
  ]
}

const contextTitle = computed(() => route.query.fault_title || '')
const contextParts = computed(() => {
  const parts = [route.query.product_name, route.query.part_name].filter(Boolean)
  return parts.join(' / ')
})

function payload() {
  const body = {
    contact: form.contact.trim(),
    contact_name: form.contact_name.trim() || null,
    description: form.description.trim(),
    need_on_site: form.need_on_site
  }
  // 选填的上下文：用户可能直接从首页进来
  for (const key of ['product_id', 'part_id', 'fault_id']) {
    const value = route.query[key]
    if (value) body[key] = Number(value)
  }
  return body
}

async function onSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    const data = await submitTicket(payload())
    router.replace({
      name: 'ticket-success',
      query: { ticket_no: data.ticket_no, created_at: data.created_at }
    })
  } catch (e) {
    const body = e.response?.data
    if (e.response?.status === 429) {
      ElMessage.warning('提交太频繁，请稍后再试')
    } else {
      ElMessage.error(body?.detail || '提交失败，请稍后重试')
    }
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.page-header {
  margin-bottom: 16px;
}

.block {
  margin-bottom: 16px;
}

.context {
  margin: 0;
  font-weight: 600;
}

.muted {
  margin: 4px 0 0;
  color: #909399;
  font-size: 13px;
}
</style>
