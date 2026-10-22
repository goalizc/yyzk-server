import { createRouter, createWebHistory } from 'vue-router'
import { fetchMe } from '../api/auth'
import { clearPermissions, hasPermission, setPermissions } from '../utils/permissions'

const routes = [
  {
    // 客户侧：无需登录
    path: '/',
    component: () => import('../views/public/PublicLayout.vue'),
    meta: { public: true },
    children: [
      {
        path: '',
        name: 'home',
        component: () => import('../views/public/Home.vue')
      },
      {
        path: 'faults/:id',
        name: 'fault-detail',
        component: () => import('../views/public/FaultDetail.vue')
      },
      {
        path: 'tickets/new',
        name: 'ticket-new',
        component: () => import('../views/public/TicketNew.vue')
      },
      {
        path: 'tickets/success',
        name: 'ticket-success',
        component: () => import('../views/public/TicketSuccess.vue')
      }
    ]
  },
  {
    path: '/admin/login',
    name: 'login',
    component: () => import('../views/admin/Login.vue'),
    meta: { public: true }
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
        meta: { title: '工单管理', permission: 'ticket:read' }
      },
      {
        path: 'products',
        name: 'admin-products',
        component: () => import('../views/admin/products/ProductList.vue'),
        meta: { title: '产品管理', permission: 'product:read' }
      },
      {
        path: 'product-lines',
        name: 'admin-product-lines',
        component: () => import('../views/admin/product-lines/ProductLineList.vue'),
        meta: { title: '产品线管理', permission: 'product_line:read' }
      },
      {
        path: 'parts',
        name: 'admin-parts',
        component: () => import('../views/admin/parts/PartList.vue'),
        meta: { title: '零件管理', permission: 'part:read' }
      },
      {
        path: 'faults',
        name: 'admin-faults',
        component: () => import('../views/admin/faults/FaultList.vue'),
        meta: { title: '故障知识库', permission: 'fault:read' }
      },
      {
        // id 可选：不带 id 即新建（P-16 的路由约定 /admin/faults/edit/:id?）
        path: 'faults/edit/:id?',
        name: 'admin-fault-edit',
        component: () => import('../views/admin/faults/FaultEdit.vue'),
        meta: { title: '故障编辑', permission: 'fault:read', requires: ['product:read', 'part:read'] }
      },
      {
        path: 'stats',
        name: 'admin-stats',
        component: () => import('../views/admin/stats/StatsDashboard.vue'),
        meta: { title: '数据看板', permission: 'stats:read' }
      },
      {
        path: 'users',
        name: 'admin-users',
        component: () => import('../views/admin/users/UserList.vue'),
        meta: { title: '用户管理', permission: 'user:read' }
      }
    ]
  },
  {
    // 兜底：未匹配路径不再白屏
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('../views/NotFound.vue'),
    meta: { public: true }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach(async (to) => {
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
