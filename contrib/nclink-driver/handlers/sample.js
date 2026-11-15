/* NC-Link sample ingestion. Validate the entire batch before database writes. */
'use strict'
const Mongo = require('mongodb')
const { log, APP_NAME } = require('../config')
const { buildOK, buildNG, ERRORS } = require('../pdu')
function rowsFor(pdu, connection) {
  if (!Array.isArray(pdu.data) || !pdu.data.length || pdu.data.length > 4096) throw new Error('Invalid sample batch')
  if ((connection.sampleLayout || 'rows') === 'rows') return pdu.data
  if (connection.sampleLayout !== 'mtconnect-columns') throw new Error('Unknown sample layout')
  const columns = pdu.data.map(column => column?.data)
  if (columns.some(c => !Array.isArray(c) || !c.length || c.length !== columns[0].length) || columns[0].length > 4096) throw new Error('Invalid MTConnect columns')
  return columns[0].map((_, index) => columns.map(column => column[index]))
}
async function handle(pdu, context) {
  const id = pdu['@id'], guid = pdu.guid, channelId = pdu.id
  const channel = context.sampleChannels.get(JSON.stringify([guid, channelId]))
  if (!channel || !context.registry.get(guid)?.probeReceived) return buildNG(id, guid, 'Unknown device/channel or missing model', ERRORS.UNAVAILABLE)
  let rows
  try {
    rows = rowsFor(pdu, context.connection)
    if (!channel.ids.length || channel.ids.length > 2048 || rows.some(row => !Array.isArray(row) || row.length !== channel.ids.length)) throw new Error('Sample column count mismatch')
  } catch (err) { log(0, err.message); return buildNG(id, guid, err.message, ERRORS.UNAVAILABLE) }
  const latest = rows.at(-1)
  const now = new Date()
  const suppliedTime = pdu.timestamp || pdu.startTime || pdu.beginTime
  const parsedTime = suppliedTime ? Date.parse(suppliedTime) : NaN
  const sourceTime = Number.isFinite(parsedTime) ? new Date(parsedTime + (rows.length - 1) * channel.sampleInterval) : now
  const collection = context.db.collection('realtimeData')
  for (let i = 0; i < channel.ids.length; i++) {
    const value = latest[i]
    const numeric = typeof value === 'boolean' ? Number(value) : (typeof value === 'number' || (typeof value === 'string' && value.trim()) ? Number(value) : NaN)
    const update = {
      valueAtSource: new Mongo.Double(Number.isFinite(numeric) ? numeric : 0),
      valueStringAtSource: typeof value === 'object' ? JSON.stringify(value) : String(value),
      valueJsonAtSource: value && typeof value === 'object' ? JSON.stringify(value) : null,
      asduAtSource: 'VALUE', causeOfTransmissionAtSource: '20',
      timeTagAtSource: sourceTime, timeTagAtSourceOk: Number.isFinite(parsedTime), timeTag: now,
      originator: APP_NAME + '|' + context.connection.protocolConnectionNumber + '|sample|' + guid + '|' + channelId,
      invalidAtSource: value === null, transientAtSource: false, notTopicalAtSource: false,
      overflowAtSource: false, blockedAtSource: false, substitutedAtSource: false,
    }
    const result = await collection.updateOne({
      protocolSourceConnectionNumber: context.connection.protocolConnectionNumber,
      protocolSourceCommonAddress: guid, protocolSourceObjectAddress: channel.ids[i],
    }, { $set: { sourceDataUpdate: update } })
    if (result.matchedCount !== 1) throw new Error('Sample tag missing or ambiguous')
  }
  context.registry.get(guid).lastSampleAt = now
  return buildOK(id, guid)
}
module.exports = { handle, rowsFor }
