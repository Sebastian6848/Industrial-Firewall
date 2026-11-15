/*
 * NC-LINK Protocol Driver for JSON-SCADA
 * mongo.js — MongoDB 连接管理模块
 *
 * 做三件事：
 *   1. 连接 MongoDB（带自动重连）
 *   2. 找到自己的驱动实例配置（protocolDriverInstances）
 *   3. 找到自己的连接配置（protocolConnections）
 *   4. 每30秒更新一次心跳，告诉系统"我还活着"
 *
 * 对应 mqtt-sparkplug 里 index.js 的 MongoDB 连接部分 + redundancy.js 的心跳部分
 */

'use strict'

const { MongoClient, Double } = require('mongodb')
const { APP_NAME, log } = require('./config')

// ─────────────────────────────────────────────────────────
//  全局状态（这个模块的内部状态）
// ─────────────────────────────────────────────────────────

let mongoClient = null      // MongoDB 客户端对象
let db = null               // 数据库对象
let driverInstance = null   // 当前驱动实例的配置文档
let connection = null       // 当前连接的配置文档
let heartbeatTimer = null   // 心跳定时器

// ─────────────────────────────────────────────────────────
//  connectMongo — 连接 MongoDB
//
//  参数：
//    jsConfig — 从 config.js 的 loadConfig() 拿到的配置对象
//
//  返回：成功返回 db 对象，失败抛异常
//
//  如果连接失败，调用方应该 catch 异常后重试
// ─────────────────────────────────────────────────────────

async function connectMongo(jsConfig) {
  log(1, '正在连接 MongoDB')

  mongoClient = new MongoClient(
    jsConfig.mongoConnectionString,
    jsConfig.MongoConnectionOptions
  )

  await mongoClient.connect()
  db = mongoClient.db(jsConfig.mongoDatabaseName)

  log(1, `MongoDB 连接成功，数据库: ${jsConfig.mongoDatabaseName}`)
  return db
}

// ─────────────────────────────────────────────────────────
//  loadDriverInstance — 读取当前驱动实例的配置
//
//  从 protocolDriverInstances 集合里找到：
//    protocolDriver = "NC-LINK"
//    protocolDriverInstanceNumber = 命令行传入的实例编号
//    enabled = true
//
//  这条文档需要你提前在 MongoDB 里手动插入
//  （README 里会写清楚怎么插）
//
//  如果找不到，说明 MongoDB 里还没注册这个驱动，程序退出并提示
// ─────────────────────────────────────────────────────────

async function loadDriverInstance(jsConfig) {
  const col = db.collection(jsConfig.ProtocolDriverInstancesCollectionName)

  driverInstance = await col.findOne({
    protocolDriver: APP_NAME,
    protocolDriverInstanceNumber: new Double(jsConfig.InstanceNumber),
    enabled: true,
  })

  if (!driverInstance) {
    log(0, `错误：找不到已启用的驱动实例配置（${APP_NAME} 实例 ${jsConfig.InstanceNumber}）`)
    log(0, `请先在 MongoDB 里插入驱动实例配置，参考 README.md`)
    process.exit(1)
  }

  log(1, `驱动实例配置已加载，实例编号 = ${jsConfig.InstanceNumber}`)
  return driverInstance
}

// ─────────────────────────────────────────────────────────
//  loadConnection — 读取连接配置
//
//  从 protocolConnections 集合里找到属于当前驱动实例的连接配置。
//  按你的需求，我们只支持一个连接（取第一个）。
//
//  这条文档也需要你提前手动插入。它包含：
//    - protocolConnectionNumber: 连接号（用来定位标签）
//    - tcpListenPort:            驱动监听的 TCP 端口（适配器连进来的端口）
//    - autoCreateTags:           是否自动建标签
//    - commandsEnabled:          是否允许下行指令
//
//  注意字段方向：因为我们是"代理器"角色，所以是 tcpListenPort（监听端口）
//  不是 tcpRemoteHost / tcpRemotePort（连接远端的地址）
// ─────────────────────────────────────────────────────────

async function loadConnection(jsConfig) {
  const col = db.collection(jsConfig.ProtocolConnectionsCollectionName)

  connection = await col.findOne({
    protocolDriver: APP_NAME,
    protocolDriverInstanceNumber: new Double(jsConfig.InstanceNumber),
    enabled: true,
  })

  if (!connection) {
    log(0, `错误：找不到已启用的连接配置（${APP_NAME} 实例 ${jsConfig.InstanceNumber}）`)
    log(0, `请先在 MongoDB 里插入连接配置，参考 README.md`)
    process.exit(1)
  }

  log(1, `连接配置已加载，连接号 = ${connection.protocolConnectionNumber}`)
  log(1, `MQTT broker: ${connection.endpointURLs ? connection.endpointURLs[0] : '(未配置)'}`)
  log(1, `  自动建标签: ${connection.autoCreateTags ? '是' : '否'}`)
  log(1, `  允许指令: ${connection.commandsEnabled ? '是' : '否'}`)

  return connection
}

// ─────────────────────────────────────────────────────────
//  startHeartbeat — 启动心跳
//
//  每30秒更新一次 protocolDriverInstances 集合里这个驱动的
//  activeNodeKeepAliveTimeTag 字段，告诉系统"我还活着"。
//
//  如果你的驱动崩溃了，这个时间戳就会停止更新，
//  json-scada 的其他组件可以据此判断驱动是否离线。
//
//  这是 json-scada 所有驱动都有的标准行为，参考 mqtt-sparkplug redundancy.js
// ─────────────────────────────────────────────────────────

function startHeartbeat(jsConfig) {
  const col = db.collection(jsConfig.ProtocolDriverInstancesCollectionName)

  async function beat() {
    try {
      await col.updateOne(
        { _id: driverInstance._id },
        {
          $set: {
            activeNodeName: jsConfig.nodeName,
            activeNodeKeepAliveTimeTag: new Date(),
          },
        }
      )
      log(3, '心跳已发送')
    } catch (err) {
      log(1, `心跳发送失败: ${err.message}`)
    }
  }

  // 立即跳一次，之后每30秒一次
  beat()
  heartbeatTimer = setInterval(beat, 30000)
  log(1, '心跳已启动（每30秒一次）')
}

// ─────────────────────────────────────────────────────────
//  stopHeartbeat — 停止心跳（程序退出时清理用）
// ─────────────────────────────────────────────────────────

function stopHeartbeat() {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer)
    heartbeatTimer = null
  }
}

// ─────────────────────────────────────────────────────────
//  getDb — 提供给其他模块拿 db 对象的接口
//
//  其他模块（比如 handlers/sample.js）需要写数据时，
//  调用 getDb() 拿到 db 对象，然后用 db.collection('realtimeData') 操作集合
// ─────────────────────────────────────────────────────────

function getDb() {
  return db
}

function getConnection() {
  return connection
}

function getDriverInstance() {
  return driverInstance
}

// ─────────────────────────────────────────────────────────
//  initialize — 一站式初始化（推荐用法）
//
//  index.js 调用这一个函数就完成所有 MongoDB 相关的初始化
// ─────────────────────────────────────────────────────────

async function initialize(jsConfig) {
  await connectMongo(jsConfig)
  await loadDriverInstance(jsConfig)
  await loadConnection(jsConfig)
  startHeartbeat(jsConfig)
}

// ─────────────────────────────────────────────────────────
//  导出
// ─────────────────────────────────────────────────────────

module.exports = {
  initialize,
  connectMongo,
  loadDriverInstance,
  loadConnection,
  startHeartbeat,
  stopHeartbeat,
  getDb,
  getConnection,
  getDriverInstance,
}
