<template>
  <DetailPanel
    :model-value="modelValue"
    :title="$t('admin.ticket.detail.title')"
    :size="880"
    @update:model-value="(v) => emit('update:modelValue', v)"
    @open="load"
  >
    <div v-loading="loading" class="panel-body">
      <template v-if="detail">
        <div class="top">
          <span class="ticket-no">{{ detail.ticket_no }}</span>
          <el-tag :type="ticketStatusType(detail.status)" size="small">
            {{ ticketStatusLabel(detail.status) }}
          </el-tag>
        </div>

        <el-descriptions :column="descColumns" border size="small" class="desc">
          <el-descriptions-item :label="$t('admin.ticket.detail.product')">
            <span v-if="detail.product">{{ detail.product.name }} {{ detail.product.model }}</span>
            <span v-else class="muted">-</span>
          </el-descriptions-item>
          <el-descriptions-item :label="$t('admin.ticket.detail.part')">
            {{ detail.part?.name || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="$t('admin.ticket.detail.fault')">
            <span v-if="detail.fault">
              {{ detail.fault.title }}
              <el-tag v-if="detail.fault.needs_professional" size="small" type="warning">
                {{ $t('admin.ticket.detail.needsPro') }}
              </el-tag>
            </span>
            <span v-else class="muted">-</span>
          </el-descriptions-item>
          <el-descriptions-item :label="$t('admin.ticket.detail.contact')">
            {{ detail.contact_name || $t('admin.ticket.detail.contactMissing') }} / {{ detail.contact }}
          </el-descriptions-item>
          <el-descriptions-item :label="$t('admin.ticket.detail.onSite')">
            {{ detail.need_on_site ? $t('admin.ticket.detail.onSiteYes') : $t('admin.ticket.detail.onSiteNo') }}
          </el-descriptions-item>
          <el-descriptions-item :label="$t('admin.ticket.detail.assignee')">
            {{ detail.assignee_name || $t('admin.ticket.detail.unassigned') }}
          </el-descriptions-item>
          <el-descriptions-item :label="$t('admin.ticket.detail.createdAt')">
            {{ formatDateTime(detail.created_at) }}
          </el-descriptions-item>
          <el-descriptions-item :label="$t('admin.ticket.detail.userDescription')" :span="descColumns">
            <div class="long-text">{{ detail.description }}</div>
          </el-descriptions-item>
        </el-descriptions>

        <!-- 只有可写角色才渲染处理表单；只读审计仍能看到上面的详情和下面的流转历史 -->
        <template v-if="canWrite">
          <h4 class="block-title">{{ $t('admin.ticket.detail.handle') }}</h4>
          <el-form :label-width="labelWidth" class="edit-form">
            <el-form-item :label="$t('admin.ticket.detail.status')">
              <!-- 只列出合法流转目标（契约 §5）；closed 为终态，没有可选值 -->
              <el-select
                v-model="form.status"
                :placeholder="$t('admin.ticket.detail.keepUnchanged')"
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
              <span v-if="!nextStatuses.length" class="hint">
                {{ $t('admin.ticket.detail.closedNoTransition') }}
              </span>
            </el-form-item>
            <!-- 处理人放在"状态"之后：E2E 依赖 .el-select 第一个元素选状态 -->
            <el-form-item v-if="canAssign" :label="$t('admin.ticket.detail.assignee')">
              <el-select
                v-model="form.assignee_id"
                clearable
                :placeholder="$t('admin.ticket.detail.keepUnchanged')"
                class="wd"
              >
                <el-option
                  v-for="user in assignable"
                  :key="user.id"
                  :label="user.real_name"
                  :value="user.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item :label="$t('admin.ticket.detail.onSiteShort')">
              <el-radio-group v-model="form.need_on_site">
                <el-radio :value="true">{{ $t('admin.ticket.detail.onSiteYes') }}</el-radio>
                <el-radio :value="false">{{ $t('admin.ticket.detail.onSiteNo') }}</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item :label="$t('admin.ticket.detail.remark')" :error="remarkError">
              <el-input
                v-model="form.remark"
                type="textarea"
                :rows="3"
                maxlength="2000"
                show-word-limit
                :placeholder="remarkPlaceholder"
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="saving" @click="onSave">
                {{ $t('common.action.save') }}
              </el-button>
              <!-- 契约 §5 处理人归属：只有"未传并处理人且本单当前无处理人"才认领；
                   已有人处理时不传则保持原处理人，不能写成"首次处理自动认领" -->
              <span class="hint">{{ assigneeHint }}</span>
            </el-form-item>
          </el-form>
        </template>

        <h4 class="block-title">{{ $t('admin.ticket.detail.history') }}</h4>
        <el-timeline v-if="detail.history?.length">
          <el-timeline-item
            v-for="(item, index) in detail.history"
            :key="index"
            :timestamp="formatDateTime(item.created_at)"
          >
            <div class="history-line">
              <template v-if="item.from_status">
                {{ item.operator_name || $t('admin.ticket.detail.operatorSystem') }}：
                {{ ticketStatusLabel(item.from_status) }} →
                {{ ticketStatusLabel(item.to_status) }}
              </template>
              <template v-else>{{ $t('admin.ticket.detail.historyCreated') }}</template>
            </div>
            <div v-if="item.remark" class="history-remark">{{ item.remark }}</div>
          </el-timeline-item>
        </el-timeline>
        <el-empty v-else :description="$t('admin.ticket.detail.historyEmpty')" :image-size="60" />
      </template>

      <el-empty v-else-if="!loading" :description="$t('admin.ticket.detail.notFound')" />
    </div>
  </DetailPanel>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import DetailPanel from '../../../components/DetailPanel.vue'
import { adminGetTicket, adminListAssignable, adminUpdateTicket } from '../../../api/admin'
import {
  errorCode,
  TICKET_TRANSITIONS,
  ticketStatusLabel,
  ticketStatusType
} from '../../../utils/admin'
import { errorMessage } from '../../../utils/error'
import { formatDateTime } from '../../../utils/format'
import { hasPermission } from '../../../utils/permissions'
import { useNarrow } from '../../../utils/viewport'
import { useFormLabelWidth } from '../../../utils/formLabel'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  ticketId: { type: Number, default: null }
})
const emit = defineEmits(['update:modelValue', 'updated'])
const { t } = useI18n()

const detail = ref(null)
const loading = ref(false)
const saving = ref(false)
const remarkError = ref('')

// 处理表单只对可写角色渲染；改派入口再额外要求 ticket:assign
const canWrite = computed(() => hasPermission('ticket:write'))
const canAssign = computed(() => hasPermission('ticket:assign'))
const assignable = ref([])

// 面板从 560 加宽到 880 后，单列描述表会拉得极空，宽屏排两列；窄屏回到一列
const labelWidth = useFormLabelWidth('72px', '105px')
const isNarrow = useNarrow()
const descColumns = computed(() => (isNarrow.value ? 1 : 2))

const form = reactive({ status: null, remark: '', need_on_site: false, assignee_id: null })

async function loadAssignable(productId) {
  if (!canAssign.value || !productId) {
    assignable.value = []
    return
  }
  try {
    assignable.value = await adminListAssignable({ product_id: productId })
  } catch {
    assignable.value = []
  }
}

const nextStatuses = computed(() => {
  if (!detail.value) return []
  return TICKET_TRANSITIONS[detail.value.status] || []
})

const assigneeHint = computed(() => {
  if (!detail.value) return ''
  return detail.value.assignee_id
    ? t('admin.ticket.detail.hintCurrentAssignee', {
        name: detail.value.assignee_name || t('admin.ticket.detail.unassigned')
      })
    : t('admin.ticket.detail.hintClaim')
})

// placeholder 说明"该写什么"，报错说明"为什么不行"。
// 两者若是同一句话，报错时同一句文案会灰红并排出现两遍，读起来像重复渲染。
const remarkPlaceholder = computed(() =>
  form.status
    ? t('admin.ticket.detail.remarkPlaceholderWithStatus')
    : t('admin.ticket.detail.remarkPlaceholderNoStatus')
)

function resetForm(data) {
  form.status = null
  form.remark = ''
  form.need_on_site = Boolean(data?.need_on_site)
  form.assignee_id = null
  remarkError.value = ''
}

async function load() {
  if (!props.ticketId) return
  loading.value = true
  // 不把 detail 置 null：置 null 会让 <template v-if="detail"> 整块销毁再重建，
  // 用户看到面板内容闪一下、滚动位置也跳回顶部（刷新场景尤其明显）。
  // 保留旧内容 + loading 遮罩，数据回来直接覆盖，视觉上更稳。
  // 首次打开时 detail 本就是 null，此时走下面的空态，行为不变。
  try {
    const data = await adminGetTicket(props.ticketId)
    detail.value = data
    resetForm(data)
    // 候选人随产品线变化，拿到详情后再请求；无权限或产品缺失时清空
    await loadAssignable(data.product?.id || null)
  } catch (e) {
    ElMessage.error(errorMessage(e, { fallbackKey: 'admin.ticket.detail.loadFailed' }))
  } finally {
    loading.value = false
  }
}

async function onSave() {
  remarkError.value = ''
  const statusChanged = form.status && form.status !== detail.value.status
  // 契约 §5：状态变化必须带非空备注；纯备注/上门变更不强制
  if (statusChanged && !form.remark.trim()) {
    remarkError.value = t('admin.ticket.detail.remarkRequired')
    return
  }

  const payload = {}
  if (statusChanged) payload.status = form.status
  if (form.remark.trim()) payload.remark = form.remark.trim()
  if (form.need_on_site !== detail.value.need_on_site) payload.need_on_site = form.need_on_site
  // 只有主管（ticket:assign）且确实选了与当前不同的处理人才传，未改则保持后端原归属
  if (canAssign.value && form.assignee_id && form.assignee_id !== detail.value.assignee_id) {
    payload.assignee_id = form.assignee_id
  }

  if (!Object.keys(payload).length) {
    ElMessage.info(t('admin.ticket.detail.noChanges'))
    return
  }

  saving.value = true
  try {
    const updated = await adminUpdateTicket(props.ticketId, payload)
    detail.value = updated
    resetForm(updated)
    ElMessage.success(t('admin.ticket.detail.saved'))
    emit('updated', updated)
  } catch (e) {
    const code = errorCode(e)
    if (code === 'TICKET_STATUS_INVALID') {
      // 流转不被允许：通常是他人在此期间已改动，重新拉一次拿到最新状态
      ElMessage.error(errorMessage(e, { fallbackKey: 'admin.ticket.detail.transitionInvalid' }))
      await load()
      return
    }
    ElMessage.error(errorMessage(e))
  } finally {
    saving.value = false
  }
}

defineExpose({ refresh: load })
</script>

<style scoped>
.panel-body {
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
  /* 面板加宽到 880 后，180px 的下拉在表单里显得很空 */
  width: 240px;
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

/* 窄屏下描述表只剩一列，label 不锁宽会被挤成"联系/人"竖排两行 */
@media (max-width: 768px) {
  .desc :deep(.el-descriptions__label) {
    width: 80px;
    min-width: 80px;
    white-space: nowrap;
  }

  .desc :deep(.el-descriptions__content) {
    word-break: break-word;
    line-height: 1.6;
  }
}
</style>
