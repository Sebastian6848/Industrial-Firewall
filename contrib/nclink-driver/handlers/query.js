/*
 * NC-LINK Protocol Driver for JSON-SCADA
 * handlers/query.js — 数据查询处理器（占位版）
 *
 * ⚠️ 这是占位实现 ⚠️
 *
 * 国标里 Query 的方向是：
 *   应用系统 → 代理器（我们）→ 适配器
 *   应用系统问"010302 当前值是多少"，我们转发给适配器，再把答复转回去。
 *
 * 这属于"收应用系统消息 + 转发"的范畴，跟本驱动当前阶段
 *（只做"收适配器数据 → 写 MongoDB"）不是一回事。
 *
 * 完整的 Query 转发逻辑（请求配对、上游连接管理）将在
 * "NC-Link Server 收应用系统端" 的对话里实现。
 *
 * 现在先占位：收到 Query 一律回 NG，并记录日志，
 * 这样驱动不会因为收到意外的 Query 而崩溃或行为异常。
 */

'use strict'

const { log } = require('../config')
const { buildNG, ERRORS } = require('../pdu')

async function handle(pdu, context) {
  const id = pdu['@id']
  const guid = pdu.guid

  log(1, `收到 Query 请求（当前阶段不支持，已拒绝）: guid=${guid}, ids=${JSON.stringify(pdu.ids)}`)

  // 暂时拒绝。完整实现见"收应用系统"对话。
  return buildNG(id, guid, 'Query forwarding not implemented in this stage', ERRORS.UNAVAILABLE)
}

module.exports = {
  handle,
}
