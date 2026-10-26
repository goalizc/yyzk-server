import { createRouter, createWebHistory } from 'vue-router'
import { fetchMe } from '../api/auth'
import { clearPermissions, hasPermission, setPermissions } from '../utils/permissions'
import { DEFAULT_LOCALE, localeFromPath, setLocale } from '../locales'
import { applyPageTitle } from '../utils/pageTitle'

const routes = [
  {
    // 客户侧：无需登录。
    // :locale(en)? 只匹配字面量 en，不会把 /admin 当成语言段；
    // 无前缀 = 默认语言（中文），保证既有链接与已发出的工单短信不失效。
    path: '/:locale(en)?',
    component: () => import('../views/public/PublicLayout.vue'),
    meta: { public: true },
    children: [
      {
        path: '',
        name: 'home',
        component: () => import('../views/public/Home.vue')
        // 首页标题直接用 common.appName，不需要 titleKey
      },
      {
        path: 'faults/:id',
        name: 'fault-detail',
        component: () => import('../views/public/FaultDetail.vue'),
        meta: { titleKey: 'public.faultDetail.pageTitle' }
      },
      {
        path: 'tickets/new',
        name: 'ticket-new',
        component: () => import('../views/public/TicketNew.vue'),
        meta: { titleKey: 'public.ticketNew.pageTitle' }
      },
      {
        path: 'tickets/success',
        name: 'ticket-success',
        component: () => import('../views/public/TicketSuccess.vue'),
        meta: { titleKey: 'public.ticketSuccess.title' }
      }
    ]
  },
  {
    path: '/admin/login',
    name: 'login',
    component: () => import('../views/admin/Login.vue'),
    meta: { public: true, titleKey: 'admin.page.login' }
  },
  {
    path: '/admin',
    component: () => import('../views/admin/Layout.vue'),
    redirect: '/admin/tickets',
    children: [
      {
        path: 'tickets',
        name: 'admin-tickets',
        component: () => import('../views/admin/tickets/TicketList.vue'),
        // title 保留中文原值（旧测试与外部引用可能读它），titleKey 供界面取词
        meta: { titleKey: 'admin.page.tickets', permission: 'ticket:read' }
      },
      {
        path: 'products',
        name: 'admin-products',
        component: () => import('../views/admin/products/ProductList.vue'),
        meta: { titleKey: 'admin.page.products', permission: 'product:read' }
      },
      {
        path: 'product-lines',
        name: 'admin-product-lines',
        component: () => import('../views/admin/product-lines/ProductLineList.vue'),
        meta: { titleKey: 'admin.page.productLines', permission: 'product_line:read' }
      },
      {
        path: 'parts',
        name: 'admin-parts',
        component: () => import('../views/admin/parts/PartList.vue'),
        meta: { titleKey: 'admin.page.parts', permission: 'part:read' }
      },
      {
        path: 'faults',
        name: 'admin-faults',
        component: () => import('../views/admin/faults/FaultList.vue'),
        meta: { titleKey: 'admin.page.faults', permission: 'fault:read' }
      },
      {
        // id 可选：不带 id 即新建（P-16 的路由约定 /admin/faults/edit/:id?）
        path: 'faults/edit/:id?',
        name: 'admin-fault-edit',
        component: () => import('../views/admin/faults/FaultEdit.vue'),
        meta: { titleKey: 'admin.page.faultEdit', permission: 'fault:read' }
      },
      {
        path: 'stats',
        name: 'admin-stats',
        component: () => import('../views/admin/stats/StatsDashboard.vue'),
        meta: { titleKey: 'admin.page.stats', permission: 'stats:read' }
      },
      {
        path: 'users',
        name: 'admin-users',
        component: () => import('../views/admin/users/UserList.vue'),
        meta: { titleKey: 'admin.page.users', permission: 'user:read' }
      },
      {
        path: 'audit-logs',
        name: 'admin-audit-logs',
        component: () => import('../views/admin/audit/AuditLogList.vue'),
        meta: { titleKey: 'admin.page.auditLogs', permission: 'audit:read' }
      }
    ]
  },
  {
    // 兜底：未匹配路径不再白屏
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('../views/NotFound.vue'),
    meta: { public: true, titleKey: 'common.notFound.title' }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach(async (to) => {
  // 语言同步：客户侧 URL 是权威（带前缀=英文，无前缀=中文）；
  // 后台没有前缀，保持本地偏好，不动。
  if (to.path.startsWith('/admin')) {
    // 后台沿用启动时从 localStorage 解析出的语言，不做切换
  } else {
    const prefixed = localeFromPath(to.path)
    // persist=false：客户侧语言由 URL 承载，写 localStorage 会污染后台偏好
    setLocale(prefixed || DEFAULT_LOCALE, { persist: false })
  }

  // 客户侧与登录页公开
  if (to.meta.public) return true
  if (!localStorage.getItem('token')) {
    return { path: '/admin/login', query: { redirect: to.fullPath } }
  }

  // 老会话只存了 token（此前的版本不落权限），首次进入先拉一次 /auth/me
  if (!localStorage.getItem('permissions')) {
    try {
      const data = await fetchMe()
      setPermissions(data.permissions)
    } catch {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      clearPermissions()
      return { path: '/admin/login', query: { redirect: to.fullPath } }
    }
  }

  if (to.meta.permission && !hasPermission(to.meta.permission)) {
    return { path: '/admin/faults' }
  }
  if (to.meta.requires && !to.meta.requires.every(hasPermission)) {
    return { path: '/admin/faults' }
  }
  return true
})

export default router

// 标签页标题：按 meta.titleKey 取词。语言切换不换路由，afterEach 不会跑，
// 那条路径由 Layout / PublicLayout 在切换后自行调 applyPageTitle。
router.afterEach((to) => {
  applyPageTitle(to.meta)
})
