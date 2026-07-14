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
            const details = data.details || "{{ lang._('Sorry, plugin details are currently not available.') }}";
            stdDialogInform("{{ lang._('Plugin details') }}", details, "{{ lang._('Close') }}");
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
                    "{{ lang._('Plugin operation') }}",
                    data.status_msg || "{{ lang._('The plugin operation was rejected.') }}",
                    "{{ lang._('Close') }}",
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
                title: "{{ lang._('Confirm installation') }}",
                message: "{{ lang._('Install this plugin and its required packages from the official signed repository?') }}" +
                    ' <strong>' + escapeHtml(packageName) + '</strong>',
                buttons: [{
                    label: "{{ lang._('Install') }}",
                    cssClass: 'btn-primary',
                    action: function (dialogRef) {
                        dialogRef.close();
                        runPluginAction('install', packageName);
                    }
                }, {
                    label: "{{ lang._('Cancel') }}",
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
                title: "{{ lang._('Confirm reinstallation') }}",
                message: "{{ lang._('Reinstall this plugin from the official signed repository?') }}" +
                    ' <strong>' + escapeHtml(packageName) + '</strong>',
                buttons: [{
                    label: "{{ lang._('Reinstall') }}",
                    cssClass: 'btn-primary',
                    action: function (dialogRef) {
                        dialogRef.close();
                        runPluginAction('reinstall', packageName);
                    }
                }, {
                    label: "{{ lang._('Cancel') }}",
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
                title: "{{ lang._('Confirm removal') }}",
                message: "{{ lang._('Do you really want to remove this plugin?') }}" +
                    ' <strong>' + escapeHtml(packageName) + '</strong>',
                buttons: [{
                    label: "{{ lang._('Remove') }}",
                    cssClass: 'btn-warning',
                    action: function (dialogRef) {
                        dialogRef.close();
                        runPluginAction('remove', packageName);
                    }
                }, {
                    label: "{{ lang._('Cancel') }}",
                    action: function (dialogRef) {
                        dialogRef.close();
                    }
                }]
            });
        });
    }

    function loadPlugins() {
        $('#plugin_progress').addClass('fa fa-spinner fa-pulse');
        ajaxGet('/api/core/firmware/info', {}, function (data) {
            const tbody = $('#pluginlist > tbody');
            tbody.empty();

            $.each(data.plugin || [], function (index, plugin) {
                const installed = plugin.installed === '1';
                const provided = plugin.provided === '1';
                const installedVersion = installed ? plugin.version : "{{ lang._('N/A') }}";
                const availableVersion = provided ? plugin.remote_version : "{{ lang._('N/A') }}";
                let actions = '<button class="btn btn-default btn-xs act-details" data-package="' +
                    escapeHtml(plugin.name) + '" data-toggle="tooltip" title="{{ lang._('Info') }}">' +
                    '<i class="fa fa-info-circle fa-fw"></i></button>';

                if (!installed && provided) {
                    actions += '<button class="btn btn-default btn-xs act-install" data-package="' +
                        escapeHtml(plugin.name) + '" data-toggle="tooltip" title="{{ lang._('Install') }}">' +
                        '<i class="fa fa-plus fa-fw"></i></button>';
                } else if (installed && provided) {
                    actions += '<button class="btn btn-default btn-xs act-reinstall" data-package="' +
                        escapeHtml(plugin.name) + '" data-toggle="tooltip" title="{{ lang._('Reinstall') }}">' +
                        '<i class="fa fa-repeat fa-fw"></i></button>';
                }

                if (installed) {
                    actions += '<button class="btn btn-default btn-xs act-remove" data-package="' +
                        escapeHtml(plugin.name) + '" data-toggle="tooltip" title="{{ lang._('Remove') }}">' +
                        '<i class="fa fa-trash fa-fw"></i></button>';
                }

                tbody.append(
                    '<tr class="plugin-entry">' +
                    '<td>' + escapeHtml(plugin.name) + (installed ? " <b>({{ lang._('installed') }})</b>" : '') + '</td>' +
                    '<td>' + escapeHtml(installedVersion) + '</td>' +
                    '<td>' + escapeHtml(availableVersion) + '</td>' +
                    '<td>' + escapeHtml(plugin.flatsize) + '</td>' +
                    '<td>' + escapeHtml(plugin.repository) + '</td>' +
                    '<td>' + escapeHtml(plugin.comment) + '</td>' +
                    '<td style="white-space:nowrap"><div class="input-group">' + actions + '</div></td>' +
                    '</tr>'
                );
            });

            if (tbody.children().length === 0) {
                tbody.append('<tr><td colspan="7">{{ lang._('No plugins were returned by the configured repository.') }}</td></tr>');
            }

            $('#plugin_progress').removeClass('fa fa-spinner fa-pulse');
            bindPluginActions();
            filterPlugins();
        });
    }

    $(document).ready(function () {
        $('#plugin_search').keyup(filterPlugins);
        $('#refresh_plugins').click(loadPlugins);
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
            }
        });
        loadPlugins();
    });
</script>

<div class="container-fluid">
    <div class="row">
        <div class="col-md-12">
            <div class="content-box table-responsive">
                <div style="padding: 10px 8px;">
                    <button class="btn btn-primary" id="refresh_plugins">
                        <i class="fa fa-refresh"></i> {{ lang._('Refresh official plugins') }}
                    </button>
                    <i id="plugin_progress"></i>
                    <span class="text-muted" style="margin-left:10px;">
                        {{ lang._('System updates remain disabled. Only os-* plugins and their dependencies can be installed from the official signed repository.') }}
                    </span>
                </div>
                <table class="table table-striped table-condensed" id="pluginlist">
                    <thead>
                        <tr>
                            <th><input type="text" class="input-sm" autocomplete="off" id="plugin_search" placeholder="{{ lang._('Name') }}"></th>
                            <th>{{ lang._('Version') }}</th>
                            <th>{{ lang._('Available') }}</th>
                            <th>{{ lang._('Size') }}</th>
                            <th>{{ lang._('Repository') }}</th>
                            <th>{{ lang._('Comment') }}</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody></tbody>
                </table>
                <div id="plugin_output_container" style="display:none; padding: 0 8px 10px;">
                    <textarea id="plugin_output" class="form-control" rows="12" readonly="readonly" style="font-family:monospace"></textarea>
                    <a href="#" id="plugin_output_copy">{{ lang._('Copy operation output to clipboard') }}</a>
                </div>
            </div>
        </div>
    </div>
</div>
