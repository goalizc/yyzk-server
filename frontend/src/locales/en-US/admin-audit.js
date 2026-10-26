export default {
  title: 'Audit log',
  intro: 'Who did what and when. Filter by account or object to investigate; filter by person or IP to hold someone accountable.',

  filter: {
    username: 'Account',
    usernamePlaceholder: 'Account name, partial match allowed',
    action: 'Action',
    actionAll: 'All actions',
    result: 'Result',
    resultAll: 'All results',
    dateRange: 'Date range',
    startDate: 'Start date',
    endDate: 'End date',
    keyword: 'Keyword',
    keywordPlaceholder: 'Object name / path / account',
    search: 'Search',
    reset: 'Reset',
    export: 'Export CSV'
  },

  summary: {
    title: 'Last {days} days',
    total: '{count} operations',
    failures: '{count} failed',
    actors: '{count} accounts involved',
    topActor: 'Most active',
    multiIp: '{count} IPs',
    multiIpHint: 'One account used from several IPs — worth a look'
  },

  col: {
    time: 'Time',
    username: 'Account',
    action: 'Action',
    target: 'Object',
    result: 'Result',
    ip: 'Source IP',
    status: 'Status'
  },

  result: {
    success: 'Success',
    failure: 'Failed'
  },

  action: {
    authLogin: 'Signed in',
    authPasswordChange: 'Changed own password',
    ticketCreate: 'Customer submitted a ticket',
    ticketUpdate: 'Handled a ticket',
    productCreate: 'Created a product',
    productUpdate: 'Updated a product',
    productDelete: 'Deleted a product',
    partCreate: 'Created a part',
    partUpdate: 'Updated a part',
    partDelete: 'Deleted a part',
    productLineCreate: 'Created a product line',
    productLineUpdate: 'Updated a product line',
    productLineDelete: 'Deleted a product line',
    faultCreate: 'Created a fault solution',
    faultUpdate: 'Updated a fault solution',
    faultDelete: 'Deleted a fault solution',
    userCreate: 'Created an account',
    userUpdate: 'Updated an account',
    userResetPassword: 'Reset a password',
    userGrant: 'Granted a temporary permission',
    userRevokeGrant: 'Revoked a temporary permission',
    userSetProductLines: 'Changed data scope',
    auditExport: 'Exported the audit log',
    uploadCreate: 'Uploaded a file',
    uploadDelete: 'Deleted an uploaded file',
    unknown: 'Other action'
  },

  detail: {
    title: 'Operation detail',
    basic: 'Basic information',
    time: 'Time',
    username: 'Operator',
    action: 'Action',
    target: 'Object',
    targetNone: 'No specific object',
    result: 'Result',
    ip: 'Source IP',
    path: 'Request path',
    status: 'Status',
    requestId: 'Request ID',
    userAgent: 'Browser',
    errorCode: 'Error code',
    extra: 'Additional information',
    empty: 'Nothing else recorded'
  },

  field: {
    reason: 'Reason',
    identityVerified: 'Account name verified',
    errorClass: 'Error type',
    titleFrom: 'Previous title',
    titleTo: 'New title',
    fromStatus: 'From status',
    toStatus: 'To status',
    assigneeFrom: 'Previous assignee',
    assigneeTo: 'New assignee',
    remarkUpdated: 'Remark updated',
    role: 'Role',
    roleFrom: 'Previous role',
    roleTo: 'New role',
    isActiveFrom: 'Previous state',
    isActiveTo: 'New state',
    usernameChanged: 'Username changed',
    permission: 'Permission',
    expiresAt: 'Valid until',
    grantId: 'Grant ID',
    lineId: 'Product line ID',
    productId: 'Product ID',
    lineCount: 'Product line count',
    query: 'Query parameters',
    errorCode: 'Error code'
  },

  verified: {
    yes: 'Verified',
    no: 'From input (unverified)'
  },

  reason: {
    success: 'Signed in',
    wrongPassword: 'Wrong password',
    userNotFound: 'Account not found',
    disabled: 'Account disabled',
    adminReset: 'Reset by an admin',
    selfChange: 'Changed by the owner'
  },

  status: {
    open: 'Open',
    processing: 'In progress',
    resolved: 'Resolved',
    closed: 'Closed'
  },

  anonymous: 'Anonymous',
  empty: 'No records match the filters',
  total: '{count} records',
  loadFailed: 'Failed to load the audit log',
  exportFailed: 'Export failed'
}
