/*
 * NC-LINK Protocol Driver for JSON-SCADA
 * handlers/register.js — 注册请求处理器
 *
 * 对应 handlers/register.py。
 *
 * 适配器连上来后，第一条消息就是注册请求，长这样：
 *   {"@id":"reg001", "cli_uuid":"adapter-uuid-xxx"}
 *
 * 我们要做的事：
 *   1. 记下适配器的身份标识（guid）
 *   2. 回复一个 OK，表示登记成功
 *
 */

'use strict'

const { log } = require('../config')
const { buildOK, buildNG, ERRORS } = require('../pdu')

// ─────────────────────────────────────────────────────────
//  handle — 处理注册请求
//
//  参数：
//    pdu     — 已解析的消息对象，至少包含 @id 和 guid
//    context — 由 router 传入的上下文，包含 db、connection、registry 等
//
//  返回：回复字符串（JSON）
// ─────────────────────────────────────────────────────────

async function handle(pdu, context) {
  const id = pdu['@id']
  const guid = pdu.guid

  if (!guid) {
    log(1, `注册请求缺少 guid/cli_uuid 字段，已忽略: ${JSON.stringify(pdu)}`)
    // Missing identity must never create an authorized registry entry.
    return buildNG(id, '', 'Missing device identity', ERRORS.UNKNOWN_COMMAND)
  }

  if (!context.registry.has(guid) && context.registry.size >= (context.connection.maxDevices || 1024)) {
    return buildNG(id, guid, 'Device registry limit reached', ERRORS.UNAVAILABLE)
  }
  log(1, `适配器注册: guid=${guid}`)

  // ── 把适配器登记到 registry（一个简单的 Map，存在 context 里）──
  //
  // registry 由 index.js 在初始化时创建并放进 context，
  // 这样所有 handler 都能访问。
  //
  // 这是为了后续 sample 数据来时知道"这个 guid 对应哪台机床"。
  // 现在我们只存最基本的信息：连接时间、是否已发过 probe 等
  if (context.registry) {
    const existing = context.registry.get(guid)
    if (existing) {
      // 同一个适配器重新注册（可能断线重连），更新时间戳
      existing.lastRegisterAt = new Date()
      existing.registerCount = (existing.registerCount || 1) + 1
      log(2, `适配器重新注册（第 ${existing.registerCount} 次）`)
    } else {
      // 第一次注册
      context.registry.set(guid, {
        guid,
        firstRegisterAt: new Date(),
        lastRegisterAt: new Date(),
        registerCount: 1,
        probeReceived: false,   // 还没收到 probe，所以还没建标签
      })
    }
  }

  // ── 回复 OK, 走 Register/Response 接口 ──
  // NC-Link 标准要求注册成功返回 code:"OK"
  return {
    topic : 'Register/Response/' + guid,
    payload : buildOK(id, guid)
  }
}

// ─────────────────────────────────────────────────────────
//  导出
//
//  router 会用 handlers.register(pdu, ctx) 调用我们，
//  所以我们导出一个 handle 函数，由 index.js 包装成
//  handlers.register = require('./handlers/register').handle
// ─────────────────────────────────────────────────────────

module.exports = {
  handle,
}
