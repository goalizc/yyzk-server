# 故障知识库阅读抽屉 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 后台故障列表点行改为打开阅读抽屉，复用客户侧图文排版，并支持复制带链接的方案文本。

**Architecture:** 抽出纯展示组件 `FaultSolutionView`，客户详情页与后台抽屉共用；抽屉负责加载详情和底部动作；复制文本由纯函数生成，剪贴板写入带 HTTP 兜底。

**Tech Stack:** Vue 3、Element Plus、vue-router、Vitest、happy-dom。

---

## 文件结构

| 文件 | 责任 |
|---|---|
| `frontend/src/components/FaultSolutionView.vue` | 纯展示：标题、状态、元信息、风险、描述、步骤、附件 |
| `frontend/src/views/admin/faults/FaultReaderDrawer.vue` | 抽屉容器：加载、错误、复制、编辑跳转、打开客户页 |
| `frontend/src/utils/faultCopy.js` | 生成复制文本，纯函数 |
| `frontend/src/utils/clipboard.js` | 写剪贴板，Clipboard API + textarea 兜底 |
| `frontend/src/views/public/FaultDetail.vue` | 改为复用展示组件 |
| `frontend/src/views/admin/faults/FaultList.vue` | 行点击开抽屉，保留编辑/删除按钮 |

---

## Task 1: 抽取 FaultSolutionView

**Files:**
- Create: `frontend/src/components/FaultSolutionView.vue`
- Create: `frontend/src/components/FaultSolutionView.spec.js`
- Modify: `frontend/src/views/public/FaultDetail.vue`

- [ ] **Step 1: 写失败测试**

```javascript
// frontend/src/components/FaultSolutionView.spec.js
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import FaultSolutionView from './FaultSolutionView.vue'

const FAULT = {
  id: 21,
  title: '主刷不转',
  product_name: '扫地机器人',
  part_name: '主刷模组',
  symptom: '启动后主刷不转',
  root_cause: '主刷被毛发缠绕',
  required_tools: '十字螺丝刀',
  needs_professional: false,
  is_published: true,
  solution_steps: [
    { step: 1, text: '关闭电源', image_url: null },
    { step: 2, text: '拆下主刷', image_url: '/uploads/a.jpg' }
  ],
  attachment_urls: [{ name: '说明书.pdf', url: '/uploads/b.pdf', size: 2048 }],
  view_count: 30,
  resolved_count: 20
}

function mountView(props = {}) {
  return mount(FaultSolutionView, {
    props: { fault: FAULT, ...props },
    global: { plugins: [ElementPlus] }
  })
}

describe('FaultSolutionView', () => {
  it('渲染标题、描述、步骤、图片与附件', () => {
    const wrapper = mountView()

    expect(wrapper.text()).toContain('主刷不转')
    expect(wrapper.text()).toContain('主刷被毛发缠绕')
    expect(wrapper.text()).toContain('拆下主刷')
    expect(wrapper.find('img').attributes('src')).toContain('/uploads/a.jpg')
    expect(wrapper.text()).toContain('说明书.pdf')
  })

  it('showStats 控制查看/解决次数', () => {
    expect(mountView({ showStats: true }).text()).toContain('30 人看过')
    expect(mountView().text()).not.toContain('人看过')
  })

  it('showStatus 控制发布与需专业标签', () => {
    const published = mountView({ showStatus: true })
    expect(published.text()).toContain('已发布')

    const unpublished = mountView({
      showStatus: true,
      fault: { ...FAULT, is_published: false, needs_professional: true }
    })
    expect(unpublished.text()).toContain('未发布')
    expect(unpublished.text()).toContain('需专业')
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && NODE_OPTIONS=--no-experimental-webstorage npx vitest run src/components/FaultSolutionView.spec.js`
Expected: FAIL，模块不存在

- [ ] **Step 3: 实现组件**

```vue
<!-- frontend/src/components/FaultSolutionView.vue -->
<template>
  <div class="solution">
    <el-card shadow="never" class="block">
      <div class="title-row">
        <h1 class="title">{{ fault.title }}</h1>
        <div v-if="showStatus" class="tags">
          <el-tag v-if="fault.is_published" type="success" size="small">已发布</el-tag>
          <el-tag v-else type="info" size="small">未发布</el-tag>
          <el-tag v-if="fault.needs_professional" type="warning" size="small">需专业</el-tag>
        </div>
      </div>

      <p class="meta">
        {{ fault.product_name }} / {{ fault.part_name }}
        <template v-if="showStats">
          <span class="dot">·</span>{{ fault.view_count }} 人看过
          <span class="dot">·</span>{{ fault.resolved_count }} 人反馈已解决
        </template>
        <template v-if="fault.updated_at">
          <span class="dot">·</span>更新于 {{ formatDate(fault.updated_at) }}
        </template>
      </p>

      <el-alert
        v-if="fault.needs_professional"
        type="error"
        show-icon
        :closable="false"
        title="该故障建议由专业人员处理，请勿自行拆机"
        class="pro-alert"
      />

      <el-descriptions :column="1" border size="small" class="desc">
        <el-descriptions-item label="现象描述">
          {{ fault.symptom || '暂无' }}
        </el-descriptions-item>
        <el-descriptions-item label="可能原因">
          {{ fault.root_cause || '暂无' }}
        </el-descriptions-item>
        <el-descriptions-item v-if="fault.required_tools" label="所需工具">
          {{ fault.required_tools }}
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card shadow="never" class="block">
      <template #header>排查步骤</template>
      <ol class="steps">
        <li v-for="step in steps" :key="step.step">
          <div class="step-text">{{ step.text }}</div>
          <el-image
            v-if="step.image_url"
            :src="step.image_url"
            fit="contain"
            class="step-image"
            :preview-src-list="[step.image_url]"
            preview-teleported
          />
        </li>
      </ol>
      <p v-if="!steps.length" class="muted">暂无分步说明</p>
    </el-card>

    <el-card v-if="attachments.length" shadow="never" class="block">
      <template #header>相关附件</template>
      <div v-for="file in attachments" :key="file.url" class="attachment">
        <a :href="file.url" target="_blank" rel="noopener">{{ file.name }}</a>
        <span class="muted">{{ formatSize(file.size) }}</span>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { formatDate } from '../utils/format'

const props = defineProps({
  fault: { type: Object, required: true },
  showStats: { type: Boolean, default: false },
  showStatus: { type: Boolean, default: false }
})

const steps = computed(() =>
  [...(props.fault.solution_steps || [])].sort((a, b) => a.step - b.step)
)
const attachments = computed(() => props.fault.attachment_urls || [])

function formatSize(size) {
  if (!size) return ''
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}
</script>

<style scoped>
.block {
  margin-bottom: 16px;
}

.title-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.title {
  margin: 0 0 8px;
  font-size: 20px;
  line-height: 1.4;
  word-break: break-word;
}

.tags {
  display: flex;
  gap: 6px;
  padding-top: 4px;
}

.meta {
  margin: 0 0 16px;
  color: #909399;
  font-size: 13px;
  line-height: 1.6;
}

.dot {
  margin: 0 6px;
}

.pro-alert {
  margin-bottom: 16px;
}

.desc {
  margin-top: 8px;
}

.steps {
  margin: 0;
  padding-left: 20px;
}

.steps li {
  margin-bottom: 16px;
}

.step-text {
  margin-bottom: 8px;
  line-height: 1.6;
}

.step-image {
  max-width: 360px;
  width: 100%;
  border-radius: 6px;
  border: 1px solid #ebeef5;
}

.attachment {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 0;
}

.attachment a {
  color: #409eff;
  text-decoration: none;
}

.muted {
  color: #a8abb2;
  font-size: 12px;
}

@media (max-width: 640px) {
  .block {
    margin-bottom: 12px;
  }

  .block :deep(.el-card__body) {
    padding: 14px;
  }

  .block :deep(.el-card__header) {
    padding: 12px 14px;
    line-height: 1.4;
  }

  .title {
    font-size: 18px;
  }

  .desc :deep(.el-descriptions__label) {
    width: 84px;
    min-width: 84px;
    white-space: nowrap;
  }

  .desc :deep(.el-descriptions__content) {
    word-break: break-word;
    line-height: 1.6;
  }

  .steps {
    padding-left: 18px;
  }

  .steps li {
    margin-bottom: 14px;
    padding-left: 2px;
  }

  .step-image {
    max-width: 100%;
  }

  .attachment {
    padding: 0;
    gap: 8px;
    flex-wrap: wrap;
    align-items: baseline;
  }

  .attachment a {
    word-break: break-all;
  }
}
</style>
```

- [ ] **Step 4: 公共详情页改为复用**

`frontend/src/views/public/FaultDetail.vue`：

1. `<script setup>` 增加 `import FaultSolutionView from '../../components/FaultSolutionView.vue'`。
2. 把模板中 `<template v-else-if="fault">` 内从 `<el-card ... class="block">`（标题卡）到附件卡（`fault.attachment_urls.length` 那个 card）整段替换为：

```vue
      <FaultSolutionView :fault="fault" show-stats />
```

3. 保留其后的「这个方案解决您的问题了吗？」反馈卡。
4. 删除 `formatSize` 函数与对应样式（`.block/.title/.meta/.dot/.pro-alert/.desc/.steps/.step-text/.step-image/.attachment` 中与展示卡相关的部分）；保留 `.page-header`、`.fb-alert`、`.actions` 及其移动端样式。

- [ ] **Step 5: 运行测试**

Run:
```bash
cd frontend && NODE_OPTIONS=--no-experimental-webstorage npx vitest run \
  src/components/FaultSolutionView.spec.js src/views/public/FaultDetail.spec.js
```
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add frontend/src/components/FaultSolutionView.vue \
  frontend/src/components/FaultSolutionView.spec.js \
  frontend/src/views/public/FaultDetail.vue
git commit -m "refactor(fault): 抽出方案展示组件供客户页与后台复用"
```

---

## Task 2: 复制文本与剪贴板兜底

**Files:**
- Create: `frontend/src/utils/faultCopy.js`
- Create: `frontend/src/utils/faultCopy.spec.js`
- Create: `frontend/src/utils/clipboard.js`
- Create: `frontend/src/utils/clipboard.spec.js`

- [ ] **Step 1: 写失败测试**

```javascript
// frontend/src/utils/faultCopy.spec.js
import { describe, expect, it } from 'vitest'
import { buildFaultCopyText } from './faultCopy'

const ORIGIN = 'http://192.168.1.2'

const BASE = {
  id: 123,
  title: '开机无反应',
  product_name: '扫地机器人 X1',
  part_name: '电池组',
  symptom: '插电后指示灯不亮',
  root_cause: '电池过放保护',
  required_tools: '十字螺丝刀',
  needs_professional: false,
  is_published: true,
  solution_steps: [
    { step: 2, text: '长按电源键 10 秒', image_url: '/uploads/a.jpg' },
    { step: 1, text: '检查电源适配器指示灯', image_url: null }
  ]
}

describe('buildFaultCopyText', () => {
  it('已发布方案包含文字、图片标注与客户页链接', () => {
    const text = buildFaultCopyText(BASE, ORIGIN)

    expect(text).toContain('【开机无反应】')
    expect(text).toContain('产品：扫地机器人 X1 / 电池组')
    expect(text).toContain('1. 检查电源适配器指示灯')
    expect(text).toContain('2. 长按电源键 10 秒')
    expect(text).toContain('[含示意图]')
    expect(text).toContain(`完整图文方案：${ORIGIN}/faults/123`)
  })

  it('未发布方案不附链接', () => {
    const text = buildFaultCopyText({ ...BASE, is_published: false }, ORIGIN)

    expect(text).not.toContain('完整图文方案')
    expect(text).toContain('该方案尚未发布')
  })

  it('需专业处理时加警示', () => {
    const text = buildFaultCopyText({ ...BASE, needs_professional: true }, ORIGIN)

    expect(text).toContain('该故障建议由专业人员处理')
  })

  it('空字段整行省略', () => {
    const text = buildFaultCopyText(
      { ...BASE, root_cause: null, required_tools: null },
      ORIGIN
    )

    expect(text).not.toContain('可能原因')
    expect(text).not.toContain('所需工具')
  })
})
```

```javascript
// frontend/src/utils/clipboard.spec.js
import { afterEach, describe, expect, it, vi } from 'vitest'
import { copyText } from './clipboard'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('copyText', () => {
  it('优先使用 Clipboard API', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText } })

    await expect(copyText('hello')).resolves.toBe(true)
    expect(writeText).toHaveBeenCalledWith('hello')
  })

  it('API 不可用时走 textarea 兜底', async () => {
    vi.stubGlobal('navigator', {})
    document.execCommand = vi.fn().mockReturnValue(true)

    await expect(copyText('fallback')).resolves.toBe(true)
    expect(document.execCommand).toHaveBeenCalledWith('copy')
    expect(document.querySelector('textarea')).toBeNull()
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && NODE_OPTIONS=--no-experimental-webstorage npx vitest run src/utils/faultCopy.spec.js src/utils/clipboard.spec.js`
Expected: FAIL，模块不存在

- [ ] **Step 3: 实现 faultCopy**

```javascript
// frontend/src/utils/faultCopy.js
const PROFESSIONAL_WARNING = '⚠️ 该故障建议由专业人员处理，请勿自行拆机'

export function buildFaultCopyText(fault, origin = window.location.origin) {
  const lines = []

  if (fault.needs_professional) {
    lines.push(PROFESSIONAL_WARNING)
  }

  lines.push(`【${fault.title}】`)
  lines.push(`产品：${fault.product_name || '—'} / ${fault.part_name || '—'}`)

  if (fault.symptom) lines.push('', `现象：${fault.symptom}`)
  if (fault.root_cause) lines.push(`可能原因：${fault.root_cause}`)
  if (fault.required_tools) lines.push(`所需工具：${fault.required_tools}`)

  const steps = [...(fault.solution_steps || [])].sort((a, b) => a.step - b.step)
  if (steps.length) {
    lines.push('', '处理步骤：')
    for (const step of steps) {
      lines.push(`${step.step}. ${step.text}`)
      if (step.image_url) lines.push('   [含示意图]')
    }
  }

  lines.push('')
  if (fault.is_published) {
    lines.push(`完整图文方案：${origin}/faults/${fault.id}`)
  } else {
    lines.push('（该方案尚未发布，配图请在系统内查看）')
  }

  return lines.join('\n')
}
```

- [ ] **Step 4: 实现 clipboard**

```javascript
// frontend/src/utils/clipboard.js
export async function copyText(text) {
  if (!text) return false

  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // 继续走 textarea 兜底：HTTP 内网或权限被拒时 Clipboard API 会抛错
  }

  try {
    const area = document.createElement('textarea')
    area.value = text
    area.setAttribute('readonly', '')
    area.style.position = 'fixed'
    area.style.top = '-1000px'
    area.style.opacity = '0'
    document.body.appendChild(area)
    area.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(area)
    return ok
  } catch {
    return false
  }
}
```

- [ ] **Step 5: 运行测试**

Run: `cd frontend && NODE_OPTIONS=--no-experimental-webstorage npx vitest run src/utils/faultCopy.spec.js src/utils/clipboard.spec.js`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add frontend/src/utils/faultCopy.js frontend/src/utils/faultCopy.spec.js \
  frontend/src/utils/clipboard.js frontend/src/utils/clipboard.spec.js
git commit -m "feat(fault): 方案复制文本生成与剪贴板兜底"
```

---

## Task 3: 阅读抽屉

**Files:**
- Create: `frontend/src/views/admin/faults/FaultReaderDrawer.vue`
- Create: `frontend/src/views/admin/faults/FaultReaderDrawer.spec.js`

- [ ] **Step 1: 写失败测试**

```javascript
// frontend/src/views/admin/faults/FaultReaderDrawer.spec.js
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import FaultReaderDrawer from './FaultReaderDrawer.vue'
import { setPermissions } from '../../../utils/permissions'

vi.mock('../../../api/admin', () => ({
  adminGetFault: vi.fn()
}))
vi.mock('../../../utils/clipboard', () => ({
  copyText: vi.fn().mockResolvedValue(true)
}))

import { adminGetFault } from '../../../api/admin'
import { copyText } from '../../../utils/clipboard'

const DETAIL = {
  id: 21,
  title: '主刷不转',
  product_id: 1,
  product_name: '扫地机器人',
  part_id: 11,
  part_name: '主刷模组',
  symptom: '启动后主刷不转',
  root_cause: '毛发缠绕',
  required_tools: null,
  solution_steps: [{ step: 1, text: '拆下主刷', image_url: null }],
  attachment_urls: [],
  needs_professional: false,
  is_published: true,
  created_at: '2026-10-01T09:00:00+08:00',
  updated_at: '2026-10-05T09:00:00+08:00',
  view_count: 30,
  resolved_count: 20
}

async function mountDrawer(props = {}) {
  const wrapper = mount(FaultReaderDrawer, {
    props: { modelValue: true, faultId: 21, ...props },
    global: { plugins: [ElementPlus] },
    attachTo: document.body
  })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  vi.clearAllMocks()
  setPermissions(['fault:read', 'fault:write'])
  adminGetFault.mockResolvedValue(DETAIL)
  copyText.mockResolvedValue(true)
})

describe('FaultReaderDrawer', () => {
  it('打开时加载并渲染方案', async () => {
    const wrapper = await mountDrawer()

    expect(adminGetFault).toHaveBeenCalledWith(21)
    expect(wrapper.text()).toContain('主刷不转')
    expect(wrapper.text()).toContain('拆下主刷')
  })

  it('有 fault:write 时显示编辑入口', async () => {
    const wrapper = await mountDrawer()
    expect(wrapper.text()).toContain('编辑')
  })

  it('无 fault:write 时隐藏编辑入口', async () => {
    setPermissions(['fault:read'])
    const wrapper = await mountDrawer()
    expect(wrapper.text()).not.toContain('编辑')
  })

  it('只有已发布方案显示打开客户页', async () => {
    const published = await mountDrawer()
    expect(published.text()).toContain('打开客户页')

    adminGetFault.mockResolvedValue({ ...DETAIL, is_published: false })
    const draft = await mountDrawer()
    expect(draft.text()).not.toContain('打开客户页')
  })

  it('复制调用 copyText 并包含客户页链接', async () => {
    const wrapper = await mountDrawer()

    const button = wrapper.findAll('button').find((node) => node.text() === '复制方案文本')
    await button.trigger('click')
    await flushPromises()

    expect(copyText).toHaveBeenCalledTimes(1)
    expect(copyText.mock.calls[0][0]).toContain('/faults/21')
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && NODE_OPTIONS=--no-experimental-webstorage npx vitest run src/views/admin/faults/FaultReaderDrawer.spec.js`
Expected: FAIL，组件不存在

- [ ] **Step 3: 实现抽屉**

```vue
<!-- frontend/src/views/admin/faults/FaultReaderDrawer.vue -->
<template>
  <el-drawer
    v-model="visible"
    title="方案详情"
    :size="isNarrow ? '100%' : '720px'"
    destroy-on-close
  >
    <el-skeleton v-if="loading" :rows="8" animated />

    <ErrorState v-else-if="error" :error="error" @retry="load" />

    <FaultSolutionView v-else-if="detail" :fault="detail" show-stats show-status />

    <template #footer>
      <div class="footer">
        <el-button v-if="canWrite" @click="onEdit">编辑</el-button>
        <el-button type="primary" :disabled="!detail" @click="onCopy">复制方案文本</el-button>
        <el-button v-if="detail?.is_published" @click="openCustomerPage">打开客户页</el-button>
        <el-button @click="visible = false">关闭</el-button>
      </div>
    </template>
  </el-drawer>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { adminGetFault } from '../../../api/admin'
import ErrorState from '../../../components/ErrorState.vue'
import FaultSolutionView from '../../../components/FaultSolutionView.vue'
import { errorText } from '../../../utils/admin'
import { copyText } from '../../../utils/clipboard'
import { buildFaultCopyText } from '../../../utils/faultCopy'
import { hasPermission } from '../../../utils/permissions'
import { useNarrow } from '../../../utils/viewport'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  faultId: { type: Number, default: null }
})
const emit = defineEmits(['update:modelValue', 'edit'])

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
})

const isNarrow = useNarrow()
const canWrite = computed(() => hasPermission('fault:write'))

const detail = ref(null)
const loading = ref(false)
const error = ref('')

async function load() {
  if (!props.faultId) return
  loading.value = true
  error.value = ''
  detail.value = null
  try {
    detail.value = await adminGetFault(props.faultId)
  } catch (e) {
    error.value = errorText(e, '方案加载失败')
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.modelValue, props.faultId],
  ([opened]) => {
    if (opened) load()
  },
  { immediate: true }
)

function onEdit() {
  emit('edit', detail.value.id)
  visible.value = false
}

async function onCopy() {
  const ok = await copyText(buildFaultCopyText(detail.value))
  if (ok) ElMessage.success('已复制，可直接粘贴给客户')
  else ElMessage.error('复制失败，请手动选择文本')
}

function openCustomerPage() {
  window.open(`/faults/${detail.value.id}`, '_blank', 'noopener,noreferrer')
}
</script>

<style scoped>
.footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
```

- [ ] **Step 4: 运行测试**

Run: `cd frontend && NODE_OPTIONS=--no-experimental-webstorage npx vitest run src/views/admin/faults/FaultReaderDrawer.spec.js`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/admin/faults/FaultReaderDrawer.vue \
  frontend/src/views/admin/faults/FaultReaderDrawer.spec.js
git commit -m "feat(fault): 故障方案阅读抽屉"
```

---

## Task 4: 列表接入抽屉

**Files:**
- Modify: `frontend/src/views/admin/faults/FaultList.vue`
- Modify: `frontend/src/views/admin/faults/FaultList.spec.js`

- [ ] **Step 1: 更新测试**

在 `FaultList.spec.js`：

1. `vi.mock('../../../api/admin')` 工厂与 import 列表加入 `adminGetFault`，默认返回 `FAULTS[0]` 的完整详情（补 `root_cause: '毛发缠绕'`、`solution_steps: [{ step: 1, text: '拆下主刷', image_url: null }]`、`attachment_urls: []`）。
2. 把现有用例：

```javascript
  it('仅有 fault:read 时行点击也能打开故障详情（客服场景）', async () => {
    setPermissions(['fault:read'])
    const { wrapper, router } = await mountList()

    await wrapper.findAll('.el-table__row')[0].trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('admin-fault-edit')
    expect(router.currentRoute.value.params.id).toBe('21')
  })
```

改为：

```javascript
  it('仅有 fault:read 时行点击打开阅读抽屉（客服场景）', async () => {
    setPermissions(['fault:read'])
    const { wrapper, router } = await mountList()

    await wrapper.findAll('.el-table__row')[0].trigger('click')
    await flushPromises()

    expect(adminGetFault).toHaveBeenCalledWith(21)
    // el-drawer 会 teleport 到 body，不能只看 wrapper.text()
    expect(document.body.textContent).toContain('主刷不转')
    expect(router.currentRoute.value.name).toBe('admin-faults')
  })
```

3. 新增一条用例，确认行内「编辑」按钮仍进编辑页：

```javascript
  it('行内编辑按钮仍进入编辑页', async () => {
    const { wrapper, router } = await mountList()

    const editButton = wrapper.findAll('button').find((node) => node.text() === '编辑')
    await editButton.trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('admin-fault-edit')
    expect(router.currentRoute.value.params.id).toBe('21')
  })
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && NODE_OPTIONS=--no-experimental-webstorage npx vitest run src/views/admin/faults/FaultList.spec.js`
Expected: FAIL，行点击仍跳编辑页 / 未调用 adminGetFault

- [ ] **Step 3: 修改 FaultList**

模板在分页之后、`</el-card>` 之前加入：

```vue
      <FaultReaderDrawer v-model="readerVisible" :fault-id="readerId" @edit="goEditById" />
```

（放在 `</el-card>` 之后、外层 `</div>` 之前也可以，保证只渲染一次。）

`<script setup>`：

```javascript
import FaultReaderDrawer from './FaultReaderDrawer.vue'

const readerVisible = ref(false)
const readerId = ref(null)

function onRowClick(row) {
  if (!canOpen.value) return
  readerId.value = row.id
  readerVisible.value = true
}

function goEditById(id) {
  router.push({ name: 'admin-fault-edit', params: { id } })
}
```

`goEdit(row)` 保持不变，行内「编辑」按钮继续走它。

- [ ] **Step 4: 运行测试**

Run:
```bash
cd frontend && NODE_OPTIONS=--no-experimental-webstorage npx vitest run \
  src/views/admin/faults/FaultList.spec.js src/views/admin/faults/FaultReaderDrawer.spec.js
```
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/admin/faults/FaultList.vue \
  frontend/src/views/admin/faults/FaultList.spec.js
git commit -m "feat(fault): 列表行点击改为打开阅读抽屉"
```

---

## Task 5: 文档同步与全量验证

**Files:**
- Modify: `docs/01-需求设计/页面清单与交互说明.md`
- Modify: `docs/03-测试与验收/测试用例清单.md`
- Modify: `docs/03-测试与验收/验收检查表.md`

- [ ] **Step 1: 同步页面清单**

P-15 故障知识库：
- 行点击行为由「进入编辑页」改为「打开阅读抽屉」
- 抽屉内容按设计稿 §3：标题、状态标签、元信息、风险提示、现象/原因/工具、分步图文、附件、创建时间
- 底部操作：编辑（`fault:write`）、复制方案文本、打开客户页（仅已发布）、关闭
- 复制文本规则：已发布附 `/faults/{id}` 链接；未发布附提示；图片步骤标注 `[含示意图]`
- P-16 编辑页仍由行内「编辑」按钮或抽屉「编辑」进入

- [ ] **Step 2: 同步测试用例与验收表**

测试用例清单新增：
- TC-97 任意角色点故障行打开阅读抽屉，不进入编辑页
- TC-98 抽屉按权限显示编辑入口
- TC-99 已发布方案复制文本含客户页链接，未发布不含
- TC-100 图片步骤复制时标注 `[含示意图]`
- TC-101 HTTP 内网下复制按钮可用（兜底）

验收检查表新增：设计稿 §9 的 7 条验收标准。

- [ ] **Step 3: 全量验证**

Run:
```bash
cd frontend && NODE_OPTIONS=--no-experimental-webstorage npx vitest run && npm run lint && npm run build
python scripts/dev/check_links.py
```
Expected: 前端全部 PASS、lint 0 error、build 成功、链接 0 失效

- [ ] **Step 4: 提交**

```bash
git add docs
git commit -m "docs(fault): 阅读抽屉交互、测试用例与验收项"
```

---

## 自查记录

- **Spec 覆盖**：行点击抽屉（T4）、抽屉内容（T1/T3）、复制格式与链接规则（T2）、HTTP 剪贴板兜底（T2）、编辑入口（T3/T4）、窄屏（T3）、文档（T5）。
- **类型一致性**：`FaultSolutionView` 的 props 为 `fault/showStats/showStatus`；`FaultReaderDrawer` 的 props 为 `modelValue/faultId`，事件 `update:modelValue/edit`；`buildFaultCopyText(fault, origin)` 与 `copyText(text)` 签名在测试与实现中一致。
- **无后端改动**：全部复用 `GET /api/admin/faults/{id}`。
