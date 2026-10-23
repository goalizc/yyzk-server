import { createApp } from 'vue'
import 'element-plus/dist/index.css'

import App from './App.vue'
import router from './router'
import { i18n } from './locales'
import './assets/main.css'

// 组件与 ElMessage 等由 unplugin 按需引入（见 vite.config.js），
// 中文语言包在 App.vue 的 el-config-provider 上全局生效。
const app = createApp(App)

// i18n 先于 router 安装：router 的守卫里会调 setLocale，
// 此时 i18n.global 必须已经可用
app.use(i18n)
app.use(router)
app.mount('#app')
