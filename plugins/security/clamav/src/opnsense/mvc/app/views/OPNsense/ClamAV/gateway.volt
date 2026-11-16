<link rel="stylesheet" href="{{ cache_safe('/ui/css/industrial-ui.css') }}">
<style>
.av-page{padding:22px;max-width:1300px}.av-header{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap}.av-header h2{margin:0 0 8px;font-size:26px;font-weight:600}.av-muted{color:#687782}.av-cards{display:grid;grid-template-columns:repeat(4,minmax(130px,1fr));gap:12px;margin:20px 0}.av-card{border:1px solid #dce4e9;border-radius:5px;padding:16px;background:#f8fafb}.av-card strong{display:block;font-size:17px;margin-top:8px}.av-pane{padding:24px 12px}.av-fields{max-width:960px}.av-fields fieldset{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:20px 24px}.av-fields .form-group{margin-bottom:0}.av-fields .av-wide,.av-fields .av-toolbar{grid-column:1/-1}.av-fields label{font-weight:600}.av-fields .help-block{font-size:12px;line-height:1.7}.av-fields textarea{min-height:90px}.av-toolbar{display:flex;gap:10px;flex-wrap:wrap;margin:20px 0}.av-header-actions{display:flex;flex-wrap:wrap;gap:10px}.av-database-settings{margin-bottom:24px;padding-bottom:20px;border-bottom:1px solid #ddd}.av-database-settings h4{margin:0 0 16px}.av-log{max-height:420px;overflow:auto}.av-log td{white-space:pre-wrap;word-break:break-word}.av-state{padding:12px 16px;border-left:4px solid #438f91;background:#eef7f7;margin:16px 0}.av-state.error{border-color:#bc4141;background:#fff1f1}.av-switch{display:flex;align-items:center;gap:10px}.av-switch input{margin:0}.av-advanced{margin-top:26px;border-top:1px solid #ddd;padding-top:16px}@media(max-width:700px){.av-cards{grid-template-columns:repeat(2,minmax(120px,1fr))}.av-page{padding:14px}.av-fields fieldset{grid-template-columns:1fr}}
</style>
<div class="content-box av-page feature-ui">
 <div class="av-header"><div><h2><i class="fa fa-shield"></i> 防病毒</h2><p class="av-muted">统一配置下载扫描、客户端访问和病毒库更新</p></div><div class="av-header-actions">
  <button id="avEngine" type="button" class="btn btn-primary av-operation" disabled><i class="fa fa-power-off" aria-hidden="true"></i> <span>防病毒启停</span></button>
  <button id="avRefresh" type="button" class="btn btn-default"><i class="fa fa-refresh" aria-hidden="true"></i> 刷新状态</button>
 </div></div>
 <p class="av-muted">停止防病毒会停止下载代理和扫描链路。病毒库自动更新按已保存的设置继续运行。</p>
 <div id="avMessage" class="av-state" role="status">正在读取防病毒状态…</div>
 <div class="av-cards" id="avServices"></div>
 <div id="avWarnings" class="alert alert-warning" style="display:none"></div>
 <ul class="nav nav-tabs"><li class="active"><a href="#avConfig" data-toggle="tab">防病毒配置</a></li><li><a href="#avDatabase" data-toggle="tab">病毒库与诊断</a></li></ul>
 <div class="tab-content">
  <div class="tab-pane active av-pane" id="avConfig">
   <form id="avForm" class="av-fields"><fieldset id="avFields" disabled>
    <div class="form-group"><label for="avInterfaces">代理监听接口</label><select id="avInterfaces" class="form-control" multiple size="3"></select><span class="help-block">选择客户端连接的接口，可按住 Ctrl 多选。只选本机回环时，仅限本机或 SSH 转发。</span></div>
    <div class="form-group"><label for="avPort">代理端口</label><input id="avPort" type="number" class="form-control" min="1024" max="65535" required><span class="help-block">客户端在浏览器或系统中配置 HTTP 代理，地址为上述接口的防火墙 IP，端口为此处设置值。需确保原有防火墙规则允许客户端连接该端口。</span></div>
    <div class="form-group"><label for="avNetworks">允许的客户端地址或网段</label><textarea id="avNetworks" class="form-control" placeholder="192.168.1.0/24&#10;192.168.2.10"></textarea><span class="help-block">每行一个地址或 CIDR，仅允许这些客户端使用代理。不会自动允许整个监听接口网段。</span></div>
    <div class="form-group"><label for="avSize">最大扫描文件大小（MB）</label><input id="avSize" type="number" class="form-control" min="1" max="100" required><span class="help-block">超过该大小的文件不保证扫描。本功能扫描经过显式代理的明文 HTTP 内容；HTTPS 隧道中的加密内容不会自动解密扫描。</span></div>
    <div class="av-toolbar"><button type="submit" id="avApply" class="btn btn-primary av-operation">保存扫描配置</button><button type="button" id="avTest" class="btn btn-default av-operation">检查扫描链路</button></div>
   </fieldset></form>
   <div class="av-advanced"><p class="av-muted">通常只需在本页配置。已有的缓存、认证及其他高级选项继续保留；此处只配置扫描和客户端访问。启停使用页面顶部按钮，病毒库更新在另一标签页设置。</p><button id="avAdvancedToggle" type="button" class="btn btn-default" aria-expanded="false" aria-controls="avAdvancedLinks"><i class="fa fa-cog" aria-hidden="true"></i> 高级配置 <i class="fa fa-angle-down" aria-hidden="true"></i></button><div id="avAdvancedLinks" class="av-toolbar" hidden><a class="btn btn-default" href="/ui/clamav/general/index">扫描引擎高级选项</a><a class="btn btn-default" href="/ui/cicap/general/index">扫描连接高级选项</a><a class="btn btn-default" href="/ui/proxy/">代理高级选项</a></div></div>
  </div>
  <div class="tab-pane av-pane" id="avDatabase">
   <div class="av-database-settings">
    <h4>病毒库更新设置</h4>
    <form id="avUpdateForm" class="av-fields"><fieldset id="avUpdateFields" disabled>
    <div class="form-group av-wide"><label class="av-switch"><input type="checkbox" id="avUpdates"> 自动更新病毒库</label></div>
    <div class="form-group"><label for="avUpdateHost">病毒库更新代理主机</label><input id="avUpdateHost" class="form-control" placeholder="留空表示直接连接"><span class="help-block">仅用于病毒库下载。填写 IP 或主机名。</span></div>
    <div class="form-group"><label for="avUpdatePort">病毒库更新代理端口</label><input id="avUpdatePort" type="number" class="form-control" min="1" max="65535" required><span class="help-block">填写上述代理的端口。</span></div>
     <div class="av-toolbar"><button type="submit" id="avSaveUpdates" class="btn btn-primary av-operation">保存更新设置</button></div>
    </fieldset></form>
   </div>
   <table class="table table-striped"><thead><tr><th>病毒库</th><th>状态</th><th>版本</th><th>特征数</th><th>构建时间</th></tr></thead><tbody id="avDatabases"></tbody></table>
   <div class="av-toolbar"><button type="button" id="avUpdate" class="btn btn-primary av-operation">立即检查病毒库更新</button><button type="button" id="avLogs" class="btn btn-default">查看诊断日志</button></div>
   <p class="av-muted">手动更新使用已保存的更新设置。下载在后台执行，完成后状态会自动刷新。</p>
   <div class="av-log"><table class="table table-striped"><thead><tr><th style="width:140px">组件</th><th>诊断记录</th></tr></thead><tbody id="avLogRows"></tbody></table></div>
  </div>
 </div>
</div>
<script>
$(function () {
    const endpoint = '/api/clamav/gateway/';
    let loaded = false, statusLoaded = false, submitting = false, running = false;
    let engineEnabled = false, timer = null, statusRequest = null, seenJob = '', pendingJob = '';

    function message(text, error = false) {
        $('#avMessage').text(text).toggleClass('error', error);
    }

    function syncControls() {
        const locked = !loaded || submitting || running || pendingJob !== '';
        $('#avFields, #avUpdateFields, .av-operation').prop('disabled', locked);
        $('#avEngine').prop('disabled', locked || !statusLoaded)
            .find('span').text(engineEnabled ? '停止防病毒' : '启动防病毒');
        $('#avTest').prop('disabled', locked || !statusLoaded || !engineEnabled);
    }

    function populateInterfaces(settings, selected) {
        const select = $('#avInterfaces').empty();
        settings.interface_options.forEach(function (option) {
            const name = option.id === 'lo0' ? '本机回环' : option.name;
            const address = option.address ? ' · ' + option.address : '';
            const info = option.dhcp ? (option.available ? '（DHCP）' : '（等待 DHCP 地址）') : '';
            select.append($('<option>').val(option.id).text(name + address + info)
                .prop('disabled', !option.available && !selected.includes(option.id)));
        });
        select.val(selected);
    }

    function load(initial) {
        return $.getJSON(endpoint + 'get').done(function (data) {
            if (data.status !== 'ok') {
                message(data.message, true);
                return;
            }
            const settings = data.settings;
            populateInterfaces(settings, initial ? settings.interfaces.split(',') : ($('#avInterfaces').val() || []));
            if (initial) {
                $('#avPort').val(settings.port);
                $('#avNetworks').val(settings.networks);
                $('#avSize').val(settings.max_file_mb);
                $('#avUpdates').prop('checked', settings.automatic_updates === '1');
                $('#avUpdateHost').val(settings.update_proxy_host);
                $('#avUpdatePort').val(settings.update_proxy_port);
                loaded = true;
            }
            syncControls();
        }).fail(function () { message('无法读取防病毒设置，请刷新重试。', true); });
    }

    function poll() {
        clearTimeout(timer);
        if (statusRequest) statusRequest.abort();
        statusRequest = $.getJSON(endpoint + 'status').done(function (data) {
            if (data.status !== 'ok') {
                message(data.message, true);
                timer = setTimeout(poll, 5000);
                return;
            }
            const cards = $('#avServices').empty();
            data.services.forEach(function (service) {
                cards.append($('<div class="av-card">').append($('<span>').text(service.name),
                    $('<strong>').addClass(service.running ? 'text-success' : 'text-muted').text(service.running ? '运行中' : '已停止')));
            });
            const db = $('#avDatabases').empty();
            const names = {main: '主病毒库', daily: '每日更新库', bytecode: '字节码库'};
            data.databases.forEach(function (item) {
                const row = $('<tr>');
                [names[item.name] || item.name, item.present ? '已安装' : '未安装', item.version,
                    item.signatures, item.built_at].forEach((value) => row.append($('<td>').text(value)));
                db.append(row);
            });
            $('#avWarnings').text(data.warnings.join(' ')).toggle(data.warnings.length > 0);
            const job = data.job || {};
            running = job.running === true;
            engineEnabled = data.engine_enabled === true;
            if (!submitting && job.id && (running || seenJob !== job.id || pendingJob === job.id)) {
                message(job.message, job.status === 'error');
                seenJob = job.id;
            } else if (!statusLoaded && !job.id && !submitting) {
                message(engineEnabled ? '防病毒已启用。' : '防病毒已停止。');
            }
            if (!running && pendingJob === job.id) pendingJob = '';
            statusLoaded = true;
            syncControls();
            timer = setTimeout(poll, running || pendingJob ? 1500 : 15000);
        }).fail(function (xhr, status) {
            if (status === 'abort') return;
            statusLoaded = false;
            syncControls();
            message('状态查询失败，正在重新连接…', true);
            timer = setTimeout(poll, 5000);
        });
    }

    function run(operation, settings = {}) {
        if (!loaded || submitting || running || pendingJob) return;
        submitting = true;
        syncControls();
        message('正在提交防病毒操作…');
        $.ajax({url: endpoint + 'run', method: 'POST', contentType: 'application/json', dataType: 'json',
            data: JSON.stringify({operation: operation, settings: settings})})
            .done(function (data) {
                if (data.status === 'accepted') {
                    pendingJob = data.id;
                    message(data.message);
                } else {
                    message(data.message || '操作未开始。', true);
                }
            }).fail(function (xhr) {
                message(xhr.responseJSON?.message || '操作请求失败，请检查连接和权限。', true);
            }).always(function () {
                submitting = false;
                syncControls();
                poll();
            });
    }

    $('#avForm').on('submit', function (event) {
        event.preventDefault();
        run('configure', {interfaces: ($('#avInterfaces').val() || []).join(','), port: $('#avPort').val(),
            networks: $('#avNetworks').val(), max_file_mb: $('#avSize').val()});
    });
    $('#avUpdateForm').on('submit', function (event) {
        event.preventDefault();
        run('save_updates', {automatic_updates: $('#avUpdates').is(':checked') ? '1' : '0',
            update_proxy_host: $('#avUpdateHost').val(), update_proxy_port: $('#avUpdatePort').val()});
    });
    $('#avEngine').on('click', () => run('set_engine', {enabled: engineEnabled ? '0' : '1'}));
    $('#avTest').on('click', () => run('test'));
    $('#avUpdate').on('click', () => run('update'));
    $('#avRefresh').on('click', function () { load(!loaded); poll(); });
    $('#avAdvancedToggle').on('click', function () {
        const open = $(this).attr('aria-expanded') !== 'true';
        $(this).attr('aria-expanded', String(open)).find('.fa-angle-down,.fa-angle-up')
            .toggleClass('fa-angle-down', !open).toggleClass('fa-angle-up', open);
        $('#avAdvancedLinks').prop('hidden', !open);
    });
    $('#avLogs').on('click', function () {
        const button = $(this).prop('disabled', true);
        $.getJSON(endpoint + 'logs').done(function (data) {
            const rows = $('#avLogRows').empty();
            if (data.status !== 'ok') {
                message(data.message, true);
                return;
            }
            if (!data.rows.length) rows.append($('<tr>').append($('<td colspan="2">').text('暂无诊断记录')));
            data.rows.forEach((row) => rows.append($('<tr>').append($('<td>').text(row.component), $('<td>').text(row.message))));
        }).fail(function () { message('诊断日志读取失败。', true); })
            .always(function () { button.prop('disabled', false); });
    });
    syncControls();
    load(true);
    poll();
    $(window).on('beforeunload', () => clearTimeout(timer));
});
</script>
