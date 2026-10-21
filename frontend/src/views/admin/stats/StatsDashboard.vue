<template>
  <div class="page">
    <el-card shadow="never">
      <div class="toolbar">
        <span class="label">时间范围</span>
        <el-radio-group v-model="days" @change="loadAll">
          <el-radio-button :value="7">近 7 天</el-radio-button>
          <el-radio-button :value="30">近 30 天</el-radio-button>
          <el-radio-button :value="0">全部</el-radio-button>
        </el-radio-group>
        <span class="tip">切换后除"当前积压"外全部联动</span>
      </div>
    </el-card>

    <el-row :gutter="16" class="cards">
      <el-col :xs="24" :sm="12" :md="6">
        <el-card shadow="never" class="metric" v-loading="loading.overview">
          <div class="metric-label">查询次数</div>
          <div class="metric-value">{{ formatNumber(overview.total_queries) }}</div>
          <div class="metric-sub">含未命中 {{ formatNumber(overview.missed_queries) }} 次</div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <el-card shadow="never" class="metric" v-loading="loading.overview">
          <div class="metric-label">
            自助解决率
            <!-- 悬停展示分子分母，分母必须是 view_queries（不是 total_queries） -->
            <el-tooltip
              :content="`${formatNumber(overview.resolved_queries)} / ${formatNumber(overview.view_queries)}（已解决 / 查看方案）`"
              placement="top"
            >
              <span class="q">?</span>
            </el-tooltip>
          </div>
          <div class="metric-value">{{ formatPercent(overview.resolve_rate) }}</div>
          <div class="metric-sub">查看方案 {{ formatNumber(overview.view_queries) }} 次</div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <el-card shadow="never" class="metric" v-loading="loading.overview">
          <div class="metric-label">工单总数</div>
          <div class="metric-value">{{ formatNumber(overview.total_tickets) }}</div>
          <div class="metric-sub">窗口内新建</div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <el-card shadow="never" class="metric" v-loading="loading.overview">
          <div class="metric-label">
            当前积压
            <el-tooltip content="待处理 + 处理中的工单数，不随时间范围变化" placement="top">
              <span class="q">?</span>
            </el-tooltip>
          </div>
          <div class="metric-value warn">{{ formatNumber(overview.open_tickets) }}</div>
          <div class="metric-sub">不随筛选变化</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" v-loading="loading.topFaults">
      <template #header>TOP 10 故障（按所选时间窗内查看次数）</template>
      <div v-if="topFaults.length" ref="chartRef" class="chart" />
      <el-empty v-else description="该时间范围内还没有查看记录" :image-size="70" />
    </el-card>

    <el-card shadow="never" v-loading="loading.missed">
      <template #header>未命中检索（用户查了但没结果）</template>
      <el-table v-if="missedRows.length" :data="missedRows" border size="small">
        <el-table-column label="检索词" min-width="200">
          <template #default="{ row }">
            <span :class="{ weak: row.isBlank }">{{ row.isBlank ? row.raw_query : `「${row.raw_query}」` }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="count" label="次数" width="90" align="center" />
        <el-table-column label="出现在" min-width="220">
          <template #default="{ row }">
            <span v-if="row.sample_product_name || row.sample_part_name">
              {{ row.sample_product_name || '-' }} / {{ row.sample_part_name || '-' }}
            </span>
            <span v-else class="weak">-</span>
          </template>
        </el-table-column>
        <el-table-column label="最近出现" width="110">
          <template #default="{ row }">{{ formatMonthDay(row.last_seen_at) }}</template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="暂无未命中记录 —— 说明知识库覆盖良好" :image-size="70" />
    </el-card>
  </div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { adminStatsMissed, adminStatsOverview, adminStatsTopFaults } from '../../../api/admin'
import { errorText } from '../../../utils/admin'
import { formatNumber, formatPercent } from '../../../utils/format'

// 按需注册，避免把整个 echarts（~1MB）打进看板 chunk
echarts.use([BarChart, GridComponent, TooltipComponent, CanvasRenderer])

const router = useRouter()

// 契约 §6：days=0 表示全部
const days = ref(30)

const overview = ref({
  total_queries: 0,
  view_queries: 0,
  resolved_queries: 0,
  resolve_rate: null,
  total_tickets: 0,
  open_tickets: 0,
  missed_queries: 0
})
const topFaults = ref([])
const missedRows = ref([])
const loading = reactive({ overview: false, topFaults: false, missed: false })

const chartRef = ref()
let chart = null
// 快速切换时间范围时，先发的请求可能后到，把旧窗口的数据盖到新窗口上
let reqSeq = 0

/**
 * (未输入关键词) 行置底并弱化样式 —— 契约 §6 的归一化结果，
 * 不能让空关键词和真实关键词混排，否则看到"最高频检索词是一次都没输入"会误判。
 */
const BLANK_QUERY = '(未输入关键词)'

function splitMissed(items) {
  const normal = []
  const blank = []
  for (const item of items) {
    if (item.raw_query === BLANK_QUERY) blank.push({ ...item, isBlank: true })
    else normal.push({ ...item, isBlank: false })
  }
  return [...normal, ...blank]
}

function formatMonthDay(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  const parts = new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    month: '2-digit',
    day: '2-digit'
  }).format(date)
  return parts.replace(/\//g, '-')
}

async function loadOverview(my) {
  loading.overview = true
  try {
    const data = await adminStatsOverview({ days: days.value })
    if (my !== reqSeq) return
    overview.value = data
  } catch (e) {
    if (my !== reqSeq) return
    ElMessage.error(errorText(e, '指标加载失败'))
  } finally {
    if (my === reqSeq) loading.overview = false
  }
}

async function loadTopFaults(my) {
  loading.topFaults = true
  try {
    const data = await adminStatsTopFaults({ days: days.value, limit: 10 })
    if (my !== reqSeq) return
    topFaults.value = data
    await nextTick()
    renderChart()
  } catch (e) {
    if (my !== reqSeq) return
    topFaults.value = []
    ElMessage.error(errorText(e, 'TOP 故障加载失败'))
  } finally {
    if (my === reqSeq) loading.topFaults = false
  }
}

async function loadMissed(my) {
  loading.missed = true
  try {
    const data = await adminStatsMissed({ days: days.value, limit: 20 })
    if (my !== reqSeq) return
    missedRows.value = splitMissed(data)
  } catch (e) {
    if (my !== reqSeq) return
    missedRows.value = []
    ElMessage.error(errorText(e, '未命中记录加载失败'))
  } finally {
    if (my === reqSeq) loading.missed = false
  }
}

async function loadAll() {
  const my = (reqSeq += 1)
  chart?.clear()
  // 三个接口相互独立，并发拉取；任一失败不影响另外两个
  await Promise.all([loadOverview(my), loadTopFaults(my), loadMissed(my)])
}

function renderChart() {
  if (!chartRef.value) return
  chart = chart || echarts.init(chartRef.value)

  // 横向条形图：标签过长时不挤，且顺序与"最多的在最上"一致
  const data = [...topFaults.value].reverse()
  chart.setOption(
    {
      grid: { left: 8, right: 48, top: 8, bottom: 8, containLabel: true },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params) => {
          const item = params[0]
          const source = data[item.dataIndex]
          if (!source) return ''
          return `${source.title}<br/>${source.product_name} / ${source.part_name}<br/>窗口内查看 ${source.period_views} 次（累计 ${source.view_count}）`
        }
      },
      xAxis: { type: 'value', splitLine: { lineStyle: { color: '#f0f2f5' } } },
      yAxis: {
        type: 'category',
        data: data.map((item) => item.title),
        axisTick: { show: false },
        axisLine: { lineStyle: { color: '#e4e7ed' } }
      },
      series: [
        {
          type: 'bar',
          // 每根柱子额外挂 fault_id，点击时直接取，避免"再 reverse 一次对索引"
          data: data.map((item) => ({ value: item.period_views, faultId: item.fault_id })),
          barMaxWidth: 18,
          itemStyle: { color: '#409eff', borderRadius: [0, 4, 4, 0] },
          label: { show: true, position: 'right', color: '#606266', fontSize: 12 }
        }
      ]
    },
    true
  )
}

function onChartClick(params) {
  const faultId = params?.data?.faultId
  // 不能用 if (faultId)：id=0 是合法值，会被当成假值静默丢弃
  if (faultId === undefined || faultId === null) return
  router.push({ name: 'admin-fault-edit', params: { id: faultId } })
}

function onResize() {
  chart?.resize()
}

onMounted(async () => {
  await loadAll()
  chart?.on('click', onChartClick)
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.label {
  font-size: 13px;
  color: #606266;
}

.tip {
  color: #a8abb2;
  font-size: 12px;
}

.cards .metric {
  margin-bottom: 16px;
}

.metric-label {
  display: flex;
  align-items: center;
  gap: 4px;
  color: #909399;
  font-size: 13px;
}

.q {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #f0f2f5;
  color: #909399;
  font-size: 10px;
  cursor: help;
}

.metric-value {
  margin: 8px 0 4px;
  font-size: 26px;
  font-weight: 600;
  color: #303133;
  line-height: 1.2;
}

.metric-value.warn {
  color: #e6a23c;
}

.metric-sub {
  color: #a8abb2;
  font-size: 12px;
}

.chart {
  width: 100%;
  height: 340px;
}

.weak {
  color: #a8abb2;
}
</style>
