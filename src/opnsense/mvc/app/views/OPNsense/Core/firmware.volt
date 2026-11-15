{#
 # Copyright (c) 2015-2026 Franco Fichtner <franco@opnsense.org>
 # Copyright (c) 2015-2018 Deciso B.V.
 # All rights reserved.
 #
 # Redistribution and use in source and binary forms, with or without modification,
 # are permitted provided that the following conditions are met:
 #
 # 1. Redistributions of source code must retain the above copyright notice,
 # this list of conditions and the following disclaimer.
 #
 # 2. Redistributions in binary form must reproduce the above copyright notice,
 # this list of conditions and the following disclaimer in the documentation
 # and/or other materials provided with the distribution.
 #
 # THIS SOFTWARE IS PROVIDED "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
 # INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY
 # AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
 # AUTHOR BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY,
 # OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
 # SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
 # INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
 # CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
 # ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 # POSSIBILITY OF SUCH DAMAGE.
 #}

<script>
    function escapeHtml(value) {
        return $('<div>').text(value == null ? '' : value).html();
    }

    let pluginFilter = 'all';
    function filterPlugins() {
        const search = $('#plugin_search').val().toLowerCase();
        let matches = 0;
        $('.plugin-entry').each(function () {
            const match = $(this).text().toLowerCase().includes(search) &&
                (pluginFilter === 'all' || (pluginFilter === 'installed' ? $(this).attr('data-installed') === '1' : $(this).attr('data-custom') === '1'));
            $(this).toggle(match);
            if (match) matches++;
        });
        $('#pluginNoMatches').prop('hidden', matches > 0 || $('.plugin-entry').length === 0);
    }

    function showPluginDetails(packageName) {
        ajaxCall('/api/core/firmware/details/' + packageName, {}, function (data) {
            const details = data.details || "{{ lang._('暂时无法取得插件详情。') }}";
            stdDialogInform("{{ lang._('插件详情') }}", details, "{{ lang._('关闭') }}");
        });
    }

    function trackPluginAction() {
        ajaxGet('/api/core/firmware/upgradestatus', {v: Date.now()}, function (data, status) {
            if (status !== 'success') {
                setTimeout(trackPluginAction, 1000);
                return;
            }

            if (data.log !== undefined) {
                $('#plugin_output').val(data.log).scrollTop($('#plugin_output')[0].scrollHeight);
            }

            if (data.status === 'done' || data.status === 'error') {
                $('#plugin_progress').removeClass('fa fa-spinner fa-pulse');
                loadPlugins();
            } else {
                setTimeout(trackPluginAction, 500);
            }
        });
    }

    function runPluginAction(action, packageName) {
        $('#plugin_output_container').show();
        $('#plugin_output').val('');
        $('#plugin_progress').addClass('fa fa-spinner fa-pulse');
        ajaxCall('/api/core/firmware/' + action + '/' + packageName, {}, function (data) {
            if (data.status === 'ok') {
                setTimeout(trackPluginAction, 500);
            } else {
                $('#plugin_progress').removeClass('fa fa-spinner fa-pulse');
                stdDialogInform(
                    "{{ lang._('插件操作') }}",
                    data.status_msg || "{{ lang._('插件操作未执行。') }}",
                    "{{ lang._('关闭') }}",
                    undefined,
                    'danger'
                );
            }
        });
    }

    function bindPluginActions() {
        $('.act-details').click(function () {
            showPluginDetails($(this).data('package'));
        });
        $('.act-install').click(function () {
            const packageName = $(this).data('package');
            BootstrapDialog.show({
                type: BootstrapDialog.TYPE_WARNING,
                title: "{{ lang._('确认安装') }}",
                message: "{{ lang._('从签名软件源安装此插件及其依赖？') }}" +
                    ' <strong>' + escapeHtml(packageName) + '</strong>',
                buttons: [{
                    label: "{{ lang._('安装') }}",
                    cssClass: 'btn-primary',
                    action: function (dialogRef) {
                        dialogRef.close();
                        runPluginAction('install', packageName);
                    }
                }, {
                    label: "{{ lang._('取消') }}",
                    action: function (dialogRef) {
                        dialogRef.close();
                    }
                }]
            });
        });
        $('.act-reinstall').click(function () {
            const packageName = $(this).data('package');
            BootstrapDialog.show({
                type: BootstrapDialog.TYPE_WARNING,
                title: "{{ lang._('确认重装') }}",
                message: "{{ lang._('从签名软件源重新安装此插件？') }}" +
                    ' <strong>' + escapeHtml(packageName) + '</strong>',
                buttons: [{
                    label: "{{ lang._('重装') }}",
                    cssClass: 'btn-primary',
                    action: function (dialogRef) {
                        dialogRef.close();
                        runPluginAction('reinstall', packageName);
                    }
                }, {
                    label: "{{ lang._('取消') }}",
                    action: function (dialogRef) {
                        dialogRef.close();
                    }
                }]
            });
        });
        $('.act-remove').click(function () {
            const packageName = $(this).data('package');
            BootstrapDialog.show({
                type: BootstrapDialog.TYPE_WARNING,
                title: "{{ lang._('确认卸载') }}",
                message: "{{ lang._('确认卸载此插件？') }}" +
                    ' <strong>' + escapeHtml(packageName) + '</strong>',
                buttons: [{
                    label: "{{ lang._('卸载') }}",
                    cssClass: 'btn-warning',
                    action: function (dialogRef) {
                        dialogRef.close();
                        runPluginAction('remove', packageName);
                    }
                }, {
                    label: "{{ lang._('取消') }}",
                    action: function (dialogRef) {
                        dialogRef.close();
                    }
                }]
            });
        });
    }

    function loadPlugins(showError) {
        $('#refresh_plugins').prop('disabled', true);
        $('#plugin_progress').addClass('fa fa-spinner fa-pulse');
        $('#plugin_refresh_status').text("{{ lang._('正在读取插件目录…') }}");
        ajaxGet('/api/core/firmware/info' + (showError === true ? '/1' : ''), {v: Date.now()}, function (data) {
            const tbody = $('#pluginlist > tbody');
            tbody.empty();

            $.each(data.plugin || [], function (index, plugin) {
                const installed = plugin.installed === '1';
                const provided = plugin.provided === '1';
                const localCustom = plugin.local_custom === '1';
                const installedVersion = installed ? plugin.version : "{{ lang._('N/A') }}";
                const availableVersion = provided && !localCustom ? plugin.remote_version : '-';
                const stateLabel = installed
                    ? (localCustom ? '本地定制' : provided ? '已安装' : plugin.catalogue_known === '1' ? '源中未提供' : '目录待确认')
                    : '';
                let actions = '<button class="btn btn-default btn-xs act-details" data-package="' +
                    escapeHtml(plugin.name) + '" data-toggle="tooltip" title="{{ lang._('详情') }}">' +
                    '<i class="fa fa-info-circle fa-fw"></i></button>';

                if (!installed && provided && !localCustom) {
                    actions += '<button class="btn btn-default btn-xs act-install" data-package="' +
                        escapeHtml(plugin.name) + '" data-toggle="tooltip" title="{{ lang._('安装') }}">' +
                        '<i class="fa fa-plus fa-fw"></i></button>';
                } else if (installed && provided && !localCustom) {
                    actions += '<button class="btn btn-default btn-xs act-reinstall" data-package="' +
                        escapeHtml(plugin.name) + '" data-toggle="tooltip" title="{{ lang._('重装') }}">' +
                        '<i class="fa fa-repeat fa-fw"></i></button>';
                }

                if (installed) {
                    actions += '<button class="btn btn-default btn-xs act-remove" data-package="' +
                        escapeHtml(plugin.name) + '" data-toggle="tooltip" title="{{ lang._('卸载') }}">' +
                        '<i class="fa fa-trash fa-fw"></i></button>';
                }

                tbody.append(
                    '<tr class="plugin-entry" data-installed="'+plugin.installed+'" data-custom="'+plugin.local_custom+'">' +
                    '<td><div class="if-package-name">' + escapeHtml(plugin.name) + (stateLabel ? '<span class="if-chip '+(localCustom?'if-chip-custom':provided?'if-chip-good':'if-chip-warning')+'">'+escapeHtml(stateLabel)+'</span>' : '') + '</div><div class="if-package-desc">'+escapeHtml(plugin.comment)+'</div></td>' +
                    '<td>' + escapeHtml(installedVersion) + '</td>' +
                    '<td>' + escapeHtml(availableVersion) + '</td>' +
                    '<td>' + escapeHtml(plugin.flatsize) + '</td>' +
                    '<td>' + escapeHtml(plugin.tier) + '</td>' +
                    '<td>' + escapeHtml(plugin.repository) + '</td>' +
                    '<td class="text-right" style="white-space:nowrap"><div class="input-group">' + actions + '</div></td>' +
                    '</tr>'
                );
            });

            if (tbody.children().length === 0) {
                tbody.append('<tr><td colspan="7">{{ lang._('软件源尚未返回插件目录。') }}</td></tr>');
            }

            $('#refresh_plugins').prop('disabled', false);
            $('#plugin_progress').removeClass('fa fa-spinner fa-pulse');

            if (data.catalogue_status === 'ok') {
                $('#plugin_refresh_status').text(
                    data.catalogue_message || "{{ lang._('插件目录已加载。') }}"
                );
            } else {
                const message = data.catalogue_message ||
                    "{{ lang._('无法刷新插件目录，请检查连接设置。') }}";
                $('#plugin_refresh_status').text(message);
                if (showError === true) {
                    stdDialogInform(
                        "{{ lang._('插件目录') }}",
                        escapeHtml(message),
                        "{{ lang._('关闭') }}",
                        undefined,
                        'danger'
                    );
                }
            }

            $('#plugin_count_all').text((data.plugin || []).length);
            $('#plugin_count_installed').text((data.plugin || []).filter(p=>p.installed==='1').length);
            $('#plugin_count_custom').text((data.plugin || []).filter(p=>p.local_custom==='1'&&p.installed==='1').length);
            $('#pluginlist button[title]').each(function(){$(this).attr('aria-label',$(this).attr('title'));});
            bindPluginActions();
            filterPlugins();
        });
    }

    $(document).ready(function () {
        ajaxGet('/api/core/firmware/plugin_settings', {}, function (data) {
            const mirrors = $('#plugin_mirror').empty();
            $.each(data.mirrors || {}, function (url, label) {
                mirrors.append($('<option>').val(url).text(label));
            });
            mirrors.val(data.mirror);
            $('#plugin_proxy').val(data.plugin_proxy || '');
        });
        $('#save_plugin_connection').click(function () {
            const button = $(this).prop('disabled', true);
            ajaxCall('/api/core/firmware/plugin_settings', {connection: {
                mirror: $('#plugin_mirror').val(), plugin_proxy: $('#plugin_proxy').val().trim()
            }}, function (data) {
                button.prop('disabled', false);
                $('#plugin_connection_status').text(data.status === 'ok' ? '' : data.status_msg || '保存失败');
                if(data.status==='ok'){$('#pluginConnectionModal').modal('hide');$('#plugin_refresh_status').text('连接设置已保存，点击刷新获取最新目录。');}
            });
        });
        $('[data-plugin-filter]').click(function(){pluginFilter=$(this).data('plugin-filter');$('[data-plugin-filter]').removeClass('active').attr('aria-pressed','false');$(this).addClass('active').attr('aria-pressed','true');filterPlugins();});
        $('#plugin_search').on('input',filterPlugins);
        $('#pluginConnectionModal').on('shown.bs.modal',function(){$('#plugin_mirror').trigger('focus');});
        $('#refresh_plugins').click(function () {
            loadPlugins(true);
        });
        $('#plugin_output_copy').click(function (event) {
            event.preventDefault();
            $('#plugin_output').select();
            document.execCommand('copy');
            document.getSelection().removeAllRanges();
        });

        ajaxGet('/api/core/firmware/running', {}, function (data) {
            if (data.status === 'busy') {
                $('#plugin_output_container').show();
                trackPluginAction();
            } else {
                loadPlugins(false);
            }
        });
    });
</script>

<link rel="stylesheet" href="{{ cache_safe('/css/industrial-ui.css') }}">
<script>document.body.classList.add('if-console-view');</script>
<div class="if-ui">
 <header class="if-page-header">
  <div class="if-heading"><span class="if-heading-icon"><i class="fa fa-cubes" aria-hidden="true"></i></span><div><h2>插件管理</h2><p class="if-subtitle">安装扩展功能，管理已安装插件与软件来源</p></div></div>
  <div class="if-actions"><button class="btn btn-default" id="plugin_connection_open" type="button" data-toggle="modal" data-target="#pluginConnectionModal" aria-haspopup="dialog"><i class="fa fa-cog" aria-hidden="true"></i>连接设置</button><button class="btn btn-primary" id="refresh_plugins" type="button"><i class="fa fa-refresh" aria-hidden="true"></i>刷新插件目录</button></div>
 </header>
 <div class="if-panel">
  <div class="if-toolbar">
   <div class="if-segments" role="group" aria-label="插件筛选"><button class="btn active" type="button" data-plugin-filter="all" aria-pressed="true">全部 <span id="plugin_count_all"></span></button><button class="btn" type="button" data-plugin-filter="installed" aria-pressed="false">已安装 <span id="plugin_count_installed"></span></button><button class="btn" type="button" data-plugin-filter="custom" aria-pressed="false">本地定制 <span id="plugin_count_custom"></span></button></div>
   <div class="if-search"><i class="fa fa-search" aria-hidden="true"></i><label class="sr-only" for="plugin_search">搜索插件</label><input type="search" class="form-control" autocomplete="off" id="plugin_search" placeholder="搜索插件名称或功能"></div>
  </div>
  <div class="if-panel-head"><span id="plugin_refresh_status" class="if-muted" role="status" aria-live="polite">正在读取插件目录…</span><i id="plugin_progress" aria-hidden="true"></i></div>
  <div class="if-table-scroll"><table class="table" id="pluginlist"><thead><tr><th>插件</th><th>已安装版本</th><th>源版本</th><th>大小</th><th>支持级别</th><th>来源</th><th class="text-right">操作</th></tr></thead><tbody></tbody></table></div>
  <div id="pluginNoMatches" class="if-empty" hidden><i class="fa fa-search" aria-hidden="true"></i> 没有匹配的插件，请调整搜索或筛选条件。</div>
 </div>
 <section class="if-panel" id="plugin_output_container" style="display:none"><div class="if-panel-head"><h3>操作日志</h3><button class="btn btn-default" type="button" id="plugin_output_copy"><i class="fa fa-copy" aria-hidden="true"></i>复制日志</button></div><div class="if-panel-body"><textarea id="plugin_output" aria-label="插件操作日志" class="form-control" rows="10" readonly></textarea></div></section>
</div>
<div class="modal fade if-ui if-modal" id="pluginConnectionModal" tabindex="-1" role="dialog" aria-labelledby="pluginConnectionTitle">
 <div class="modal-dialog" role="document"><div class="modal-content">
  <div class="modal-header"><button type="button" class="close" data-dismiss="modal" aria-label="关闭"><span aria-hidden="true">&times;</span></button><h3 class="modal-title" id="pluginConnectionTitle">软件源连接设置</h3><p class="if-subtitle" style="margin-top:6px">选择下载镜像与代理，保存后刷新插件目录</p></div>
  <div class="modal-body">
   <div class="form-group"><label for="plugin_mirror">下载镜像</label><select id="plugin_mirror" class="form-control"></select></div>
   <div class="form-group"><label for="plugin_proxy">下载代理</label><input id="plugin_proxy" class="form-control" type="text" placeholder="http://主机:端口" autocomplete="off" aria-describedby="plugin_proxy_help"><p id="plugin_proxy_help" class="help-block">留空直接连接；填写可供防火墙访问的代理地址。</p></div>
   <div id="plugin_connection_status" role="status" aria-live="polite"></div>
  </div>
  <div class="modal-footer"><button type="button" class="btn btn-default" data-dismiss="modal">取消</button><button id="save_plugin_connection" type="button" class="btn btn-primary"><i class="fa fa-check" aria-hidden="true"></i>保存连接设置</button></div>
 </div></div>
</div>
