<template>
  <el-dialog
    v-model="visible"
    :title="title || t('admin.inventory.common.reverse')"
    :width="isNarrow ? '92%' : '480px'"
    @closed="reset"
  >
    <el-alert
      v-if="docNo"
      type="warning"
      :closable="false"
      :title="t('admin.inventory.common.reverseConfirm', { docNo })"
    />
    <el-form ref="formRef" :model="form" :rules="rules" :label-width="labelWidth">
      <el-form-item :label="t('admin.inventory.common.reverseReason')" prop="remark">
        <el-input
          v-model="form.remark"
          type="textarea"
          :rows="3"
          maxlength="200"
          :placeholder="t('admin.inventory.common.reverseReasonPlaceholder')"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="danger" :loading="submitting" @click="onSubmit">
        {{ t('admin.inventory.common.reverse') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { inventoryReverseDocument } from '../../../api/inventory'
import { errorMessage } from '../../../utils/error'
import { useNarrow } from '../../../utils/viewport'
import { useFormLabelWidth } from '../../../utils/formLabel'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  // 冲正目标单据 id；由父级解析/传递，本组件不负责查找
  docId: { type: Number, default: null },
  docNo: { type: String, default: '' },
  title: { type: String, default: '' }
})
const emit = defineEmits(['update:modelValue', 'reversed'])

const { t } = useI18n()
const isNarrow = useNarrow()
// 英文 "Reason for reversal" 较长，给足宽度
const labelWidth = useFormLabelWidth('88px', '150px')
const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
})
const formRef = ref()
const submitting = ref(false)
const form = ref({ remark: '' })

const rules = computed(() => ({
  remark: [
    { required: true, message: t('admin.inventory.common.reverseReasonRequired'), trigger: 'blur' }
  ]
}))

function reset() {
  form.value.remark = ''
  formRef.value?.clearValidate()
}

watch(visible, (value) => {
  if (value) reset()
})

async function onSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid || !props.docId) return
  submitting.value = true
  try {
    await inventoryReverseDocument(props.docId, { remark: form.value.remark.trim() })
    ElMessage.success(t('admin.inventory.common.reverseSuccess'))
    visible.value = false
    emit('reversed', props.docId)
  } catch (e) {
    ElMessage.error(errorMessage(e, { fallbackKey: 'admin.inventory.common.reverseFailed' }))
  } finally {
    submitting.value = false
  }
}
</script>
