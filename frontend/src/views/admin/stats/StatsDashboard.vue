<template>
  <div class="page">
    <el-card shadow="never">
      <div class="toolbar">
        <span class="label">{{ $t('admin.stats.period') }}</span>
        <el-radio-group v-model="days" @change="loadAll">
          <el-radio-button :value="7">{{ $t('admin.stats.last7Days') }}</el-radio-button>
          <el-radio-button :value="30">{{ $t('admin.stats.last30Days') }}</el-radio-button>
          <el-radio-button :value="0">{{ $t('admin.stats.allTime') }}</el-radio-button>
        </el-radio-group>
        <span class="tip">{{ $t('admin.stats.periodHint') }}</span>
      </div>
    </el-card>

    <el-row :gutter="16" class="cards">
      <el-col :xs="24" :sm="12" :md="6">
        <el-card shadow="never" class="metric" v-loading="loading.overview">
          <div class="metric-label">{{ $t('admin.stats.totalQueries') }}</div>
          <div class="metric-value">{{ formatNumber(overview.total_queries) }}</div>
          <div class="metric-sub">{{ $t('admin.stats.missedSub', { count: formatNumber(overview.missed_queries) }) }}</div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <el-card shadow="never" class="metric" v-loading="loading.overview">
          <div class="metric-label">
            {{ $t('admin.stats.resolveRate') }}
            <!-- 悬停展示分子分母，分母必须是 view_queries（不是 total_queries） -->
            <el-tooltip
              :content="$t('admin.stats.resolveRateTip', { resolved: formatNumber(overview.resolved_queries), viewed: formatNumber(overview.view_queries) })"
              placement="top"
            >
              <span class="q">?</span>
            </el-tooltip>
          </div>
          <div class="metric-value">{{ formatPercent(overview.resolve_rate) }}</div>
          <div class="metric-sub">{{ $t('admin.stats.viewedSub', { count: formatNumber(overview.view_queries) }) }}</div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <el-card shadow="never" class="metric" v-loading="loading.overview">
          <div class="metric-label">{{ $t('admin.stats.totalTickets') }}</div>
          <div class="metric-value">{{ formatNumber(overview.total_tickets) }}</div>
          <div class="metric-sub">{{ $t('admin.stats.totalTicketsSub') }}</div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <el-card shadow="never" class="metric" v-loading="loading.overview">
          <div class="metric-label">
            {{ $t('admin.stats.backlog') }}
            <el-tooltip :content="$t('admin.stats.backlogTip')" placement="top">
              <span class="q">?</span>
            </el-tooltip>
          </div>
          <div class="metric-value warn">{{ formatNumber(overview.open_tickets) }}</div>
          <div class="metric-sub">{{ $t('admin.stats.backlogSub') }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" v-loading="loading.topFaults">
      <template #header>{{ $t('admin.stats.topFaultsTitle') }}</template>
      <div v-if="topFaults.length" ref="chartRef" class="chart" />
      <el-empty v-else :description="$t('admin.stats.topFaultsEmpty')" :image-size="70" />
    </el-card>

    <el-card shadow="never" v-loading="loading.missed">
      <template #header>{{ $t('admin.stats.missedTitle') }}</template>
      <el-table v-if="missedRows.length" :data="missedRows" border size="small">
        <el-table-column :label="$t('admin.stats.colQuery')" min-width="200">
          <template #default="{ row }">
            <span :class="{ weak: row.isBlank }">{{ row.isBlank ? $t('admin.stats.blankQuery') : `「${row.raw_query}」` }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="count" :label="$t('admin.stats.colCount')" width="90" align="center" />
        <el-table-column :label="$t('admin.stats.colAppearedIn')" min-width="220">
          <template #default="{ row }">
            <span v-if="row.sample_product_name || row.sample_part_name">
              {{ row.sample_product_name || '-' }} / {{ row.sample_part_name || '-' }}
            </span>
            <span v-else class="weak">-</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('admin.stats.colLastSeen')" width="110">
          <template #default="{ row }">{{ formatMonthDay(row.last_seen_at) }}</template>
        </el-table-column>
      </el-table>
      <el-empty v-else :description="$t('admin.stats.missedEmpty')" :image-size="70" />
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
import { useI18n } from 'vue-i18n'
import { errorMessage } from '../../../utils/error'
import { formatNumber, formatPercent } from '../../../utils/format'

// 按需注册，避免把整个 echarts（~1MB）打进看板 chunk
echarts.use([BarChart, GridComponent, TooltipComponent, CanvasRenderer])

const router = useRouter()
const { t } = useI18n()

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
// 与后端约定的归一化值，用于比较而不是展示，翻译会导致匹配失效 —— 不能改
const BLANK_QUERY = '(未输入关键词)'  // i18n-ignore: 契约值，非展示文案

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
    ElMessage.error(errorMessage(e, { fallbackKey: 'admin.stats.overviewLoadFailed' }))
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
    ElMessage.error(errorMessage(e, { fallbackKey: 'admin.stats.topFaultsLoadFailed' }))
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
    ElMessage.error(errorMessage(e, { fallbackKey: 'admin.stats.missedLoadFailed' }))
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
  // 故障标题是运营录入的长文本，固定宽度截断，完整标题在 tooltip 里看；
  // 窄屏再收窄，否则左侧标签会把柱子挤没
  const boxWidth = chartRef.value.clientWidth || 600
  const labelWidth = boxWidth < 480 ? 96 : 168
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
          return `${source.title}<br/>${source.product_name} / ${source.part_name}<br/>${t('admin.stats.chartTooltip', { views: source.period_views, total: source.view_count })}`
        }
      },
      xAxis: {
        type: 'value',
        splitLine: { lineStyle: { color: '#f0f2f5' } },
        // 刻度数字是次要信息，用次级文字色；默认浅灰在浅底上不够清楚
        axisLabel: { color: '#606266', fontSize: 12 }
      },
      yAxis: {
        type: 'category',
        data: data.map((item) => item.title),
        axisTick: { show: false },
        axisLine: { lineStyle: { color: '#e4e7ed' } },
        // ECharts 默认标签色是浅灰（#6E7079），在浅色卡片上偏淡；
        // 这里用正文色 #303133，与页面其余文字一致
        axisLabel: {
          color: '#303133',
          fontSize: 12,
          width: labelWidth,
          overflow: 'truncate'
        }
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
