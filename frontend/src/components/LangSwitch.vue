<template>
  <button type="button" class="lang-switch" :title="tip" :aria-label="tip" @click="toggle">
    <svg
      class="globe"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="1.8"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18" />
      <path d="M12 3.2c2.4 2.4 3.8 5.5 3.8 8.8s-1.4 6.4-3.8 8.8c-2.4-2.4-3.8-5.5-3.8-8.8S9.6 5.6 12 3.2z" />
    </svg>
    <span class="label">{{ targetLabel }}</span>
  </button>
</template>

<script setup>
/*
 * 语言切换入口（后台顶栏）。
 *
 * 按钮上显示的是**目标语言**（中文界面显示 English，英文界面显示 简体中文），
 * 不是当前语言 —— 中文界面下一个英文母语者看不到任何英文线索，
 * 根本认不出这里是切换入口。地球图标兜底：连目标语言名都不认识的
 * 第三国用户也能凭图标想到"语言"。
 * 相关设计：docs/02-技术设计/国际化设计.md §语言入口
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { setLocale } from '../locales'
import { applyPageTitle } from '../utils/pageTitle'

const route = useRoute()
// locale 是 i18n 的 ref：切换后 computed 会重算，不能用 currentLocale()（读的是快照）
const { t, locale } = useI18n()

const isEn = computed(() => locale.value === 'en-US')

// 语言名用**本族语**书写（English / 简体中文），不翻译：给不懂当前界面语言的人看
const targetLabel = computed(() => (isEn.value ? t('common.language.zhCN') : t('common.language.enUS')))
const tip = computed(() => t('common.language.switchTo', { name: targetLabel.value }))

function toggle() {
  setLocale(isEn.value ? 'zh-CN' : 'en-US', { persist: true })
  // 切语言不换路由，afterEach 不触发，标签页标题要手动补一次
  applyPageTitle(route.meta)
}
</script>

<style scoped>
.lang-switch {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0;
  border: 0;
  background: none;
  color: var(--el-color-primary);
  font-family: inherit;
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
}

.lang-switch:hover {
  opacity: 0.75;
}

.lang-switch:focus-visible {
  outline: 2px solid var(--el-color-primary);
  outline-offset: 2px;
  border-radius: 2px;
}

.globe {
  width: 15px;
  height: 15px;
  flex: none;
}

/* 窄屏：顶栏放不下"图标 + 语言名"（还要挤修改密码/退出登录），
   文字收起来只留地球图标；读屏与悬停仍能从 aria-label / title 得到说明 */
@media (max-width: 768px) {
  .lang-switch {
    min-height: var(--tap-min, 44px);
    min-width: var(--tap-min, 44px);
    justify-content: center;
  }

  .label {
    display: none;
  }

  .globe {
    width: 18px;
    height: 18px;
  }
}
</style>
