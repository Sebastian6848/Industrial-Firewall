/*
 * NC-LINK Protocol Driver for JSON-SCADA
 * pdu.js — 消息格式模块
 *
 * 对应 base.py，定义所有 NC-Link 消息的"信封"格式。
 *
 * NC-Link 里每条消息（不管是注册、查询、采样）都遵循同一个结构：
 * {
 *   "@id":        "reg001",         ← 消息ID，回复时原样带回，让对方知道这是哪个请求的答复
 *   "guid":       "adapter-uuid",   ← 发送方的身份标识
 *   "code":       "OK",             ← 成功=OK，失败=NG
 *   "reason":     "...",            ← 失败时的原因说明（可选）
 *   "error":      401,              ← 失败时的错误码（可选）
 *   "privateInfo": { ... }          ← 附带的数据，比如机床模型、采样值（可选）
 * }
 */

'use strict'

// ─────────────────────────────────────────────────────────
//  buildResponse — 构造一条回复消息（JSON 字符串）
//
//  参数说明：
//    id          — 消息ID，从对方发来的请求里原样拿过来
//    guid        — 对方的身份标识，也是从请求里原样拿过来
//    code        — 'OK' 或 'NG'（默认 'OK'）
//    reason      — 失败原因，字符串，可不传
//    error       — 失败错误码，数字，可不传
//    privateInfo — 附带数据，对象，可不传
//
//  返回值：一行 JSON 字符串（不含换行符）
//  调用方发送时需要自己加 \n，因为 NC-Link 用换行符分隔消息
// ─────────────────────────────────────────────────────────

function buildResponse({ id, guid, code = 'OK', reason, error, privateInfo , extra}) {
  const msg = {
    '@id': id,
    'guid': guid,
    'code': code,
  }
  if (extra && typeof extra === 'object') {
    Object.assign(msg, extra)
  }
  // 只在有值时才加这些字段（跟师姐的 to_json 逻辑一致）
  if (reason !== undefined && reason !== null) msg.reason = reason
  if (error !== undefined && error !== null) msg.error = error
  if (privateInfo !== undefined && privateInfo !== null) msg.privateInfo = privateInfo

  return JSON.stringify(msg)
}

// ─────────────────────────────────────────────────────────
//  buildOK — 快捷方式，构造一条成功回复
//
//  例子：
//    buildOK('reg001', 'adapter-001')
//    → '{"@id":"reg001","guid":"adapter-001","code":"OK"}'
//
//    buildOK('probe001', 'adapter-001', { probe: { ... } })
//    → '{"@id":"probe001","guid":"adapter-001","code":"OK","privateInfo":{...}}'
// ─────────────────────────────────────────────────────────

function buildOK(id, guid, privateInfo,extra) {
  return buildResponse({ id, guid, code: 'OK', privateInfo,extra })
}

// ─────────────────────────────────────────────────────────
//  buildNG — 快捷方式，构造一条失败回复
//
//  例子：
//    buildNG('query001', 'adapter-001', '未知指令', 401)
//    → '{"@id":"query001","guid":"adapter-001","code":"NG","reason":"未知指令","error":401}'
// ─────────────────────────────────────────────────────────

function buildNG(id, guid, reason, error) {
  return buildResponse({ id, guid, code: 'NG', reason, error })
}

// ─────────────────────────────────────────────────────────
//  parseMessage — 把从适配器收到的一行字符串解析成对象
//
//  NC-Link 消息是纯 JSON，直接 JSON.parse 就行。
//  这里加了错误处理，解析失败返回 null，调用方自己决定怎么处理。
//
//  同时把两种身份标识字段统一成 guid：
//    适配器注册时用的是 "cli_uuid"
//    其他消息用的是 "guid"
//  我们统一成 guid，后面的 handler 不需要再判断用哪个字段
// ─────────────────────────────────────────────────────────

function parseMessage(rawLine) {
  if (typeof rawLine !== 'string' || Buffer.byteLength(rawLine) > 1024 * 1024) return null
  let pdu
  try { pdu = JSON.parse(rawLine) } catch { return null }
  if (!pdu || typeof pdu !== 'object' || Array.isArray(pdu)) return null
  const pending = [[pdu, 0]]
  let nodes = 0
  while (pending.length) {
    const [value, depth] = pending.pop()
    if (++nodes > 50000 || depth > 32) return null
    if (value && typeof value === 'object') {
      for (const child of Object.values(value)) pending.push([child, depth + 1])
    }
  }
  const identities = ['guid', 'cli_uuid', 'dev_uuid'].filter(k => pdu[k] !== undefined)
  if (identities.some(k => typeof pdu[k] !== 'string' || !pdu[k] || pdu[k].length > 255 || /[\0/+#]/.test(pdu[k]))) return null
  if (new Set(identities.map(k => pdu[k])).size > 1) return null
  if (identities.length) pdu.guid = pdu[identities[0]]
  if (pdu['@id'] !== undefined && (typeof pdu['@id'] !== 'string' || pdu['@id'].length > 255)) return null
  return pdu
}

// ─────────────────────────────────────────────────────────
//  NC-Link 错误码常量（来自标准文档）
// ─────────────────────────────────────────────────────────

const ERRORS = {
  UNKNOWN_COMMAND:   401,   // 未知指令
  UNAVAILABLE:       202,   // 数据不可用
  INTERNAL_ERROR:    500,   // 内部错误
}

// ─────────────────────────────────────────────────────────
//  导出
// ─────────────────────────────────────────────────────────

module.exports = {
  buildResponse,
  buildOK,
  buildNG,
  parseMessage,
  ERRORS,
}
