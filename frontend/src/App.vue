<template>
  <el-config-provider :locale="elLocale">
    <router-view />
  </el-config-provider>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import en from 'element-plus/es/locale/lang/en'

// Element Plus 内置文案（日期选择器、分页、表格空态、下拉无匹配）
// 必须跟着应用语言走，否则英文界面里会冒出中文的"暂无数据""至"
const { locale } = useI18n()
const elLocale = computed(() => (locale.value === 'en-US' ? en : zhCn))
</script>
