<template>
  <div class="ticket-success">
    <el-card shadow="never">
      <el-result
        icon="success"
        :title="$t('public.ticketSuccess.title')"
        :sub-title="$t('public.ticketSuccess.subtitle')"
      >
        <template #extra>
          <div class="ticket-no">
            <span class="label">{{ $t('public.ticketSuccess.ticketNo') }}</span>
            <span class="value">{{ ticketNo || '-' }}</span>
            <el-button v-if="ticketNo" link type="primary" @click="copy">
              {{ $t('public.ticketSuccess.copy') }}
            </el-button>
          </div>
          <p v-if="createdAt" class="time">
            {{ $t('public.ticketSuccess.createdAt', { time: formatDateTime(createdAt) }) }}
          </p>

          <div class="actions">
            <el-button type="primary" @click="goHome">
              {{ $t('public.ticketSuccess.backHome') }}
            </el-button>
          </div>
        </template>
      </el-result>
    </el-card>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { formatDateTime } from '../../utils/format'
import { currentLocale } from '../../locales'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const ticketNo = computed(() => String(route.query.ticket_no || ''))
const createdAt = computed(() => String(route.query.created_at || ''))

function goHome() {
  router.push(currentLocale() === 'en-US' ? '/en' : '/')
}

async function copy() {
  try {
    await navigator.clipboard.writeText(ticketNo.value)
    ElMessage.success(t('public.ticketSuccess.copied'))
  } catch {
    ElMessage.warning(t('public.ticketSuccess.copyFailed'))
  }
}
</script>

<style scoped>
.ticket-no {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-bottom: 8px;
}

.label {
  color: #909399;
  font-size: 13px;
}

.value {
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 1px;
}

.time {
  margin: 0 0 16px;
  color: #909399;
  font-size: 13px;
}

.actions {
  margin-top: 8px;
}

/* ---------- 手机 ---------- */
@media (max-width: 640px) {
  /* el-result 默认左右各 40px 内边距，375px 屏上只剩 295px，工单号会被折成两行 */
  :deep(.el-result) {
    padding: 24px 4px;
  }

  .ticket-no {
    /* 工单号 + "复制"横排放不下时整体换行，而不是把号码截断 */
    flex-wrap: wrap;
    gap: 4px 8px;
  }

  .value {
    font-size: 17px;
    /* 超长工单号（如时间戳式 TK2026102100041234）允许从任意处断开 */
    word-break: break-all;
  }

  /* "复制"是 link 型按钮，视觉只有 20px 高，但点击区必须够 */
  .ticket-no :deep(.el-button) {
    min-height: var(--tap-min);
    padding: 0 10px;
  }

  .time {
    line-height: 1.6;
  }

  /* 结果动作在手机上撑满整行 */
  .actions :deep(.el-button) {
    width: 100%;
  }
}
</style>
