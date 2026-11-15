/*
 * NC-LINK Protocol Driver for JSON-SCADA
 * config.js — 配置加载模块
 *
 * 做两件事：
 *   1. 解析命令行参数（实例编号、日志级别、配置文件路径）
 *   2. 读取 json-scada.json 配置文件（拿到 MongoDB 地址和数据库名）
 *
 * 用法（跟所有 json-scada 驱动一模一样）：
 *   node index.js <实例编号> <日志级别> <配置文件路径>
 *   node index.js 1 1 ../conf/json-scada.json
 */

'use strict'

const Fs = require('fs')
const Path = require('path')

// ─────────────────────────────────────────────────────────
//  驱动常量（对应 mqtt-sparkplug 的 app-defs.js）
//  这些值在整个驱动里都会用到
// ─────────────────────────────────────────────────────────

const APP_NAME = 'NC-LINK'              // 驱动名称，必须跟 MongoDB 里 protocolDriver 字段一致
const AUTOTAG_PREFIX = 'NC-LINK'         // 自动建标签时的前缀
const AUTO_KEY_MULTIPLIER = 1000000      // _id 范围 = connectionNumber * 这个数

// ─────────────────────────────────────────────────────────
//  解析命令行参数
//
//  json-scada 所有驱动的统一约定：
//    参数1 = protocolDriverInstanceNumber（数字）
//    参数2 = logLevel（0=最少, 1=基础, 2=详细, 3=调试）
//    参数3 = json-scada.json 的路径（可选，默认 ../conf/json-scada.json）
// ─────────────────────────────────────────────────────────

const INSTANCE_NUMBER = parseInt(process.argv[2]) || 1
const LOG_LEVEL = /^\d+$/.test(process.argv[3] || '') ? Number(process.argv[3]) : 1
const CONFIG_FILE_PATH = process.argv[4] || Path.join(__dirname, '..', '..','conf', 'json-scada.json')

// ─────────────────────────────────────────────────────────
//  读取 json-scada.json
//
//  这个文件你已经见过了——就是你之前改 TLS 和 LDAP 的那个。
//  里面最重要的两个字段：
//    mongoConnectionString — MongoDB 的连接地址
//    mongoDatabaseName     — 数据库名（通常是 "json_scada"）
//    nodeName              — 当前节点名（冗余用）
// ─────────────────────────────────────────────────────────

function loadConfig() {
  let fileContent
  try {
    fileContent = Fs.readFileSync(CONFIG_FILE_PATH, 'utf8')
  } catch (err) {
    console.error(
      `[${APP_NAME}] 无法读取配置文件: ${CONFIG_FILE_PATH}\n` +
      `  错误: ${err.message}\n` +
      `  请确认文件存在，或者用第三个参数指定正确路径：\n` +
      `  node index.js 1 1 /你的路径/json-scada.json`
    )
    process.exit(1)
  }

  let jsConfig
  try {
    jsConfig = JSON.parse(fileContent)
  } catch (err) {
    console.error(
      `[${APP_NAME}] 配置文件 JSON 格式错误: ${CONFIG_FILE_PATH}\n` +
      `  错误: ${err.message}`
    )
    process.exit(1)
  }

  // 把命令行参数也塞进配置对象里，方便后面统一使用
  // （跟 mqtt-sparkplug 的 LoadConfig 做法一致）
  jsConfig.InstanceNumber = INSTANCE_NUMBER
  jsConfig.LogLevel = LOG_LEVEL
  jsConfig.ConfigFilePath = CONFIG_FILE_PATH

  // 给缺失的字段设默认值，防止后面代码报错
  jsConfig.mongoConnectionString = jsConfig.mongoConnectionString || 'mongodb://localhost:27017'
  jsConfig.mongoDatabaseName = jsConfig.mongoDatabaseName || 'json_scada'
  jsConfig.nodeName = jsConfig.nodeName || 'mainNode'

  // json-scada 的集合名称（硬编码，跟其他驱动保持一致）
  jsConfig.RealtimeDataCollectionName = 'realtimeData'
  jsConfig.ProtocolDriverInstancesCollectionName = 'protocolDriverInstances'
  jsConfig.ProtocolConnectionsCollectionName = 'protocolConnections'
  jsConfig.CommandsQueueCollectionName = 'commandsQueue'

  // MongoDB 连接选项（跟 mqtt-sparkplug 保持一致）
  jsConfig.MongoConnectionOptions = {
    appname: APP_NAME + ' ' + INSTANCE_NUMBER,
    maxPoolSize: 20,
  }

  return jsConfig
}

// ─────────────────────────────────────────────────────────
//  简单日志工具
//
//  json-scada 的 mqtt-sparkplug 用了一个 simple-logger.js，
//  我们做一个等效的，但更简单：
//    log(0, '...')  → 总是打印（最重要的信息）
//    log(1, '...')  → LogLevel >= 1 才打印（基础信息）
//    log(2, '...')  → LogLevel >= 2 才打印（详细信息）
//    log(3, '...')  → LogLevel >= 3 才打印（调试信息）
// ─────────────────────────────────────────────────────────

function log(level, ...args) {
  if (level <= LOG_LEVEL) {
    console.log(new Date().toISOString(), `[${APP_NAME}][${INSTANCE_NUMBER}]`, ...args)
  }
}

// ─────────────────────────────────────────────────────────
//  导出
// ─────────────────────────────────────────────────────────

module.exports = {
  // 常量
  APP_NAME,
  AUTOTAG_PREFIX,
  AUTO_KEY_MULTIPLIER,
  INSTANCE_NUMBER,
  LOG_LEVEL,

  // 函数
  loadConfig,
  log,
}
