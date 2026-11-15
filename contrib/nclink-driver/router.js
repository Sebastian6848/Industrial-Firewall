/* NC-Link routing: topic structure and payload identity are checked before handlers. */
'use strict'
const { log } = require('./config')
const { buildNG, ERRORS } = require('./pdu')
let context, handlers
function initialize(ctx, h) { context = ctx; handlers = h }
function canonical(id) { return context.connection.deviceAliases?.[id] || id }
function responseTopic(prefix, guid) {
  return prefix + guid + (context.connection.topicStyle === 'device_endpoint' ? '/' + context.brokerExCid : '')
}
async function route(topic, incoming) {
  if (!handlers || typeof topic !== 'string' || !incoming || typeof incoming !== 'object') return null
  const s = topic.split('/')
  if (s.some(x => !x || /[\0+#]/.test(x))) return null
  const pdu = { ...incoming }
  let kind, device, endpoint, prefix
  if (topic === 'Register/Request') { kind = 'register'; prefix = 'Register/Response/' }
  else if (s[0] === 'Probe' && s[1] === 'Version' && s.length === 3 && s[2] !== 'Response') {
    kind = 'version'; device = s[2]; prefix = 'Probe/Version/Response/'
  } else if (s[0] === 'Probe' && s[1] === 'Version' && s[2] === 'Response') return null
  else if (s[0] === 'Probe' && ['Query','Set'].includes(s[1]) && ['Request','Response'].includes(s[2]) && [4,5].includes(s.length)) {
    device = s[3]; endpoint = s[4]
    if (s[1] === 'Query' && s[2] === 'Response') kind = 'model'
    else if (s[1] === 'Set' && s[2] === 'Request') { kind = 'model_set'; prefix = 'Probe/Set/Response/' }
    else return null
  } else if (s[0] === 'Sample' && s.length === 3) { kind = 'sample'; device = s[1]; endpoint = s[2] }
  else if (s[0] === 'Notify' && s[1] === 'State' && s.length === 3) { kind = 'notify'; device = s[2] }
  else if (s[0] === 'Query' && s[1] === 'Request' && [3,4].includes(s.length)) {
    kind = 'query'; device = s[2]; endpoint = s[3]; prefix = 'Query/Response/'
  } else return null // Includes our own responses; never publish reply loops.
  if (device && pdu.guid && canonical(device) !== canonical(pdu.guid)) {
    log(0, '拒绝主题与报文设备身份冲突'); return null
  }
  pdu.guid = canonical(pdu.guid || device || '')
  if (!pdu.guid) { log(0, '拒绝缺少设备身份的消息'); return null }
  if (kind !== 'register' && !context.registry.has(pdu.guid)) { log(0, '拒绝未注册设备消息'); return null }
  if (kind === 'sample' && pdu.id !== endpoint) { log(0, '拒绝主题与报文通道冲突'); return null }
  let result
  try {
    if (kind === 'register') result = await handlers.register(pdu, context)
    if (kind === 'version') result = await handlers.probe(pdu, context, 'Version')
    if (kind === 'model') result = await handlers.probe(pdu, context, 'Query')
    if (kind === 'model_set') result = await handlers.probe(pdu, context, 'Set')
    if (kind === 'sample') result = await handlers.sample(pdu, context)
    if (kind === 'notify') result = await handlers.notify(pdu, context)
    if (kind === 'query') result = await handlers.query(pdu, context)
  } catch (err) {
    log(0, 'NC-Link handler failed:', err.message)
    result = buildNG(pdu['@id'], pdu.guid, 'Internal error', ERRORS.INTERNAL_ERROR)
  }
  // Pushes and responses never elicit another publish on their input topic.
  if (!prefix || !result) return null
  const response = typeof result === 'string' ? result : result.payload
  if (!response) return null
  return { topic: responseTopic(prefix, device || pdu.guid), payload: response }
}
function disconnect(guid) {
  context.registry.delete(guid)
  context.machineModels.delete(guid)
  for (const [key, channel] of context.sampleChannels) if (channel.guid === guid) context.sampleChannels.delete(key)
}
module.exports = { initialize, route, responseTopic, disconnect }
