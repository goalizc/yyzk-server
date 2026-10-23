<template>
  <div class="not-found">
    <el-result
      icon="warning"
      :title="$t('common.notFound.title')"
      :sub-title="$t('common.notFound.subtitle')"
    >
      <template #extra>
        <el-button type="primary" @click="goHome">{{ $t('common.notFound.backHome') }}</el-button>
      </template>
    </el-result>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { currentLocale } from '../locales'

const router = useRouter()

function goHome() {
  // 404 页在客户侧也会命中：英文用户点"返回首页"不该被丢回中文首页
  router.replace(currentLocale() === 'en-US' ? '/en' : '/')
}
</script>

<style scoped>
.not-found {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100%;
  padding: 48px 16px;
}
</style>
