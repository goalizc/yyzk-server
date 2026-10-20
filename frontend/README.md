# frontend

Vue 3 + Vite + Element Plus 前端。**当前为空，待 S0 任务产出。**

## 计划结构

依据 `docs/02-技术设计/系统架构设计.md` §4：

```
frontend/
├── src/
│   ├── main.js
│   ├── App.vue
│   ├── router/index.js       # 路由守卫：/admin/* 需 token
│   ├── api/                  # request.js（axios 实例 + 401 分支）
│   ├── views/
│   │   ├── public/           # Home / FaultDetail / TicketNew / TicketSuccess
│   │   └── admin/            # Login / Layout / Tickets / Products / Parts / Faults / FaultEdit / Stats
│   ├── components/
│   └── utils/format.js       # 时间与百分比统一格式化
├── Dockerfile                # 多阶段：node build → nginx serve
├── nginx.conf                # 复制自 deploy/frontend-nginx.conf（SPA 回退）
├── package.json
└── vite.config.js
```

## 本地运行

```bash
npm install
npm run dev        # 5173，需 vite proxy 到 localhost:8000
npm run build      # 产物 dist/
```

## 约定

- 禁止 `v-html` 渲染故障内容与工单描述（XSS）
- 列表/详情必须实现三态：加载骨架、空态（带引导）、错误态（可重试）
- 详情页保存 `query_log_id`，反馈时回传
- 见 `docs/02-技术设计/代码与目录规范.md` §3

## 待办（S0）

- [ ] Vite 脚手架 + Element Plus + 路由（12 个页面占位）
- [ ] `api/request.js`：baseURL `/api`、token 注入、401 按 `code` 分支
- [ ] 登录页 + 路由守卫
- [ ] Dockerfile（node:22-alpine 构建 → nginx:1.25-alpine 运行）
