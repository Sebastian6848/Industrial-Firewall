{#

Copyright (C) 2026 Deciso B.V.
All rights reserved.

#}

<link rel="stylesheet" href="{{ cache_safe('/ui/css/industrial-ui.css') }}">
<div class="feature-ui">
<style>
.appident-settings {
	padding: 18px 22px 24px;
}
.appident-settings > .tab-pane > .content-box {
	padding: 8px 12px 20px;
}
.appident-settings .form-group {
	margin-bottom: 14px;
}
.appident-settings hr {
	margin: 20px 0 16px;
}
@media (max-width: 767px) {
	.appident-settings {
		padding: 14px;
	}
}
</style>

<ul class="nav nav-tabs" data-tabs="tabs" id="maintabs">
	<li class="active"><a data-toggle="tab" href="#general">{{ lang._('常规') }}</a></li>
</ul>

<div class="tab-content content-box tab-content appident-settings">
	<div id="general" class="tab-pane fade in active">
		<div class="content-box" style="padding-bottom: 1.5em;">
			{{ partial("layout_partials/base_form",['fields':generalForm,'id':'frm_general_settings'])}}
			<div class="col-md-12">
				<hr />
				<button class="btn btn-primary" id="saveAct" type="button"><b>{{ lang._('保存') }}</b> <i id="saveAct_progress"></i></button>
				<button class="btn btn-default" id="testAct" type="button"><span class="fa fa-plug"></span> {{ lang._('测试连接') }} <i id="testAct_progress"></i></button>
				<button class="btn btn-default" id="restartAct" type="button"><span class="fa fa-refresh"></span> {{ lang._('重启采集服务') }} <i id="restartAct_progress"></i></button>
				<button class="btn btn-default" id="openNtopngAct" type="button"><span class="fa fa-external-link"></span> {{ lang._('在 ntopng 中查看') }}</button>
				<button class="btn btn-default" id="ntopngGuideAct" type="button" title="{{ lang._('配置指引') }}"><span class="fa fa-info-circle text-info"></span> {{ lang._('配置指引') }}</button>
			</div>
		</div>
	</div>
</div>

<div class="modal fade" id="ntopngGuideModal" tabindex="-1" role="dialog" aria-labelledby="ntopngGuideModalLabel">
	<div class="modal-dialog modal-lg" role="document">
		<div class="modal-content">
			<div class="modal-header">
				<button type="button" class="close" data-dismiss="modal" aria-label="{{ lang._('关闭') }}"><span aria-hidden="true">&times;</span></button>
				<h4 class="modal-title" id="ntopngGuideModalLabel">{{ lang._('ntopng 初次配置指引') }}</h4>
			</div>
			<div class="modal-body">
				<ol>
					<li>
						<p><strong>{{ lang._('第一步：修改默认密码') }}</strong></p>
						<p>{{ lang._('打开 ntopng 页面（可点击上方“在 ntopng 中查看”按钮），使用默认账号 admin / admin 登录。点击左上角用户头像，进入') }} <code>admin &rarr; Password</code>{{ lang._('，修改密码。') }}</p>
					</li>
					<li>
						<p><strong>{{ lang._('第二步：生成 API Token') }}</strong></p>
						<p>{{ lang._('点击 ntopng 左上角用户头像，进入') }} <code>admin &rarr; User Authentication Token</code>{{ lang._('，生成并复制 Token 字符串。') }}</p>
					</li>
					<li>
						<p><strong>{{ lang._('第三步：填写 Auth Token') }}</strong></p>
						<p>{{ lang._('将复制的 Token 粘贴到本页面“Auth Token”字段中，点击“保存”，然后点击“测试连接”验证配置是否正确。') }}</p>
					</li>
				</ol>
			</div>
			<div class="modal-footer">
				<button type="button" class="btn btn-default" data-dismiss="modal">{{ lang._('我知道了') }}</button>
				<button type="button" class="btn btn-primary" id="ntopngGuideOpenAct"><span class="fa fa-external-link"></span> {{ lang._('直接打开 ntopng') }}</button>
			</div>
		</div>
	</div>
</div>

<script>
$(document).ready(function() {
	const action = new URLSearchParams(window.location.search).get('action');
	if (window.location.hash === '#rules' || action === 'add' || action === 'import') {
		window.location.replace('/ui/appidentification/applications/' + window.location.search + '#rules');
		return;
	}
	function esc(value) {
		return $('<div/>').text(value === null || value === undefined ? '' : String(value)).html();
	}

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

	function getNtopngBaseUrl() {
		const host = $.trim(window.location.hostname || '');
		if (host === '') {
			return '';
		}
		const port = $.trim($('#general\\.rest_port').val() || '3000');
		const scheme = $('#general\\.rest_scheme').val() === 'https' ? 'https' : 'http';
		let url = scheme + '://' + ($.trim($('#general\\.rest_host').val() || '') || host);

		if (port !== '') {
			url += ':' + port;
		}

		return url;
	}

	function openNtopngConsole() {
		const url = getNtopngBaseUrl();
		if (url === '') {
			BootstrapDialog.show({
				type: BootstrapDialog.TYPE_WARNING,
				title: '{{ lang._('提示') }}',
				message: esc('{{ lang._('请先填写 ntopng 主机地址') }}'),
				buttons: [{label: '{{ lang._('关闭') }}', action: function(d){ d.close(); }}]
			});
			return false;
		}
		window.open(url, '_blank', 'noopener');
		return true;
	}

	const dataGetMap = {'frm_general_settings': '/api/appidentification/general/get'};
	mapDataToFormUI(dataGetMap).done(function() {
		formatTokenizersUI();
		$('.selectpicker').selectpicker('refresh');
	});

	$('#saveAct').click(function() {
		$('#saveAct_progress').addClass('fa fa-spinner fa-pulse');
		saveFormToEndpoint('/api/appidentification/general/set', 'frm_general_settings', function() {
			$('#saveAct_progress').removeClass('fa fa-spinner fa-pulse');
		}, true, function() {
			$('#saveAct_progress').removeClass('fa fa-spinner fa-pulse');
			showApiError('{{ lang._('保存配置失败') }}', '{{ lang._('无法保存采集服务配置') }}');
		});
	});

	$('#restartAct').click(function() {
		$('#restartAct_progress').addClass('fa fa-spinner fa-pulse');
		ajaxCall('/api/appidentification/general/ntopngrestart', {}, function() {
			$('#restartAct_progress').removeClass('fa fa-spinner fa-pulse');
		}, function(data) {
			$('#restartAct_progress').removeClass('fa fa-spinner fa-pulse');
			if (!data || data.status === 'error') {
				showApiError('{{ lang._('重启 ntopng 失败') }}', (data && data.message) ? data.message : '{{ lang._('无法重启流量采集服务') }}', function () {
					$('#restartAct').click();
				});
			}
		});
	});

	$('#testAct').click(function() {
		$('#testAct_progress').addClass('fa fa-spinner fa-pulse');
		$.ajax({
			url: '/api/appidentification/general/status',
			method: 'GET',
			dataType: 'json',
			success: function(data) {
				$('#testAct_progress').removeClass('fa fa-spinner fa-pulse');
				if (!data || data.status === 'error') {
					showApiError('{{ lang._('连接测试失败') }}', (data && data.message) ? data.message : '{{ lang._('无法连接流量采集服务') }}');
					return;
				}
				BootstrapDialog.show({
					type: BootstrapDialog.TYPE_PRIMARY,
					title: '{{ lang._('操作成功') }}',
					message: $('<div/>').text(data.message || '{{ lang._('连接成功') }}').html(),
					buttons: [{label: '{{ lang._('关闭') }}', action: function(d){ d.close(); }}]
				});
			},
			error: function(xhr) {
				$('#testAct_progress').removeClass('fa fa-spinner fa-pulse');
				const msg = xhr.responseJSON ? xhr.responseJSON.message : '{{ lang._('网络请求失败') }}';
				showApiError('{{ lang._('连接测试失败') }}', msg);
			}
		});
	});

	$('#openNtopngAct').on('click', function () {
		openNtopngConsole();
	});

	$('#ntopngGuideAct').on('click', function () {
		$('#ntopngGuideModal').modal('show');
	});

	$('#ntopngGuideOpenAct').on('click', function () {
		openNtopngConsole();
	});

	$(document).ajaxError(function(event, xhr, settings) {
		if (settings && settings.url && settings.url.indexOf('/api/appidentification/') === 0) {
			const msg = xhr.responseJSON ? xhr.responseJSON.message : '{{ lang._('网络请求失败') }}';
			showApiError('{{ lang._('加载失败') }}', msg);
		}
	});
});
</script>

</div>
