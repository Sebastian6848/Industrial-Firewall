'use strict'
const { test } = require('node:test')
const assert = require('node:assert/strict')
const net = require('node:net')
const { once } = require('node:events')
const mqtt = require('mqtt')
const { parseMessage } = require('../pdu')
const Router = require('../router')
const Probe = require('../handlers/probe')
const Sample = require('../handlers/sample')
const Register = require('../handlers/register')
const AutoTag = require('../auto-tag')
const Mqtt = require('../mqtt-client')
const Tcp = require('../tcp-server')
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
async function until(predicate) {
  for (let i=0;i<200;i++) { if (predicate()) return; await delay(10) }
  throw new Error('Timed out waiting for expected operation')
}
function setup(options = {}, publish = () => true) {
  const docs=[], updates=[]
  const matches=(doc,q)=>Object.entries(q).every(([key,value])=>Number.isNaN(Number(value)) ? doc[key]===value : Number(doc[key])===Number(value))
  const collection={
    find(q) { return { toArray:async()=>docs.filter(x=>matches(x,q)) } },
    async insertOne(doc) { docs.push(doc); return { acknowledged:true } },
    async updateOne(q,change) { const doc=docs.find(x=>matches(x,q)); if(doc) { updates.push({q,change}); Object.assign(doc,change.$set) } return {matchedCount:doc?1:0} },
  }
  const context={ connection:{protocolConnectionNumber:1, ...options}, db:{collection:()=>collection},
    registry:new Map(), machineModels:new Map(), sampleChannels:new Map(), brokerExCid:'broker', publish }
  Router.initialize(context,{register:Register.handle,probe:Probe.handle,sample:Sample.handle,
    notify:async()=>null,query:async()=>null})
  return {context, docs, updates}
}
function model(id='v1') {
  return {version:id,devices:[{id:'machine',version:id,configs:[{id:'c0',type:'SAMPLE_CHANNEL',ids:[{id:'speed'},{id:'state'}]}],
    dataItems:[{id:'speed',type:'SPEED'},{id:'state',type:'STATUS'}]}]}
}
async function enroll(context, guid) {
  await Router.route('Register/Request',{guid,'@id':'r'})
  await Router.route('Probe/Version/'+guid,{guid,'@id':'v',version:'v1'})
  const request=context.registry.get(guid).probeQueryAtId
  await Router.route('Probe/Query/Response/'+guid,{'@id':request,probe:model()})
}
test('JSON parser rejects malformed envelopes and conflicting identities',()=>{
  for(const raw of ['null','[]','"a"','{','{"guid":"a","dev_uuid":"b"}','{"guid":42}']) assert.equal(parseMessage(raw),null)
  assert.equal(parseMessage('{"dev_uuid":"a"}').guid,'a')
  assert.equal(parseMessage('{"cli_uuid":"a"}').guid,'a')
  assert.equal(parseMessage(JSON.stringify({a:'x'.repeat(1024*1024)})),null)
  let deep={};for(let i=0;i<40;i++)deep={a:deep};assert.equal(parseMessage(JSON.stringify(deep)),null)
})
test('registration requires identity and topic/payload identities must agree',async()=>{
  const {context}=setup()
  assert.equal(await Router.route('Register/Request',{}),null)
  assert.equal(context.registry.size,0)
  await Router.route('Register/Request',{guid:'a'})
  assert.equal(await Router.route('Probe/Version/b',{guid:'a',version:'v1'}),null)
  assert.equal(context.registry.has('b'),false)
})
test('two devices with equal channel and object names remain isolated',async()=>{
  const {context,docs,updates}=setup()
  await enroll(context,'a');await enroll(context,'b')
  assert.equal(context.sampleChannels.size,2)
  assert.equal(docs.length,4)
  await Router.route('Sample/a/c0',{guid:'a',id:'c0',data:[[100,true]]})
  await Router.route('Sample/b/c0',{guid:'b',id:'c0',data:[[200,false]]})
  assert.deepEqual(updates.map(x=>x.q.protocolSourceCommonAddress),['a','a','b','b'])
  assert.equal(Number(docs.find(x=>x.protocolSourceCommonAddress==='a'&&x.protocolSourceObjectAddress==='speed').sourceDataUpdate.valueAtSource),100)
  assert.equal(Number(docs.find(x=>x.protocolSourceCommonAddress==='b'&&x.protocolSourceObjectAddress==='speed').sourceDataUpdate.valueAtSource),200)
})
test('invalid batch or spoofed channel never writes partial sample data',async()=>{
  const {context,updates}=setup();await enroll(context,'c')
  await Router.route('Sample/c/c0',{guid:'c',id:'other',data:[[1,2]]})
  await Router.route('Sample/c/c0',{guid:'c',id:'c0',data:[[1,2],[3]]})
  assert.equal(updates.length,0)
})
test('MTConnect column layout requires explicit profile and validates every column',()=>{
  const pdu={data:[{data:[1,2]},{data:[3,4]}]}
  assert.deepEqual(Sample.rowsFor(pdu,{sampleLayout:'mtconnect-columns'}),[[1,3],[2,4]])
  assert.throws(()=>Sample.rowsFor({data:[{data:[1]},{data:[2,3]}]},{sampleLayout:'mtconnect-columns'}))
})
test('model responses are correlated; duplicate responses and versions do not refetch',async()=>{
  const sent=[];const {context,docs}=setup({},(topic,payload)=>{sent.push({topic,payload});return true})
  await enroll(context,'d')
  const count=docs.length
  await Router.route('Probe/Query/Response/d',{'@id':'unrelated',probe:model()})
  await Router.route('Probe/Version/d',{guid:'d',version:'v1'})
  assert.equal(docs.length,count);assert.equal(sent.length,1)
  assert.equal(sent[0].topic,'Probe/Query/Request/d')
  assert.equal(await Router.route('Probe/Version/Response/d',{guid:'d'}),null)
})
test('explicit endpoint and device alias profiles work without weakening default matching',async()=>{
  const sent=[];const {context}=setup({topicStyle:'device_endpoint',deviceAliases:{modelRoot:'e'}},topic=>{sent.push(topic);return true})
  await enroll(context,'e')
  assert.equal(sent[0],'Probe/Query/Request/e/broker')
  await Router.route('Sample/modelRoot/c0',{guid:'modelRoot',id:'c0',data:[[1,2]]})
  assert.ok(context.registry.get('e').lastSampleAt)
})
test('real MQTT broker: registration, legacy exact topic, model, sample and root prefix',async(t)=>{
  const broker=require('aedes')()
  const server=net.createServer(broker.handle);server.listen(0,'127.0.0.1');await once(server,'listening')
  const url='mqtt://127.0.0.1:'+server.address().port
  const adapter=mqtt.connect(url,{clientId:'adapter-test'})
  const received=[];adapter.on('message',(topic,data)=>received.push({topic,pdu:JSON.parse(data)}))
  t.after(async()=>{Mqtt.stop();await adapter.endAsync(true);await new Promise(r=>broker.close(r));await new Promise(r=>server.close(r))})
  await once(adapter,'connect')
  await adapter.subscribeAsync(['factory/nclink/Register/Response/mqttdev','factory/nclink/Probe/Version/Response/mqttdev','factory/nclink/Probe/Query/Request/mqttdev'])
  const {context,updates}=setup({},Mqtt.publish)
  Mqtt.start({endpointURLs:[url],topicRoot:'factory/nclink',clientId:'driver-test'},Router.route)
  await until(()=>Mqtt.getClient().connected)
  await delay(100)
  await adapter.publishAsync('factory/nclink/Register/Request',JSON.stringify({cli_uuid:'mqttdev','@id':'r'}))
  await until(()=>received.some(x=>x.topic.endsWith('Register/Response/mqttdev')))
  await adapter.publishAsync('factory/nclink/Probe/Version/mqttdev',JSON.stringify({cli_uuid:'mqttdev',version:'v1','@id':'v'}))
  await until(()=>received.some(x=>x.topic.endsWith('Probe/Query/Request/mqttdev')))
  const request=received.find(x=>x.topic.endsWith('Probe/Query/Request/mqttdev')).pdu
  await adapter.publishAsync('factory/nclink/Probe/Query/Response/mqttdev',JSON.stringify({'@id':request['@id'],probe:model()}))
  await until(()=>context.registry.get('mqttdev').probeReceived)
  await adapter.publishAsync('factory/nclink/Sample/mqttdev/c0',JSON.stringify({dev_uuid:'mqttdev',id:'c0',data:[[42,1]]}))
  await until(()=>updates.length===2)
  assert.equal(received.filter(x=>x.topic.endsWith('Probe/Version/Response/mqttdev')).length,1)
  await adapter.publishAsync('factory/nclink/Sample/mqttdev/c0',JSON.stringify({guid:'other',id:'c0',data:[[99,1]]}))
  await delay(100);assert.equal(updates.length,2)
})
test('TCP JSON framing: split UTF-8, coalesced messages and bound identity',async(t)=>{
  const {context}=setup({},Tcp.publish)
  const server=Tcp.start({tcpListenPort:0},Router.route)
  await once(server,'listening')
  const socket=net.connect(server.address().port,'127.0.0.1');socket.on('error',()=>{})
  t.after(()=>{socket.destroy();Tcp.stop()})
  await once(socket,'connect')
  const replies=[];let buffer='';socket.on('data',data=>{buffer+=data.toString();let n;while((n=buffer.indexOf('\n'))>=0){replies.push(JSON.parse(buffer.slice(0,n)));buffer=buffer.slice(n+1)}})
  const registration=Buffer.from(JSON.stringify({topic:'Register/Request',cli_uuid:'tcpdev','@id':'注册'})+'\n')
  const split=registration.indexOf(Buffer.from('注册'))+1
  socket.write(registration.subarray(0,split));await delay(5);socket.write(registration.subarray(split))
  await until(()=>replies.length===1)
  assert.equal(replies[0].payload['@id'],'注册')
  socket.write(JSON.stringify({topic:'Probe/Version/tcpdev',guid:'tcpdev',version:'v1'})+'\n'+JSON.stringify({topic:'Notify/State/tcpdev',guid:'tcpdev',state:'online'})+'\n')
  await until(()=>context.registry.get('tcpdev').probeQueryPending)
  socket.write(JSON.stringify({topic:'Probe/Version/other',guid:'other',version:'v1'})+'\n')
  await once(socket,'close');assert.equal(context.registry.has('other'),false)
})
