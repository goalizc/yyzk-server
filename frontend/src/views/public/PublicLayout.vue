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
  padding: 0 20px;
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
}

.footer {
  padding: 16px;
  color: #a8abb2;
  font-size: 12px;
  text-align: center;
}
</style>
