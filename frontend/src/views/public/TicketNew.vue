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
        :label-width="labelWidth"
        :label-position="labelPosition"
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
            :rows="descriptionRows"
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
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { submitTicket } from '../../api/ticket'

const route = useRoute()
const router = useRouter()

const formRef = ref()
const submitting = ref(false)

// 96px 的左侧标签在 375px 屏上要占掉四分之一宽度，输入框只剩 180px 左右，
// 联系方式这种长占位符直接被截断。手机上改为标签在上、输入框在下，撑满整行。
const NARROW_QUERY = '(max-width: 640px)'
const isNarrow = ref(false)
const labelWidth = computed(() => (isNarrow.value ? 'auto' : '96px'))
const labelPosition = computed(() => (isNarrow.value ? 'top' : 'right'))
// 手机屏幕矮，5 行文本框会把"提交工单"按钮顶到首屏之外，先给 4 行
const descriptionRows = computed(() => (isNarrow.value ? 4 : 5))

let mql = null
const syncNarrow = (event) => {
  isNarrow.value = event.matches
}

onMounted(() => {
  mql = window.matchMedia?.(NARROW_QUERY)
  if (!mql) return
  isNarrow.value = mql.matches
  // 窗口旋转/跨断点拖动时同步，避免停在"标签在左"的压缩布局
  mql.addEventListener?.('change', syncNarrow)
})

onBeforeUnmount(() => mql?.removeEventListener?.('change', syncNarrow))

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

/* ---------- 手机 ---------- */
@media (max-width: 640px) {
  .page-header {
    margin-bottom: 12px;
  }

  .block {
    margin-bottom: 12px;
  }

  .block :deep(.el-card__body) {
    padding: 14px;
  }

  .block :deep(.el-card__header) {
    padding: 12px 14px;
    line-height: 1.4;
  }

  .context {
    line-height: 1.5;
    word-break: break-word;
  }

  /* 标签在上时 el-form-item 自带 22px 的下边距，配合标签间距会更透气 */
  .block :deep(.el-form-item) {
    margin-bottom: 18px;
  }

  /* 窄屏由 JS 切换了 label-position="top"，此时纵向空间充裕，
     label-width:auto 会退化成"标签按内容宽度"并对不齐，这里统一顶满 */
  .block :deep(.el-form-item__label) {
    width: 100% !important;
    padding-bottom: 6px;
    line-height: 1.4;
  }

  /* 提交与返回竖排整行：拇指区在屏幕下半部，横排两个按钮右侧那个更难点到 */
  .block :deep(.el-form-item:last-child .el-form-item__content) {
    display: flex;
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
  }

  .block :deep(.el-form-item:last-child .el-button) {
    width: 100%;
    margin-left: 0;
  }

  .muted {
    line-height: 1.5;
  }
}
</style>
