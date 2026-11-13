<template>
  <div class="page">
    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>{{ t('admin.inventory.movement.title') }}</span>
          <div v-if="canExport" class="exports">
            <el-button :loading="exportingBalance" @click="onExport('balance')">
              {{ t('admin.inventory.common.exportBalance') }}
            </el-button>
            <el-button :loading="exportingMovement" @click="onExport('movement')">
              {{ t('admin.inventory.common.exportMovement') }}
            </el-button>
          </div>
        </div>
      </template>
      <MovementTable />
    </el-card>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import MovementTable from './MovementTable.vue'
import { inventoryExport } from '../../../api/inventory'
import { errorMessage } from '../../../utils/error'
import { hasPermission } from '../../../utils/permissions'

const { t } = useI18n()
// 导出是独立权限码，不能因为能看流水就默认能导出
const canExport = computed(() => hasPermission('inventory:export'))
const exportingBalance = ref(false)
const exportingMovement = ref(false)

function triggerDownload(blob, name) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

async function onExport(type) {
  const flag = type === 'balance' ? exportingBalance : exportingMovement
  flag.value = true
  try {
    const response = await inventoryExport({ type })
    const truncated = response.headers?.['x-export-truncated'] === '1'
    if (truncated) {
      ElMessage.warning(
        t('admin.inventory.common.exportTruncated', {
          total: response.headers?.['x-export-total'] || '?'
        })
      )
    }
    const stamp = new Date().toISOString().slice(0, 16).replace(/[:T]/g, '')
    triggerDownload(response.data, `inventory-${type}-${stamp}.csv`)
  } catch (e) {
    ElMessage.error(errorMessage(e, { fallbackKey: 'admin.inventory.common.exportFailed' }))
  } finally {
    flag.value = false
  }
}
</script>

<style scoped>
.page { display: flex; flex-direction: column; gap: 16px; }
.head { display: flex; align-items: center; justify-content: space-between; }
.exports { display: flex; gap: 8px; }
</style>
