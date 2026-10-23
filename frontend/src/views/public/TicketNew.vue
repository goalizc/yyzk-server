<template>
  <div class="ticket-new">
    <el-page-header :content="$t('public.ticketNew.pageTitle')" @back="router.back()" class="page-header" />

    <el-card v-if="contextTitle" shadow="never" class="block">
      <template #header>{{ $t('public.ticketNew.related') }}</template>
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
        <el-form-item :label="$t('public.ticketNew.contact')" prop="contact">
          <el-input
            v-model="form.contact"
            :placeholder="$t('public.ticketNew.contactPlaceholder')"
            maxlength="100"
          />
        </el-form-item>

        <el-form-item :label="$t('public.ticketNew.name')" prop="contact_name">
          <el-input
            v-model="form.contact_name"
            :placeholder="$t('public.ticketNew.namePlaceholder')"
            maxlength="50"
          />
        </el-form-item>

        <el-form-item :label="$t('public.ticketNew.description')" prop="description">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="descriptionRows"
            maxlength="2000"
            show-word-limit
            :placeholder="$t('public.ticketNew.descriptionPlaceholder')"
          />
        </el-form-item>

        <el-form-item :label="$t('public.ticketNew.needOnSite')">
          <el-switch v-model="form.need_on_site" :active-text="$t('public.ticketNew.needOnSiteText')" />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="submitting" @click="onSubmit">
            {{ $t('public.ticketNew.submit') }}
          </el-button>
          <el-button @click="router.back()">{{ $t('public.ticketNew.back') }}</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { submitTicket } from '../../api/ticket'
import { errorMessage } from '../../utils/error'
import { localeRoute } from '../../locales'
import { useFormLabelWidth } from '../../utils/formLabel'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const formRef = ref()
const submitting = ref(false)

// 96px 的左侧标签在 375px 屏上要占掉四分之一宽度，输入框只剩 180px 左右，
// 联系方式这种长占位符直接被截断。手机上改为标签在上、输入框在下，撑满整行。
const NARROW_QUERY = '(max-width: 640px)'
const isNarrow = ref(false)
// 英文 "On-site service" 比中文「需要上门」长一倍，96px 会折行。
// 窄屏是 label-position="top"（标签独占一行），此时宽度无意义，保持 auto。
const fullLabelWidth = useFormLabelWidth('96px', '130px')
const labelWidth = computed(() => (isNarrow.value ? 'auto' : fullLabelWidth.value))
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

// computed：语言切换后校验文案跟着变
const rules = computed(() => ({
  contact: [
    { required: true, message: t('public.ticketNew.contactRequired'), trigger: 'blur' },
    { min: 5, max: 100, message: t('public.ticketNew.contactLength'), trigger: 'blur' }
  ],
  description: [
    { required: true, message: t('public.ticketNew.descriptionRequired'), trigger: 'blur' },
    { min: 5, max: 2000, message: t('public.ticketNew.descriptionLength'), trigger: 'blur' }
  ]
}))

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
    router.replace(
      localeRoute('ticket-success', {}, {
        ticket_no: data.ticket_no,
        created_at: data.created_at
      })
    )
  } catch (e) {
    if (e.response?.status === 429) {
      ElMessage.warning(t('public.ticketNew.tooFrequent'))
    } else {
      ElMessage.error(errorMessage(e, { fallbackKey: 'public.ticketNew.submitFailed' }))
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
