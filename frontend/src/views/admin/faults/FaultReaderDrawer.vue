<template>
  <el-drawer
    v-model="visible"
    title="方案详情"
    :size="isNarrow ? '100%' : '720px'"
    destroy-on-close
  >
    <el-skeleton v-if="loading" :rows="8" animated />

    <ErrorState v-else-if="error" :error="error" @retry="load" />

    <FaultSolutionView v-else-if="detail" :fault="detail" show-stats show-status />

    <template #footer>
      <div class="footer">
        <el-button v-if="canWrite" @click="onEdit">编辑</el-button>
        <el-button type="primary" :disabled="!detail" @click="onCopy">复制方案文本</el-button>
        <el-button v-if="detail?.is_published" @click="openCustomerPage">打开客户页</el-button>
        <el-button @click="visible = false">关闭</el-button>
      </div>
    </template>
  </el-drawer>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { adminGetFault } from '../../../api/admin'
import ErrorState from '../../../components/ErrorState.vue'
import FaultSolutionView from '../../../components/FaultSolutionView.vue'
import { errorText } from '../../../utils/admin'
import { copyText } from '../../../utils/clipboard'
import { buildFaultCopyText } from '../../../utils/faultCopy'
import { hasPermission } from '../../../utils/permissions'
import { useNarrow } from '../../../utils/viewport'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  faultId: { type: Number, default: null }
})
const emit = defineEmits(['update:modelValue', 'edit'])

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
})

const isNarrow = useNarrow()
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
    error.value = errorText(e, '方案加载失败')
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
  if (ok) ElMessage.success('已复制，可直接粘贴给客户')
  else ElMessage.error('复制失败，请手动选择文本')
}

function openCustomerPage() {
  window.open(`/faults/${detail.value.id}`, '_blank', 'noopener,noreferrer')
}
</script>

<style scoped>
.footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
