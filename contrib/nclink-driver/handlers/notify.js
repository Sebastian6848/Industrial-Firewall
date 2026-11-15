/*
 * NC-LINK Protocol Driver for JSON-SCADA
 * handlers/notify.js — 状态通知处理器
 *
 * 对应 handlers/notify.py。
 *
 * 适配器通过这类消息告诉代理器它的状态变化，例如：
 *   - 适配器上线/下线
 *   - 跟机床的连接断了/恢复了
 *   - 某些内部状态变化
 *
 * 消息长这样（参考意见稿yi）：
 *   {"@id":"notify001", "guid":"adapter-uuid", "state":"online"}
 *   {"@id":"state001",  "guid":"adapter-uuid", "state":"machine_disconnected"}
 *
 * 我们要做的：
 *   1. 记录通知到日志
 *   2. （以后可以加：把适配器的在线状态写进 MongoDB，方便监控）
 *   3. 回复 OK
 */

'use strict'

const { log } = require('../config')
const { buildOK } = require('../pdu')

async function handle(pdu, context) {
  const id = pdu['@id']
  const guid = pdu.guid
  // 通知内容可能在 state 字段，也可能在 privateInfo 里，做兼容处理
  const state = pdu.state || pdu.privateInfo?.state || pdu.privateInfo || '(未知)'

  log(1, `适配器通知: guid=${guid}, state=${JSON.stringify(state)}`)

  // ── 更新 registry 里这个适配器的状态 ──
  if (context.registry && guid) {
    const entry = context.registry.get(guid)
    if (entry) {
      entry.lastNotifyAt = new Date()
      entry.lastState = state
    } else {
      // 没注册过就来发通知，记录一下但不阻止
      log(1, `收到未注册适配器的通知: guid=${guid}`)
    }
  }

  return buildOK(id, guid)
}

module.exports = {
  handle,
}
