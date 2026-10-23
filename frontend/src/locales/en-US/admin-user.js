export default {
  list: {
    searchPlaceholder: 'Search username or name',
    allRoles: 'All roles',
    allStatuses: 'All statuses',
    enabled: 'Active',
    disabled: 'Disabled',
    newUser: 'New user',
    colUser: 'Username / Name',
    colRole: 'Role',
    activeGrants: 'Grants: {count}',
    colLines: 'Product lines',
    noLines: 'Not assigned',
    colStatus: 'Status',
    colLastLogin: 'Last login',
    neverLoggedIn: 'Never',
    colActions: 'Actions',
    resetPassword: 'Reset password',
    grant: 'Grants',
    loadFailed: 'Failed to load users',
    temporary: ' (temp.)'
  },

  form: {
    createTitle: 'New user',
    editTitle: 'Edit user',
    username: 'Username',
    realName: 'Full name',
    password: 'Initial password',
    confirmPassword: 'Confirm password',
    role: 'Role',
    productLines: 'Product lines',
    addLine: 'Add product line',
    selectLine: 'Select a product line',
    lineInactive: '{name} (disabled)',
    longTerm: 'Indefinite (leave blank)',
    renameHint: 'After renaming, sign in with the new username',
    ruleUsername: 'Please enter a username',
    ruleRealName: 'Please enter a name',
    rulePassword: 'Please enter an initial password',
    rulePasswordMin: 'Password must be at least 8 characters',
    ruleConfirmRequired: 'Please confirm the initial password',
    ruleConfirmMismatch: 'The two passwords do not match',
    ruleRole: 'Please select a role',
    saved: 'Saved',
    usernameDuplicated: 'This username already exists'
  },

  toggle: {
    disableConfirm: 'This account will be unable to sign in immediately. Disable "{name}"?',
    disableTitle: 'Confirm disable',
    confirmDisable: 'Disable',
    enabled: 'Enabled',
    disabled: 'Disabled',
    failed: 'Failed to update status'
  },

  role: {
    changeTitle: 'Confirm role change',
    changeConfirm: 'Change the role of "{name}" from {from} to {to}? Permissions take effect immediately.',
    confirmChange: 'Change role'
  },

  reset: {
    confirm: 'Reset the password for "{name}"?',
    title: 'Reset password',
    doneTitle: 'Password reset',
    alert: 'Copy it now and hand it over through a secure channel. It cannot be viewed again after closing.',
    copyFailedLong: 'Copy failed. Please select and copy the password manually.',
    failed: 'Reset failed'
  },

  grant: {
    title: 'Temporary grants — {name}',
    colPermission: 'Permission',
    colReason: 'Reason',
    colGrantedBy: 'Granted by',
    colExpiresAt: 'Expires',
    colStatus: 'Status',
    colActions: 'Actions',
    active: 'Active',
    inactive: 'Expired',
    revoke: 'Revoke',
    issueTitle: 'Issue a new grant',
    permission: 'Permission',
    expiresAt: 'Expires at',
    reason: 'Reason',
    issue: 'Issue',
    issued: 'Granted',
    revoked: 'Revoked',
    revokeFailed: 'Failed to revoke',
    loadFailed: 'Failed to load grants',
    grantedBySystem: 'System',
    copy: 'Copy',
    copied: 'Copied',
    rulePermission: 'Please select a permission',
    ruleExpiresAt: 'Please select an expiry time',
    ruleReason: 'Please enter a reason'
  }
}
