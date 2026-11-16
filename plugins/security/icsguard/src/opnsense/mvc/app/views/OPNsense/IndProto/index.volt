<script>
    $(document).ready(function() {
        const displayLabels={"read": "只读", "write": "只写", "readwrite": "读写", "pass": "允许", "block": "阻断", "drop": "阻断", "publish": "发布", "subscribe": "订阅", "unsubscribe": "取消订阅", "register": "设备注册", "version_probe": "版本探测", "model_query": "模型查询", "model_set": "模型设置", "data_query": "数据查询", "data_set": "数据设置", "sample": "采样上报", "sample_register": "采样注册", "sample_unregister": "采样注销", "method_call": "方法调用", "method_control": "方法控制", "method_status": "方法进度", "method_result": "方法结果", "event_register": "事件注册", "event_unregister": "事件注销", "event": "事件上报", "state_notify": "状态通知", "discovery": "终端发现", "request": "请求", "response": "响应"};
        function displayValue(value){return String(value || "").split(",").map(item=>displayLabels[item.trim()] || item.trim()).join("、");}
        function htmlEscape(value) {
            return $("<div/>").text(value === undefined ? "" : value).html();
        }

        $("#{{formGridRule['table_id']}}").UIBootgrid(
            {   search:'/api/indproto/rules/search_rule/',
                get:'/api/indproto/rules/get_rule/',
                set:'/api/indproto/rules/set_rule/',
                add:'/api/indproto/rules/add_rule/',
                del:'/api/indproto/rules/del_rule/',
                toggle:'/api/indproto/rules/toggle_rule/',
                options: {
                    formatters: {
                        protocolName: function(column,row){return htmlEscape(({modbus:'Modbus TCP',dnp3:'DNP3',s7comm:'S7comm',mqtt:'MQTT',nclink:'NC-Link',enip:'EtherNet/IP / CIP',iec104:'IEC-104',fins:'FINS/TCP',melsec:'MELSEC',bacnet:'BACnet/IP',opcua:'OPC UA TCP'})[row.protocol] || row.protocol);},
                        policyAction: function(column,row){return htmlEscape(displayValue(row.action));},
                        logOnly: function(column,row){return row.log_only==='1'?'是':'否';},
                        protocolOperation: function(column, row) {
                            const protocol = String(row.protocol || '').toLowerCase();
                            let operation = row.protocol_operations || row.access;
                            if (protocol === 'mqtt') {
                                operation = row.mqtt_operations;
                            } else if (protocol === 'nclink') {
                                operation = row.nclink_operations;
                            }
                            return htmlEscape(displayValue(operation) || '-');
                        }
                    }
                }
            }
        );

        $("#applyAct").SimpleActionButton({
            onPreAction: function() {
                const dfObj = new $.Deferred();
                saveFormToEndpoint("/api/indproto/general/set", "frm_general_settings", function() {
                    dfObj.resolve();
                }, true, function() {
                    dfObj.reject();
                });
                return dfObj;
            },
            onAction: function(data) {
                if (data.status === "ok") {
                    $("#indprotoChangeMessage").hide();
                    $("#{{formGridRule['table_id']}}").bootgrid("reload");
                }
            }
        });

        mapDataToFormUI({'frm_general_settings':"/api/indproto/general/get"}).done(function() {
            $('.selectpicker').selectpicker('refresh');
        });

        ajaxGet('/api/indproto/rules/list_network_select_options', [], function(data) {
            if (data && data.single) {
                $('.net_selector').each(function() {
                    $(this).replaceInputWithSelector(data, false);
                });
            }
        });

        ajaxGet('/api/indproto/rules/list_port_select_options', [], function(data) {
            if (data && data.single) {
                $('.port_selector').each(function() {
                    $(this).replaceInputWithSelector(data, false);
                });
            }
        });

        const protocolCatalog = {};
        const ruleDialog = $('#{{formGridRule['edit_dialog_id']}}');
        function updateProtocolFields() {
            const protocol = ruleDialog.find('[id="rule.protocol"]').val() || 'modbus';
            const protocolSettings = ruleDialog.find('.protocol-settings-section');
            const mqttSettings = ruleDialog.find(
                '.protocol-mqtt-section, .protocol-mqtt-advanced-section'
            );
            const nclinkSettings = ruleDialog.find('.protocol-nclink-section');

            protocolSettings.hide();
            mqttSettings.hide();
            nclinkSettings.hide();
            ruleDialog.find('[id="row_rule.access"]').show();
            ruleDialog.find('[id="row_rule.protocol_operations"], [id="row_rule.enip_services"]').hide();
            const capability = protocolCatalog[protocol] || {};
            $('#indprotoRuleInfo').text((capability.operations && Object.keys(capability.operations).length ? ' 操作码：' + Object.entries(capability.operations).map(([code,name])=>code+' = '+name).join('；') : ''));
            $('#indprotoOperationTools').toggle(['enip','iec104','fins','melsec','bacnet','opcua'].includes(protocol));
            $('#indprotoOperationTools [data-preset=read], #indprotoOperationTools [data-preset=write]').toggle(protocol!=='opcua');
            $('#indprotoOperationTools [data-preset=types]').toggle(protocol==='opcua');

            if (protocol === 'modbus' || protocol === 'dnp3') {
                protocolSettings.show();
                protocolSettings.find('thead b').text(
                    protocol === 'modbus'
                        ? "{{ lang._('Modbus 设置') }}"
                        : "{{ lang._('DNP3 设置') }}"
                );
                ruleDialog.find('[id="row_rule.modbus_unit_id"]').toggle(protocol === 'modbus');
                ruleDialog.find('[id="row_rule.modbus_function_codes"]').toggle(protocol === 'modbus');
                ruleDialog.find('[id="row_rule.dnp3_function_codes"]').toggle(protocol === 'dnp3');
                ruleDialog.find('[id="row_rule.dnp3_object_group"]').toggle(protocol === 'dnp3');
            } else if (['enip','iec104','fins','melsec','bacnet','opcua'].includes(protocol)) {
                protocolSettings.show();
                protocolSettings.find('thead b').text(capability.name || protocol);
                ['modbus_unit_id','modbus_function_codes','dnp3_function_codes','dnp3_object_group'].forEach(function(field){ruleDialog.find('[id="row_rule.'+field+'"]').hide();});
                ruleDialog.find('[id="row_rule.protocol_operations"]').show();
                ruleDialog.find('[id="row_rule.enip_services"]').toggle(protocol==='enip');
                ruleDialog.find('[id="row_rule.access"]').toggle(protocol!=='opcua');
            } else if (protocol === 'mqtt') {
                mqttSettings.show();
                const mqttTls = ruleDialog.find('[id="rule.mqtt_tls"]').is(':checked');
                [
                    'mqtt_allow_connect', 'mqtt_operations', 'mqtt_topic', 'mqtt_client_id',
                    'mqtt_username', 'mqtt_qos'
                ].forEach(function(field) {
                    ruleDialog.find('[id="row_rule.' + field + '"]').toggle(!mqttTls);
                });
                ruleDialog.find('[id="row_rule.access"]').hide();
            } else if (protocol === 'nclink') {
                nclinkSettings.show();
                ruleDialog.find('[id="row_rule.access"]').hide();
            }
        }
        ruleDialog.find('.modal-body').append($('<div id="indprotoRuleInfo" class="help-block" style="margin-top:16px;line-height:1.7"></div>'));
        const tools=$('<div id="indprotoOperationTools" style="display:none;margin:12px 0"></div>');
        [['读取预设','read'],['写入预设','write'],['默认消息类型','types'],['填入默认端口','port']].forEach(function(item){
            tools.append($('<button type="button" class="btn btn-default btn-sm" style="margin-right:8px"></button>').attr('data-preset',item[1]).text(item[0]).click(function(){
                const protocol=ruleDialog.find('[id="rule.protocol"]').val();const cap=protocolCatalog[protocol];if(!cap)return;
                if(item[1]==='port'){ruleDialog.find('[id="rule.dst_port"]').val(String(cap.port)).trigger('change');}
                else{ruleDialog.find('[id="rule.protocol_operations"]').val((cap[item[1]==='types'?'read':item[1]]||[]).join(','));
                    if(item[1]!=='types'){ruleDialog.find('[id="rule.access"]').val(item[1]).selectpicker('refresh');if(protocol==='enip'){ruleDialog.find('[id="rule.enip_services"]').val('');}}
                }
            }));
        });
        ruleDialog.find('.modal-body').append(tools);
        ajaxGet('/api/indproto/rules/protocols',[],function(data){
            if(!data||!data.protocols)return;
            data.protocols.forEach(function(cap){protocolCatalog[cap.id]=cap;});updateProtocolFields();
        });
        ruleDialog.on('change', '[id="rule.protocol"]', updateProtocolFields);
        ruleDialog.on('change', '[id="rule.mqtt_tls"]', updateProtocolFields);
        ruleDialog.on('opnsense_bootgrid_mapped shown.bs.modal', function() {
            window.setTimeout(updateProtocolFields, 0);
        });
    });
</script>

<style>
    #{{formGridRule['edit_dialog_id']}} .protocol-settings-section,
    #{{formGridRule['edit_dialog_id']}} .protocol-mqtt-section,
    #{{formGridRule['edit_dialog_id']}} .protocol-mqtt-advanced-section,
    #{{formGridRule['edit_dialog_id']}} .protocol-nclink-section {
        display: none;
    }
</style>

<div class="content-box">
    <div class="table-responsive">
        {{ partial("layout_partials/base_form", ['fields':formGeneral, 'id':'frm_general_settings']) }}
    </div>
</div>

<div class="content-box">
    {{ partial('layout_partials/base_bootgrid_table', formGridRule) }}
</div>

<div class="content-box">
    <div id="indprotoChangeMessage" class="alert alert-info" style="display: none" role="alert">
        {{ lang._('设置已修改，请点击应用使策略生效。') }}
    </div>
    <button class="btn btn-primary" id="applyAct"
            data-endpoint="/api/indproto/rules/apply"
            data-label="{{ lang._('应用') }}"
            data-error-title="{{ lang._('应用工业协议策略失败') }}"
            type="button"></button>
</div>

{{ partial("layout_partials/base_dialog", ['fields':formDialogRule, 'id':formGridRule['edit_dialog_id'], 'label':lang._('编辑规则')]) }}
