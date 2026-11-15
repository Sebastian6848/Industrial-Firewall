/* Optional newline-delimited JSON transport. Every envelope carries a topic. */
'use strict'
const net = require('net')
const { StringDecoder } = require('string_decoder')
const { parseMessage } = require('./pdu')
const { log } = require('./config')
const MAX_BYTES = 1024 * 1024
let server
const activeConnections = new Map()
function start(connection, router, onDisconnect = () => {}) {
  server = net.createServer(socket => {
    const state = { buffer: '', guid: null, decoder: new StringDecoder('utf8'), queue: Promise.resolve(), pending: 0 }
    activeConnections.set(socket, state)
    socket.setTimeout(60000, () => socket.destroy())
    socket.on('data', chunk => {
      state.buffer += state.decoder.write(chunk)
      if (Buffer.byteLength(state.buffer) > MAX_BYTES) { socket.destroy(); return }
      let newline
      while ((newline = state.buffer.indexOf('\n')) !== -1) {
        const line = state.buffer.slice(0, newline).trim()
        state.buffer = state.buffer.slice(newline + 1)
        if (!line) continue
        if (++state.pending > 128) { socket.destroy(); return }
        state.queue = state.queue.then(async () => {
          if (socket.destroyed) return
          const envelope = parseMessage(line)
          if (!envelope || typeof envelope.topic !== 'string') { socket.destroy(); return }
          const pdu = envelope.payload ? parseMessage(JSON.stringify(envelope.payload)) : envelope
          if (!pdu) { socket.destroy(); return }
          const rawGuid = pdu.guid || ''
          const incomingGuid = connection.deviceAliases?.[rawGuid] || rawGuid
          if ((state.guid && incomingGuid && state.guid !== incomingGuid) || (!state.guid && envelope.topic !== 'Register/Request')) { socket.destroy(); return }
          if (!state.guid && Array.from(activeConnections.values()).some(other => other !== state && other.guid === incomingGuid)) { socket.destroy(); return }
          if (state.guid && !incomingGuid) pdu.guid = state.guid
          const result = await router(envelope.topic, pdu)
          if (!state.guid && incomingGuid && result && JSON.parse(result.payload).code === 'OK') state.guid = incomingGuid
          if (result) await write(socket, { topic: result.topic, payload: JSON.parse(result.payload) })
        }).catch(err => { log(0, 'TCP message rejected:', err.message); socket.destroy() }).finally(() => { state.pending-- })
      }
    })
    socket.on('error', err => log(1, 'TCP client:', err.message))
    socket.on('close', () => {
      activeConnections.delete(socket)
      if (state.guid) onDisconnect(state.guid)
    })
  })
  server.on('error', err => log(0, 'TCP server:', err.message))
  server.listen(connection.tcpListenPort ?? 8081, connection.tcpListenHost || '127.0.0.1')
  return server
}
function write(socket, envelope) {
  return new Promise((resolve, reject) => socket.write(JSON.stringify(envelope) + '\n', err => err ? reject(err) : resolve()))
}
function publish(topic, payload) {
  const pdu = typeof payload === 'string' ? parseMessage(payload) : payload
  for (const [socket, state] of activeConnections) {
    if (pdu?.guid && state.guid === pdu.guid && !socket.destroyed) {
      write(socket, { topic, payload: pdu }).catch(() => socket.destroy())
      return true
    }
  }
  return false
}
function stop() {
  for (const socket of activeConnections.keys()) socket.destroy()
  activeConnections.clear()
  if (server) server.close()
  server = null
}
module.exports = { start, stop, publish, getActiveConnections: () => activeConnections }
