/*
 * NC-LINK Protocol Driver for JSON-SCADA
 * mqtt-client.js — MQTT 客户端传输层模块
 *
 * 取代 tcp-server.js。Opensense server.py / server_mqtt.py 的等价物，但做完整：
 *   - 连到外部 MQTT broker（我们是 client，不是 broker）
 *   - 宽订阅 NC-Link 的几类指令 topic
 *   - 收到消息 → 解析 payload → 连同 topic 交给 router 处理
 *   - 提供 publish 能力，让 handler 能"主动发消息"（拉模型、转发、回响应）
 *
 * 与 TCP 版的关键区别：
 *   1. TCP 是服务端 listen/accept；MQTT 是客户端 connect 到 broker。
 *   2. TCP 要处理粘包（按 \n 切分）；MQTT 每条 message 天然是完整一条，无需切分。
 *   3. TCP 回复靠 socket.write 顺原路返回；MQTT 回复是 publish 到“响应 topic”。
 *   4. 消息类型 TCP 靠 @id 前缀猜；MQTT 靠 topic 判定（见 router.js 改造）。
 *
 * 依赖：npm i mqtt
 */

'use strict'

const mqtt = require('mqtt')
const fs = require('fs')
const { log } = require('./config')
const { parseMessage } = require('./pdu')

// ─────────────────────────────────────────────────────────
//  模块内部状态
// ─────────────────────────────────────────────────────────

let client = null          // mqtt.MqttClient 对象
let routerFn = null        // 由 index.js 注入的 router.route，签名 async (topic, pdu) => {topic,payload}|null
let topicRoot = ''         // 可配置的 topic 根前缀（默认空=裸 topic）

// 宽订阅的 6 个指令大类。覆盖南端全部接口，又不会收 NC-Link 之外的流量。
// 加新接口时只要 topic 落在这些前缀下，无需改订阅。
const SUBSCRIBE_GROUPS = [
  'Register/#',
  'Probe/#',
  'Sample/#',
  'Notify/#',
  'Method/#',
  'Event/#',
  'Unregister/#',
  'Query/Request/#',
  'Discovery/Response/#',
]

// ─────────────────────────────────────────────────────────
//  withRoot — 给 topic 统一加上根前缀
//
//  topicRoot='' → 'Sample/dev01/cn1'         （裸 topic，贴国标）
//  topicRoot='nclink' → 'nclink/Sample/dev01/cn1'  （隔离命名空间）
// ─────────────────────────────────────────────────────────

function withRoot(topic) {
  if (!topicRoot) return topic
  return topicRoot.replace(/\/+$/, '') + '/' + topic
}

// ─────────────────────────────────────────────────────────
//  stripRoot — 把收到的 topic 去掉根前缀，方便 router 按国标 topic 匹配
//
//  收到 'nclink/Sample/dev01/cn1'（topicRoot='nclink'）→ 'Sample/dev01/cn1'
//  收到 'Sample/dev01/cn1'（topicRoot=''）→ 原样
// ─────────────────────────────────────────────────────────

function stripRoot(topic) {
  if (!topicRoot) return topic
  const prefix = topicRoot.replace(/\/+$/, '') + '/'
  return topic.startsWith(prefix) ? topic.slice(prefix.length) : null
}

// ─────────────────────────────────────────────────────────
//  start — 启动 MQTT 客户端
//
//  参数：
//    connection — 从 mongo.js 加载的连接配置文档，需要这些字段：
//      endpointURLs   [Array<String>] broker 地址，如 ["mqtt://127.0.0.1:1883"]
//      clientId       [String]  可选，MQTT 客户端 id
//      username       [String]  可选
//      password       [String]  可选
//      topicRoot      [String]  可选，默认 ''
//      TLS: useSecurity、caFile、certFile、keyFile；始终验证服务端证书。
//    router     — router.js 的 route 函数，签名 async (topic, pdu) => {topic,payload}|null
// ─────────────────────────────────────────────────────────

function start(connection, router) {
  routerFn = router
  topicRoot = connection.topicRoot || ''
  if (topicRoot && (topicRoot.split('/').some(x => !x || /[+#\0]/.test(x)) || topicRoot.length > 255)) throw new Error('Invalid topicRoot')

  // endpointURLs 是数组（支持冗余 broker），这里取第一个；
  // mqtt 库本身也支持传数组做故障转移，后续可扩展。
  const brokerUrl =
    Array.isArray(connection.endpointURLs) && connection.endpointURLs.length > 0
      ? connection.endpointURLs[0]
      : 'mqtt://127.0.0.1:1883'

  const options = {
    clientId:
      connection.clientId ||
      'nclink-driver-' + Math.random().toString(16).slice(2, 10),
    username: connection.username || undefined,
    password: connection.password || undefined,
    clean: true,            // 清洁会话（不持久化订阅，重连后重新订阅）
    reconnectPeriod: 5000,  // 断线后每 5 秒自动重连（mqtt 库内置）
    connectTimeout: 30000,
  }

  const displayUrl = new URL(brokerUrl)
  displayUrl.username = ''; displayUrl.password = ''
  log(1, `正在连接 MQTT broker: ${displayUrl}`)
  log(1, `  clientId: ${options.clientId}`)
  log(1, `  topicRoot: ${topicRoot ? topicRoot : '(空，裸 topic)'}`)

  if (connection.useSecurity && !brokerUrl.startsWith('mqtts://')) throw new Error('useSecurity requires mqtts://')
  if (brokerUrl.startsWith('mqtts://')) {
    options.rejectUnauthorized = true
    for (const [option, field] of [['ca','caFile'],['cert','certFile'],['key','keyFile']]) {
      if (connection[field]) options[option] = fs.readFileSync(connection[field])
    }
    if (Boolean(options.cert) !== Boolean(options.key)) throw new Error('Client certificate and key must be configured together')
  }
  client = mqtt.connect(brokerUrl, options)

  // ── 连接成功 ──
  client.on('connect', () => {
    log(0, `MQTT broker 已连接: ${displayUrl}`)
    // 连上（含每次自动重连后）都要重新订阅
    for (const g of SUBSCRIBE_GROUPS) {
      const topic = withRoot(g)
      client.subscribe(topic, { qos: 1 }, (err) => {
        if (err) {
          log(0, `订阅失败 ${topic}: ${err.message}`)
        } else {
          log(1, `已订阅: ${topic}`)
        }
      })
    }
  })

  // ── 收到消息 ──
  let queue = Promise.resolve(), pending = 0
  client.on('message', (topic, payloadBuf) => {
    if (payloadBuf.length > 1024 * 1024 || pending >= 128) { client.end(true); return }
    pending++
    queue = queue.then(() => handleMessage(topic, payloadBuf)).catch(err => log(0, 'MQTT message:', err.message)).finally(() => pending--)
  })

  // ── 重连中 ──
  client.on('reconnect', () => {
    log(1, 'MQTT 正在重连...')
  })

  // ── 连接断开 ──
  client.on('close', () => {
    log(1, 'MQTT 连接已关闭')
  })

  // ── 错误（不让单个错误把驱动崩掉） ──
  client.on('error', (err) => {
    log(0, `MQTT 错误: ${err.message}`)
  })
}

// ─────────────────────────────────────────────────────────
//  handleMessage — 处理一条收到的 MQTT 消息
//
//  流程：
//    1. 去掉根前缀，得到国标 topic
//    2. 解析 payload（JSON → pdu 对象）
//    3. 交给 router（连同 topic）
//    4. router 返回 {topic, payload} 时，publish 出去（这是“回复/转发”）
//       返回 null 表示不需要发任何东西（纯数据写库）
// ─────────────────────────────────────────────────────────

async function handleMessage(rawTopic, payloadBuf) {
  const topic = stripRoot(rawTopic)
  if (topic === null) return
  const payloadStr = payloadBuf.toString('utf8')

  log(3, `收到 [${topic}]: ${payloadStr.slice(0, 300)}`)

  // 解析 JSON payload
  const pdu = parseMessage(payloadStr)
  if (!pdu) {
    log(1, `非法 JSON，已忽略 [${topic}]: ${payloadStr.slice(0, 100)}`)
    return
  }

  // 交给 router 处理（注意：现在传 topic + pdu 两个参数）
  let result
  try {
    result = await routerFn(topic, pdu)
  } catch (err) {
    log(0, `router 处理出错 [${topic}]: ${err.message}`)
    return
  }

  // router 返回 null → 不需要发任何东西（比如采样数据只写库）
  if (!result) return

  // router 返回 {topic, payload} → publish 出去（回复或转发）
  publish(result.topic, result.payload)
}

// ─────────────────────────────────────────────────────────
//  publish — 主动发一条 NC-Link 消息
//
//  这是 handler“主动发消息”的统一出口：
//    - probe.js 主动拉模型（发 Probe/Query/Request）
//    - 各 handler 回响应（发 .../Response/...）
//    - 转发类接口
//
//  参数：
//    topic   — 国标 topic（不含根前缀，本函数自动加）
//    payload — 字符串（通常是 pdu.js 的 buildXXX 产出）或对象（自动 JSON 序列化）
//    opts    — 可选 { qos, retain }
// ─────────────────────────────────────────────────────────

function publish(topic, payload, opts = {}) {
  if (!client || !client.connected) {
    log(1, `MQTT 未连接，发送失败 [${topic}]`)
    return false
  }

  const fullTopic = withRoot(topic)
  const payloadStr =
    typeof payload === 'string' ? payload : JSON.stringify(payload)

  const qos = opts.qos !== undefined ? opts.qos : 1
  const retain = opts.retain !== undefined ? opts.retain : false

  client.publish(fullTopic, payloadStr, { qos, retain }, (err) => {
    if (err) {
      log(1, `发送失败 [${fullTopic}]: ${err.message}`)
    } else {
      log(3, `已发送 [${fullTopic}]: ${payloadStr.slice(0, 300)}`)
    }
  })
  return true
}

// ─────────────────────────────────────────────────────────
//  stop — 关闭客户端（程序退出时清理用）
// ─────────────────────────────────────────────────────────

function stop() {
  if (client) {
    log(1, '正在关闭 MQTT 客户端...')
    try {
      client.end(true) // force=true，立即断开
    } catch (err) {
      log(1, `关闭 MQTT 出错: ${err.message}`)
    }
    client = null
  }
}

// ─────────────────────────────────────────────────────────
//  getClient — 给其他模块（如需要）拿到底层 client
// ─────────────────────────────────────────────────────────

function getClient() {
  return client
}

// ─────────────────────────────────────────────────────────
//  导出
// ─────────────────────────────────────────────────────────

module.exports = {
  start,
  stop,
  publish,      // handler 主动发消息时用这个
  getClient,
  withRoot,
  stripRoot,
}
