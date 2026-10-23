export default {
  appName: 'Fault Diagnosis System',
  action: {
    save: 'Save',
    cancel: 'Cancel',
    delete: 'Delete',
    add: 'Add',
    search: 'Search',
    reset: 'Reset',
    close: 'Close',
    copy: 'Copy',
    retry: 'Retry',
    reload: 'Reload',
    back: 'Back',
    submit: 'Submit',
    edit: 'Edit',
    view: 'View',
    remove: 'Remove',
    upload: 'Upload'
  },
  upload: {
    onlyFormats: 'Only {formats} files are supported',
    tooLarge: 'File exceeds the 20 MB limit',
    timeout: 'Upload timed out. Check your network and try again.',
    storageUnavailable:
      'The server cannot save files right now. Please retry later, and contact your administrator if it persists.',
    failed: 'Upload failed',
    noImage: 'No image',
    pickImage: 'Upload image',
    reupload: 'Replace image'
  },
  confirm: {
    deleteTitle: 'Confirm deletion',
    delete: 'Delete'
  },
  error: {
    generic: 'Something went wrong. Please try again.',
    loadFailed: 'Failed to load'
  },
  notFound: {
    title: 'Page not found',
    subtitle: 'This link may have expired, or the feature is not available yet',
    backHome: 'Back to home'
  },
  empty: {
    none: 'No data'
  },
  status: {
    open: 'Open',
    processing: 'In progress',
    resolved: 'Resolved',
    closed: 'Closed'
  },
  role: {
    super_admin: 'Super Admin',
    supervisor: 'Service Supervisor',
    agent: 'Support Agent',
    auditor: 'Auditor'
  },
  count: {
    // vue-i18n 复数：单位数用第一段。调用处传数字（t(key, n)）而不是 {count} 对象
    viewed: '{count} person viewed | {count} people viewed',
    resolved: '{count} resolved'
  },
  language: {
    label: 'Language',
    zhCN: '简体中文',
    enUS: 'English'
  }
}
