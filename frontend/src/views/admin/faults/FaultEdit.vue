<template>
  <div class="page">
    <el-card v-loading="loading" shadow="never">
      <template #header>
        <div class="head">
          <span>{{ isEdit ? $t('admin.fault.edit.titleEdit') : $t('admin.fault.edit.titleNew') }}</span>
          <div class="head-actions">
            <el-button @click="goBack">{{ $t('common.action.cancel') }}</el-button>
            <el-button type="primary" v-if="canWrite" :loading="submitting" @click="onSubmit">
              {{ $t('common.action.save') }}
            </el-button>
          </div>
        </div>
      </template>

      <el-form ref="formRef" :model="form" :rules="rules" :disabled="!canWrite" :label-width="labelWidth" class="form">
        <h3 class="section">{{ $t('admin.fault.edit.sectionBasic') }}</h3>
        <el-form-item :label="$t('admin.fault.edit.product')" prop="product_id">
          <el-select
            v-if="canWrite"
            v-model="form.product_id"
            :placeholder="$t('admin.fault.edit.selectProduct')"
            filterable
            class="wd"
            :loading="loadingProducts"
            @change="onProductChange"
          >
            <el-option
              v-for="item in products"
              :key="item.id"
              :label="`${item.name}（${item.model}）`"
              :value="item.id"
            />
          </el-select>
          <span v-else class="readonly">{{ productSummary }}</span>
        </el-form-item>
        <el-form-item :label="$t('admin.fault.edit.part')" prop="part_id">
          <el-select
            v-if="canWrite"
            v-model="form.part_id"
            :placeholder="form.product_id
              ? $t('admin.fault.edit.selectPart')
              : $t('admin.fault.edit.selectProductFirst')"
            filterable
            class="wd"
            :disabled="!form.product_id"
            :loading="loadingParts"
          >
            <el-option
              v-for="item in parts"
              :key="item.id"
              :label="item.group_name ? `${item.group_name} / ${item.name}` : item.name"
              :value="item.id"
            />
          </el-select>
          <span v-else class="readonly">{{ partSummary }}</span>
          <span v-if="canWrite && !parts.length && form.product_id && !loadingParts" class="hint">
            {{ $t('admin.fault.edit.noPartsHint') }}
          </span>
        </el-form-item>
        <el-form-item :label="$t('admin.fault.edit.title')" prop="title">
          <el-input
            v-model="form.title"
            maxlength="200"
            show-word-limit
            :placeholder="$t('admin.fault.edit.titlePlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="$t('admin.fault.edit.symptom')" prop="symptom">
          <el-input
            v-model="form.symptom"
            type="textarea"
            :rows="3"
            :placeholder="$t('admin.fault.edit.symptomPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="$t('admin.fault.edit.rootCause')" prop="root_cause">
          <el-input
            v-model="form.root_cause"
            type="textarea"
            :rows="2"
            :placeholder="$t('admin.fault.edit.rootCausePlaceholder')"
          />
        </el-form-item>

        <h3 class="section">{{ $t('admin.fault.edit.sectionSteps') }}</h3>
        <div v-for="(item, index) in form.solution_steps" :key="item.uid" class="step">
          <span class="step-no">{{ index + 1 }}</span>
          <el-input
            v-model="item.text"
            type="textarea"
            :rows="2"
            :placeholder="$t('admin.fault.edit.stepPlaceholder')"
          />
          <ImageUpload v-model="item.image_url" :readonly="!canWrite" />
          <el-button v-if="canWrite" link type="danger" @click="removeStep(index)">
            {{ $t('common.action.delete') }}
          </el-button>
        </div>
        <el-button v-if="canWrite" class="add-step" @click="addStep">
          {{ $t('admin.fault.edit.addStep') }}
        </el-button>

        <h3 class="section">{{ $t('admin.fault.edit.sectionOther') }}</h3>
        <el-form-item :label="$t('admin.fault.edit.requiredTools')" prop="required_tools">
          <el-input
            v-model="form.required_tools"
            maxlength="200"
            :placeholder="$t('admin.fault.edit.requiredToolsPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="$t('admin.fault.edit.needsProfessional')" prop="needs_professional">
          <el-switch v-model="form.needs_professional" :disabled="!canWrite" />
          <span class="hint">{{ $t('admin.fault.edit.needsProfessionalHint') }}</span>
        </el-form-item>
        <el-form-item :label="$t('admin.fault.edit.attachments')">
          <div class="attachments">
            <div v-for="(item, index) in form.attachment_urls" :key="item.url" class="attachment">
              <span class="att-name">{{ item.name }}</span>
              <span class="att-size">{{ formatSize(item.size) }}</span>
              <el-button v-if="canWrite" link type="danger" @click="removeAttachment(index)">
                {{ $t('common.action.remove') }}
              </el-button>
            </div>
            <el-upload
              v-if="canWrite"
              :show-file-list="false"
              :http-request="doUploadAttachment"
              :before-upload="beforeUploadAttachment"
              :accept="ATTACHMENT_EXTS.join(',')"

            >
              <el-button size="small" :loading="uploadingAttachment">
                {{ $t('admin.fault.edit.uploadAttachment') }}
              </el-button>
            </el-upload>
            <span class="hint">{{ $t('admin.fault.edit.attachmentHint') }}</span>
          </div>
        </el-form-item>
        <el-form-item :label="$t('admin.fault.edit.published')" prop="is_published">
          <el-switch
            v-model="form.is_published"
            :disabled="!canWrite"
            inline-prompt
            :active-text="$t('admin.fault.edit.publish')"
            :inactive-text="$t('admin.fault.edit.draft')"
          />
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import ImageUpload from '../../../components/ImageUpload.vue'
import {
  adminCreateFault,
  adminGetFault,
  adminListParts,
  adminListProducts,
  adminUpdateFault,
  adminUpload
} from '../../../api/admin'
import { errorCode } from '../../../utils/admin'
import { errorMessage } from '../../../utils/error'
import { hasPermission } from '../../../utils/permissions'
import { ATTACHMENT_EXTS, extHint, isAllowedExt, UPLOAD_MAX_SIZE } from '../../../utils/upload'
import { useFormLabelWidth } from '../../../utils/formLabel'

const { t } = useI18n()
const canWrite = computed(() => hasPermission('fault:write'))
const labelWidth = useFormLabelWidth('110px', '180px')

const route = useRoute()
const router = useRouter()

const formRef = ref()
const loading = ref(false)
const submitting = ref(false)
const uploadingAttachment = ref(false)
// 只读用户拿不到产品/零件下拉时的可读摘要（详情里没有名称就退回 id）
const detail = ref(null)

const products = ref([])
const parts = ref([])
const loadingProducts = ref(false)
const loadingParts = ref(false)

// 步骤行需要一个稳定的 key：后端只认 step/text/image_url，
// uid 仅用于前端列表渲染，提交前会剥掉
let uidSeed = 0
const nextUid = () => `s${(uidSeed += 1)}`

const form = reactive({
  product_id: null,
  part_id: null,
  title: '',
  symptom: '',
  root_cause: '',
  solution_steps: [],
  required_tools: '',
  needs_professional: false,
  attachment_urls: [],
  is_published: true
})

const isEdit = computed(() => Boolean(route.params.id))

const productSummary = computed(() => {
  const found = products.value.find((item) => item.id === form.product_id)
  if (found) return `${found.name}（${found.model}）`
  return (
    detail.value?.product_name ||
    (form.product_id ? t('admin.fault.edit.productRef', { id: form.product_id }) : '-')
  )
})

const partSummary = computed(() => {
  const found = parts.value.find((item) => item.id === form.part_id)
  if (found) return found.group_name ? `${found.group_name} / ${found.name}` : found.name
  return (
    detail.value?.part_name ||
    (form.part_id ? t('admin.fault.edit.partRef', { id: form.part_id }) : '-')
  )
})

// computed：语言切换后校验文案跟着变
const rules = computed(() => ({
  product_id: [{ required: true, message: t('admin.fault.edit.ruleProduct'), trigger: 'change' }],
  part_id: [{ required: true, message: t('admin.fault.edit.rulePart'), trigger: 'change' }],
  title: [{ required: true, message: t('admin.fault.edit.ruleTitle'), trigger: 'blur' }]
}))

function addStep() {
  form.solution_steps.push({ uid: nextUid(), text: '', image_url: null })
}

function removeStep(index) {
  // 这里**故意不删除**对应的 image_url 文件。
  //
  // 与 ImageUpload 的"移除"不同：那里是刚上传就反悔，文件必然没被引用；
  // 而这里删的是**已经保存过**的步骤。用户点完删除后可能不保存就离开
  // （或点取消），此时图还在别的版本里用着，删了就再也找不回来。
  // 无法区分"手滑删了又取消"和"真的要删"，所以不做即时删除。
  //
  // 这些文件由 backend/app/services/upload_cleanup.py 的孤儿清理任务回收：
  // 保存后 JSONB 里不再引用它们，下次扫描时自然成为孤儿被删掉。
  form.solution_steps.splice(index, 1)
}

function removeAttachment(index) {
  // 同上：附件也可能是库里已有的，删除后不保存就撤销不回来了
  form.attachment_urls.splice(index, 1)
}

function formatSize(size) {
  if (!size) return '-'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(0)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

async function loadProducts() {
  loadingProducts.value = true
  try {
    const data = await adminListProducts({ page: 1, page_size: 100 })
    products.value = data.items
  } catch (e) {
    ElMessage.error(errorMessage(e, { fallbackKey: 'admin.fault.edit.productLoadFailed' }))
  } finally {
    loadingProducts.value = false
  }
}

async function loadParts(productId) {
  // 没有零件读权限时不要发请求（只读用户连下拉都不渲染）
  if (!hasPermission('part:read') || !productId) {
    parts.value = []
    return
  }
  loadingParts.value = true
  try {
    const data = await adminListParts({ product_id: productId, page: 1, page_size: 100 })
    parts.value = data.items
  } catch (e) {
    parts.value = []
    ElMessage.error(errorMessage(e, { fallbackKey: 'admin.fault.edit.partLoadFailed' }))
  } finally {
    loadingParts.value = false
  }
}

function onProductChange(value) {
  // 产品变了，原零件必然不属于新产品；清空避免提交时 PART_PRODUCT_MISMATCH
  form.part_id = null
  loadParts(value)
}

/** 把后端的 solution_steps 补上 uid，并按 step 升序展示 */
function fillSteps(steps) {
  const sorted = [...(steps || [])].sort((a, b) => (a.step || 0) - (b.step || 0))
  form.solution_steps = sorted.map((item) => ({
    uid: nextUid(),
    text: item.text || '',
    image_url: item.image_url || null
  }))
}

async function loadFault(id) {
  loading.value = true
  try {
    const data = await adminGetFault(id)
    detail.value = data
    form.product_id = data.product_id
    form.title = data.title
    form.symptom = data.symptom || ''
    form.root_cause = data.root_cause || ''
    form.required_tools = data.required_tools || ''
    form.needs_professional = data.needs_professional
    form.is_published = data.is_published
    form.attachment_urls = [...(data.attachment_urls || [])]
    fillSteps(data.solution_steps)
    // 先拿到零件列表再回填 part_id，否则下拉里没有这一项会显示成原始数字。
    // 只读用户不加载下拉（没有 part:read 也不该发请求），直接用详情摘要展示。
    if (canWrite.value) await loadParts(data.product_id)
    form.part_id = data.part_id
  } catch (e) {
    ElMessage.error(errorMessage(e, { fallbackKey: 'admin.fault.edit.detailLoadFailed' }))
  } finally {
    loading.value = false
  }
}

function beforeUploadAttachment(file) {
  if (!isAllowedExt(file.name, ATTACHMENT_EXTS)) {
    ElMessage.error(extHint(ATTACHMENT_EXTS))
    return false
  }
  if (file.size > UPLOAD_MAX_SIZE) {
    ElMessage.error(t('admin.fault.edit.uploadTooLarge'))
    return false
  }
  return true
}

async function doUploadAttachment({ file }) {
  uploadingAttachment.value = true
  try {
    const result = await adminUpload(file)
    // 契约 §4：附件元数据随故障一起存进 attachment_urls，服务端不单独建表
    form.attachment_urls.push({ name: result.filename, url: result.url, size: result.size })
  } catch (e) {
    if (errorCode(e) === 'UPLOAD_TOO_LARGE') ElMessage.error(t('admin.fault.edit.uploadTooLarge'))
    else if (e?.code === 'ECONNABORTED') ElMessage.error(t('admin.fault.edit.uploadTimeout'))
    else ElMessage.error(errorMessage(e, { fallbackKey: 'admin.fault.edit.uploadFailed' }))
  } finally {
    uploadingAttachment.value = false
  }
}

function buildPayload() {
  // 后端按 step 去重升序，这里把空行剔掉后按序号重排，避免留空导致 422
  const steps = form.solution_steps
    .filter((item) => item.text.trim())
    .map((item, index) => ({
      step: index + 1,
      text: item.text.trim(),
      image_url: item.image_url || null
    }))

  return {
    product_id: form.product_id,
    part_id: form.part_id,
    title: form.title.trim(),
    symptom: form.symptom.trim() || null,
    root_cause: form.root_cause.trim() || null,
    solution_steps: steps,
    required_tools: form.required_tools.trim() || null,
    needs_professional: form.needs_professional,
    attachment_urls: form.attachment_urls,
    is_published: form.is_published
  }
}

async function onSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    const payload = buildPayload()
    if (isEdit.value) {
      await adminUpdateFault(route.params.id, payload)
    } else {
      await adminCreateFault(payload)
    }
    ElMessage.success(t('admin.fault.edit.saved'))
    router.push({ name: 'admin-faults' })
  } catch (e) {
    if (errorCode(e) === 'PART_PRODUCT_MISMATCH') {
      // 选完零件后产品被改过：定位到零件字段，别让用户自己猜
      form.part_id = null
      ElMessage.error(t('admin.fault.edit.partMismatch'))
      return
    }
    ElMessage.error(errorMessage(e))
  } finally {
    submitting.value = false
  }
}

function goBack() {
  router.push({ name: 'admin-faults' })
}

onMounted(async () => {
  // 写权限 + 产品读权限才需要下拉；只读页只展示详情里的摘要
  if (canWrite.value && hasPermission('product:read')) await loadProducts()
  if (isEdit.value) {
    await loadFault(route.params.id)
  } else {
    // 新建：默认给 3 行（P-16 规则 2）
    addStep()
    addStep()
    addStep()
  }
})
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.form {
  max-width: 860px;
}

.section {
  margin: 8px 0 16px;
  padding-left: 8px;
  font-size: 14px;
  font-weight: 600;
  border-left: 3px solid #409eff;
  line-height: 1;
}

.wd {
  width: 240px;
}

.hint {
  margin-left: 8px;
  color: #a8abb2;
  font-size: 12px;
}

.readonly {
  color: #606266;
}

.step {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  margin-bottom: 12px;
  background: #fafafa;
  border: 1px solid #f0f2f5;
  border-radius: 4px;
}

.step-no {
  flex: 0 0 24px;
  height: 24px;
  line-height: 24px;
  text-align: center;
  border-radius: 50%;
  background: #ecf5ff;
  color: #409eff;
  font-size: 12px;
}

.step :deep(.el-textarea) {
  flex: 1;
}

.add-step {
  margin: 0 0 8px 12px;
}

.attachments {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: flex-start;
}

.attachment {
  display: flex;
  align-items: center;
  gap: 12px;
}

.att-name {
  color: #303133;
}

.att-size {
  color: #a8abb2;
  font-size: 12px;
}
</style>
