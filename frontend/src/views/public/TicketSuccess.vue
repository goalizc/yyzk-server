<template>
  <div class="ticket-success">
    <el-card shadow="never">
      <el-result icon="success" title="工单已提交" sub-title="我们会尽快与您联系，请保持电话畅通">
        <template #extra>
          <div class="ticket-no">
            <span class="label">工单号</span>
            <span class="value">{{ ticketNo || '-' }}</span>
            <el-button v-if="ticketNo" link type="primary" @click="copy">复制</el-button>
          </div>
          <p v-if="createdAt" class="time">提交时间：{{ formatDateTime(createdAt) }}</p>

          <div class="actions">
            <el-button type="primary" @click="router.push('/')">返回首页</el-button>
          </div>
        </template>
      </el-result>
    </el-card>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { formatDateTime } from '../../utils/format'

const route = useRoute()
const router = useRouter()

const ticketNo = computed(() => String(route.query.ticket_no || ''))
const createdAt = computed(() => String(route.query.created_at || ''))

async function copy() {
  try {
    await navigator.clipboard.writeText(ticketNo.value)
    ElMessage.success('已复制工单号')
  } catch {
    ElMessage.warning('复制失败，请手动记录工单号')
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
