<template>
  <!-- 规范 §Vue 3 风格：列表/详情需实现三态（加载中 / 空态 / 错误态可重试）。
       抽成组件是为了四个列表页与抽屉共用同一套交互与文案，不必各写一遍 -->
  <div v-if="error" class="state">
    <el-result icon="error" title="加载失败" :sub-title="error">
      <template #extra>
        <el-button type="primary" @click="$emit('retry')">重新加载</el-button>
      </template>
    </el-result>
  </div>
</template>

<script setup>
defineProps({
  error: { type: String, default: '' }
})
defineEmits(['retry'])
</script>

<style scoped>
.state {
  padding: 8px 0;
}
</style>
