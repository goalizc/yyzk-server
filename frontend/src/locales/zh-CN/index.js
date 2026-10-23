import common from './common'
import publicPages from './public'
import fault from './fault'
import adminShell from './admin'
import adminTicket from './admin-ticket'
import adminFault from './admin-fault'
import adminCatalog from './admin-catalog'
import adminStats from './admin-stats'
import adminUser from './admin-user'
import permission from './permission'
import error from './error'

export default {
  common,
  public: publicPages,
  fault,
  // admin 按页面拆文件：外壳（导航/顶栏/登录）留在 admin.js，
  // 各业务页挂在 admin.<module> 下，避免单文件无限膨胀
  admin: {
    ...adminShell,
    ticket: adminTicket,
    fault: adminFault,
    ...adminCatalog,
    stats: adminStats,
    user: adminUser
  },
  permission,
  error
}
