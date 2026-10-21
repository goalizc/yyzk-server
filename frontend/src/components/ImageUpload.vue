<template>
  <div class="uploader">
    <div class="preview">
      <el-image
        v-if="modelValue"
        :src="modelValue"
        fit="cover"
        class="thumb"
        :preview-src-list="[modelValue]"
        preview-teleported
      />
      <div v-else class="placeholder">无图</div>
    </div>
    <div class="ops">
      <!-- http-request 里上传成功才写回 url，失败可直接提示，
           不像 el-upload 默认行为那样只留一条红字文件行 -->
      <el-upload
        :show-file-list="false"
        :http-request="doUpload"
        :before-upload="beforeUpload"
        :accept="IMAGE_EXTS.join(',')"
      >
        <el-button size="small" :loading="uploading">
          {{ modelValue ? '重新上传' : '上传图片' }}
        </el-button>
      </el-upload>
      <el-button
        v-if="modelValue"
        size="small"
        link
        type="danger"
        @click="$emit('update:modelValue', null)"
      >
        移除
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { adminUpload } from '../api/admin'
import { errorCode, errorText } from '../utils/admin'
import { extHint, IMAGE_EXTS, isAllowedExt, UPLOAD_MAX_SIZE } from '../utils/upload'

defineProps({
  modelValue: { type: String, default: null }
})
const emit = defineEmits(['update:modelValue'])

const uploading = ref(false)

function beforeUpload(file) {
  // 后端还会校验 MIME，但这里先拦：否则用户要等整个文件上传完才收到失败
  if (!isAllowedExt(file.name, IMAGE_EXTS)) {
    ElMessage.error(extHint(IMAGE_EXTS))
    return false
  }
  if (file.size > UPLOAD_MAX_SIZE) {
    ElMessage.error('文件超过 20MB 限制')
    return false
  }
  return true
}

/** 上传失败的统一文案：区分"超时"与"服务端拒绝"，否则弱网下会误导成文件问题 */
function uploadErrorText(e) {
  if (errorCode(e) === 'UPLOAD_TOO_LARGE') return '文件超过 20MB 限制'
  if (e?.code === 'ECONNABORTED') return '上传超时，请检查网络后重试'
  return errorText(e, '上传失败')
}

async function doUpload({ file }) {
  uploading.value = true
  try {
    const result = await adminUpload(file)
    emit('update:modelValue', result.url)
  } catch (e) {
    ElMessage.error(uploadErrorText(e))
  } finally {
    uploading.value = false
  }
}
</script>

<style scoped>
.uploader {
  display: flex;
  align-items: center;
  gap: 12px;
}

.thumb {
  width: 72px;
  height: 72px;
  border-radius: 4px;
  border: 1px solid #e4e7ed;
  display: block;
}

.placeholder {
  width: 72px;
  height: 72px;
  border: 1px dashed #dcdfe6;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #c0c4cc;
  font-size: 12px;
}

.ops {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: flex-start;
}
</style>
