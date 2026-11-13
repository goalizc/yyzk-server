import { createRouter, createWebHistory } from 'vue-router'
import { fetchMe } from '../api/auth'
import { hasPermission, setPermissions } from '../utils/permissions'
import { hasValidToken, clearAuthLocal } from '../utils/session'
import { isIdleExpired } from '../utils/idle'
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
    // 不写死默认 redirect：登录落地由守卫按角色权限动态决定
    // （见 firstAccessibleAdminPath），避免无售后权限的角色陷入重定向死循环。
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
      // 进销存：独立内部台账，与售后业务不互通。路径统一带 inventory 前缀，
      // 每个页面挂自己的静态权限码（调整页用高危的 inventory:adjust:write）。
      {
        path: 'inventory/categories',
        name: 'admin-inventory-categories',
        component: () => import('../views/admin/inventory/CategoryList.vue'),
        // home:false —— 分类是 SKU 的从属主数据，虽然排在菜单第一项（先建分类再建物资），
        // 但不该成为仓管登录后的落地页：他的日常主战场是物资 SKU 列表。
        meta: { titleKey: 'admin.page.inventoryCategories', permission: 'inventory:sku:read', home: false }
      },
      {
        path: 'inventory/skus',
        name: 'admin-inventory-skus',
        component: () => import('../views/admin/inventory/SkuList.vue'),
        meta: { titleKey: 'admin.page.inventorySkus', permission: 'inventory:sku:read' }
      },
      {
        path: 'inventory/inbound',
        name: 'admin-inventory-inbound',
        component: () => import('../views/admin/inventory/InboundList.vue'),
        meta: { titleKey: 'admin.page.inventoryInbound', permission: 'inventory:inbound:read' }
      },
      {
        path: 'inventory/outbound',
        name: 'admin-inventory-outbound',
        component: () => import('../views/admin/inventory/OutboundList.vue'),
        meta: { titleKey: 'admin.page.inventoryOutbound', permission: 'inventory:outbound:read' }
      },
      {
        path: 'inventory/movements',
        name: 'admin-inventory-movements',
        component: () => import('../views/admin/inventory/MovementList.vue'),
        meta: { titleKey: 'admin.page.inventoryMovements', permission: 'inventory:movement:read' }
      },
      {
        path: 'inventory/adjustments',
        name: 'admin-inventory-adjustments',
        component: () => import('../views/admin/inventory/AdjustmentList.vue'),
        meta: { titleKey: 'admin.page.inventoryAdjustments', permission: 'inventory:adjust:write' }
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

/**
 * 后台"首页"候选：按路由定义顺序，用作登录落地与无权限兜底。
 *
 * 为什么不能写死 /admin/tickets 或 /admin/faults：
 * 不同角色权限不同——典型如 warehouse 只有进销存权限、没有任何售后模块权限。
 * 一旦默认页 / 兜底页本身需要该角色没有的权限，守卫就会把用户又弹回同一个页，
 * 形成"重定向到自己"的死循环，表现为登录后浏览器卡死。
 * 这里动态取当前用户第一个真正可见的页面，兜底目标自身一定有权限，循环不成立。
 *
 * 排除带动态段（如 faults/edit/:id?）的路径：编辑页不适合做落地首页。
 */
// 登录后的落地页候选：按路由声明顺序取第一个有权限的页面。
// meta.home === false 的页面只进菜单、不当落地页（目前只有物资分类：
// 它排在 SKU 前面，但仓管登录应该直接看到物资列表而不是分类主数据）。
const ADMIN_HOME_CANDIDATES = routes
  .find((r) => r.path === '/admin')
  .children.filter((r) => r.meta?.permission && !r.path.includes(':') && r.meta.home !== false)
  .map((r) => ({ path: `/admin/${r.path}`, permission: r.meta.permission }))

// 独立导出便于单测（见 router/guard.spec.js）。
export function firstAccessibleAdminPath() {
  for (const c of ADMIN_HOME_CANDIDATES) {
    if (hasPermission(c.permission)) return c.path
  }
  // 安全网：角色必带权限，走到这里说明配置异常，退回登录页
  return '/admin/login'
}

const router = createRouter({
  history: createWebHistory(),
  routes
})

/**
 * 已登录的人不该再看到登录页。
 *
 * 客户侧右上角「后台入口」指向 /admin/login，这是给未登录访客用的；
 * 已登录用户（token 未过期）点进来却还要重登一次，是最常见的抱怨。
 * 这里统一在守卫里兜住——客户侧链接、浏览器书签、手敲 URL 全部生效。
 *
 * 独立导出是为了能脱离真实导航做单测（见 router/guard.spec.js），
 * 接入点是下面的 beforeEach 第一段。
 */
export function loggedInRedirect(to) {
  if (to.path !== '/admin/login') return null
  if (!hasValidToken()) return null
  // 带上 redirect 时优先回原页面；只接受站内 /admin 路径，
  // 不把 query 里塞进来的任意外部地址当跳转目标（开放重定向）
  const redirect = typeof to.query?.redirect === 'string' ? to.query.redirect : ''
  return { path: redirect.startsWith('/admin') ? redirect : '/admin' }
}

/**
 * 空闲超时（默认 60 分钟）时把后台页面踢回登录页。
 *
 * 为什么必须在守卫里做、不能只靠 Layout 里的定时器：
 * 下班关机后第二天开机，浏览器恢复的是"后台某页"的地址。守卫先跑，
 * 用户看不到后台内容一闪而过；只靠定时器会先渲染出工单列表再跳走。
 *
 * 只作用于 `/admin/*`：客户侧页面不读也不清后台凭证。
 * 独立导出便于单测（见 router/guard.spec.js）。
 */
export function idleRedirect(to) {
  // 只管后台。客户侧页面与后台会话无关：同一个浏览器登录过后台的人，
  // 空闲超时后再打开客户首页，不能被弹到后台登录页（自助查询直接不可用）
  if (!to.path.startsWith('/admin')) return null
  if (!localStorage.getItem('token')) return null
  if (!isIdleExpired()) return null
  clearAuthLocal()
  // 目标本来就是登录页：凭证已清，别再让它跳自己一次
  if (to.path === '/admin/login') return null
  return { path: '/admin/login', query: { reason: 'idle' } }
}

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

  // 空闲超时优先于"已登录跳过登录页"：否则会被送回后台再被判一次
  const idle = idleRedirect(to)
  if (idle) return idle

  // 已登录（token 未过期）再进登录页没有意义，直接送进后台。
  // 放在 public 放行之前：登录页是 public，先放行就轮不到这条判断了
  const skipLogin = loggedInRedirect(to)
  if (skipLogin) return skipLogin

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
      clearAuthLocal()
      return { path: '/admin/login', query: { redirect: to.fullPath } }
    }
  }

  // 根路径 /admin：按角色权限落地到第一个可见页面。
  // 不能写死 /admin/tickets——warehouse 等无售后权限角色会陷入
  // "重定向到自己"的死循环（登录后浏览器卡死）。
  if (to.path === '/admin') {
    return { path: firstAccessibleAdminPath() }
  }

  // 目标页无权限：回退到当前角色第一个可见页面（同样是动态取的，
  // 保证回退目标自身一定有权限，不会二次触发 403 死循环）。
  if (to.meta.permission && !hasPermission(to.meta.permission)) {
    return { path: firstAccessibleAdminPath() }
  }
  if (to.meta.requires && !to.meta.requires.every(hasPermission)) {
    return { path: firstAccessibleAdminPath() }
  }
  return true
})

export default router

// 标签页标题：按 meta.titleKey 取词。语言切换不换路由，afterEach 不会跑，
// 那条路径由 Layout / PublicLayout 在切换后自行调 applyPageTitle。
router.afterEach((to) => {
  applyPageTitle(to.meta)
})
