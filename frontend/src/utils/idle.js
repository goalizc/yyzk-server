/**
 * 空闲自动登出。
 *
 * 解决的场景：下班直接关机（或忘了退出），第二天开机浏览器把标签页恢复回来，
 * JWT 还在 24 小时有效期内，任何人打开电脑都能直接进后台看工单（含客户手机号）。
 *
 * 做法：把"最后一次操作时间"写进 localStorage，超过阈值就清凭证回登录页。
 * - 用 localStorage 而不是内存：关机/关浏览器后要留下时间戳，重启才能算出"已经空闲多久"
 * - 监听用户活动并节流写盘：mousemove 很密集，每 15 秒最多写一次足够
 * - 定时检查 + 页面重新可见时补查：后台标签的 setInterval 会被浏览器节流
 *
 * 边界（必须说清）：这是**客户端**行为，token 在 exp 之前本身仍然有效。
 * 它挡的是"同事顺手打开你没退出的电脑"，挡不住"提前把 token 复制走的人"。
 * 后者要服务端会话表或 refresh_token + httpOnly cookie 才管得住。
 */

/**
 * 默认空闲阈值：60 分钟（产品确认值）。
 * 改这里就是改行为，没有配置入口——一期单机部署，不值得为它加一层配置下发。
 */
const IDLE_TIMEOUT_MS = 60 * 60 * 1000

/** 超时前多久提醒一次（只在最后这段时间弹一条，避免反复打扰） */
const WARN_BEFORE_MS = 2 * 60 * 1000

const ACTIVITY_KEY = 'lastActiveAt'
const TOUCH_THROTTLE_MS = 15 * 1000
const CHECK_INTERVAL_MS = 30 * 1000

// 这些事件都代表"人在电脑前"。wheel 与 touchstart 覆盖触控板滚动和触屏。
const ACTIVITY_EVENTS = ['mousemove', 'mousedown', 'keydown', 'wheel', 'touchstart', 'scroll']

let lastWriteAt = 0

function safeGet(key) {
  try {
    return localStorage.getItem(key)
  } catch {
    // 隐私模式读不了 localStorage：当作没有记录
    return null
  }
}

function safeSet(key, value) {
  try {
    localStorage.setItem(key, value)
  } catch {
    // 写不进去只影响本机记忆，不影响本次会话
  }
}

function safeRemove(key) {
  try {
    localStorage.removeItem(key)
  } catch {
    // 忽略
  }
}

/** 最后一次操作的时间戳（毫秒）；没有记录返回 0 */
export function readLastActive() {
  const raw = Number(safeGet(ACTIVITY_KEY) || 0)
  return Number.isFinite(raw) && raw > 0 ? raw : 0
}

/** 记录一次操作。内部按 15 秒节流，调用方可以放心在 mousemove 里直接调 */
export function touchActivity(now = Date.now()) {
  if (now - lastWriteAt < TOUCH_THROTTLE_MS) return
  lastWriteAt = now
  safeSet(ACTIVITY_KEY, String(now))
}

/**
 * 强制记一次操作，无视节流。
 * 登录成功时用：登录页可能已经开了很久（活动记录是两小时前的），
 * 若被节流跳过，紧接着的守卫会立刻把刚登录的人判成"空闲超时"踢回登录页。
 */
export function resetActivity(now = Date.now()) {
  lastWriteAt = now
  safeSet(ACTIVITY_KEY, String(now))
}

/** 清掉活动记录：退出登录、切换账号时调用，避免把上一个会话的空闲时长带给下一个人 */
export function clearActivity() {
  lastWriteAt = 0
  safeRemove(ACTIVITY_KEY)
}

/**
 * 是否已经空闲超时。
 * 没有活动记录时返回 false —— 那说明从没登录过或刚被清理，不该判成超时。
 */
export function isIdleExpired(now = Date.now()) {
  const last = readLastActive()
  if (!last) return false
  return now - last >= IDLE_TIMEOUT_MS
}

/**
 * 开始监控空闲。
 * @param {object} options
 * @param {() => void} options.onIdle 超时回调（调用前已自动停止监控，不会重复触发）
 * @param {() => void} [options.onWarn] 即将超时的提醒回调（每个空闲周期最多一次）
 * @returns {() => void} 停止监控
 */
export function startIdleWatch({ onIdle, onWarn } = {}) {
  // 首次进入时若没有记录（刚登录 / 本机第一次用），立刻写一次：
  // 否则会被"无记录"当成空闲很久，或者反过来要等到第一次鼠标移动才开始计时
  if (!readLastActive()) touchActivity()

  let warned = false
  let stopped = false
  // 先声明再赋值：stop() 里会用到，不能依赖"首次 check 一定发生在赋值之后"
  let timer = null

  const onActivity = () => touchActivity()

  function check() {
    if (stopped) return
    const last = readLastActive()
    // 没有记录就别判：`Date.now() - 0` 是"空闲了 56 年"，会立刻误触发。
    // 记录会被 clearAuthLocal() 清掉（另一个标签登出、401 拦截器清理），
    // 此时本标签还没卸载，定时器仍会跑一次。口径要与 isIdleExpired() 一致。
    if (!last) return
    const idle = Date.now() - last
    if (idle >= IDLE_TIMEOUT_MS) {
      stop()
      onIdle?.()
      return
    }
    if (!warned && idle >= IDLE_TIMEOUT_MS - WARN_BEFORE_MS) {
      warned = true
      onWarn?.()
    } else if (idle < IDLE_TIMEOUT_MS - WARN_BEFORE_MS) {
      warned = false
    }
  }

  function onVisibility() {
    // 后台标签里 setInterval 会被节流（最慢约 1 分钟一跳），
    // 切回来的瞬间补一次判断，别留"回来了还能点一下"的空窗
    if (document.visibilityState === 'visible') check()
  }

  function stop() {
    if (stopped) return
    stopped = true
    if (timer) clearInterval(timer)
    ACTIVITY_EVENTS.forEach((name) => window.removeEventListener(name, onActivity, true))
    document.removeEventListener('visibilitychange', onVisibility)
  }

  timer = setInterval(check, CHECK_INTERVAL_MS)
  ACTIVITY_EVENTS.forEach((name) =>
    window.addEventListener(name, onActivity, { passive: true, capture: true })
  )
  document.addEventListener('visibilitychange', onVisibility)

  // 挂载时就查一次：直接输网址进后台时，可能上个会话已经空闲很久了
  check()

  return stop
}
