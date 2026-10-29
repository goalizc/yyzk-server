<template>
  <div class="home">
    <section class="hero">
      <h1>{{ $t('public.home.title') }}</h1>
      <p>{{ $t('public.home.subtitle') }}</p>
    </section>

    <el-card shadow="never" class="panel">
      <el-row :gutter="16">
        <el-col :xs="24" :sm="12">
          <div class="field">
            <label>{{ $t('public.home.step1') }}</label>
            <el-select
              v-model="productId"
              :placeholder="$t('public.home.selectProduct')"
              filterable
              clearable
              :loading="loading.products"
              style="width: 100%"
              @change="onProductChange"
            >
              <el-option
                v-for="item in products"
                :key="item.id"
                :label="$t('public.home.productOption', { name: item.name, model: item.model })"
                :value="item.id"
              />
            </el-select>
          </div>
        </el-col>

        <!-- 零件是可选过滤器：客户多数不知道内部零件叫什么，不选也能看全部故障。
             提示语直接写进 placeholder：能省一行高度，英文句子也不会因折行把关键词框顶下去 -->
        <el-col :xs="24" :sm="12">
          <div class="field">
            <label>{{ $t('public.home.step2') }}</label>
            <el-select
              v-model="partId"
              :placeholder="$t('public.home.allParts')"
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
                :label="item.group_name
                  ? $t('public.home.partOption', { group: item.group_name, name: item.name })
                  : item.name"
                :value="item.id"
              />
            </el-select>
          </div>
        </el-col>
      </el-row>

      <!-- 关键词只过滤下面这份列表，不再承担"再选一次"的职责 -->
      <el-input
        v-model="keyword"
        class="search"
        :placeholder="$t('public.home.keywordPlaceholder')"
        clearable
        :disabled="!productId"
        @input="onKeywordInput"
      />
    </el-card>

    <!-- 加载中 -->
    <el-card v-if="loading.faults" shadow="never" class="panel">
      <el-skeleton :rows="3" animated />
    </el-card>

    <!-- 错误态：可重试 -->
    <el-card v-else-if="error" shadow="never" class="panel">
      <el-result icon="error" :title="$t('public.home.loadFailed')" :sub-title="error">
        <template #extra>
          <el-button type="primary" @click="retry">{{ $t('common.action.retry') }}</el-button>
        </template>
      </el-result>
    </el-card>

    <!--
      结果列表 = 故障现象选择器。
      以前这里还有一级"3. 选择故障现象"下拉，选项和下面的列表是同一批数据，
      下拉里又只有标题（维修术语）、没有现象描述，反而比列表更难选，已删除。
      选完产品就出列表，零件只是可选过滤器。
    -->
    <el-card v-else-if="productId && filteredFaults.length" shadow="never" class="panel">
      <template #header>
        {{ $t('public.home.foundCount', filteredFaults.length) }}
      </template>
      <div
        v-for="item in visibleFaults"
        :key="item.id"
        class="fault-item"
        @click="openDetail(item.id)"
      >
        <div class="fault-title">{{ item.title }}</div>
        <div class="fault-symptom">{{ item.symptom || $t('public.home.symptomEmpty') }}</div>
        <div class="fault-meta">
          <!-- 零件名是参考信息：客户不知道自己坏在哪也能读，知道的话还能据此确认 -->
          <span v-if="item.part_name" class="fault-part">{{ item.part_name }}</span>
          <span>{{ $t('common.count.viewed', item.view_count) }}</span>
        </div>
      </div>

      <div v-if="hasMore" class="more">
        <el-button text type="primary" @click="showMore">
          {{ $t('public.home.expandMore', remaining) }}
        </el-button>
      </div>

      <!-- 列表里都不像自己的情况时，别逼用户挨个点开找"提交工单" -->
      <div class="list-footer">
        <span>{{ $t('public.home.notListed') }}</span>
        <el-button link type="primary" @click="goTicket">
          {{ $t('public.home.submitTicket') }}
        </el-button>
      </div>
    </el-card>

    <!-- 空态：搜不到 / 该产品还没有故障记录，两种情况都要能直接报障 -->
    <el-card v-else-if="productId" shadow="never" class="panel">
      <el-empty :description="hasKeyword ? $t('public.home.noResult') : $t('public.home.noFaultData')">
        <p class="empty-tip">
          {{ hasKeyword ? $t('public.home.emptyTip') : $t('public.home.noDataTip') }}
        </p>
        <div class="empty-actions">
          <el-button v-if="hasKeyword" @click="clearKeyword">
            {{ $t('public.home.clearKeyword') }}
          </el-button>
          <el-button v-if="partId && !hasKeyword" @click="clearPart">
            {{ $t('public.home.clearPart') }}
          </el-button>
          <el-button type="primary" @click="goTicket">
            {{ $t('public.home.submitTicket') }}
          </el-button>
        </div>
      </el-empty>
    </el-card>

    <!-- 初始引导 -->
    <el-card v-else shadow="never" class="panel">
      <el-empty :description="$t('public.home.initialTip')" />
    </el-card>
  </div>
</template>

<script setup>
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { listParts, listProducts } from '../../api/product'
import { listFaults, reportMiss } from '../../api/fault'
import { errorMessage } from '../../utils/error'
import { localeRoute } from '../../locales'

const router = useRouter()
const { t } = useI18n()

// keep-alive 的 include="Home" 按组件 name 匹配，<script setup> 默认没有 name，必须显式声明
defineOptions({ name: 'Home' })

// 一次展开多少条。故障数通常 1~3 条（78% 的零件只有 1 条），
// 但真实客户环境一个零件可能有十几条，超过就先折叠
const PAGE_SIZE = 5

const products = ref([])
const parts = ref([])
const faults = ref([])

const productId = ref(null)
const partId = ref(null)
const keyword = ref('')
const visibleCount = ref(PAGE_SIZE)

const loading = reactive({ products: false, parts: false, faults: false })
const error = ref('')

// 未命中上报去重：同一 产品|零件|关键词 30 秒内只报一次（契约 §4）
const REPORT_INTERVAL = 30 * 1000
const reported = new Map()
let missTimer = null

const hasKeyword = computed(() => keyword.value.trim().length > 0)

const filteredFaults = computed(() => {
  const key = keyword.value.trim().toLowerCase()
  if (!key) return faults.value
  return faults.value.filter(
    (item) =>
      item.title.toLowerCase().includes(key) ||
      (item.symptom || '').toLowerCase().includes(key)
  )
})

const visibleFaults = computed(() => filteredFaults.value.slice(0, visibleCount.value))
const remaining = computed(() => filteredFaults.value.length - visibleCount.value)
const hasMore = computed(() => remaining.value > 0)

// 关键词一变就缩回第一屏，否则搜完一个词再搜另一个会停在"展开很多条"的状态
watch(keyword, () => {
  visibleCount.value = PAGE_SIZE
})

function showMore() {
  visibleCount.value += PAGE_SIZE
}

function clearKeyword() {
  keyword.value = ''
}

async function loadProducts() {
  loading.products = true
  error.value = ''
  try {
    products.value = await listProducts()
  } catch (e) {
    error.value = errorMessage(e, { fallbackKey: 'public.home.productLoadFailed' })
  } finally {
    loading.products = false
  }
}

async function onProductChange(value) {
  partId.value = null
  parts.value = []
  faults.value = []
  keyword.value = ''
  visibleCount.value = PAGE_SIZE
  if (!value) return

  loading.parts = true
  error.value = ''
  try {
    parts.value = await listParts(value)
  } catch (e) {
    error.value = errorMessage(e, { fallbackKey: 'public.home.partLoadFailed' })
    return
  } finally {
    loading.parts = false
  }
  // 选完产品就出列表（零件可选），不用等用户再挑零件
  await loadFaults()
}

async function onPartChange() {
  keyword.value = ''
  faults.value = []
  visibleCount.value = PAGE_SIZE
  if (!productId.value) return

  await loadFaults()
}

function clearPart() {
  partId.value = null
  onPartChange()
}

/**
 * 未命中上报（契约 §4）：同一 产品|零件|关键词 30 秒内只报一次。
 * 抽出来是因为有两个触发点——接口本身 0 条（raw_query=null）与关键词过滤为空。
 * 零件可能为 null（零件是可选过滤器），此时上报体里带 part_id=null。
 */
function reportMissOnce(pid, part, rawQuery) {
  const key = `${pid}|${part}|${rawQuery || ''}`
  const now = Date.now()
  if (now - (reported.get(key) || 0) < REPORT_INTERVAL) return
  reported.set(key, now)
  reportMiss({ product_id: pid, part_id: part ?? null, raw_query: rawQuery }).catch(() => {
    // 上报失败不影响用户操作，也不弹错误
  })
}

async function loadFaults() {
  loading.faults = true
  error.value = ''
  try {
    faults.value = await listFaults(productId.value, partId.value)
    // 接口本身 0 条 = "这个产品（或产品+零件）下没有任何故障记录"，与关键词无关，记一条 raw_query=null。
    // 有关键词的情况交给 onKeywordInput：一次操作只记一条，不能两边都报
    if (!faults.value.length) reportMissOnce(productId.value, partId.value, null)
  } catch (e) {
    error.value = errorMessage(e, { fallbackKey: 'public.home.faultLoadFailed' })
  } finally {
    loading.faults = false
  }
}

function onKeywordInput() {
  // 选完产品就能用关键词，不需要先选零件
  if (!productId.value) return
  clearTimeout(missTimer)
  missTimer = setTimeout(() => {
    // 只有"过滤结果为 0"才算未命中
    if (filteredFaults.value.length > 0) return
    reportMissOnce(productId.value, partId.value, keyword.value.trim() || null)
  }, 600)
}

function openDetail(id) {
  router.push(
    localeRoute('fault-detail', { id }, keyword.value.trim() ? { q: keyword.value.trim() } : {})
  )
}

// 没有选中故障这回事了，工单只带产品与零件上下文（零件未选时不带该参数）
function goTicket() {
  const query = { product_id: productId.value }
  if (partId.value) query.part_id = partId.value
  router.push(localeRoute('ticket-new', {}, query))
}

function retry() {
  if (!productId.value) {
    loadProducts()
  } else if (parts.value.length === 0 && faults.value.length === 0) {
    // 零件列表没拿到（选产品后连请求就失败了）→ 整个产品的上下文重来一遍
    onProductChange(productId.value)
  } else {
    loadFaults()
  }
  if (error.value) ElMessage.warning(t('public.home.retrying'))
}

onMounted(loadProducts)

// 首页被 keep-alive 缓存：从详情页返回时不会重新挂载，这里兜底补一次产品列表
// （极端情况：首次进入即被缓存但 loadProducts 失败，激活后仍为空时重拉）
onActivated(() => {
  if (products.value.length === 0) loadProducts()
})

// 防抖定时器里引用着产品/零件 id：离开首页（失活或最终卸载）后触发只会拿过期上下文上报
onDeactivated(() => clearTimeout(missTimer))
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
  /* 与上一行下拉拉开距离：两列并排时 4px 会贴着，像同一条表单 */
  margin-top: 12px;
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
  /* 文档 P-01 规则 4：摘要最多 2 行、超出省略。
     列表现在是唯一的故障入口，一条症状写满三四行会把整屏占掉 */
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.fault-meta {
  margin-top: 4px;
  color: #a8abb2;
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

/* 零件名只是参考：用标签形态与前两项的纯文本元信息区分开。
   底色比 #f4f4f5 深一档，浅色背景上原值几乎看不出是个标签 */
.fault-part {
  padding: 0 6px;
  border-radius: 3px;
  background: #eef0f3;
  color: #6b7280;
  line-height: 18px;
}

.more {
  text-align: center;
  padding-top: 8px;
}

.list-footer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  flex-wrap: wrap;
  margin-top: 8px;
  padding-top: 10px;
  border-top: 1px solid #f0f2f5;
  color: #909399;
  font-size: 13px;
}

.empty-tip {
  margin: 0 0 12px;
  color: #909399;
  font-size: 13px;
}

.empty-actions {
  display: flex;
  justify-content: center;
  gap: 10px;
  flex-wrap: wrap;
}

/* ---------- 手机 ----------
 *
 * 两级联动在窄屏靠 el-col :xs="24" 自动换行，但每列之间只有 16px gutter
 * 的横向间距、没有纵向间距，两个 select 会挤成一片看不出步骤先后。
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

  /* 两个按钮并排会各自挤成半行，竖排整行更容易点 */
  .empty-actions {
    flex-direction: column;
    align-items: stretch;
  }

  .empty-actions :deep(.el-button) {
    width: 100%;
    margin-left: 0;
  }
}
</style>
