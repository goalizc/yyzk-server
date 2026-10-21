<template>
  <div class="home">
    <section class="hero">
      <h1>售后自助故障诊断</h1>
      <p>按产品 → 零件 → 故障现象逐级选择，快速找到解决办法</p>
    </section>

    <el-card shadow="never" class="panel">
      <el-row :gutter="16">
        <el-col :xs="24" :sm="8">
          <div class="field">
            <label>1. 选择产品</label>
            <el-select
              v-model="productId"
              placeholder="请选择产品"
              filterable
              clearable
              :loading="loading.products"
              style="width: 100%"
              @change="onProductChange"
            >
              <el-option
                v-for="item in products"
                :key="item.id"
                :label="`${item.name}（${item.model}）`"
                :value="item.id"
              />
            </el-select>
          </div>
        </el-col>

        <el-col :xs="24" :sm="8">
          <div class="field">
            <label>2. 选择零件</label>
            <el-select
              v-model="partId"
              placeholder="请先选择产品"
              filterable
              clearable
              :disabled="!productId"
              :loading="loading.parts"
              style="width: 100%"
              @change="onPartChange"
            >
              <el-option
                v-for="item in parts"
                :key="item.id"
                :label="item.group_name ? `${item.group_name} / ${item.name}` : item.name"
                :value="item.id"
              />
            </el-select>
          </div>
        </el-col>

        <el-col :xs="24" :sm="8">
          <div class="field">
            <label>3. 选择故障现象</label>
            <el-select
              v-model="faultId"
              placeholder="请先选择零件"
              filterable
              clearable
              :disabled="!partId"
              :loading="loading.faults"
              style="width: 100%"
            >
              <el-option
                v-for="item in filteredFaults"
                :key="item.id"
                :label="item.title"
                :value="item.id"
              />
            </el-select>
          </div>
        </el-col>
      </el-row>

      <el-input
        v-model="keyword"
        class="search"
        placeholder="还可以输入关键词过滤，例如：漏水、不充电"
        clearable
        :disabled="!partId"
        @input="onKeywordInput"
      />
    </el-card>

    <!-- 加载中 -->
    <el-card v-if="loading.faults" shadow="never" class="panel">
      <el-skeleton :rows="3" animated />
    </el-card>

    <!-- 错误态：可重试 -->
    <el-card v-else-if="error" shadow="never" class="panel">
      <el-result icon="error" title="加载失败" :sub-title="error">
        <template #extra>
          <el-button type="primary" @click="retry">重试</el-button>
        </template>
      </el-result>
    </el-card>

    <!-- 选中故障 -->
    <el-card v-else-if="selectedFault" shadow="never" class="panel">
      <div class="fault-head">
        <h2>{{ selectedFault.title }}</h2>
        <el-tag size="small" type="info">{{ selectedFault.view_count }} 人看过</el-tag>
      </div>
      <p class="symptom">{{ selectedFault.symptom || '暂无现象描述' }}</p>
      <el-button type="primary" @click="openDetail(selectedFault.id)">查看解决方案</el-button>
    </el-card>

    <!-- 结果列表 -->
    <el-card v-else-if="filteredFaults.length" shadow="never" class="panel">
      <template #header>找到 {{ filteredFaults.length }} 条可能的故障，点击查看方案</template>
      <div
        v-for="item in filteredFaults"
        :key="item.id"
        class="fault-item"
        @click="openDetail(item.id)"
      >
        <div class="fault-title">{{ item.title }}</div>
        <div class="fault-symptom">{{ item.symptom || '暂无现象描述' }}</div>
        <div class="fault-meta">{{ item.view_count }} 人看过</div>
      </div>
    </el-card>

    <!-- 空态：引导转工单 -->
    <el-card v-else-if="partId" shadow="never" class="panel">
      <el-empty description="没有找到匹配的解决方案">
        <p class="empty-tip">可以换个关键词，或直接把问题提交给我们</p>
        <el-button type="primary" @click="goTicket">提交工单</el-button>
      </el-empty>
    </el-card>

    <!-- 初始引导 -->
    <el-card v-else shadow="never" class="panel">
      <el-empty description="请先选择产品和零件" />
    </el-card>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { listParts, listProducts } from '../../api/product'
import { listFaults, reportMiss } from '../../api/fault'

const router = useRouter()

const products = ref([])
const parts = ref([])
const faults = ref([])

const productId = ref(null)
const partId = ref(null)
const faultId = ref(null)
const keyword = ref('')

const loading = reactive({ products: false, parts: false, faults: false })
const error = ref('')

// 未命中上报去重：同一 产品|零件|关键词 30 秒内只报一次（契约 §4）
const REPORT_INTERVAL = 30 * 1000
const reported = new Map()
let missTimer = null

const filteredFaults = computed(() => {
  const key = keyword.value.trim().toLowerCase()
  if (!key) return faults.value
  return faults.value.filter(
    (item) =>
      item.title.toLowerCase().includes(key) ||
      (item.symptom || '').toLowerCase().includes(key)
  )
})

const selectedFault = computed(() => {
  if (!faultId.value) return null
  return filteredFaults.value.find((item) => item.id === faultId.value) || null
})

async function loadProducts() {
  loading.products = true
  error.value = ''
  try {
    products.value = await listProducts()
  } catch (e) {
    error.value = e.response?.data?.detail || '产品列表加载失败'
  } finally {
    loading.products = false
  }
}

async function onProductChange(value) {
  partId.value = null
  faultId.value = null
  parts.value = []
  faults.value = []
  keyword.value = ''
  if (!value) return

  loading.parts = true
  error.value = ''
  try {
    parts.value = await listParts(value)
  } catch (e) {
    error.value = e.response?.data?.detail || '零件列表加载失败'
  } finally {
    loading.parts = false
  }
}

async function onPartChange(value) {
  faultId.value = null
  keyword.value = ''
  faults.value = []
  if (!value) return

  await loadFaults()
}

async function loadFaults() {
  loading.faults = true
  error.value = ''
  try {
    faults.value = await listFaults(productId.value, partId.value)
  } catch (e) {
    error.value = e.response?.data?.detail || '故障列表加载失败'
  } finally {
    loading.faults = false
  }
}

function onKeywordInput() {
  if (!partId.value || !productId.value) return
  clearTimeout(missTimer)
  missTimer = setTimeout(() => {
    // 只有"过滤结果为 0"才算未命中；空关键词也要上报（raw_query=null），
    // 否则"未输入关键词"这一桶永远为空
    if (filteredFaults.value.length > 0) return
    const key = `${productId.value}|${partId.value}|${keyword.value.trim()}`
    const now = Date.now()
    const last = reported.get(key) || 0
    if (now - last < REPORT_INTERVAL) return
    reported.set(key, now)
    reportMiss({
      product_id: productId.value,
      part_id: partId.value,
      raw_query: keyword.value.trim() || null
    }).catch(() => {
      // 上报失败不影响用户操作，也不弹错误
    })
  }, 600)
}

function openDetail(id) {
  router.push({
    name: 'fault-detail',
    params: { id },
    query: keyword.value.trim() ? { q: keyword.value.trim() } : {}
  })
}

function goTicket() {
  router.push({
    name: 'ticket-new',
    query: {
      product_id: productId.value,
      part_id: partId.value,
      ...(faultId.value ? { fault_id: faultId.value } : {})
    }
  })
}

function retry() {
  if (!productId.value) {
    loadProducts()
  } else if (!partId.value) {
    onProductChange(productId.value)
  } else {
    loadFaults()
  }
  if (error.value) ElMessage.warning('正在重试…')
}

onMounted(loadProducts)

// 防抖定时器里引用着产品/零件 id，卸载后触发只会拿过期上下文上报
onBeforeUnmount(() => clearTimeout(missTimer))
</script>

<style scoped>
.hero {
  margin: 8px 0 20px;
  text-align: center;
}

.hero h1 {
  margin: 0 0 8px;
  font-size: 22px;
}

.hero p {
  margin: 0;
  color: #909399;
  font-size: 13px;
}

.panel {
  margin-bottom: 16px;
}

.field label {
  display: block;
  margin-bottom: 6px;
  color: #606266;
  font-size: 13px;
}

.search {
  margin-top: 4px;
}

.fault-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.fault-head h2 {
  margin: 0;
  font-size: 18px;
}

.symptom {
  margin: 0 0 16px;
  color: #606266;
}

.fault-item {
  padding: 12px 4px;
  border-bottom: 1px solid #f0f2f5;
  cursor: pointer;
}

.fault-item:last-child {
  border-bottom: none;
}

.fault-item:hover {
  background: #fafafa;
}

.fault-title {
  font-weight: 600;
  margin-bottom: 4px;
}

.fault-symptom {
  color: #606266;
  font-size: 13px;
}

.fault-meta {
  margin-top: 4px;
  color: #a8abb2;
  font-size: 12px;
}

.empty-tip {
  margin: 0 0 12px;
  color: #909399;
  font-size: 13px;
}

/* ---------- 手机 ----------
 *
 * 三级级联在窄屏本来是 el-col :xs="24" 自动换行，但每列之间只有 16px gutter
 * 的横向间距、没有纵向间距，三个 select 会挤成一片看不出步骤先后。
 * 这里补成单列堆叠 + 纵向间距，并让控件撑满宽度。
 */
@media (max-width: 640px) {
  .hero {
    margin: 0 0 14px;
    text-align: left;
  }

  /* 标题已在顶栏出现过一次，手机上重复大标题只是浪费首屏高度 */
  .hero h1 {
    font-size: 18px;
    margin-bottom: 6px;
  }

  .hero p {
    line-height: 1.5;
  }

  .panel {
    margin-bottom: 12px;
  }

  /* el-card 默认 20px 内边距，375px 屏上左右各占 20px 太窄 */
  .panel :deep(.el-card__body) {
    padding: 14px;
  }

  .panel :deep(.el-card__header) {
    padding: 12px 14px;
    line-height: 1.4;
  }

  .field {
    margin-bottom: 14px;
  }

  .field:last-of-type {
    margin-bottom: 10px;
  }

  .field label {
    font-size: 14px;
    font-weight: 600;
    color: #303133;
    margin-bottom: 8px;
  }

  .search {
    margin-top: 0;
  }

  .fault-head {
    gap: 8px;
  }

  .fault-head h2 {
    font-size: 17px;
    line-height: 1.4;
    /* 长标题允许换行，不要挤成一条把"人看过"推出去 */
    word-break: break-word;
  }

  .symptom {
    line-height: 1.6;
    margin-bottom: 14px;
  }

  /* 按钮在窄屏上撑满整行，拇指更容易点到 */
  .symptom + .el-button,
  .panel :deep(.el-empty) .el-button {
    width: 100%;
  }

  /* 列表项整块可点，内边距也要够大。
     单条至少 44px 高（三行文字约 87px，本来就超），这里主要给足左右与纵向留白 */
  .fault-item {
    padding: 14px 4px;
    min-height: var(--tap-min);
  }

  .fault-title {
    font-size: 15px;
    line-height: 1.45;
    word-break: break-word;
  }

  .fault-symptom {
    line-height: 1.55;
    margin-top: 2px;
  }
}
</style>
