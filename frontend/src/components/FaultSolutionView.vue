<template>
  <div class="solution">
    <el-card shadow="never" class="block">
      <div class="title-row">
        <h1 class="title">{{ fault.title }}</h1>
        <div v-if="showStatus" class="tags">
          <el-tag v-if="fault.is_published" type="success" size="small">已发布</el-tag>
          <el-tag v-else type="info" size="small">未发布</el-tag>
          <el-tag v-if="fault.needs_professional" type="warning" size="small">需专业</el-tag>
        </div>
      </div>

      <p class="meta">
        {{ fault.product_name }} / {{ fault.part_name }}
        <template v-if="showStats">
          <span class="dot">·</span>{{ fault.view_count }} 人看过
          <span class="dot">·</span>{{ fault.resolved_count }} 人反馈已解决
        </template>
        <template v-if="fault.updated_at">
          <span class="dot">·</span>更新于 {{ formatDate(fault.updated_at) }}
        </template>
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
        <li v-for="step in steps" :key="step.step">
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
      <p v-if="!steps.length" class="muted">暂无分步说明</p>
    </el-card>

    <el-card v-if="attachments.length" shadow="never" class="block">
      <template #header>相关附件</template>
      <div v-for="file in attachments" :key="file.url" class="attachment">
        <a :href="file.url" target="_blank" rel="noopener">{{ file.name }}</a>
        <span class="muted">{{ formatSize(file.size) }}</span>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { formatDate } from '../utils/format'

const props = defineProps({
  fault: { type: Object, required: true },
  showStats: { type: Boolean, default: false },
  showStatus: { type: Boolean, default: false }
})

const steps = computed(() =>
  [...(props.fault.solution_steps || [])].sort((a, b) => a.step - b.step)
)
const attachments = computed(() => props.fault.attachment_urls || [])

function formatSize(size) {
  if (!size) return ''
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}
</script>

<style scoped>
.block {
  margin-bottom: 16px;
}

.title-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.title {
  margin: 0 0 8px;
  font-size: 20px;
  line-height: 1.4;
  word-break: break-word;
}

.tags {
  display: flex;
  gap: 6px;
  padding-top: 4px;
}

.meta {
  margin: 0 0 16px;
  color: #909399;
  font-size: 13px;
  line-height: 1.6;
}

.dot {
  margin: 0 6px;
}

.pro-alert {
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

@media (max-width: 640px) {
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
  }

  .desc :deep(.el-descriptions__label) {
    width: 84px;
    min-width: 84px;
    white-space: nowrap;
  }

  .desc :deep(.el-descriptions__content) {
    word-break: break-word;
    line-height: 1.6;
  }

  .steps {
    padding-left: 18px;
  }

  .steps li {
    margin-bottom: 14px;
    padding-left: 2px;
  }

  .step-image {
    max-width: 100%;
  }

  .attachment {
    padding: 0;
    gap: 8px;
    flex-wrap: wrap;
    align-items: baseline;
  }

  .attachment a {
    word-break: break-all;
  }
}
</style>
