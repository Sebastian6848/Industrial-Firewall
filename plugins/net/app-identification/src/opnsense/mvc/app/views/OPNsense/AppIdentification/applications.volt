{#

Copyright (C) 2026 Deciso B.V.
All rights reserved.

#}

<link rel="stylesheet" href="{{ cache_safe('/ui/css/industrial-ui.css') }}">
<div class="feature-ui">
<style>
.appident-applications {
	padding: 20px 24px 24px;
}
.appident-applications .appident-section + .appident-section {
	margin-top: 28px;
	padding-top: 24px;
	border-top: 1px solid #e5e5e5;
}
.appident-applications .appident-section-title {
	margin: 0 0 16px;
	font-size: 18px;
	line-height: 1.5;
	font-weight: 600;
}
.appident-applications .appident-section-tools {
	margin: 0 0 12px 18px;
}
.appident-applications .table {
	margin-bottom: 0;
}
@media (max-width: 767px) {
	.appident-applications {padding: 16px;}
	.appident-applications .appident-section-tools {
		float: none !important;
		margin: 0 0 14px;
	}
}
</style>

<script>
	$(document).ready(function () {
		'use strict';

		function showApiError(title, message, retryFn) {
			const buttons = [{
				label: '{{ lang._('关闭') }}',
				action: function (dialog) {
					dialog.close();
				}
			}];

			if (typeof retryFn === 'function') {
				buttons.unshift({
					label: '{{ lang._('重试') }}',
					cssClass: 'btn-primary',
					action: function (dialog) {
						dialog.close();
						retryFn();
					}
				});
			}

			BootstrapDialog.show({
				type: BootstrapDialog.TYPE_DANGER,
				title: title,
				message: esc(message || '{{ lang._('未知错误') }}'),
				buttons: buttons
			});
		}

		function esc(value) {
			return $('<div/>').text(value === null || value === undefined ? '' : String(value)).html();
		}

		function bytesToSize(bytes) {
			let value = Number(bytes || 0);
			const units = ['B', 'KB', 'MB', 'GB', 'TB'];
			let idx = 0;
			if (value === 0) {
				return '0 B';
			}
			while (value >= 1024 && idx < units.length - 1) {
				value /= 1024;
				idx += 1;
			}
			return value.toFixed(2) + ' ' + units[idx];
		}

		function normalizeColor(color) {
			const value = String(color || '').replace(/cc$/i, '');
			return /^#[0-9a-f]{3,8}$/i.test(value) ? value : '#337ab7';
		}

		function displayApplicationName(name) {
			const value = String(name || '').trim();
			const parts = value.split('.');
			if (parts.length > 1) {
				const suffix = parts.slice(1).join('.').trim();
				if (suffix !== '') {
					return suffix;
				}
			}
			return value;
		}

		function renderL7StatsTable(data) {
			const tbody = $('#l7-stats-body');
			const noApplicationDataText = "{{ lang._('暂无应用流量数据') }}";
			let applications = Array.isArray(data && data.applications) ? data.applications : [];

			if (applications.length === 0 && data && Array.isArray(data.labels)) {
				const labels = data.labels || [];
				const series = Array.isArray(data.series) ? data.series : [];
				applications = labels.map(function (label, idx) {
					return {
						name: label,
						bytes: Number(series[idx] || 0),
						is_custom: false
					};
				});
				}

				if (applications.length === 0) {
					tbody.html('<tr><td colspan="4" class="text-center text-muted">' + esc(noApplicationDataText) + '</td></tr>');
					return;
				}

			const total = applications.reduce(function (sum, item) {
				return sum + Number(item.bytes || 0);
			}, 0);
			const maxVal = Math.max.apply(null, applications.map(function (item) {
				return Number(item.bytes || 0);
			})) || 1;
			let rows = '';

			applications.slice(0, 10).forEach(function (item) {
				const bytes = Number(item.bytes || 0);
				const percent = total > 0 ? (bytes / total * 100).toFixed(1) : '0.0';
				const barW = maxVal > 0 ? (bytes / maxVal * 100).toFixed(1) : '0.0';
				const color = item.is_custom ? '#d9534f' : '#337ab7';
				const appName = displayApplicationName(item.name);

				rows += '<tr>' +
					'<td>' + esc(appName) + '</td>' +
					'<td>' + esc(item.bytes_fmt || bytesToSize(bytes)) + '</td>' +
					'<td>' + esc(percent + '%') + '</td>' +
					'<td style="width:200px;">' +
					'<div style="background:' + color + ';width:' + barW + '%;height:14px;border-radius:3px;min-width:2px;"></div>' +
					'</td>' +
					'</tr>';
			});

			tbody.html(rows);
			updateHostAppFilter(applications);
		}

		function updateHostAppFilter(applications) {
			const select = $('#top_host_app_filter');
			const current = select.val() || 'all';
			const customApps = {};
			applications.forEach(function (item) {
				if (item.is_custom && item.name) {
					customApps[item.name] = true;
				}
			});

			select.find('option[data-custom-app="1"]').remove();
			Object.keys(customApps).sort().forEach(function (name) {
				select.append('<option data-custom-app="1" value="custom:' + esc(name) + '">' + esc(name) + '</option>');
			});
			const hasCurrent = select.find('option').filter(function () {
				return $(this).val() === current;
			}).length > 0;
			select.val(hasCurrent ? current : 'all');
			$('.selectpicker').selectpicker('refresh');
		}

		function loadL7Stats() {
			const updatingText = "{{ lang._('更新中...') }}";
			const refreshFailedText = "{{ lang._('刷新失败') }}";
			const updatedText = "{{ lang._('已更新') }}";
			$('#app-stats-refresh-status').show().removeClass('text-danger text-success').addClass('text-muted')
				.html('<span class="fa fa-refresh fa-spin"></span> ' + esc(updatingText));
			ajaxCall('/api/appidentification/applications/topApplications', {}, function (response) {
				if (!response || response.status === 'error') {
					$('#app-stats-refresh-status').removeClass('text-muted text-success').addClass('text-danger')
						.html('<span class="fa fa-exclamation-triangle"></span> ' + esc(refreshFailedText));
					showApiError('{{ lang._('加载应用数据失败') }}', (response && response.message) ? response.message : '{{ lang._('无法加载应用数据') }}', loadL7Stats);
					return;
				}

				const data = response.data || {};
				renderL7StatsTable(data);
				$('#app-stats-refresh-status').removeClass('text-muted text-danger').addClass('text-success')
					.html('<span class="fa fa-check"></span> ' + esc(updatedText));
				window.setTimeout(function () {
					$('#app-stats-refresh-status').fadeOut(300);
				}, 1200);
			});
		}

		function renderHostRole(host) {
			const asClient = Number(host.as_client || 0);
			const asServer = Number(host.as_server || 0);
			if (asClient > 0 && asServer > 0) {
				return '<span class="label label-info">{{ lang._('双向') }}</span>';
			}
			if (asClient > 0) {
				return '<span class="label label-primary">{{ lang._('客户端') }}</span>';
			}
			return '<span class="label label-success">{{ lang._('服务器') }}</span>';
		}

		function loadTopHosts() {
			ajaxCall('/api/appidentification/applications/getTopHosts', {
				app_filter: $('#top_host_app_filter').val() || 'all'
			}, function (response) {
				if (!response || response.status !== 'ok' || !Array.isArray(response.data) || response.data.length === 0) {
					$('#top-hosts-body').html('<tr><td colspan="5" class="text-center text-muted">{{ lang._('暂无主机数据') }}</td></tr>');
					return;
				}

				let rows = '';
				response.data.forEach(function (host) {
					const ip = host.ip || '';
					const name = host.name && host.name !== ip ? host.name : '-';
					rows += '<tr>' +
						'<td><code>' + esc(ip) + '</code></td>' +
						'<td>' + esc(name) + '</td>' +
						'<td>' + esc(host.flows || 0) + '</td>' +
						'<td>' + esc(host.bytes_fmt || bytesToSize(host.bytes || 0)) + '</td>' +
						'<td>' + renderHostRole(host) + '</td>' +
						'</tr>';
				});

				$('#top-hosts-body').html(rows);
			});
		}

		$('#reload-app-data').on('click', function () {
			loadL7Stats();
			loadTopHosts();
		});

		$('#top_host_app_filter').on('change', function () {
			loadTopHosts();
		});

		loadL7Stats();
		loadTopHosts();
		setInterval(function () {
			loadL7Stats();
			loadTopHosts();
		}, 30000);

		$(document).ajaxError(function (event, xhr, settings) {
			if (settings && settings.url && settings.url.indexOf('/api/appidentification/') === 0) {
				const msg = xhr.responseJSON ? xhr.responseJSON.message : '{{ lang._('网络请求失败') }}';
				showApiError('{{ lang._('加载失败') }}', msg);
			}
		});
	});
</script>

<div class="content-box appident-applications">
	<div class="row appident-section">
		<div class="col-md-12">
			<div class="pull-right appident-section-tools">
				<small id="app-stats-refresh-status" class="text-muted" style="display:none;"></small>
			</div>
			<h4 class="appident-section-title">{{ lang._('Top 10 应用流量分布') }}</h4>
			<table class="table table-striped table-condensed">
				<thead>
				<tr>
					<th>{{ lang._('应用名称') }}</th>
					<th>{{ lang._('总流量') }}</th>
					<th>{{ lang._('占比') }}</th>
					<th>{{ lang._('流量条') }}</th>
				</tr>
				</thead>
				<tbody id="l7-stats-body">
				<tr>
					<td colspan="4" class="text-center text-muted">{{ lang._('加载中...') }}</td>
				</tr>
				</tbody>
			</table>
		</div>
	</div>

	<div class="row appident-section">
		<div class="col-md-12">
			<div class="pull-right appident-section-tools">
				<select id="top_host_app_filter" class="selectpicker" data-width="180px">
					<option value="all">{{ lang._('所有应用') }}</option>
					<option value="custom_only">{{ lang._('仅自定义应用') }}</option>
				</select>
				<button id="reload-app-data" type="button" class="btn btn-default btn-xs">
					<span class="fa fa-refresh"></span> {{ lang._('刷新') }}
				</button>
			</div>
			<h4 class="appident-section-title">{{ lang._('Top 10 主机流量排行') }}</h4>
			<table class="table table-condensed table-hover table-striped table-responsive">
				<thead>
				<tr>
					<th>{{ lang._('IP 地址') }}</th>
					<th>{{ lang._('主机名') }}</th>
					<th>{{ lang._('活跃流') }}</th>
					<th>{{ lang._('总流量') }}</th>
					<th>{{ lang._('角色') }}</th>
				</tr>
				</thead>
				<tbody id="top-hosts-body">
				<tr>
					<td colspan="5" class="text-center text-muted">{{ lang._('加载中...') }}</td>
				</tr>
				</tbody>
			</table>
		</div>
	</div>
</div>

{{ partial("OPNsense/AppIdentification/rules", ['formDialogRule': formDialogRule]) }}

</div>
