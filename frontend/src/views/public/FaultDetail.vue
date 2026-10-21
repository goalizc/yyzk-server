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
      <el-card shadow="never" class="block">
        <h1 class="title">{{ fault.title }}</h1>
        <p class="meta">
          {{ fault.product_name }} / {{ fault.part_name }}
          <span class="dot">·</span>{{ fault.view_count }} 人看过
          <span class="dot">·</span>{{ fault.resolved_count }} 人反馈已解决
        </p>

        <el-alert
          v-if="fault.needs_professional"
          type="error"
          show-icon
          :closable="false"
          title="该故障建议由专业人员处理，请勿自行拆机"
          class="pro-alert"
        />

        <el-descriptions :column="1" border size="small" class="desc">
          <el-descriptions-item label="现象描述">
            {{ fault.symptom || '暂无' }}
          </el-descriptions-item>
          <el-descriptions-item label="可能原因">
            {{ fault.root_cause || '暂无' }}
          </el-descriptions-item>
          <el-descriptions-item v-if="fault.required_tools" label="所需工具">
            {{ fault.required_tools }}
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-card shadow="never" class="block">
        <template #header>排查步骤</template>
        <ol class="steps">
          <li v-for="step in fault.solution_steps" :key="step.step">
            <div class="step-text">{{ step.text }}</div>
            <el-image
              v-if="step.image_url"
              :src="step.image_url"
              fit="contain"
              class="step-image"
              :preview-src-list="[step.image_url]"
              preview-teleported
            />
          </li>
        </ol>
        <p v-if="!fault.solution_steps.length" class="muted">暂无分步说明</p>
      </el-card>

      <el-card v-if="fault.attachment_urls.length" shadow="never" class="block">
        <template #header>相关附件</template>
        <div v-for="file in fault.attachment_urls" :key="file.url" class="attachment">
          <a :href="file.url" target="_blank" rel="noopener">{{ file.name }}</a>
          <span class="muted">{{ formatSize(file.size) }}</span>
        </div>
      </el-card>

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

function formatSize(size) {
  if (!size) return ''
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
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

.title {
  margin: 0 0 8px;
  font-size: 20px;
}

.meta {
  margin: 0 0 16px;
  color: #909399;
  font-size: 13px;
}

.dot {
  margin: 0 6px;
}

.pro-alert,
.fb-alert {
  margin-bottom: 16px;
}

.desc {
  margin-top: 8px;
}

.steps {
  margin: 0;
  padding-left: 20px;
}

.steps li {
  margin-bottom: 16px;
}

.step-text {
  margin-bottom: 8px;
  line-height: 1.6;
}

.step-image {
  max-width: 360px;
  width: 100%;
  border-radius: 6px;
  border: 1px solid #ebeef5;
}

.attachment {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 0;
}

.attachment a {
  color: #409eff;
  text-decoration: none;
}

.muted {
  color: #a8abb2;
  font-size: 12px;
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

  .title {
    font-size: 18px;
    line-height: 1.4;
    word-break: break-word;
  }

  .meta {
    line-height: 1.6;
    margin-bottom: 14px;
  }

  /* el-descriptions 的 label 默认宽度由内容撑开，窄屏上"现象描述"会被挤成
     一字一行（实测 label 列只有 40px 左右）。这里固定 label 列宽并让值列换行。 */
  .desc :deep(.el-descriptions__label) {
    width: 84px;
    min-width: 84px;
    white-space: nowrap;
  }

  .desc :deep(.el-descriptions__content) {
    word-break: break-word;
    line-height: 1.6;
  }

  /* 步骤缩进在窄屏上白占 20px，改成与正文对齐 */
  .steps {
    padding-left: 18px;
  }

  .steps li {
    margin-bottom: 14px;
    padding-left: 2px;
  }

  .step-text {
    line-height: 1.65;
  }

  .step-image {
    max-width: 100%;
  }

  /* 附件链接是手指点击目标，给足纵向高度；文件名过长要能换行 */
  .attachment {
    padding: 0;
    gap: 8px;
    flex-wrap: wrap;
    align-items: baseline;
  }

  .attachment a {
    display: inline-flex;
    align-items: center;
    min-height: var(--tap-min);
    word-break: break-all;
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
