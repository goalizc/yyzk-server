import { createApp } from 'vue'
import 'element-plus/dist/index.css'

import App from './App.vue'
import router from './router'
import './assets/main.css'

// 组件与 ElMessage 等由 unplugin 按需引入（见 vite.config.js），
// 中文语言包在 App.vue 的 el-config-provider 上全局生效。
const app = createApp(App)

app.use(router)
app.mount('#app')
