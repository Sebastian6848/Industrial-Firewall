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

    function filterPlugins() {
        const search = $('#plugin_search').val().toLowerCase();
        $('.plugin-entry').each(function () {
            $(this).toggle($(this).text().toLowerCase().indexOf(search) !== -1);
        });
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
                    '<tr class="plugin-entry">' +
                    '<td>' + escapeHtml(plugin.name) + (stateLabel ? ' <b>(' + stateLabel + ')</b>' : '') + '</td>' +
                    '<td>' + escapeHtml(installedVersion) + '</td>' +
                    '<td>' + escapeHtml(availableVersion) + '</td>' +
                    '<td>' + escapeHtml(plugin.flatsize) + '</td>' +
                    '<td>' + escapeHtml(plugin.tier) + '</td>' +
                    '<td>' + escapeHtml(plugin.repository) + '</td>' +
                    '<td>' + escapeHtml(plugin.comment) + '</td>' +
                    '<td style="white-space:nowrap"><div class="input-group">' + actions + '</div></td>' +
                    '</tr>'
                );
            });

            if (tbody.children().length === 0) {
                tbody.append('<tr><td colspan="8">{{ lang._('软件源尚未返回插件目录。') }}</td></tr>');
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
                $('#plugin_connection_status').text(data.status === 'ok' ? '已保存，点击刷新获取目录。' : data.status_msg || '保存失败');
            });
        });
        $('#plugin_search').keyup(filterPlugins);
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

<div class="container-fluid">
    <div class="content-box" style="padding:12px;margin-bottom:12px">
        <details>
            <summary style="cursor:pointer">软件源连接设置</summary>
            <div class="form-group" style="margin-top:12px">
                <label for="plugin_mirror">镜像</label>
                <select id="plugin_mirror" class="form-control"></select>
            </div>
            <div class="form-group">
                <label for="plugin_proxy">下载代理</label>
                <input id="plugin_proxy" class="form-control" type="text" placeholder="http://主机:端口，留空直接连接" autocomplete="off">
            </div>
            <button id="save_plugin_connection" type="button" class="btn btn-default">保存连接设置</button>
            <span id="plugin_connection_status" role="status" style="margin-left:10px"></span>
        </details>
    </div>
    <div class="row">
        <div class="col-md-12">
            <div class="content-box table-responsive">
                <div style="padding: 10px 8px;">
                    <button class="btn btn-primary" id="refresh_plugins">
                        <i class="fa fa-refresh"></i> {{ lang._('刷新插件目录') }}
                    </button>
                    <i id="plugin_progress"></i>
                    <span id="plugin_refresh_status" class="text-muted" style="margin-left:10px;">
                        {{ lang._('可安装兼容插件及其依赖。') }}
                    </span>
                </div>
                <table class="table table-striped table-condensed" id="pluginlist">
                    <thead>
                        <tr>
                            <th><input type="text" class="input-sm" autocomplete="off" id="plugin_search" placeholder="{{ lang._('名称') }}"></th>
                            <th>{{ lang._('已安装版本') }}</th>
                            <th>{{ lang._('源版本') }}</th>
                            <th>{{ lang._('大小') }}</th>
                            <th>{{ lang._('支持级别') }}</th>
                            <th>{{ lang._('来源') }}</th>
                            <th>{{ lang._('说明') }}</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody></tbody>
                </table>
                <div id="plugin_output_container" style="display:none; padding: 0 8px 10px;">
                    <textarea id="plugin_output" class="form-control" rows="12" readonly="readonly" style="font-family:monospace"></textarea>
                    <a href="#" id="plugin_output_copy">{{ lang._('复制操作日志') }}</a>
                </div>
            </div>
        </div>
    </div>
</div>
