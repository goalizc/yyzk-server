<template>
  <DetailPanel
    v-model="visible"
    :title="$t('admin.fault.reader.title')"
    :size="880"
    destroy-on-close
  >
    <el-skeleton v-if="loading" :rows="8" animated />

    <ErrorState v-else-if="error" :error="error" @retry="load" />

    <FaultSolutionView v-else-if="detail" :fault="detail" show-stats show-status />

    <template #footer>
      <div class="footer">
        <el-button v-if="canWrite" @click="onEdit">{{ $t('admin.fault.reader.edit') }}</el-button>
        <el-button type="primary" :disabled="!detail" @click="onCopy">
          {{ $t('admin.fault.reader.copyText') }}
        </el-button>
        <el-button v-if="detail?.is_published" @click="openCustomerPage">
          {{ $t('admin.fault.reader.openCustomerPage') }}
        </el-button>
        <el-button @click="visible = false">{{ $t('common.action.close') }}</el-button>
      </div>
    </template>
  </DetailPanel>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { adminGetFault } from '../../../api/admin'
import DetailPanel from '../../../components/DetailPanel.vue'
import ErrorState from '../../../components/ErrorState.vue'
import FaultSolutionView from '../../../components/FaultSolutionView.vue'
import { errorMessage } from '../../../utils/error'
import { localeHref } from '../../../locales'
import { copyText } from '../../../utils/clipboard'
import { buildFaultCopyText } from '../../../utils/faultCopy'
import { hasPermission } from '../../../utils/permissions'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  faultId: { type: Number, default: null }
})
const emit = defineEmits(['update:modelValue', 'edit'])

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
})

const { t } = useI18n()

// 宽度由 DetailPanel 的 min(880px, 92vw) 自适应，不再需要断点判断
const canWrite = computed(() => hasPermission('fault:write'))

const detail = ref(null)
const loading = ref(false)
const error = ref('')

async function load() {
  if (!props.faultId) return
  loading.value = true
  error.value = ''
  detail.value = null
  try {
    detail.value = await adminGetFault(props.faultId)
  } catch (e) {
    error.value = errorMessage(e, { fallbackKey: 'admin.fault.reader.loadFailed' })
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.modelValue, props.faultId],
  ([opened]) => {
    if (opened) load()
  },
  { immediate: true }
)

function onEdit() {
  emit('edit', detail.value.id)
  visible.value = false
}

async function onCopy() {
  const ok = await copyText(buildFaultCopyText(detail.value))
  if (ok) ElMessage.success(t('admin.fault.reader.copied'))
  else ElMessage.error(t('admin.fault.reader.copyFailed'))
}

function openCustomerPage() {
  // 带语言前缀：英文后台点开客户页应仍是英文（同一处缺陷，审查发现）
  window.open(localeHref(`/faults/${detail.value.id}`), '_blank', 'noopener,noreferrer')
}
</script>

<style scoped>
.footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
