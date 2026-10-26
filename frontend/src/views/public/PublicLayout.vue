<template>
  <div class="public-layout">
    <header class="header">
      <router-link :to="homePath" class="brand">{{ $t('public.brand') }}</router-link>
      <div class="header-right">
        <!-- 切换语言 = 换一个 URL 前缀，页面位置和查询参数都保留。
             按钮上写**目标语言**，后面跟地球图标兜底：
             只写"English"时，语言名完全没见过的人认不出这是语言入口 -->
        <button
          type="button"
          class="lang-switch"
          :aria-label="$t('common.language.switchTo', { name: otherLocaleLabel })"
          @click="toggleLocale"
        >
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
          <span>{{ otherLocaleLabel }}</span>
        </button>
        <router-link to="/admin/login" class="admin-link">{{ $t('public.adminEntry') }}</router-link>
      </div>
    </header>

    <main class="main">
      <router-view />
    </main>

    <footer class="footer">{{ $t('public.footer') }}</footer>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { currentLocale, setLocale } from '../../locales'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const homePath = computed(() => (currentLocale() === 'en-US' ? '/en' : '/'))
// 按钮上显示"另一种语言"，点它就切过去——比显示当前语言更符合用户的预期
const otherLocaleLabel = computed(() =>
  currentLocale() === 'en-US' ? t('common.language.zhCN') : t('common.language.enUS')
)

function toggleLocale() {
  const isEn = currentLocale() === 'en-US'
  // 显式切换要记住：用户选了英文，进后台也该是英文。
  // 路由守卫里的 setLocale 传 persist:false（URL 才是客户侧的权威），
  // 但"用户主动点过"这件事本身是明确的偏好，值得持久化。
  setLocale(isEn ? 'zh-CN' : 'en-US', { persist: true })

  // 用 fullPath 而不是 path：查询参数要保留（如方案页的 q、工单页的上下文 id）
  const rest = isEn ? route.fullPath.replace(/^\/en/, '') : route.fullPath
  const target = isEn
    ? rest.startsWith('/')
      ? rest
      : `/${rest}`
    : rest === '/'
      ? '/en'
      : `/en${rest}`
  router.replace(target || '/')
}
</script>

<style scoped>
.public-layout {
  display: flex;
  flex-direction: column;
  min-height: 100%;
  background: var(--app-bg);
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 0 20px;
  /* 顶部加安全区：iOS 横屏时刘海会盖住标题 */
  padding-top: var(--safe-top);
  height: 56px;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
}

.brand {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
  text-decoration: none;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

/* 用原生 button 而不是 el-button：这里只需要一个轻量文字入口，
   并且要能在窄屏上撑到 44px 命中区 */
.lang-switch {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: none;
  background: none;
  padding: 0;
  font: inherit;
  font-size: 13px;
  color: #909399;
  cursor: pointer;
}

.globe {
  width: 14px;
  height: 14px;
  flex: none;
}

.lang-switch:hover {
  color: #409eff;
}

.admin-link {
  font-size: 13px;
  color: #909399;
  text-decoration: none;
}

.main {
  flex: 1;
  width: 100%;
  max-width: 960px;
  margin: 0 auto;
  padding: 24px 16px 40px;
  padding-left: calc(16px + var(--safe-left));
  padding-right: calc(16px + var(--safe-right));
}

.footer {
  padding: 16px;
  /* 底部补安全区，否则 iPhone 的横条会盖住最后一行文字 */
  padding-bottom: calc(16px + var(--safe-bottom));
  color: #a8abb2;
  font-size: 12px;
  text-align: center;
}

/* ---------- 手机 ---------- */
@media (max-width: 640px) {
  .header {
    padding-left: calc(16px + var(--safe-left));
    padding-right: calc(16px + var(--safe-right));
  }

  /* 标题是 16px/600，行高约 22px，撑不到 44px；用 padding 补足命中高度，
     负 margin 抵消视觉位移，让标题看起来还在原来的位置 */
  .brand {
    padding: 11px 0;
    margin: -11px 0;
  }

  /* 后台入口是低频操作，但仍需可点。13px 文字纵向加 padding 到 44px 命中区 */
  .admin-link {
    display: inline-flex;
    align-items: center;
    min-height: var(--tap-min);
    padding-left: 8px;
    margin-right: -8px;
  }

  /* 语言切换同样要够 44px，否则手机上很难点中 */
  .header-right {
    gap: 10px;
  }

  .lang-switch {
    display: inline-flex;
    align-items: center;
    min-height: var(--tap-min);
    padding-right: 6px;
  }

  .main {
    padding-top: 16px;
    padding-bottom: 32px;
  }

  .footer {
    padding-left: calc(16px + var(--safe-left));
    padding-right: calc(16px + var(--safe-right));
    padding-bottom: calc(20px + var(--safe-bottom));
    line-height: 1.6;
  }
}
</style>
