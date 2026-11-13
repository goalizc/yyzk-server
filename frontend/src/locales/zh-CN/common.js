export default {
  appName: '售后故障诊断系统',
  action: {
    save: '保存',
    cancel: '取消',
    delete: '删除',
    add: '新增',
    search: '搜索',
    reset: '重置',
    close: '关闭',
    copy: '复制',
    retry: '重试',
    reload: '重新加载',
    back: '返回',
    submit: '提交',
    edit: '编辑',
    view: '查看',
    remove: '移除',
    upload: '上传'
  },
  upload: {
    onlyFormats: '仅支持 {formats} 格式',
    tooLarge: '文件超过 20MB 限制',
    timeout: '上传超时，请检查网络后重试',
    storageUnavailable: '服务器暂时无法保存文件，请稍后重试；持续失败请联系管理员',
    failed: '上传失败',
    noImage: '无图',
    pickImage: '上传图片',
    reupload: '重新上传'
  },
  confirm: {
    deleteTitle: '删除确认',
    delete: '确认删除'
  },
  error: {
    generic: '操作失败，请稍后重试',
    loadFailed: '加载失败'
  },
  notFound: {
    title: '页面不存在',
    subtitle: '链接可能已失效，或该功能尚未开放',
    backHome: '返回首页'
  },
  empty: {
    none: '暂无数据'
  },
  status: {
    open: '待处理',
    processing: '处理中',
    resolved: '已解决',
    closed: '已关闭'
  },
  roleGroup: {
    system: '系统管理',
    master: '主数据',
    service: '售后角色',
    warehouse: '仓管角色'
  },
  role: {
    // key 必须与后端 user_roles.role 的取值逐字一致（ROLE_VALUES / user_roles.role CHECK），
    // 曾因写成 warehouseClerk 驼峰，查不到中文名而把 warehouse_clerk 原样显示给用户。
    super_admin: '超级管理员',
    supervisor: '售后主管',
    product_planner: '产品计划',
    // 「录入员」「主管」单独出现会有歧义（售后也有主管），统一加「仓管」限定词
    warehouse_clerk: '仓管录入员',
    warehouse_manager: '仓管主管',
    agent: '一线客服',
    auditor: '只读审计'
  },
  count: {
    viewed: '{count} 人看过',
    resolved: '{count} 人反馈已解决'
  },
  language: {
    zhCN: '简体中文',
    enUS: 'English',
    // 入口按钮的悬停/读屏说明：按钮文字显示的是"目标语言"，光看文字不知道点了会发生什么
    switchTo: '切换到 {name}'
  }
}
