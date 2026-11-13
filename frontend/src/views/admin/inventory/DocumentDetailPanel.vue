<template>
  <div class="root">
    <DetailPanel
      :model-value="modelValue"
      :title="title"
      :size="820"
      @update:model-value="emit('update:modelValue', $event)"
    >
      <template v-if="doc">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item :label="$t('admin.inventory.common.docNo')">{{ doc.doc_no }}</el-descriptions-item>
          <el-descriptions-item :label="$t('admin.inventory.common.status')">
            <el-tag :type="doc.status === 'void' ? 'info' : 'success'" size="small">
              {{ statusLabel(doc.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="$t('admin.inventory.common.docType')">
            {{ docTypeLabel(doc.doc_type) }}
          </el-descriptions-item>
          <el-descriptions-item :label="$t('admin.inventory.common.createdAt')">
            {{ formatDateTime(doc.created_at) }}
          </el-descriptions-item>
          <el-descriptions-item :label="$t('admin.inventory.common.remark')" :span="2">
            {{ doc.remark || '-' }}
          </el-descriptions-item>
        </el-descriptions>

        <h4 class="sub-title">{{ $t('admin.inventory.common.items') }}</h4>
        <el-table :data="doc.items || []" border size="small">
          <el-table-column prop="sku_no" :label="$t('admin.inventory.common.skuNo')" min-width="140" />
          <el-table-column prop="sku_name" :label="$t('admin.inventory.common.skuName')" min-width="160" show-overflow-tooltip />
          <el-table-column prop="quantity" :label="$t('admin.inventory.common.quantity')" width="100" align="center" />
          <el-table-column prop="remark" :label="$t('admin.inventory.common.remark')" min-width="140" show-overflow-tooltip />
          <!-- 明细里故意不渲染 unit_cost：只写留档、不读、不算（§3.6） -->
        </el-table>
      </template>

      <!-- 改单需 inventory:doc:edit（主管）；冲正需 inventory:adjust:write。两者都不可用则不渲染底部栏 -->
      <template v-if="canEdit || canReverse" #footer>
        <el-button v-if="canEdit" type="primary" plain @click="onEditClick">
          {{ $t('common.action.edit') }}
        </el-button>
        <el-button v-if="canReverse" type="danger" plain @click="onReverseClick">
          {{ $t('admin.inventory.common.reverse') }}
        </el-button>
      </template>
    </DetailPanel>

    <ReverseDialog
      v-model="reverseVisible"
      :doc-id="reverseDocId"
      :doc-no="reverseDocNo"
      @reversed="onReversed"
    />
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import DetailPanel from '../../../components/DetailPanel.vue'
import ReverseDialog from './ReverseDialog.vue'
import { formatDateTime } from '../../../utils/format'
import { hasPermission } from '../../../utils/permissions'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: '' },
  doc: { type: Object, default: null }
})
const emit = defineEmits(['update:modelValue', 'reversed', 'edit'])
const { t } = useI18n()

// 冲正属 inventory:adjust:write（高危，warehouse 角色不含）；已冲正的单不可再冲。
const canReverse = computed(
  () => hasPermission('inventory:adjust:write') && props.doc && props.doc.status !== 'void'
)

// 改单属 inventory:doc:edit（仅主管）；调整单走盘点、冲正单走反向单，均不走改单
const EDITABLE_TYPES = ['inbound', 'outbound']
const canEdit = computed(
  () =>
    hasPermission('inventory:doc:edit') &&
    props.doc &&
    props.doc.status !== 'void' &&
    EDITABLE_TYPES.includes(props.doc.doc_type)
)

function onEditClick() {
  if (!props.doc) return
  emit('edit', props.doc)
  emit('update:modelValue', false)
}

const reverseVisible = ref(false)
const reverseDocId = ref(null)
const reverseDocNo = ref('')

function onReverseClick() {
  if (!props.doc) return
  reverseDocId.value = props.doc.id
  reverseDocNo.value = props.doc.doc_no
  reverseVisible.value = true
}

function onReversed() {
  // 原单变 void、生成反向单；关掉详情并通知列表刷新
  emit('update:modelValue', false)
  emit('reversed', reverseDocId.value)
}

// 映射表：禁拼 key，新增状态/类型时补这里一处
const STATUS_KEYS = {
  confirmed: 'admin.inventory.common.statusConfirmed',
  void: 'admin.inventory.common.statusVoid'
}
const DOC_TYPE_KEYS = {
  inbound: 'admin.inventory.common.inbound',
  outbound: 'admin.inventory.common.outbound',
  adjust_in: 'admin.inventory.common.adjustIn',
  adjust_out: 'admin.inventory.common.adjustOut'
}

function statusLabel(status) {
  const key = STATUS_KEYS[status]
  return key ? t(key) : status
}

function docTypeLabel(docType) {
  const key = DOC_TYPE_KEYS[docType]
  return key ? t(key) : docType
}
</script>

<style scoped>
.root { display: contents; }
.sub-title { margin: 16px 0 8px; font-size: 14px; font-weight: 600; }
</style>
