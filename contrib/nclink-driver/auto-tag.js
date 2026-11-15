/*
 * NC-LINK Protocol Driver for JSON-SCADA
 * auto-tag.js — 自动建标签工具
 *
 * 改编自 json-scada 的 mqtt-sparkplug/auto-tag.js，
 * 保持跟 json-scada 标准实现一致，确保我们建的标签能被
 * cs_data_processor、Web HMI、Grafana 等其他模块识别。
 *
 * 主要功能：
 *   - 在 realtimeData 集合里自动创建标签
 *   - 标签的 _id 按规则生成（connectionNumber * 1000000 + 序号）
 *   - 标签包含 json-scada 要求的所有字段（约 40 个），缺一不可
 *
 * 何时调用：
 *   probe handler 收到机床模型 → 遍历模型里的每个数据项 → 调用本模块为每个数据项建标签
 *   sample handler 收到数据 → 如果发现某个数据项还没有对应标签，临时调用建一个
 */

'use strict'

const Mongo = require('mongodb')
const { log, AUTOTAG_PREFIX, AUTO_KEY_MULTIPLIER } = require('./config')

// ─────────────────────────────────────────────────────────
//  模块内部状态
// ─────────────────────────────────────────────────────────

let AutoKeyId = 0                  // 当前自增到的 _id 值
let ListCreatedTags = new Set()           // 已创建过的标签名，避免重复查库

// ─────────────────────────────────────────────────────────
//  NewTag — 生成一个全新的标签对象（带所有 json-scada 必需字段）
//
//  字段清单严格照抄 json-scada 的 mqtt-sparkplug/auto-tag.js，
//  缺任何一个字段都可能导致 cs_data_processor 处理异常。
//
//  调用 NewTag() 会自增 AutoKeyId，所以每次返回的 _id 不同
// ─────────────────────────────────────────────────────────

function NewTag() {
  AutoKeyId++

  return {
    _id: new Mongo.Double(AutoKeyId),
    protocolSourceASDU: '',
    protocolSourceCommonAddress: '',
    protocolSourceConnectionNumber: new Mongo.Double(0),
    protocolSourceObjectAddress: '',
    protocolSourceCommandUseSBO: false,
    protocolSourceCommandDuration: new Mongo.Double(0),
    alarmState: new Mongo.Double(-1.0),
    alarmRange: new Mongo.Double(0.0),
    description: '',
    ungroupedDescription: '',
    group1: '',
    group2: '',
    group3: '',
    stateTextFalse: '',
    stateTextTrue: '',
    eventTextFalse: '',
    eventTextTrue: '',
    origin: 'supervised',
    tag: '',
    type: 'analog',
    value: new Mongo.Double(0),
    valueString: '',
    valueJson: {},
    alarmDisabled: false,
    alerted: false,
    alarmed: false,
    alertState: '',
    annotation: '',
    commandBlocked: false,
    commandOfSupervised: new Mongo.Double(0.0),
    commissioningRemarks: '',
    formula: new Mongo.Double(0.0),
    frozen: false,
    frozenDetectTimeout: new Mongo.Double(0.0),
    hiLimit: new Mongo.Double(Number.MAX_VALUE),
    hihiLimit: new Mongo.Double(Number.MAX_VALUE),
    hihihiLimit: new Mongo.Double(Number.MAX_VALUE),
    historianDeadBand: new Mongo.Double(0.0),
    historianPeriod: new Mongo.Double(0.0),
    hysteresis: new Mongo.Double(0.0),
    invalid: true,
    invalidDetectTimeout: new Mongo.Double(60000.0),
    isEvent: false,
    kconv1: new Mongo.Double(1.0),
    kconv2: new Mongo.Double(0.0),
    location: null,
    loLimit: new Mongo.Double(-Number.MAX_VALUE),
    loloLimit: new Mongo.Double(-Number.MAX_VALUE),
    lololoLimit: new Mongo.Double(-Number.MAX_VALUE),
    notes: '',
    overflow: false,
    parcels: null,
    priority: new Mongo.Double(0.0),
    protocolDestinations: null,
    sourceDataUpdate: null,
    supervisedOfCommand: new Mongo.Double(0.0),
    substituted: false,
    timeTag: null,
    timeTagAlarm: null,
    timeTagAtSource: null,
    timeTagAtSourceOk: false,
    transient: false,
    unit: '',
    updatesCnt: new Mongo.Double(0.0),
    valueDefault: new Mongo.Double(0.0),
    zeroDeadband: new Mongo.Double(0.0),
  }
}

// ─────────────────────────────────────────────────────────
//  GetAutoKeyInitialValue — 查询当前连接号范围内最大的 _id
//
//  规则（跟 json-scada 一致）：
//    每个连接号有一个独立的 _id 范围 = [connNum * 1000000, (connNum+1) * 1000000)
//    比如 connectionNumber=200 → _id 在 200000000 ~ 200999999 之间
//
//  启动时先查 MongoDB 里这个范围最大的 _id，从那里继续自增。
//  这样多次重启驱动也不会产生 _id 冲突。
// ─────────────────────────────────────────────────────────

async function GetAutoKeyInitialValue(rtCollection, connectionNumber) {
  AutoKeyId = connectionNumber * AUTO_KEY_MULTIPLIER

  const upperBound = (connectionNumber + 1) * AUTO_KEY_MULTIPLIER

  const resLastKey = await rtCollection
    .find({
      _id: {
        $gt: AutoKeyId,
        $lt: upperBound,
      },
    })
    .sort({ _id: -1 })
    .limit(1)
    .toArray()

  if (resLastKey.length > 0 && '_id' in resLastKey[0]) {
    const existing = parseInt(resLastKey[0]._id)
    if (existing >= AutoKeyId) {
      AutoKeyId = existing
    }
  }

  log(1, `Auto-tag _id 起始值: ${AutoKeyId}（连接号 ${connectionNumber}）`)
  return AutoKeyId
}

// ─────────────────────────────────────────────────────────
//  AutoCreateTag — 自动创建一个标签
//
//  参数：
//    data              — 描述这个数据项的对象（来自 probe 模型或 sample 数据）
//      需要至少包含：
//        protocolSourceObjectAddress  数据项地址（如 "010302"）
//      可选包含：
//        type, description, unit, valueString, valueJson, ...
//    connectionNumber  — 当前连接号
//    rtDataCollection  — realtimeData 集合对象
//
//  返回：新创建的标签对象（如果已存在，返回 null 表示没创建）
//
//  逻辑：
//    1. 计算标签名（NC-LINK:连接号:数据地址）
//    2. 检查内存缓存，已建过就跳过
//    3. 查 MongoDB，已存在就跳过
//    4. 调 NewTag() 生成新文档，填字段后插入
// ─────────────────────────────────────────────────────────

async function AutoCreateTag(data, connectionNumber, rtDataCollection) {
  // ── 1. 计算标签名 ──
  // 格式：NC-LINK:连接号:数据地址
  // 例：NC-LINK:200:010302
  const tag = AUTOTAG_PREFIX + ':' + connectionNumber + ':' + data.protocolSourceCommonAddress + ':' + data.protocolSourceObjectAddress

  // ── 2. 内存缓存检查（避免重复查库） ──
  if (ListCreatedTags.has(tag)) {
    return null
  }

  // ── 3. 查 MongoDB 看是不是已经存在 ──
  const existing = await rtDataCollection
    .find({
      protocolSourceConnectionNumber: connectionNumber,
      protocolSourceObjectAddress: data.protocolSourceObjectAddress,
      protocolSourceCommonAddress: data.protocolSourceCommonAddress,
    })
    .toArray()

  if (existing.length > 0) {
    // 已存在，记录到缓存就好
    ListCreatedTags.add(tag)
    return null
  }

  // ── 4. 生成新标签 ──
  log(2, `自动建标签: ${tag}`)

  if (AutoKeyId + 1 >= (connectionNumber + 1) * AUTO_KEY_MULTIPLIER) throw new Error('Auto-tag ID range exhausted')
  const newTag = NewTag()
  newTag.protocolSourceConnectionNumber = new Mongo.Double(connectionNumber)
  newTag.protocolSourceObjectAddress = data.protocolSourceObjectAddress
  newTag.protocolSourceASDU = data?.asduAtSource || ''
  newTag.protocolSourceCommonAddress = data.protocolSourceCommonAddress
  newTag.tag = tag

  // 数据类型（模拟量/数字量），probe handler 会根据数据项类型推断后填进 data
  if (data.type) newTag.type = data.type

  if (newTag.type === 'analog') {
    newTag.unit = data?.unit || 'units'
  } else if (newTag.type === 'digital') {
    newTag.eventTextFalse = 'false'
    newTag.eventTextTrue = 'true'
    newTag.stateTextFalse = 'false'
    newTag.stateTextTrue = 'true'
  }

  // 分组（用于 Web HMI 树形展示）
  newTag.group1 = AUTOTAG_PREFIX + ':' + connectionNumber
  newTag.group2 = data?.group2 || ''
  newTag.group3 = data?.group3 || ''

  // 描述信息
  newTag.ungroupedDescription = data?.description || data.protocolSourceCommonAddress + ':' + data.protocolSourceObjectAddress
  newTag.description =
    data?.description ||
    newTag.group1 + '~' + newTag.group2 + '~' + newTag.ungroupedDescription

  // 初始值
  if (data?.value !== undefined && data?.value !== null) {
    newTag.value = new Mongo.Double(parseFloat(data.value) || 0)
  }
  newTag.valueString = data?.valueString || ''
  if (data?.valueJson) newTag.valueJson = data.valueJson

  newTag.invalid = true                 // 还没收到真实数据前，标记为 invalid
  newTag.priority = new Mongo.Double(3.0)

  // ── 插入 MongoDB ──
  try {
    const result = await rtDataCollection.insertOne(newTag)
    if (result.acknowledged) {
      ListCreatedTags.add(tag)
      return newTag
    } else {
      throw new Error('Tag insert was not acknowledged')
    }
  } catch (err) {
    throw new Error('Tag creation failed: ' + err.message)
  }
}

// ─────────────────────────────────────────────────────────
//  导出
// ─────────────────────────────────────────────────────────

module.exports = {
  NewTag,
  GetAutoKeyInitialValue,
  AutoCreateTag,
}
