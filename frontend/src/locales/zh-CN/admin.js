// 后台外壳（导航、顶栏）的文案。
// 导航顺序与 NAV_ITEMS 一致，改顺序时两边一起改，Layout.spec.js 会校验。
export default {
  brand: '售后故障诊断',
  nav: {
    tickets: '工单管理',
    faults: '故障知识库',
    stats: '数据看板',
    productLines: '产品线',
    products: '产品管理',
    parts: '零件管理',
    users: '用户管理'
  },
  topbar: {
    changePassword: '修改密码',
    logout: '退出登录',
    loggedIn: '已登录'
  },
  login: {
    subtitle: '后台管理登录',
    username: '用户名',
    usernamePlaceholder: '请输入用户名',
    usernameRequired: '请输入用户名',
    password: '密码',
    passwordPlaceholder: '请输入密码',
    passwordRequired: '请输入密码',
    submit: '登录',
    success: '登录成功',
    failed: '登录失败，请稍后重试'
  },
  password: {
    title: '修改密码',
    old: '原密码',
    new: '新密码',
    confirm: '确认新密码',
    oldRequired: '请输入原密码',
    newRequired: '请输入新密码',
    newTooShort: '新密码至少 8 位',
    newSameAsOld: '新密码不能与原密码相同',
    confirmRequired: '请再次输入新密码',
    confirmMismatch: '两次输入的密码不一致',
    changed: '密码已修改',
    changeFailed: '修改失败，请稍后重试',
    oldInvalid: '原密码不正确'
  },
  page: {
    login: '登录',
    tickets: '工单管理',
    products: '产品管理',
    productLines: '产品线管理',
    parts: '零件管理',
    faults: '故障知识库',
    faultEdit: '故障编辑',
    stats: '数据看板',
    users: '用户管理'
  }
}
