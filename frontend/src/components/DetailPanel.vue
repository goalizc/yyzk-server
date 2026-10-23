<!--
  详情面板容器：统一「从列表点开一条记录看详情」的呈现形态。

  为什么是居中弹窗而不是右侧抽屉：
  列表里用户是在表格中部点击某一行，触点在屏幕中偏左，而右侧抽屉把结果丢到
  屏幕最右边，视线每次都要横跨半屏。居中弹窗让内容出现在视线原本的位置。

  业务组件只管提供 title + 内容 +（可选）footer，不要自己写 el-drawer/el-dialog，
  形态要换时只改这一个文件。
-->
<template>
  <el-dialog
    :model-value="modelValue"
    :title="title"
    :width="dialogWidth"
    :destroy-on-close="destroyOnClose"
    :close-on-click-modal="closeOnClickModal"
    align-center
    class="detail-panel"
    data-testid="detail-panel"
    @update:model-value="(value) => emit('update:modelValue', value)"
    @open="emit('open')"
    @closed="emit('closed')"
  >
    <div class="detail-panel__body" :class="{ 'has-footer': Boolean($slots.footer) }">
      <slot />
    </div>

    <!-- 没有传 footer 就不渲染，避免 el-dialog 冒出一条空的底部栏 -->
    <template v-if="$slots.footer" #footer>
      <slot name="footer" />
    </template>
  </el-dialog>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: '' },
  // 宽屏下的期望宽度；窄屏靠 CSS 的 min() 自动收缩，不需要再写断点
  size: { type: Number, default: 880 },
  destroyOnClose: { type: Boolean, default: false },
  // 详情里常有正在填的表单，误点遮罩就丢内容，默认不允许点外面关闭
  closeOnClickModal: { type: Boolean, default: false }
})

const emit = defineEmits(['update:modelValue', 'open', 'closed'])

// 用 CSS min() 而不是 JS 断点：宽度随视口连续变化，不用监听 resize，
// 也不会在 768px 附近跳变。92vw 保证手机上有左右留白。
const dialogWidth = computed(() => `min(${props.size}px, 92vw)`)
</script>

<style scoped>
/* 内容区自己滚，弹窗整体高度就不会被长内容撑出视口。
   有 footer 时少留一截高度给底部按钮栏。 */
.detail-panel__body {
  max-height: calc(100vh - 260px);
  overflow-y: auto;
  overflow-x: hidden;
  padding-right: 4px;
}

.detail-panel__body.has-footer {
  max-height: calc(100vh - 330px);
}

/* 窄屏：上下留白变紧，内容区可以再高一点 */
@media (max-width: 768px) {
  .detail-panel__body {
    max-height: calc(100vh - 210px);
  }

  .detail-panel__body.has-footer {
    max-height: calc(100vh - 270px);
  }
}
</style>
