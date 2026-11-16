{#

Copyright (C) 2026 Deciso B.V.
All rights reserved.

#}

<style>
.appident-catalog {
	padding: 24px;
	scroll-margin-top: 70px;
}
.appident-catalog-title-row {
	display: flex;
	align-items: baseline;
	gap: 12px;
	flex-wrap: wrap;
	margin-bottom: 10px;
}
.appident-catalog .appident-catalog-title {
	font-size: 18px;
	font-weight: 600;
	line-height: 1.5;
	margin: 0;
}
.appident-catalog #catalogCount {
	display: inline-block;
	font-size: 12px;
	font-weight: normal;
	line-height: 1.5;
	padding: 2px 8px;
	border: 1px solid #e5e5e5;
	border-radius: 3px;
}
.appident-catalog-description {
	margin: 0;
	font-size: 13px;
	line-height: 1.8;
}
.appident-catalog-toolbar {
	margin: 20px 0 16px;
	padding: 12px 14px;
	border: 1px solid #e8e8e8;
	border-radius: 4px;
	display: flex;
	justify-content: space-between;
	align-items: center;
	gap: 12px;
	flex-wrap: wrap;
}
.appident-rule-filter, .appident-rule-actions {
	display: flex;
	align-items: center;
	gap: 8px;
	flex-wrap: wrap;
}
.appident-rule-filter label {
	margin: 0;
	line-height: 1.5;
}
.appident-rule-filter .form-control {
	width: auto;
	height: auto;
	padding: 6px 32px 6px 12px;
	font-size: inherit;
	line-height: 1.5;
}
.appident-rule-detail .modal-body {
	max-height: 65vh;
	overflow-y: auto;
}
.appident-import-dialog .modal-body {padding:20px;max-height:70vh;overflow-y:auto;}
.appident-import-dialog .form-group {margin-bottom:18px;}
.appident-import-dialog .form-group>label:first-child {display:block;margin-bottom:6px;}
.appident-import-dialog .form-control {display:block;width:100%;max-width:100%;}
.appident-import-dialog #rules-import-preview {margin-top:20px;}
@media (max-width: 767px) {
	.appident-catalog {padding: 16px;}
	.appident-catalog-toolbar {padding: 12px;}
}
</style>

<section id="rules" class="content-box appident-catalog" aria-labelledby="catalogTitle">
	<header>
		<div class="appident-catalog-title-row">
			<h4 class="appident-catalog-title" id="catalogTitle">应用识别规则</h4>
			<span class="text-muted" id="catalogCount" aria-live="polite">加载中…</span>
		</div>
		<p class="appident-catalog-description text-muted">在这里查看内置规则，新增或导入自定义规则。自定义规则优先用于流量识别。</p>
	</header>
	<div class="appident-catalog-toolbar">
		<div class="appident-rule-filter">
			<label for="rules-source">规则来源</label>
			<select id="rules-source" class="form-control">
				<option value="all">全部来源</option>
				<option value="builtin">内置</option>
				<option value="custom">自定义（含导入）</option>
			</select>
		</div>
		<div class="appident-rule-actions">
			<button id="rules-add-open" type="button" class="btn btn-primary"><i class="fa fa-plus" aria-hidden="true"></i> 新增规则</button>
			<button id="rules-import-open" type="button" class="btn btn-default"><i class="fa fa-upload" aria-hidden="true"></i> 批量导入</button>
			<div class="btn-group">
				<button type="button" class="btn btn-default dropdown-toggle" data-toggle="dropdown" aria-haspopup="true" aria-expanded="false">
					<i class="fa fa-download" aria-hidden="true"></i> 导出与模板 <span class="caret"></span>
				</button>
				<ul class="dropdown-menu dropdown-menu-right">
					<li><a href="/api/appidentification/rule/export/json">导出自定义规则（JSON）</a></li>
					<li><a href="/api/appidentification/rule/export/csv">导出自定义规则（CSV）</a></li>
					<li class="divider" role="separator"></li>
					<li><a href="/api/appidentification/rule/template/json">下载 JSON 模板</a></li>
					<li><a href="/api/appidentification/rule/template/csv">下载 CSV 模板</a></li>
				</ul>
			</div>
		</div>
	</div>
	<div class="table-responsive">
		<table id="grid-app-rules" class="table table-condensed table-hover table-striped" data-editDialog="DialogRule">
			<thead>
				<tr>
					<th data-column-id="app_label" data-formatter="appname">应用或服务</th>
					<th data-column-id="source" data-width="95" data-sortable="false" data-formatter="source">来源</th>
					<th data-column-id="match_type" data-width="115" data-formatter="matchtype">匹配方式</th>
					<th data-column-id="match_value" data-sortable="false" data-formatter="matchvalues">匹配内容</th>
					<th data-column-id="enabled" data-width="85" data-formatter="rulestatus">状态</th>
					<th data-column-id="uuid" data-identifier="true" data-visible="false" data-selectable="false">ID</th>
					<th data-column-id="commands" data-width="118">操作</th>
				</tr>
			</thead>
			<tbody></tbody>
		</table>
	</div>
</section>

{{ partial("layout_partials/base_dialog",['fields':formDialogRule,'id':'DialogRule','label':lang._('编辑识别规则')]) }}

<script>
$(function () {
	function esc(value) {
		return $('<div/>').text(value === null || value === undefined ? '' : String(value)).html();
	}

	function splitMatchValues(rawValue) {
		if (Array.isArray(rawValue)) {
			return rawValue.map(function (value) {
				return $.trim(String(value || ''));
			}).filter(function (value) {
				return value !== '';
			});
		}

		return String(rawValue || '').split(/\r?\n/).map(function (value) {
			return $.trim(String(value || ''));
		}).filter(function (value) {
			return value !== '';
		});
	}

	function validateMatchValueLines(matchType, rawValue) {
		const errors = [];
		const lines = splitMatchValues(rawValue);
		if (lines.length === 0) {
			errors.push({line: 0, message: '{{ lang._('至少填写一个匹配值') }}'});
			return errors;
		}

		for (let idx = 0; idx < lines.length; idx++) {
			const lineNo = idx + 1;
			const value = lines[idx];
			if (matchType === 'domain') {
				if (/\s/.test(value)) {
					errors.push({line: lineNo, message: '{{ lang._('域名行不能包含空格') }}'});
				}
				continue;
			}
			if (matchType === 'ip') {
				const isIp = /^\d{1,3}(?:\.\d{1,3}){3}$/.test(value) || /^[0-9a-fA-F:]+$/.test(value);
				if (!isIp) {
					errors.push({line: lineNo, message: '{{ lang._('IP 行格式不正确') }}'});
				}
				continue;
			}
			if (matchType === 'cidr') {
				if (!/^([^\/\s]+)\/(\d{1,3})$/.test(value)) {
					errors.push({line: lineNo, message: '{{ lang._('CIDR 行格式不正确') }}'});
				}
				continue;
			}
			if (matchType === 'port') {
				if (!/^\d+$/.test(value) || Number(value) < 1 || Number(value) > 65535) {
					errors.push({line: lineNo, message: '{{ lang._('端口行必须是 1-65535') }}'});
				}
				continue;
			}
			if (matchType === 'protocol' && value === '') {
				errors.push({line: lineNo, message: '{{ lang._('协议行不能为空') }}'});
			}
		}

		return errors;
	}

	function setupRuleDialogUi() {
		const dialog = $('#DialogRule');
		if (!dialog.length || dialog.data('multivalue-bound') === true) {
			return;
		}

		dialog.data('multivalue-bound', true);
		let debounceTimer = null;

		function ensureValidationContainer() {
			const field = $('#rule\\.match_value');
			if (!field.length) {
				return null;
			}

			field.attr('rows', '5');
			field.attr('placeholder', '每行填写一个匹配值，例如：\nweixin.qq.com\nwechat.com\nqpic.cn');

			let container = $('#rule-match-value-validation');
			if (!container.length) {
				container = $('<div id="rule-match-value-validation" style="margin-top:6px;"></div>');
				field.closest('.form-group').append(container);
			}
			return container;
		}

		function validateDialogMatchValue() {
			const field = $('#rule\\.match_value');
			const typeField = $('#rule\\.match_type');
			const container = ensureValidationContainer();
			if (!field.length || !typeField.length || !container) {
				return;
			}

			const errors = validateMatchValueLines(String(typeField.val() || ''), String(field.val() || ''));
			const saveBtn = dialog.find('.modal-footer .btn-primary').first();
			if (errors.length === 0) {
				container.empty();
				field.css('background-color', '');
				saveBtn.prop('disabled', false);
				return;
			}

			let html = '<div class="alert alert-danger" style="margin-bottom:0; padding:6px 10px;">';
			html += '{{ lang._('以下匹配值行不合法：') }}<div style="margin-top:6px;">';
			errors.forEach(function (err) {
				html += '<div style="background:#fbe3e4; color:#a94442; padding:3px 6px; margin-bottom:4px; border-radius:2px;">';
				html += '{{ lang._('第') }} ' + esc(err.line) + ' {{ lang._('行') }}: ' + esc(err.message);
				html += '</div>';
			});
			html += '</div></div>';
			container.html(html);
			field.css('background-color', '#fff7f7');
			saveBtn.prop('disabled', true);
		}

		function scheduleValidation() {
			if (debounceTimer !== null) {
				clearTimeout(debounceTimer);
			}
			debounceTimer = setTimeout(validateDialogMatchValue, 500);
		}

		dialog.on('shown.bs.modal opnsense_bootgrid_mapped', function () {
			ensureValidationContainer();
			scheduleValidation();
		});

		dialog.on('input change', '#rule\\.match_value, #rule\\.match_type', function () {
			scheduleValidation();
		});
	}

	const matchTypes = {domain: '域名', ip: 'IP 地址', cidr: '网段', port: '端口', protocol: '应用协议'};
	const isCustom = (cell) => cell.getData().source === 'custom';
	const grid = $('#grid-app-rules').UIBootgrid({
		search: '/api/appidentification/rule/searchLibrary',
		get: '/api/appidentification/rule/getRule/',
		set: '/api/appidentification/rule/setRule/',
		add: '/api/appidentification/rule/addRule/',
		del: '/api/appidentification/rule/delRule/',
		toggle: '/api/appidentification/rule/toggleRule/',
		commands: {
			edit: {filter: isCustom},
			copy: {filter: isCustom},
			delete: {filter: isCustom},
			builtin: {
				filter: (cell) => !isCustom(cell),
				classname: 'fa fa-fw fa-info-circle',
				title: '查看内置规则',
				method: (event, cell) => viewBuiltin(cell.getData().catalog_id)
			}
		},
		options: {
			selection: false,
			disableScroll: true,
			rowCount: [25, 50, 100],
			requestHandler: (params) => Object.assign(params, {source: $('#rules-source').val()}),
			responseHandler: function (data) {
				$('#catalogCount').text('共 ' + data.library_count + ' 条');
				return data;
			},
			formatters: {
				appname: (column, row) => $('<span>').attr('title', row.description || row.app_label).text(row.app_label)[0].outerHTML,
				source: (column, row) => row.source === 'builtin' ? '<span class="text-muted">内置</span>' : '自定义',
				matchtype: (column, row) => esc(matchTypes[row.match_type] || row.match_type),
				matchvalues: (column, row) => esc(row.example) + (row.match_count > 1 ? ' <small class="text-muted">共 ' + row.match_count + ' 项</small>' : ''),
				rulestatus: (column, row) => {
					if (row.source === 'builtin') return '<span class="text-muted">生效</span>';
					const enabled = row.enabled === '1';
					return $('<button type="button" class="btn btn-xs btn-default command-toggle">')
						.attr({'data-row-id': row.uuid, 'data-value': enabled ? '1' : '0', 'aria-label': enabled ? '停用规则' : '启用规则'})
						.text(enabled ? '已启用' : '已停用')[0].outerHTML;
				}
			}
		}
	});

	function viewBuiltin(id) {
		ajaxGet('/api/appidentification/rule/builtin', {id: id}, function (data) {
			const message = $('<div>');
			if (data.status === 'ok') {
				message.append($('<p class="text-muted">').text('内置域名规则 · ' + data.rule.domains.length + ' 项匹配内容'));
				const table = $('<table class="table table-striped table-condensed">').append('<thead><tr><th>域名</th><th>匹配范围</th></tr></thead>');
				const body = $('<tbody>');
				data.rule.domains.forEach(function (domain) {
					body.append($('<tr>').append($('<td>').text(domain.value), $('<td>').text(domain.mode === 'exact' ? '仅此域名' : '含子域名')));
				});
				message.append(table.append(body));
			} else {
				message.text(data.message);
			}
			BootstrapDialog.show({
				title: data.status === 'ok' ? esc(data.rule.name) : '查看内置规则',
				cssClass: 'appident-rule-detail',
				message: message,
				buttons: [{label: '关闭', action: (dialog) => dialog.close()}]
			});
		});
	}

	function reloadRules() {
		grid.bootgrid('reload');
	}

	$('#rules-source').on('change', reloadRules);
	$('#rules-add-open').on('click', (event) => grid.data('UIBootgrid').command_add(event));
	setupRuleDialogUi();
	grid.on('loaded.rs.jquery.bootgrid', function () {
		$('#grid-app-rules-search-field').attr({placeholder: '搜索应用、域名或匹配值', 'aria-label': '搜索应用识别规则'});
	});

	let previewRequest=null, previewSequence=0, previewTimer=null;
    function importData(container) {
        return {format:container.find('input[name="import_format"]:checked').val(),
            mode:container.find('input[name="import_mode"]:checked').val(),payload:container.find('#rules-import-payload').val()};
    }
    function renderImportPreview(container) {
        if(container.data('importing'))return;
        clearTimeout(previewTimer);
        const sequence=++previewSequence;
        if(previewRequest)previewRequest.abort();
        const submit=container.closest('.modal-content').find('.btn-primary');
        submit.prop('disabled',true);
        const values=importData(container);
        if(!values.payload.trim()){container.find('#rules-import-preview').empty();return;}
        container.find('#rules-import-preview').empty().append($('<p class="text-muted">').text('正在校验规则…'));
        previewTimer=setTimeout(function(){
            previewRequest=$.ajax({url:'/api/appidentification/rule/preview',method:'POST',contentType:'application/json',dataType:'json',global:false,data:JSON.stringify(values)})
            .done(function(data){
                if(sequence!==previewSequence)return;
                const target=container.find('#rules-import-preview').empty();
                if(data.status!=='ok'){
                    target.append($('<div class="alert alert-danger">').text((data.errors||[data.message||'规则校验失败']).slice(0,8).join('\n')));
                    return;
                }
                target.append($('<div class="alert alert-info">').text('共 '+data.input+' 条：可导入 '+data.to_import+' 条，跳过 '+data.skipped+' 条重复规则；导入后共 '+data.total+' 条。'));
                if((data.duplicates||[]).length){
                    const details=$('<details class="text-muted">').css('margin-bottom','15px');
                    details.append($('<summary>').text('查看重复项及保留名称（最多显示 20 条）'));
                    const list=$('<ul>');
                    data.duplicates.forEach(function(item){list.append($('<li>').text('跳过“'+item.app_label+'”，相同条件保留“'+item.kept_app_label+'”。'));});
                    target.append(details.append(list));
                }
                const table=$('<table class="table table-condensed">').append('<thead><tr><th>匹配方式</th><th>匹配内容（前 5 条预览）</th><th>应用名称</th></tr></thead>');
                const rows=$('<tbody>');
                (data.rows||[]).forEach(function(row){rows.append($('<tr>').append($('<td>').text(({domain:'域名',ip:'IP 地址',cidr:'网段',port:'端口',protocol:'应用协议'})[row.match_type]||row.match_type),$('<td>').css({'white-space':'pre-wrap','overflow-wrap':'anywhere'}).text(row.match_value),$('<td>').text(row.app_label)));});
                target.append(table.append(rows));submit.prop('disabled',false);
            }).fail(function(xhr,status){if(sequence===previewSequence && status!=='abort')container.find('#rules-import-preview').empty().append($('<div class="alert alert-danger">').text('校验请求失败，请重试。'));});
        },350);
    }

	function submitImport(dialog, container) {
        if(container.data('importing'))return;
        container.data('importing',true);dialog.setClosable(false);
        const buttons=dialog.getModalFooter().find('button').prop('disabled',true);
        container.find('input,textarea').prop('disabled',true);
		const formData = new FormData();
		formData.append('format', container.find('input[name="import_format"]:checked').val());
		formData.append('mode', container.find('input[name="import_mode"]:checked').val());
		formData.append('payload', container.find('#rules-import-payload').val());
		container.find('#rules-import-errors').removeClass('alert alert-danger').empty();
		container.find('#rules-import-progress').show();
		$.ajax({
			url: '/api/appidentification/rule/import',
			method: 'POST',
			data: formData,
			processData: false,
			contentType: false,
			global: false,
			dataType: 'json',
			success: function (data) {
				container.find('#rules-import-progress').hide();
				if (!data || data.status !== 'ok') {
					const errors = data && data.errors ? data.errors : [data && data.message ? data.message : '{{ lang._('导入失败') }}'];
					container.find('#rules-import-errors').addClass('alert alert-danger').html(errors.map(esc).join('<br>'));
					return;
				}
				dialog.close();
				reloadRules();
				BootstrapDialog.show({
					type: BootstrapDialog.TYPE_SUCCESS,
					title: '{{ lang._('操作成功') }}',
					message: esc('{{ lang._('成功导入') }} ' + data.imported + ' {{ lang._('条规则，跳过') }} ' + data.skipped + ' {{ lang._('条重复规则') }}'),
					buttons: [{label: '{{ lang._('关闭') }}', action: function(d){ d.close(); }}]
				});
			},
			error: function (xhr) {
				container.find('#rules-import-progress').hide();
				const data = xhr.responseJSON || {};
				const errors = data.errors || [data.message || '{{ lang._('网络请求失败') }}'];
				container.find('#rules-import-errors').addClass('alert alert-danger').html(errors.map(esc).join('<br>'));
			}
		}).always(function(){container.data('importing',false);dialog.setClosable(true);buttons.prop('disabled',false);container.find('input,textarea').prop('disabled',false);});
	}

	$('#rules-import-open').on('click', function () {
		const body = $('<div>' +
			'<div class="form-group"><label>{{ lang._('格式') }}</label><br>' +
			'<label class="radio-inline"><input type="radio" name="import_format" value="csv" checked> CSV</label>' +
			'<label class="radio-inline"><input type="radio" name="import_format" value="json"> JSON</label></div>' +
			'<div class="form-group"><label>{{ lang._('模式') }}</label><br>' +
			'<label class="radio-inline"><input type="radio" name="import_mode" value="append" checked> {{ lang._('追加') }}</label>' +
			'<label class="radio-inline"><input type="radio" name="import_mode" value="replace"> {{ lang._('替换自定义规则') }}</label></div>' +
			'<p class="text-muted">支持 JSON、CSV；每次最多 5000 条、5 MB。默认追加并跳过重复项。导入不会更改内置规则。</p>'+
            '<div class="form-group"><label>{{ lang._('上传文件') }}</label><input id="rules-import-file" type="file" accept=".csv,.json,text/csv,application/json" class="form-control"></div>' +
			'<div class="form-group"><label>{{ lang._('粘贴文本') }}</label><textarea id="rules-import-payload" class="form-control" rows="5"></textarea></div>' +
			'<div id="rules-import-preview"></div><div id="rules-import-progress" class="progress" style="display:none;"><div class="progress-bar progress-bar-striped active" style="width:100%"></div></div><div id="rules-import-errors"></div>' +
			'</div>');
		const dialog = BootstrapDialog.show({
			title: '{{ lang._('批量导入应用规则') }}',
            cssClass:'appident-import-dialog',
            size:BootstrapDialog.SIZE_WIDE,
			message: body,
            onhidden:function(){clearTimeout(previewTimer);++previewSequence;if(previewRequest)previewRequest.abort();},
			buttons: [
				{label: '{{ lang._('取消') }}', action: function(d){ d.close(); }},
				{label: '{{ lang._('导入') }}', cssClass: 'btn-primary', action: function(d){
					if (body.find('input[name="import_mode"]:checked').val() === 'replace') {
						ajaxCall('/api/appidentification/rule/stats', {}, function (stats) {
							const total = stats && stats.total ? stats.total : 0;
							BootstrapDialog.confirm('{{ lang._('此操作将替换所有自定义规则（共') }} ' + total + ' {{ lang._('条），是否继续？') }}', function (ok) {
								if (ok) {
									submitImport(d, body);
								}
							});
						});
					} else {
						submitImport(d, body);
					}
				}}
			],
			onshow: function () {
				const submit = body.closest('.modal-content').find('.btn-primary');
				submit.prop('disabled', true);
				body.on('change input', 'input[name="import_format"],input[name="import_mode"], #rules-import-payload', function () {
					renderImportPreview(body);
				});
				body.find('#rules-import-file').on('change', function () {
					++previewSequence;clearTimeout(previewTimer);if(previewRequest)previewRequest.abort();submit.prop('disabled',true);
					const file = this.files[0];
					if (!file) {
						renderImportPreview(body);
						return;
					}
                    if(file.size>5*1024*1024){body.find('#rules-import-preview').text('文件不能超过 5 MB。');submit.prop('disabled',true);return;}
                    const extension=file.name.split('.').pop().toLowerCase();
                    if(['json','csv'].includes(extension))body.find('input[name="import_format"][value="'+extension+'"]').prop('checked',true);
					const reader = new FileReader();
					reader.onload = function (event) {
						body.find('#rules-import-payload').val(event.target.result);
						renderImportPreview(body);
					};
                    reader.onerror=function(){body.find('#rules-import-preview').text('文件读取失败，请重新选择。');submit.prop('disabled',true);};
					reader.readAsText(file, 'UTF-8');
				});
			}
		});
	});


	const entryAction = new URLSearchParams(window.location.search).get('action');
	if (entryAction === 'add' || entryAction === 'import') {
		grid.one('loaded.rs.jquery.bootgrid', function () {
			$(entryAction === 'add' ? '#rules-add-open' : '#rules-import-open').trigger('click');
		});
	}
});
</script>
