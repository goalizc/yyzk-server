<template>
  <div class="page">
    <el-card shadow="never">
      <template #header>
        <div class="head">
          <span>{{ t('admin.inventory.adjustment.title') }}</span>
          <el-button v-if="canWrite" type="primary" @click="formVisible = true">
            {{ t('admin.inventory.adjustment.newDoc') }}
          </el-button>
        </div>
      </template>
      <el-alert :closable="false" type="info" :title="t('admin.inventory.adjustment.hint')" />
    </el-card>

    <MovementTable
      ref="tableRef"
      reversible
      :header-key="'admin.inventory.adjustment.recentTitle'"
      @reverse="onReverse"
    />

    <ReverseDialog
      v-model="reverseVisible"
      :doc-id="reverseDocId"
      :doc-no="reverseDocNo"
      @reversed="onReversed"
    />
    <DocumentFormDialog
      v-model="formVisible"
      resource="adjustment"
      :title="t('admin.inventory.adjustment.newDoc')"
      :warehouses="warehouses"
      :skus="skus"
      :categories="categoryOptions"
      :products="productOptions"
      @created="onCreated"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import {
  inventoryCategories, inventoryRefProducts, inventorySkus, inventoryWarehouses
} from '../../../api/inventory'
import { hasPermission } from '../../../utils/permissions'
import { errorMessage } from '../../../utils/error'
import MovementTable from './MovementTable.vue'
import ReverseDialog from './ReverseDialog.vue'
import DocumentFormDialog from './DocumentFormDialog.vue'

const { t } = useI18n()
const canWrite = computed(() => hasPermission('inventory:adjust:write'))

const tableRef = ref()
const warehouses = ref([])
const skus = ref([])
const categoryOptions = ref([])
const productOptions = ref([])
const formVisible = ref(false)
const reverseVisible = ref(false)
const reverseDocId = ref(null)
const reverseDocNo = ref('')

function onReverse(docId, docNo) {
  reverseDocId.value = docId
  reverseDocNo.value = docNo
  reverseVisible.value = true
}

function onReversed() {
  tableRef.value?.reload()
}

function onCreated() {
  tableRef.value?.reload()
}

async function loadRefs() {
  try {
    const [wh, sku, cat, prod] = await Promise.all([
      inventoryWarehouses({ page: 1, page_size: 100 }),
      inventorySkus({ page: 1, page_size: 100, is_active: true }),
      inventoryCategories({ page: 1, page_size: 100, is_active: true }),
      inventoryRefProducts()
    ])
    warehouses.value = wh.items || []
    skus.value = sku.items || []
    categoryOptions.value = cat.items || []
    productOptions.value = prod || []
  } catch (e) {
    // 静默清空会让人以为「本来就没数据」，必须给出错误出口
    warehouses.value = []
    skus.value = []
    categoryOptions.value = []
    productOptions.value = []
    ElMessage.error(errorMessage(e, { fallbackKey: 'admin.inventory.common.loadFailed' }))
  }
}

onMounted(loadRefs)
</script>

<style scoped>
.page { display: flex; flex-direction: column; gap: 16px; }
.head { display: flex; align-items: center; justify-content: space-between; }
</style>
