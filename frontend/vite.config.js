import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

export default defineConfig({
  plugins: [
    vue(),
    // 按需引入：模板里的 el-* 组件与 JS 里的 ElMessage 等只打进用到的部分。
    // 全量 CSS 仍在 main.js 引入（gzip 后很小），样式不必逐个注入。
    AutoImport({ resolvers: [ElementPlusResolver({ importStyle: false })] }),
    Components({ resolvers: [ElementPlusResolver({ importStyle: false })] })
  ],
  server: {
    port: 5173,
    // 本地开发直连后端，生产由 Nginx 同源反代（不需要 CORS）
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      // 上传返回的是站内路径 /uploads/xxx，生产由 Nginx alias 直出；
      // 开发环境不代理的话会落到 SPA 回退返回 index.html，图片和附件全部裂开
      '/uploads': { target: 'http://localhost:8000', changeOrigin: true }
    }
  },
  preview: {
    port: 4173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/uploads': { target: 'http://localhost:8000', changeOrigin: true }
    }
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    rollupOptions: {
      output: {
        // 只固定 vue 核心；element-plus 已按需引入，写死 manualChunks 反而
        // 会把全量入口拖进一个 chunk（938kB），让按需引入完全失效
        manualChunks: {
          vue: ['vue', 'vue-router']
        }
      }
    }
  },
  test: {
    environment: 'happy-dom',
    setupFiles: ['./src/test-setup.js'],
    include: ['src/**/*.spec.js'],
    // Element Plus 的样式在测试里没有意义，跳过以加速
    css: false,
    // element-plus 被 SSR 外置时其 CJS 依赖（async-validator）interop 出错：
    // new AsyncValidator() 抛 TypeError，校验错误对象丢 fields → 表单校验被静默跳过。
    // 内联进转换管线后与浏览器构建走同一套 ESM 代码。
    server: {
      deps: {
        inline: [/element-plus/]
      }
    }
  }
})
