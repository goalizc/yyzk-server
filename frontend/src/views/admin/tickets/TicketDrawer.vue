<template>
  <el-drawer
    :model-value="modelValue"
    title="工单详情"
    size="560px"
    @update:model-value="(v) => emit('update:modelValue', v)"
    @open="load"
  >
    <div v-loading="loading" class="drawer-body">
      <template v-if="detail">
        <div class="top">
          <span class="ticket-no">{{ detail.ticket_no }}</span>
          <el-tag :type="ticketStatusType(detail.status)" size="small">
            {{ ticketStatusLabel(detail.status) }}
          </el-tag>
        </div>

        <el-descriptions :column="1" border size="small" class="desc">
          <el-descriptions-item label="产品">
            <span v-if="detail.product">{{ detail.product.name }} {{ detail.product.model }}</span>
            <span v-else class="muted">-</span>
          </el-descriptions-item>
          <el-descriptions-item label="零件">
            {{ detail.part?.name || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="故障">
            <span v-if="detail.fault">
              {{ detail.fault.title }}
              <el-tag v-if="detail.fault.needs_professional" size="small" type="warning">需专业维修</el-tag>
            </span>
            <span v-else class="muted">-</span>
          </el-descriptions-item>
          <el-descriptions-item label="联系人">
            {{ detail.contact_name || '未填写' }} / {{ detail.contact }}
          </el-descriptions-item>
          <el-descriptions-item label="上门服务">
            {{ detail.need_on_site ? '需要' : '不需要' }}
          </el-descriptions-item>
          <el-descriptions-item label="处理人">
            {{ detail.assignee_name || '未认领' }}
          </el-descriptions-item>
          <el-descriptions-item label="提交时间">
            {{ formatDateTime(detail.created_at) }}
          </el-descriptions-item>
          <el-descriptions-item label="用户描述">
            <div class="long-text">{{ detail.description }}</div>
          </el-descriptions-item>
        </el-descriptions>

        <h4 class="block-title">处理</h4>
        <el-form label-width="72px" class="edit-form">
          <el-form-item label="状态">
            <!-- 只列出合法流转目标（契约 §5）；closed 为终态，没有可选值 -->
            <el-select
              v-model="form.status"
              placeholder="不修改"
              clearable
              :disabled="!nextStatuses.length"
              class="wd"
            >
              <el-option
                v-for="value in nextStatuses"
                :key="value"
                :label="ticketStatusLabel(value)"
                :value="value"
              />
            </el-select>
            <span v-if="!nextStatuses.length" class="hint">已关闭，不可再流转</span>
          </el-form-item>
          <el-form-item label="上门">
            <el-radio-group v-model="form.need_on_site">
              <el-radio :value="true">需要</el-radio>
              <el-radio :value="false">不需要</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="备注" :error="remarkError">
            <el-input
              v-model="form.remark"
              type="textarea"
              :rows="3"
              maxlength="2000"
              show-word-limit
              :placeholder="form.status ? '变更状态必须填写备注' : '仅更新备注可留空'"
            />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
            <!-- 契约 §5 处理人归属：只有"未传并处理人且本单当前无处理人"才认领；
                 已有人处理时不传则保持原处理人，不能写成"首次处理自动认领" -->
            <span class="hint">{{ assigneeHint }}</span>
          </el-form-item>
        </el-form>

        <h4 class="block-title">流转历史</h4>
        <el-timeline v-if="detail.history?.length">
          <el-timeline-item
            v-for="(item, index) in detail.history"
            :key="index"
            :timestamp="formatDateTime(item.created_at)"
          >
            <div class="history-line">
              <template v-if="item.from_status">
                {{ item.operator_name || '系统' }}：{{ ticketStatusLabel(item.from_status) }} →
                {{ ticketStatusLabel(item.to_status) }}
              </template>
              <template v-else>创建工单</template>
            </div>
            <div v-if="item.remark" class="history-remark">{{ item.remark }}</div>
          </el-timeline-item>
        </el-timeline>
        <el-empty v-else description="暂无流转记录" :image-size="60" />
      </template>

      <el-empty v-else-if="!loading" description="工单不存在或已被删除" />
    </div>
  </el-drawer>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { adminGetTicket, adminUpdateTicket } from '../../../api/admin'
import {
  errorCode,
  errorText,
  TICKET_TRANSITIONS,
  ticketStatusLabel,
  ticketStatusType
} from '../../../utils/admin'
import { formatDateTime } from '../../../utils/format'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  ticketId: { type: Number, default: null }
})
const emit = defineEmits(['update:modelValue', 'updated'])

const detail = ref(null)
const loading = ref(false)
const saving = ref(false)
const remarkError = ref('')

const form = reactive({ status: null, remark: '', need_on_site: false })

const nextStatuses = computed(() => {
  if (!detail.value) return []
  return TICKET_TRANSITIONS[detail.value.status] || []
})

const assigneeHint = computed(() => {
  if (!detail.value) return ''
  return detail.value.assignee_id
    ? `当前处理人：${detail.value.assignee_name || '未知'}，保存不会改变处理人`
    : '本单暂无处理人，保存后由你认领'
})

function resetForm(data) {
  form.status = null
  form.remark = ''
  form.need_on_site = Boolean(data?.need_on_site)
  remarkError.value = ''
}

async function load() {
  if (!props.ticketId) return
  loading.value = true
  detail.value = null
  try {
    const data = await adminGetTicket(props.ticketId)
    detail.value = data
    resetForm(data)
  } catch (e) {
    ElMessage.error(errorText(e, '工单详情加载失败'))
  } finally {
    loading.value = false
  }
}

async function onSave() {
  remarkError.value = ''
  const statusChanged = form.status && form.status !== detail.value.status
  // 契约 §5：状态变化必须带非空备注；纯备注/上门变更不强制
  if (statusChanged && !form.remark.trim()) {
    remarkError.value = '变更状态必须填写备注'
    return
  }

  const payload = {}
  if (statusChanged) payload.status = form.status
  if (form.remark.trim()) payload.remark = form.remark.trim()
  if (form.need_on_site !== detail.value.need_on_site) payload.need_on_site = form.need_on_site

  if (!Object.keys(payload).length) {
    ElMessage.info('没有需要保存的修改')
    return
  }

  saving.value = true
  try {
    const updated = await adminUpdateTicket(props.ticketId, payload)
    detail.value = updated
    resetForm(updated)
    ElMessage.success('已保存')
    emit('updated', updated)
  } catch (e) {
    const code = errorCode(e)
    if (code === 'TICKET_STATUS_INVALID') {
      // 流转不被允许：通常是他人在此期间已改动，重新拉一次拿到最新状态
      ElMessage.error(errorText(e, '该状态流转不被允许'))
      await load()
      return
    }
    ElMessage.error(errorText(e))
  } finally {
    saving.value = false
  }
}

defineExpose({ refresh: load })
</script>

<style scoped>
.drawer-body {
  min-height: 200px;
}

.top {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.ticket-no {
  font-size: 16px;
  font-weight: 600;
}

.desc {
  margin-bottom: 8px;
}

.long-text {
  white-space: pre-wrap;
  word-break: break-word;
}

.block-title {
  margin: 20px 0 12px;
  font-size: 13px;
  font-weight: 600;
  color: #606266;
}

.edit-form {
  background: #fafafa;
  border: 1px solid #f0f2f5;
  border-radius: 4px;
  padding: 12px 12px 0;
}

.wd {
  width: 180px;
}

.hint {
  margin-left: 8px;
  color: #a8abb2;
  font-size: 12px;
}

.muted {
  color: #a8abb2;
}

.history-line {
  color: #303133;
  font-size: 13px;
}

.history-remark {
  margin-top: 4px;
  color: #909399;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
