<style>
.suite-toolbar {display:flex;flex-wrap:wrap;gap:8px;padding:16px 0}.suite-card {padding:20px;margin-bottom:16px}.suite-title {font-size:22px;font-weight:600}.suite-status {padding:12px;border-left:4px solid #167d8d;background:#eef7f8;margin:12px 0}.suite-result {max-height:480px;overflow:auto}.suite-result td {white-space:pre-wrap;word-break:break-word}.suite-nav {margin:20px 0}
</style>
<div class="content-box suite-card">
 <div class="suite-title"><i class="fa fa-industry"></i> 工业安全管理</div>
 <p>设备完整性检查、网关侧访问隔离与多设备策略管理</p>
 <div id="suiteStatus" class="suite-status" role="status">正在查询运行状态…</div>
 <ul class="nav nav-tabs suite-nav">
  <li class="active"><a href="#suite-settings" data-toggle="tab">基础设置</a></li>
  <li><a href="#suite-group" data-toggle="tab">设备分组</a></li>
  <li><a href="#suite-rule" data-toggle="tab">访问矩阵</a></li>
  <li><a href="#suite-node" data-toggle="tab">集中管理</a></li>
 </ul>
 <div class="tab-content">
  <div class="tab-pane active" id="suite-settings">
   {{ partial('layout_partials/base_form', ['fields':general, 'id':'suiteGeneral']) }}
   <div class="suite-toolbar"><button class="btn btn-primary" id="suiteSave">保存设置</button>
    <button class="btn btn-default suite-operation" data-operation="integrity_baseline" data-confirm="重新建立基线将接受当前文件状态，请确认这些文件来自可信版本。">建立完整性基线</button>
    <button class="btn btn-default suite-operation" data-operation="integrity_check">立即校验</button>
    <button class="btn btn-default suite-operation" data-operation="logs">查看审计记录</button>
   </div>
   <p class="text-muted">完整性检查使用软件基线。硬件可信计算尚未接入。</p>
  </div>
 <div class="tab-pane" id="suite-group">
{{ partial('layout_partials/base_bootgrid_table', groupGrid) }}
 </div>
 <div class="tab-pane" id="suite-rule">
{{ partial('layout_partials/base_bootgrid_table', ruleGrid) }}
<div class="suite-toolbar"><button class="btn btn-default suite-operation" data-operation="isolation_preview">预览策略</button><button class="btn btn-primary suite-operation" data-operation="isolation_apply" data-confirm="新策略将限制纳管设备间的新连接，请确认管理来源网络已正确设置。">应用策略</button><button class="btn btn-default suite-operation" data-operation="isolation_rollback" data-confirm="将恢复上一次已应用的隔离策略。">恢复上次策略</button></div><p class="text-muted">仅约束经过网关的流量。现有会话正常到期后使用新策略；回退不改动编辑区配置。</p> </div>
 <div class="tab-pane" id="suite-node">
{{ partial('layout_partials/base_bootgrid_table', nodeGrid) }}
<div class="suite-toolbar"><button class="btn btn-default suite-operation" data-operation="fleet_status">查询设备状态</button><button class="btn btn-default suite-operation" data-operation="fleet_logs">集中查看日志</button><button class="btn btn-default suite-operation" data-operation="fleet_preview">预览下发策略</button><button class="btn btn-primary suite-operation" data-operation="fleet_deploy" data-confirm="将向选中的设备下发本机保存的访问矩阵，并替换其项目隔离配置。">向选中设备下发策略</button></div><p class="text-muted">批量下发前先保存本机设置并预览。仅分发本项目隔离策略，设备连接凭据不随策略分发。</p> </div>
 </div>
 <div id="suiteMessage" class="alert" style="display:none" role="status"></div>
 <div class="suite-result"><table class="table table-striped" id="suiteResult"></table></div>
</div>
{{ partial('layout_partials/base_dialog', ['fields':group, 'id':groupGrid['edit_dialog_id'], 'label':'设备组']) }}
{{ partial('layout_partials/base_dialog', ['fields':rule, 'id':ruleGrid['edit_dialog_id'], 'label':'访问规则']) }}
{{ partial('layout_partials/base_dialog', ['fields':node, 'id':nodeGrid['edit_dialog_id'], 'label':'受管设备']) }}
<script>
$(function() {
 function showMessage(message, error) {$('#suiteMessage').removeClass('alert-success alert-danger').addClass(error ? 'alert-danger':'alert-success').text(message).show();}
 function status() {ajaxGet('/api/industrialsuite/service/status', [], function(data) {
  if (data.status !== 'ok') {$('#suiteStatus').text(data.message || '暂时无法获取运行状态');return;}
  const integrity=data.integrity || {};
  const label=integrity.status==='uninitialized' ? '尚未建立基线' : (integrity.healthy ? '正常':'发现文件变化');
  $('#suiteStatus').text('软件完整性：'+label+' · 已应用隔离规则：'+data.isolation_rule_count+' 条');
 });}
 function stringify(value) {return value === null || value === undefined ? '' : (typeof value === 'object' ? JSON.stringify(value) : String(value));}
 function displayCell(key,value){if(typeof value==='boolean')return value?'是':'否';if(['type','action'].includes(key))return ({pass:'允许',block:'阻断',drop:'阻断',alert:'告警'})[value]||stringify(value);if(key==='status')return ({ok:'正常',error:'失败',uninitialized:'未建立基线'})[value]||stringify(value);if(key==='direction')return ({in:'入站',out:'出站'})[value]||stringify(value);return stringify(value);}
 function render(data) {
  const table=$('#suiteResult').empty();
  let rows=data.rules || data.rows || data.changes || data.nodes;
  if (!rows) {rows=[{结果:data.healthy===true ? '校验正常' : (data.message || data.status), 文件数量:data.file_count,规则数量:data.rule_count}];}
  if (!rows.length) {table.append($('<tr>').append($('<td>').text('没有匹配记录')));return;}
  const columns=Array.from(new Set(rows.flatMap(row=>Object.keys(row))));
  const labels={from:'源地址',to:'目标地址',type:'动作',protocol:'协议',to_port:'端口',descr:'说明',path:'文件',reason:'变化',event:'事件',time:'时间',status:'状态',name:'设备',data:'结果',message:'信息',uuid:'标识',ipprotocol:'地址类型',direction:'方向',quick:'立即匹配',log:'记录日志',statetype:'会话状态'};
  const header=$('<tr>');columns.forEach(key=>header.append($('<th>').text(labels[key] || key)));table.append($('<thead>').append(header));
  const body=$('<tbody>');rows.forEach(row=>{const tr=$('<tr>');columns.forEach(key=>tr.append($('<td>').text(displayCell(key,row[key]))));body.append(tr);});table.append(body);
 }
 $('#suiteSave').on('click',function(){saveFormToEndpoint('/api/industrialsuite/settings/set','suiteGeneral',function(){showMessage('设置已保存。隔离策略需另外预览并应用。',false);status();},true);});
 $('.suite-operation').on('click',function(){
  const button=$(this), operation=button.data('operation');
  function execute() {
   let ids=[];
   if (operation==='fleet_deploy' || operation==='fleet_preview') {
    ids=$('#{{nodeGrid["table_id"]}}').bootgrid('getSelectedRows');
    if (!ids.length) {showMessage('请先勾选目标设备。',true);return;}
   }
   button.prop('disabled',true);
   if (operation==='logs') {ajaxGet('/api/industrialsuite/service/logs',[],function(data){render(data);button.prop('disabled',false);});return;}
   $.ajax({url:'/api/industrialsuite/service/run',type:'POST',contentType:'application/json',data:JSON.stringify({operation:operation,node_ids:ids}),dataType:'json'})
    .done(function(data){showMessage(data.message || (data.status==='ok' ? '操作完成':'请检查配置与运行状态'),data.status!=='ok');render(data);status();})
    .fail(function(){showMessage('请求失败，请检查连接与权限。',true);}).always(function(){button.prop('disabled',false);});
  }
  if (!button.data('confirm') || window.confirm(button.data('confirm'))) {execute();}
 });
$('#{{groupGrid["table_id"]}}').UIBootgrid({search:'/api/industrialsuite/settings/search_group',get:'/api/industrialsuite/settings/get_group/',set:'/api/industrialsuite/settings/set_group/',add:'/api/industrialsuite/settings/add_group',del:'/api/industrialsuite/settings/del_group/',toggle:'/api/industrialsuite/settings/toggle_group/'});
$('#{{ruleGrid["table_id"]}}').UIBootgrid({search:'/api/industrialsuite/settings/search_rule',get:'/api/industrialsuite/settings/get_rule/',set:'/api/industrialsuite/settings/set_rule/',add:'/api/industrialsuite/settings/add_rule',del:'/api/industrialsuite/settings/del_rule/',toggle:'/api/industrialsuite/settings/toggle_rule/',options:{formatters:{policyAction:function(column,row){return row.action==='pass'?'允许':'阻断';}}}});
$('#{{nodeGrid["table_id"]}}').UIBootgrid({search:'/api/industrialsuite/settings/search_node',get:'/api/industrialsuite/settings/get_node/',set:'/api/industrialsuite/settings/set_node/',add:'/api/industrialsuite/settings/add_node',del:'/api/industrialsuite/settings/del_node/',toggle:'/api/industrialsuite/settings/toggle_node/',options:{selection:true,multiSelect:true,rowSelect:false,keepSelection:true}});
mapDataToFormUI({'suiteGeneral':'/api/industrialsuite/settings/get'}).done(function(){$('.selectpicker').selectpicker('refresh');});status();
});
</script>
