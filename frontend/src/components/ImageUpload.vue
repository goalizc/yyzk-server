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
        @click="onRemove"
      >
        移除
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { adminDeleteUpload, adminUpload } from '../api/admin'
import { errorCode, errorText } from '../utils/admin'
import { extHint, IMAGE_EXTS, isAllowedExt, UPLOAD_MAX_SIZE } from '../utils/upload'

const props = defineProps({
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
  const code = errorCode(e)
  if (code === 'UPLOAD_TOO_LARGE') return '文件超过 20MB 限制'
  if (e?.code === 'ECONNABORTED') return '上传超时，请检查网络后重试'
  // 503 是服务端存储不可写（多为上传目录权限问题），重试没用，得找运维。
  // 后端已给中文 detail，但用户不知道"下一步做什么"，这里补一句动作指引。
  if (code === 'SERVICE_UNAVAILABLE' || e?.response?.status === 503) {
    return '服务器暂时无法保存文件，请稍后重试；持续失败请联系管理员'
  }
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

/**
 * 移除图片：先清界面，再尽力删服务器文件。
 *
 * 两点判断：
 * 1. **界面先响应**。删除请求可能因为权限、网络慢掉，让用户盯着"图还在"等几百毫秒
 *    是不可接受的；文件删不掉也不影响这条方案本身——它只是浪费磁盘。
 * 2. **删除失败不报错**。409（图还被别的方案用着）是正常情况，提示用户反而困惑；
 *    其它失败交给后端的孤儿清理任务兜底，用户没必要为此负责。
 *    这里只记日志，方便排查"为什么文件一直没被回收"。
 */
async function onRemove() {
  const oldUrl = props.modelValue
  emit('update:modelValue', null)
  if (!oldUrl) return
  try {
    await adminDeleteUpload(oldUrl)
  } catch (e) {
    console.warn('[ImageUpload] 删除上传文件失败，留给孤儿清理任务回收：', oldUrl, e)
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
