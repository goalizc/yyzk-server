<template>
  <div class="public-layout">
    <header class="header">
      <router-link to="/" class="brand">售后自助故障诊断</router-link>
      <router-link to="/admin/login" class="admin-link">后台入口</router-link>
    </header>

    <main class="main">
      <router-view />
    </main>

    <footer class="footer">遇到问题请先按方案排查；仍无法解决可提交工单，我们会尽快联系您。</footer>
  </div>
</template>

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
