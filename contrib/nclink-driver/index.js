/*
 * NC-LINK Protocol Driver for JSON-SCADA
 * index.js — 驱动入口（总指挥）
 *
 * 把所有模块串起来，按顺序启动：
 *   1. 读配置（config.js）
 *   2. 连 MongoDB + 加载驱动实例/连接配置 + 启动心跳（mongo.js）
 *   3. 初始化 auto-tag 的 _id 计数器（auto-tag.js）
 *   4. 组装 context（共享资源容器）
 *   5. 组装 handlers，初始化 router（router.js）
 *   6. 启动配置的 MQTT 或 TCP JSON 传输
 *
 * 启动命令：
 *   node index.js <实例编号> <日志级别> <配置文件路径>
 *   node index.js 1 1 ../conf/json-scada.json
 */

'use strict'

const Config = require('./config')
const Mongo = require('./mongo')
const Router = require('./router')
const MqttClient = require('./mqtt-client')
const TcpServer = require('./tcp-server')
let transport = MqttClient
const AutoTag = require('./auto-tag')

const { log } = Config

// handlers
const registerHandler = require('./handlers/register')
const probeHandler = require('./handlers/probe')
const sampleHandler = require('./handlers/sample')
const notifyHandler = require('./handlers/notify')
const queryHandler = require('./handlers/query')

// ─────────────────────────────────────────────────────────
//  捕获未处理的异常，避免整个进程意外崩溃
// ─────────────────────────────────────────────────────────

process.on('uncaughtException', (err) => {
  log(0, `未捕获的异常: ${err.message}\n${err.stack}`)
})

process.on('unhandledRejection', (reason) => {
  log(0, `未处理的 Promise 拒绝: ${reason}`)
})

// ─────────────────────────────────────────────────────────
//  主启动流程
// ─────────────────────────────────────────────────────────

async function main() {
  log(0, '========================================')
  log(0, `NC-LINK 驱动启动`)
  log(0, '========================================')

  // ── 1. 读配置 ──
  const jsConfig = Config.loadConfig()
  log(1, `配置已加载: 实例=${jsConfig.InstanceNumber}, 日志级别=${jsConfig.LogLevel}`)

  // ── 2. 连 MongoDB（带重试） ──
  // 如果 MongoDB 还没起来，等几秒重试，不要直接崩
  let connected = false
  while (!connected) {
    try {
      await Mongo.initialize(jsConfig)
      connected = true
    } catch (err) {
      log(0, `MongoDB 连接失败: ${err.message}，5秒后重试...`)
      await sleep(5000)
    }
  }

  // 拿到 mongo.js 加载好的资源
  const db = Mongo.getDb()
  const connection = Mongo.getConnection()
  const connNum = connection.protocolConnectionNumber
  if (connection.transport && !['mqtt','tcp-json'].includes(connection.transport)) throw new Error('Unknown NC-Link transport')
  transport = connection.transport === 'tcp-json' ? TcpServer : MqttClient

  // ── 3. 初始化 auto-tag 的 _id 计数器 ──
  const rtCollection = db.collection(jsConfig.RealtimeDataCollectionName)
  await AutoTag.GetAutoKeyInitialValue(rtCollection, connNum)

  // ── 4. 组装 context（所有 handler 共享的资源容器） ──
  const context = {
    db,                          // MongoDB 数据库对象
    connection,                  // 连接配置文档
    jsConfig,                    // 全局配置
    registry: new Map(),         // 适配器登记表（guid → 状态）
    machineModels: new Map(),    // 每个适配器的机床模型（guid → 模型）
    sampleChannels: new Map(),   // 采样通道定义（channelId → {ids, interval...}）
    publish: transport.publish,    // 让 handler 能主动发消息
    brokerExCid: connection.scadaHostId || 'nclink_broker',   // 代理器终端标识(ex_cid)
  }

  // ── 5. 组装 handlers，初始化 router ──
  const handlers = {
    register: registerHandler.handle,
    probe: probeHandler.handle,
    sample: sampleHandler.handle,
    notify: notifyHandler.handle,
    query: queryHandler.handle,
  }
  Router.initialize(context, handlers)

  // ── 6. 启动配置的传输方式（默认 MQTT） ──
  // 两种传输都传递明确的 topic 和 PDU，不根据消息编号猜测业务。
  transport.start(connection, Router.route, Router.disconnect)

  log(0, '========================================')
  log(0, `NC-LINK 驱动启动完成`)
  log(0, `MQTT broker: ${connection.endpointURLs ? connection.endpointURLs[0] : '(未配置)'}`)
  log(0, `连接号: ${connNum}`)
  log(0, `等待适配器连接...`)
  log(0, '========================================')

  // ── 优雅退出处理 ──
  setupGracefulShutdown()
}

// ─────────────────────────────────────────────────────────
//  优雅退出：Ctrl+C 或 kill 时，清理资源
// ─────────────────────────────────────────────────────────

function setupGracefulShutdown() {
  const shutdown = (signal) => {
    log(0, `收到 ${signal} 信号，正在关闭...`)
    try {
      transport.stop()
      Mongo.stopHeartbeat()
    } catch (err) {
      log(1, `关闭时出错: ${err.message}`)
    }
    log(0, '驱动已关闭')
    process.exit(0)
  }

  process.on('SIGINT', () => shutdown('SIGINT'))   // Ctrl+C
  process.on('SIGTERM', () => shutdown('SIGTERM')) // kill
}

// ─────────────────────────────────────────────────────────
//  工具函数
// ─────────────────────────────────────────────────────────

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

// ─────────────────────────────────────────────────────────
//  启动
// ─────────────────────────────────────────────────────────

main().catch((err) => {
  log(0, `驱动启动失败: ${err.message}\n${err.stack}`)
  process.exit(1)
})
