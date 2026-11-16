{#
 # Copyright (c) 2024 Deciso B.V.
 # All rights reserved.
 #
 # Redistribution and use in source and binary forms, with or without modification,
 # are permitted provided that the following conditions are met:
 #
 # 1. Redistributions of source code must retain the above copyright notice,
 #    this list of conditions and the following disclaimer.
 #
 # 2. Redistributions in binary form must reproduce the above copyright notice,
 #    this list of conditions and the following disclaimer in the documentation
 #    and/or other materials provided with the distribution.
 #
 # THIS SOFTWARE IS PROVIDED ``AS IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES,
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

{% set theme_name = ui_theme|default('opnsense') %}
<!-- required for gridstack calculations -->
<link href="{{ cache_safe('/ui/css/gridstack.min.css') }}" rel="stylesheet">
<!-- required for any amount of columns < 12 -->
<link href="{{ cache_safe('/ui/css/gridstack-extra.min.css') }}" rel="stylesheet">
<!-- gridstack core -->
<script src="{{ cache_safe('/ui/js/gridstack-all.min.js') }}"></script>
<script src="{{ cache_safe('/ui/js/opnsense_widget_manager.js') }}"></script>
<script src="{{ cache_safe('/ui/js/moment-with-locales.min.js') }}"></script>
<script src="{{ cache_safe('/ui/js/chart.umd.min.js') }}"></script>
<script src="{{ cache_safe('/ui/js/chartjs-plugin-colorschemes.min.js') }}"></script>
<script src="{{ cache_safe('/ui/js/chartjs-adapter-moment.min.js') }}"></script>
<script src="{{ cache_safe('/ui/js/chartjs-plugin-streaming.js') }}"></script>
<script src="{{ cache_safe('/ui/js/smoothie.js') }}"></script>
<script src="{{ cache_safe('/ui/js/widgets/BaseWidget.js') }}"></script>
<script src="{{ cache_safe('/ui/js/widgets/BaseTableWidget.js') }}"></script>
<script src="{{ cache_safe('/ui/js/widgets/BaseGaugeWidget.js') }}"></script>
<link rel="stylesheet" type="text/css" href="{{ cache_safe(theme_file_or_default('/css/dashboard.css', theme_name)) }}" rel="stylesheet" />
<link rel="stylesheet" href="{{ cache_safe('/ui/css/dashboard-layout.css') }}">

<script>
$( document ).ready(function() {
    let chartBackgroundColor = getComputedStyle(document.body).getPropertyValue('--chart-js-background-color').trim();
    let chartBorderColor = getComputedStyle(document.body).getPropertyValue('--chart-js-border-color').trim();
    let chartFontColor = getComputedStyle(document.body).getPropertyValue('--chart-js-font-color').trim();

    if (chartBackgroundColor) Chart.defaults.backgroundColor = chartBackgroundColor;
    if (chartBorderColor) Chart.defaults.borderColor = chartBorderColor;
    if (chartFontColor) Chart.defaults.color = chartFontColor;

    function layoutFromRows(rows) {
        const layout = {};
        let y = 0;
        for (const [height, widgets] of rows) {
            let x = 0;
            for (const [id, width] of widgets) {
                layout[id] = {x, y, w: width, h: height, sizeToContent: false};
                x += width;
            }
            y += height;
        }
        return layout;
    }

    let widgetManager = new WidgetManager({
        float: false,
        columnOpts: {
            breakpoints: [{w: 620, c:1}, {w:1100, c:6}, {w:9999, c:12}]
        },
        disableDrag: true,
        disableResize: true,
        columns: 12,
        margin: 8,
        alwaysShowResizeHandle: true,
        sizeToContent: true,
        resizable: {
            handles: 'all'
        }
    }, {
        'save': "{{ lang._('Save') }}",
        'ok': "{{ lang._('OK') }}",
        'restore': "{{ lang._('Restore default layout') }}",
        'restoreconfirm': "{{ lang._('Are you sure you want to restore the default widget layout?') }}",
        'addwidget': "{{ lang._('Add Widget') }}",
        'add': "{{ lang._('Add') }}",
        'cancel': "{{ lang._('Cancel') }}",
        'failed': "{{ lang._('Failed to load widget') }}",
        'options': "{{ lang._('Options') }}",
        'edit': "{{ lang._('Edit') }}",
    }, {
        excludedWidgetIds: ['systeminformation', 'announcements'],
        preferredLayouts: {
            12: layoutFromRows([
                [202, [['cpu', 4], ['memory', 2], ['disk', 2], ['gateways', 4]]],
                [314, [['interfacestatistics', 6], ['firewall', 6]]],
                [438, [['services', 6], ['traffic', 6]]]
            ]),
            6: layoutFromRows([
                [202, [['cpu', 3], ['memory', 3]]],
                [202, [['disk', 3], ['gateways', 3]]],
                [270, [['interfacestatistics', 6]]],
                [314, [['firewall', 6]]],
                [412, [['services', 6]]],
                [438, [['traffic', 6]]]
            ]),
            1: layoutFromRows([
                [202, [['cpu', 1]]], [206, [['memory', 1]]], [206, [['disk', 1]]],
                [158, [['gateways', 1]]], [256, [['interfacestatistics', 1]]],
                [282, [['firewall', 1]]], [398, [['services', 1]]], [410, [['traffic', 1]]]
            ])
        }
    });
    widgetManager.initialize();
});
</script>

<p class="dashboard-edit-hint text-muted" id="dashboard-edit-hint" hidden>{{ lang._('拖动卡片底部的橙色手柄调整高度，完成后点击保存。') }}</p>
<div class="grid-stack dashboard-grid"></div>
