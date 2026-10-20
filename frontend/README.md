# frontend

Vue 3 + Vite + Element Plus 前端。当前处于 **S0**：脚手架 + 登录页 + 路由守卫已可运行，
12 个业务页面（客户侧 4 + 后台 8）待后续阶段（WBS C-02 起）。

## 已实现

| 能力 | 位置 |
|---|---|
| Vite + Vue 3 + Element Plus（中文语言包） | `src/main.js`、`vite.config.js` |
| axios 实例：`baseURL=/api`、注入 token | `src/api/request.js` |
| 401 分支：**仅** `code === "AUTH_TOKEN_EXPIRED"` 清 token 跳登录 | `src/api/request.js` |
| 登录页（登录失败在表单内提示，不闪回登录页） | `src/views/admin/Login.vue` |
| 后台骨架：顶栏 + 修改密码 + 退出登录 | `src/views/admin/Layout.vue` |
| 路由守卫：`/admin/*` 无 token 跳登录 | `src/router/index.js` |

## 本地运行

```bash
npm install
npm run dev        # 5173，/api 已代理到 localhost:8000
npm run build      # 产物 dist/
```

后端需先起在 8000（见 `backend/README.md`）。

## 目录

```
frontend/
├── src/
│   ├── main.js / App.vue
│   ├── router/index.js
│   ├── api/            # request.js（拦截器）、auth.js
│   ├── views/admin/    # Login / Layout / Home（其余页面待补）
│   └── assets/main.css
├── index.html
├── vite.config.js
└── Dockerfile          # node:22-alpine 构建 → nginx:1.25-alpine 运行
```

## 镜像

多阶段构建（node:22-alpine → nginx:1.25-alpine），SPA 回退配置直接复用
`deploy/frontend-nginx.conf`。构建源由 build args 传入（默认 npmmirror），
可用 `deploy/.env` 的 `NPM_REGISTRY` 覆盖。

## 约定

- 禁止 `v-html` 渲染故障内容与工单描述（XSS）
- 列表与详情三态：加载骨架、空态（带引导）、错误态（可重试）
- 详情页保存 `query_log_id`，反馈时回传
- 时间与百分比统一走 `src/utils/format.js`（待补）

## 待办

- [ ] C-02 客户查询页三级级联、C-03 方案详情、C-04 工单提交
- [ ] 后台产品/零件/故障/工单/看板页面
- [ ] `utils/format.js` 统一时间与百分比格式化
