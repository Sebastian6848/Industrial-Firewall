/*
 * NC-LINK Protocol Driver for JSON-SCADA
 * handlers/probe.js — 模型侦测处理器（按国标重写版）
 *
 * 国标规定的角色和方向：
 *
 *   1. Probe/Version
 *      方向：适配器 → 代理器（我们）
 *      内容：适配器主动告知"我的模型版本号是 v1.3"
 *      我们要做：缓存版本号，对比是否变化，发现变化就标记"需要重新拉模型"
 *      响应：可选，回 OK 即可
 *
 *   2. Probe/Query/Request
 *      方向：代理器（我们）→ 适配器
 *      内容：我们主动发起"请把完整的模型给我"
 *
 *   3. Probe/Query/Response
 *      方向：适配器 → 代理器（我们）
 *      内容：适配器把完整模型推过来（响应我们的 Request）
 *      我们要做：保存模型 + 自动建标签
 *      响应：本身就是响应，不需要再回
 *
 *   4. Probe/Set/Request
 *      方向：应用系统 → 代理器 → 适配器
 *      内容：应用系统想改适配器的模型
 *      我们要做：暂时拒绝（可信网关考虑）
 *
 *  消息类型由已校验的主题确定，模型响应按设备和 @id 关联。
 */

'use strict'

const { log } = require('../config')
const { buildOK, buildNG, ERRORS } = require('../pdu')
const { AutoCreateTag } = require('../auto-tag')

// ─────────────────────────────────────────────────────────
//  handle — 入口，使用路由器提供的主题子类型
// ─────────────────────────────────────────────────────────

async function handle(pdu, context, subtype) {
  const idLower = pdu.idLower || ''

  //topic 关键字判断
  if (subtype=='Version') {
    return await handleVersion(pdu, context)
  }

  if (subtype == 'Set') {
    return await handleSet(pdu, context)
  }

  if (subtype =='Query') {
    return await handleQueryResponse(pdu, context)
  }
  log(1, `无法识别的 probe 消息: ${JSON.stringify(pdu).slice(0, 200)}`)
  return buildNG(pdu['@id'], pdu.guid, 'Unknown probe message', ERRORS.UNKNOWN_COMMAND)
}

// ─────────────────────────────────────────────────────────
//  handleVersion — 处理适配器主动推送的版本号
//
//  消息长这样（国标 PDU 定义，表26）：
//    {"@id":"some_mid_001", "guid":"dev_uuid", "version":"v1.0.1"}
//
//  我们的工作：
//    1. 拿到适配器报告的新版本号
//    2. 跟我们之前缓存的版本号对比
//    3. 如果不一致（或第一次收到），标记"需要重新拉取模型"
//    4. 回一个 OK 响应（国标说可选，但回了没坏处）
// ─────────────────────────────────────────────────────────

async function handleVersion(pdu, context) {
  const id = pdu['@id']
  const guid = pdu.guid
  const version = pdu.version || ''
  const responseTopic = 'Probe/Version/Response/' + guid
  log(1, `收到版本号校对: guid=${guid}, version=${version}`)

  if (!guid) {
    return buildNG(id, '', 'Missing guid', ERRORS.UNKNOWN_COMMAND)
  }

  // ── 1. 从 context 拿出已缓存的模型版本 ──
  if (!context.machineModels) context.machineModels = new Map()
  const cached = context.machineModels.get(guid)
  const cachedVersion = context.registry.get(guid)?.modelVersion

  // ── 2. 对比版本 ──
  let needRefetch = false
  if (!cachedVersion) {
    log(1, `首次收到 guid=${guid} 的版本号`)
    needRefetch = true
  } else if (cachedVersion !== version) {
    log(1, `guid=${guid} 版本号变化: ${cachedVersion} → ${version}`)
    needRefetch = true
  } else {
    log(2, `guid=${guid} 版本号一致，无需更新模型`)
  }

  // ── 3. 标记需要重新拉模型 ──
  // 真正的拉取动作不在这里做，由其他模块（比如 sample handler 或定时任务）
  // 看到这个标记后，再向适配器发 Probe/Query/Request
  if (needRefetch && context.registry) {
    const entry = context.registry.get(guid)
    if (entry) {
      entry.needRefetchModel = true
      entry.reportedVersion = version
    }
  }
  //向适配器所要模型文件， 走 Probe/Query/Request
  if (needRefetch && (!context.registry.get(guid)?.probeQueryPending || Date.now() - context.registry.get(guid).probeQuerySentAt > 30000)) {
    await sendProbeQueryRequest(guid, context)
  }
  // ── 4. 回响应（按国标表27） ──
  // 把收到的 version 原样回一份，告诉适配器"我们记下了"
  return {
    topic : 'Probe/Version/Response/' + guid,
    payload : buildOK(id, guid, null, { version })
  }
}
// ─────────────────────────────────────────────────────────
//  handleQueryResponse — 适配器推送完整模型（响应我们的 Request）
//
//  消息长这样（国标 PDU 定义，表29）：
//    {"@id":"some_mid_001", "code":"OK", "probe": {...完整模型...}}
//
//  我们的工作：
//    1. 提取 probe 字段（兼容师姐风格的 privateInfo.probe）
//    2. 保存到 context.machineModels[guid]
//    3. 遍历模型，自动建标签
//    4. 清除 registry 里的 needRefetchModel 标记
//
//  注意：这本身就是响应消息，按 NC-Link 标准我们不需要再回响应。
//  但师姐的代理器代码会等响应，所以我们还是回一个简单的 OK。
// ─────────────────────────────────────────────────────────

async function handleQueryResponse(pdu, context) {
  const id = pdu['@id']
  const guid = pdu.guid

  // 提取模型（兼容国标和师姐两种格式）
  const probeModel = pdu.probe || pdu.privateInfo?.probe || pdu.privateInfo

  if (!probeModel || typeof probeModel !== 'object') {
    log(1, `Probe/Query/Response 缺少 probe 字段`)
    return 0
  }

  log(1, `收到适配器模型: guid=${guid}`)
  const version = probeModel.version || probeModel.devices?.[0]?.version
  if (!version) {
    log(0, `模型无效：缺少 devices[0].version，丢弃此模型。guid=${guid}`)
    // 不建标签、不更新版本。保持 needRefetchModel/probeQueryPending 状态，
    // 留给下次版本校对或超时重发再拉一次。
    if (context.registry) {
      const entry = context.registry.get(guid)
      if (entry) entry.probeQueryPending = false   // 失败也算结束，允许下次重拉
    }
    return null
  }
  const entry = context.registry.get(guid)
  if (!entry?.probeQueryPending || pdu['@id'] !== entry.probeQueryAtId || Date.now() - entry.probeQuerySentAt > 30000) {
    log(0, '拒绝未配对或已超时的模型响应'); return null
  }
  if (entry.reportedVersion && String(version) !== String(entry.reportedVersion)) {
    log(0, '拒绝与已报告版本不一致的模型'); return null
  }
  const channels = new Map()
  const devicesForChannels = Array.isArray(probeModel.devices) ? probeModel.devices : [probeModel]
  for (const device of devicesForChannels) extractSampleChannels(device, channels, guid)
  // Do not mark a model usable before all of its tags were created.
  entry.probeReceived = false
  await createTagsFromModel(probeModel, context, guid)
  for (const [key, value] of context.sampleChannels) if (value.guid === guid) context.sampleChannels.delete(key)
  for (const [key, value] of channels) context.sampleChannels.set(key, value)
  context.machineModels.set(guid, probeModel)
  Object.assign(entry, { probeReceived: true, needRefetchModel: false, modelVersion: version,
    probeQueryPending: false, probeQueryAtId: null })

}

// ─────────────────────────────────────────────────────────
//  handleSet — 模型设置请求（拒绝）
//
//  可信网关角度：不允许外部修改适配器配置
// ─────────────────────────────────────────────────────────

async function handleSet(pdu, context) {
  const id = pdu['@id']
  const guid = pdu.guid

  log(1, `拒绝 Probe/Set 请求: guid=${guid}`)
  return buildNG(id, guid, 'Probe/Set not allowed by gateway policy', ERRORS.UNAVAILABLE)
}

// ─────────────────────────────────────────────────────────
//  createTagsFromModel — 遍历机床模型，给每个数据项建标签
//  （这部分逻辑没变，跟上一版一样）
// ─────────────────────────────────────────────────────────

async function createTagsFromModel(probeModel, context, guid) {
  const rtCollection = context.db.collection('realtimeData')
  const connNum = context.connection.protocolConnectionNumber

  let count = 0
  // 初始化采样通道索引
  if (!context.sampleChannels) context.sampleChannels = new Map()
  const devices = Array.isArray(probeModel.devices)
    ? probeModel.devices
    : [probeModel]

  const objects = new Set()
  async function visit(node, deviceId, componentId, depth = 0) {
    if (depth > 24) throw new Error('Model nesting limit')
    for (const item of (node.dataItems || [])) {
      if (typeof item.id !== 'string' || !item.id || objects.has(item.id)) throw new Error('Invalid or duplicate model data item')
      objects.add(item.id)
      const ok = await createOneTag(item, deviceId, componentId, connNum, rtCollection, guid)
      if (ok) count++
    }
    for (const child of (node.components || [])) await visit(child, deviceId, componentId + '/' + child.id, depth + 1)
  }
  for (const device of devices) await visit(device, device.id || '', '')

  return count
}
//这里初始化不同的数据类型，好在jsonscada里存储
let array_digital = ['AUTO_MODE','AXIS_TOREFPOINT','BLOCK_SKIP_MODE','COOLANT_ON','CYCLE_START','DOOR_CLOSED',
    'EDIT_MODE','EMG','FEED_HOLD','HANDLE_MODE','INCREMENTAL_MODE','JOG_MODE','LIGHTING_ON','LUBRICANT_ON',
    'MACHINE_LOCKED','MDI_MODE','MST_LOCKED','OPT_STOP_MODE','REF_MODE','RESET_MODE','SINGLE_BLOCK_MODE',
    'TOOL_CHANGING',]

let array_analog = ["ACCELERATION","ANGLE",'ANGULAR_ACCELERATION',"ANGULAR_VELOCITY","CONCENTRATION","CONDUCTIVITY","CURRENT","DISPLACEMENT",
    "ENERGY",'FLOW','FREQUENCY','LENGTH','MASS','PERIOD','POSITION','POWER','PRESSURE','RESISTANCE','ROTATING_SPEED','SPEED','TEMPERATURE',
    'TORQUE','VISCOSITY','VOLT_AMPERE','SERIAL_NUMBER','UPPER_LIMIT','AXIS_BACKLASH','AXIS_LOAD','COMPACITY','FEED_OVERRIDE','FEED_SPEED',
    'PATH_LEFT_LENGTH','PROGRAM_NUMBER','RAPID_OVERRIDE','RATE','RESIDUAL','SPINDLE_OVERRIDE','SPINDLE_SPEED','TOOL_NUMBER','TOOL_POSITION',]

let array_string = ['CATAGORY','CREATE_TIME','CREATOR','IP','MANUFACTURER','MODEL','NAME','STATUS','USER_ROLE','VERSION',
    'WORK_MODE','CHIP_REMOVAL','CONSOLE','FIXTURE_MODE','LINE_NUMBER','PART_COUNT','PROGRAM','PROGRAM_MODE','SITE',
    'SPINDLE_MODE','SUBPROGRAM','TOOL_CHANGE']

let array_json = ['PARAMETER','VARIABLE','WARNING','COORDINATE','FILE','PART','SHELF_UNIT','TOOL','TOOL_PARAM',]

async function createOneTag(item, deviceId, componentId, connNum, rtCollection, guid) {
  if (!item.id) {
    log(2, `跳过没有 id 的 dataItem`)
    return false
  }
  const itemType = String(item.type || '').toUpperCase()
  let tagType=''
  if (array_analog.includes(itemType)){
    tagType='analog'
  } else if (array_digital.includes(itemType)){
    tagType='digital'
  } else if (array_string.includes(itemType)){
    tagType='string'
  } else if (array_json.includes(itemType)){
    tagType='json'
  } else {
    log(2,`用户自建${itemType}属性，默认为string`)
    tagType='string'
  }
  //let tagType = 'analog'
  //if (itemType.includes('event') || itemType.includes('state') || itemType.includes('bool')) {
    //tagType = 'digital'
  //}

  const data = {
    protocolSourceObjectAddress: item.id,
    protocolSourceCommonAddress: guid,
    type: tagType,
    description: item.description || item.name || item.id,
    unit: item.units || item.unit || '',
    group2: deviceId,
    group3: componentId,
    asduAtSource: item.type || '',
  }

  const result = await AutoCreateTag(data, connNum, rtCollection)
  return result !== null
}

module.exports = {
  handle,
}


// 递归遍历 device/component 的 configs，提取采样通道
function extractSampleChannels(node, channels, guid) {
  for (const cfg of (node.configs || [])) {
    if (cfg.type === 'SAMPLE_CHANNEL') {
      // 把 ids 数组里的 id 提取出来（每个元素是 {id: "010302"} 这种对象）
      const idsList = (cfg.ids || []).map(item =>
        typeof item === 'string' ? item : item.id
      )
      const key = JSON.stringify([guid, cfg.id])
      if (typeof cfg.id !== 'string' || !cfg.id || channels.has(key) || !idsList.length || idsList.some(id => typeof id !== 'string' || !id) || new Set(idsList).size !== idsList.length) {
        throw new Error('Invalid or duplicate sample channel')
      }
      channels.set(key, {
        guid,
        channelId: cfg.id,
        sampleInterval: cfg.sampleInterval || 1000,
        uploadInterval: cfg.uploadInterval || 1000,
        ids: idsList,
      })
      log(1, `登记采样通道: ${cfg.id}, ${idsList.length}个数据项`)
    }
  }
  // 递归子组件
  for (const sub of (node.components || [])) {
    extractSampleChannels(sub, channels, guid)
  }
}
  // 判断不出来



// 主动向适配器请求模型文件（#5）。由 handleVersion 在 needRefetch 时调用。
async function sendProbeQueryRequest(devUuid, context) {
  // 借 scadaHostId 作 NC-Link 代理器的终端标识符(ex_cid)
  const exCid = context.brokerExCid

  // @id：请求/响应配对用，生成唯一值
  const atId = 'probe_query_' + devUuid + '_' + Date.now()

  // topic：Probe/Query/Request/dev_uuid/ex_cid
  const topic = 'Probe/Query/Request/' + devUuid + (context.connection.topicStyle === 'device_endpoint' ? '/' + exCid : '')

  // PDU（按表28）：@id 应存在、guid=dev_uuid 应存在、privateInfo 可选
  const payload = {
    '@id': atId,
    'guid': devUuid,
    'privateInfo': null,
  }

  // 记录"已发出拉取请求，等 response"（可选，防重复发、便于排查）
  if (context.registry) {
    const entry = context.registry.get(devUuid)
    if (entry) {
      entry.probeQueryPending = true
      entry.probeQueryAtId = atId
      entry.probeQuerySentAt = Date.now()
    }
  }

  const ok = context.publish(topic, payload)
  if (!ok) { const entry = context.registry?.get(devUuid); if (entry) entry.probeQueryPending = false }
  log(1, `已向适配器请求模型: ${topic}${ok ? '' : '（发送失败/未连接）'}`)
  return ok
}
