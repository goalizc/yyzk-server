import common from './common'
import publicPages from './public'
import fault from './fault'
import adminShell from './admin'
import adminTicket from './admin-ticket'
import adminFault from './admin-fault'
import adminCatalog from './admin-catalog'
import adminStats from './admin-stats'
import adminUser from './admin-user'
import adminAudit from './admin-audit'
import permission from './permission'
import error from './error'

export default {
  common,
  public: publicPages,
  fault,
  admin: {
    ...adminShell,
    ticket: adminTicket,
    fault: adminFault,
    ...adminCatalog,
    stats: adminStats,
    user: adminUser,
    audit: adminAudit
  },
  permission,
  error
}
