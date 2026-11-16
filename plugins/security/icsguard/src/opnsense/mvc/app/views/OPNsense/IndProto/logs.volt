<script>
$(document).ready(function() {
    function htmlEscape(value) {
        return $("<div/>").text(value === undefined ? "" : value).html();
    }

    const businessLabels={"read": "只读", "write": "只写", "readwrite": "读写", "pass": "允许", "block": "阻断", "drop": "阻断", "publish": "发布", "subscribe": "订阅", "unsubscribe": "取消订阅", "register": "设备注册", "version_probe": "版本探测", "model_query": "模型查询", "model_set": "模型设置", "data_query": "数据查询", "data_set": "数据设置", "sample": "采样上报", "sample_register": "采样注册", "sample_unregister": "采样注销", "method_call": "方法调用", "method_control": "方法控制", "method_status": "方法进度", "method_result": "方法结果", "event_register": "事件注册", "event_unregister": "事件注销", "event": "事件上报", "state_notify": "状态通知", "discovery": "终端发现", "request": "请求", "response": "响应"};
    var formatters = {
        safeText: function(column,row){return htmlEscape(row[column.id] || "");},
        businessOperation: function(column,row){return htmlEscape(businessLabels[row.nclink_operation] || row.nclink_operation || "");},
        businessDirection: function(column,row){return htmlEscape(businessLabels[row.nclink_direction] || (row.nclink_direction === "publish" ? "数据上报" : row.nclink_direction || ""));},
        enforcement: function(column, row) {
            return row.enforcement === 'blocked' ? '<span class="label label-danger">已阻断</span>' : '<span class="label label-info">仅观测 / 告警</span>';
        },
        indprotoAction: function(column, row) {
            var action = String(row.action || "alert").toLowerCase();
            var classes = {
                drop: "label-danger",
                blocked: "label-danger",
                pass: "label-success",
                allowed: "label-success",
                reject: "label-danger",
                alert: "label-warning"
            };
            var labels = {
                drop: "{{ lang._('阻断') }}",
                pass: "{{ lang._('允许') }}",
                alert: "{{ lang._('告警') }}"
            };
            return '<span class="label ' + (classes[action] || "label-default") + '">' +
                htmlEscape(labels[action] || action) + '</span>';
        }
    };

    $("#grid-indproto-logs").UIBootgrid({
        search: "/api/indproto/log/search_log",
        options: {
            rowCount: [10, 25, 50, 100],
            selection: false,
            rowSelect: false,
            responsive: true,
            requestHandler: function(request) {
                request.proto = $("#filter-proto").val() || "all";
                request.src_ip = $("#filter-src").val() || "";
                request.dst_ip = $("#filter-dst").val() || "";
                request.start_time = $("#filter-start").val() || "";
                request.end_time = $("#filter-end").val() || "";
                request.limit = $("#filter-limit").val() || "200";
                return request;
            },
            formatters: formatters
        }
    });

    $(".selectpicker").selectpicker("refresh");
    $("#refresh-logs").click(function() {
        $("#grid-indproto-logs").bootgrid("reload");
    });
    $("#reset-logs").click(function() {
        $("#filter-proto").val("all").selectpicker("refresh");
        $("#filter-src").val("");
        $("#filter-dst").val("");
        $("#filter-start").val("");
        $("#filter-end").val("");
        $("#filter-limit").val("200");
        $("#grid-indproto-logs").bootgrid("search", "");
        $("#grid-indproto-logs").bootgrid("reload");
    });
});
</script>

<div class="content-box">
    <div class="row" style="padding: 10px 10px 0 10px;">
        <div class="col-sm-2">
            <select class="selectpicker" id="filter-proto" data-width="100%">
                <option value="all">{{ lang._('全部协议') }}</option>
                <option value="modbus">Modbus</option>
                <option value="nclink">NC-Link</option>
                <option value="dnp3">DNP3</option>
                <option value="s7comm">S7comm</option>
                <option value="mqtt">MQTT</option><option value="enip">EtherNet/IP</option><option value="iec104">IEC-104</option><option value="fins">FINS/TCP</option><option value="melsec">MELSEC</option><option value="bacnet">BACnet/IP</option><option value="opcua">OPC UA TCP</option>
            </select>
        </div>
        <div class="col-sm-2">
            <input id="filter-src" type="text" class="form-control" placeholder="{{ lang._('源IP') }}">
        </div>
        <div class="col-sm-2">
            <input id="filter-dst" type="text" class="form-control" placeholder="{{ lang._('目标IP') }}">
        </div>
        <div class="col-sm-2">
            <input id="filter-start" type="text" class="form-control" placeholder="{{ lang._('开始时间') }}">
        </div>
        <div class="col-sm-2">
            <input id="filter-end" type="text" class="form-control" placeholder="{{ lang._('结束时间') }}">
        </div>
        <div class="col-sm-1">
            <input id="filter-limit" type="text" class="form-control" value="200" placeholder="{{ lang._('限制') }}">
        </div>
        <div class="col-sm-1 text-right">
            <button class="btn btn-default" id="refresh-logs" type="button"><span class="fa fa-refresh"></span></button>
            <button class="btn btn-default" id="reset-logs" type="button"><span class="fa fa-undo"></span></button>
        </div>
    </div>
    <table id="grid-indproto-logs" class="table table-condensed table-hover table-striped table-responsive">
        <thead>
            <tr>
                <th data-column-id="timestamp" data-width="180" data-type="string">{{ lang._('时间') }}</th>
                <th data-column-id="src_ip" data-width="140" data-type="string">{{ lang._('源IP') }}</th>
                <th data-column-id="dest_ip" data-width="140" data-type="string">{{ lang._('目标IP') }}</th>
                <th data-column-id="dest_port" data-width="90" data-type="string">{{ lang._('端口') }}</th>
                <th data-column-id="proto" data-width="100" data-type="string">{{ lang._('协议') }}</th>
                <th data-column-id="nclink_operation" data-formatter="businessOperation" data-width="130" data-type="string">{{ lang._('操作权限') }}</th>
                <th data-column-id="nclink_endpoint" data-formatter="safeText" data-width="130">客户端 / 通道</th>
                <th data-column-id="nclink_direction" data-formatter="businessDirection" data-width="100">业务方向</th>
                <th data-column-id="nclink_device_uuid" data-formatter="safeText" data-width="140" data-type="string">{{ lang._('设备标识') }}</th>
                <th data-column-id="nclink_request_id" data-formatter="safeText" data-visible="false">消息标识</th>
                <th data-column-id="nclink_payload_device_uuid" data-formatter="safeText" data-visible="false">报文设备</th>
                <th data-column-id="nclink_object_id" data-formatter="safeText" data-visible="false">数据项</th>
                <th data-column-id="nclink_sample_time" data-formatter="safeText" data-visible="false">采样时间</th>
                <th data-column-id="signature" data-type="string">{{ lang._('规则') }}</th>
                <th data-column-id="action" data-width="100" data-type="string" data-formatter="indprotoAction">策略动作</th>
                <th data-column-id="enforcement" data-width="130" data-formatter="enforcement">实际处置</th>
            </tr>
        </thead>
        <tbody></tbody>
    </table>
</div>
