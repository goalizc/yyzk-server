import { createRouter, createWebHistory } from 'vue-router'

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
    children: [
      {
        path: '',
        name: 'admin-home',
        component: () => import('../views/admin/Home.vue')
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

router.beforeEach((to) => {
  // 客户侧与登录页公开；其余后台页面需要 token
  if (to.meta.public) return true
  if (!localStorage.getItem('token')) {
    return { path: '/admin/login', query: { redirect: to.fullPath } }
  }
  return true
})

export default router
