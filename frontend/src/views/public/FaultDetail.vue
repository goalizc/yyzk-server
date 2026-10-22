<template>
  <div class="detail">
    <el-page-header content="解决方案" @back="router.back()" class="page-header" />

    <el-card v-if="loading" shadow="never">
      <el-skeleton :rows="6" animated />
    </el-card>

    <el-card v-else-if="error" shadow="never">
      <el-result icon="warning" :title="error.title" :sub-title="error.detail">
        <template #extra>
          <el-button @click="router.push('/')">返回首页</el-button>
          <el-button type="primary" @click="load">重试</el-button>
        </template>
      </el-result>
    </el-card>

    <template v-else-if="fault">
      <FaultSolutionView :fault="fault" show-stats />

      <el-card shadow="never" class="block">
        <template #header>这个方案解决您的问题了吗？</template>

        <el-alert
          v-if="feedbackDone"
          type="success"
          show-icon
          :closable="false"
          :title="feedbackResolved ? '感谢反馈，很高兴帮到您' : '已记录，建议提交工单由工程师跟进'"
          class="fb-alert"
        />

        <div class="actions">
          <el-button type="success" :disabled="feedbackDone" @click="feedback(true)">
            已解决
          </el-button>
          <el-button :disabled="feedbackDone" @click="feedback(false)">未解决</el-button>
          <el-divider direction="vertical" />
          <el-button type="primary" plain @click="goTicket">仍然不行，提交工单</el-button>
        </div>
      </el-card>
    </template>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getFault, sendFeedback } from '../../api/fault'
import FaultSolutionView from '../../components/FaultSolutionView.vue'

const route = useRoute()
const router = useRouter()

const fault = ref(null)
const loading = ref(true)
const error = ref(null)
const queryLogId = ref(null)
const feedbackDone = ref(false)
const feedbackResolved = ref(false)

async function load() {
  loading.value = true
  error.value = null
  try {
    const data = await getFault(route.params.id, route.query.q)
    fault.value = data
    // 契约：query_log_id 必须保存，反馈时回传（否则并发下无法定位日志）
    queryLogId.value = data.query_log_id
  } catch (e) {
    const body = e.response?.data
    error.value = {
      title: body?.code === 'NOT_FOUND' ? '方案不存在或已下架' : '加载失败',
      detail: body?.detail || '请稍后重试'
    }
  } finally {
    loading.value = false
  }
}

async function feedback(resolved) {
  if (!queryLogId.value) {
    ElMessage.warning('反馈信息缺失，请刷新页面重试')
    return
  }
  try {
    await sendFeedback(fault.value.id, {
      query_log_id: queryLogId.value,
      resolved
    })
    feedbackDone.value = true
    feedbackResolved.value = resolved
  } catch (e) {
    const body = e.response?.data
    if (body?.code === 'QUERY_LOG_MISMATCH') {
      // 契约建议：静默忽略并刷新详情（重新取一次日志 id）
      ElMessage.warning('页面数据已过期，正在刷新')
      await load()
      return
    }
    ElMessage.error(body?.detail || '反馈失败，请稍后重试')
  }
}

function goTicket() {
  router.push({
    name: 'ticket-new',
    query: {
      product_id: fault.value.product_id,
      part_id: fault.value.part_id,
      fault_id: fault.value.id,
      product_name: fault.value.product_name,
      part_name: fault.value.part_name,
      fault_title: fault.value.title
    }
  })
}

onMounted(load)
</script>

<style scoped>
.page-header {
  margin-bottom: 16px;
}

.block {
  margin-bottom: 16px;
}

.fb-alert {
  margin-bottom: 16px;
}

.actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
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

  /* 反馈区三个按钮在 375px 上会折成两行且右侧留白不均，
     改成竖排整行——拇指从上往下依次可达，也不容易点错 */
  .actions {
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
  }

  .actions :deep(.el-button) {
    width: 100%;
    margin-left: 0;
  }

  /* 竖排后分隔线没有意义，直接隐藏 */
  .actions :deep(.el-divider) {
    display: none;
  }
}
</style>
