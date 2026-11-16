<?php

/*
 * Copyright (C) 2026 Deciso B.V.
 * All rights reserved.
 */

namespace OPNsense\AppIdentification\Api;

use OPNsense\AppIdentification\Catalog;
use OPNsense\Base\ApiMutableModelControllerBase;
use OPNsense\Core\Config;

/**
 * Class RuleController
 *
 * CRUD endpoints for custom application identification rules.
 */
class RuleController extends ApiMutableModelControllerBase
{
	protected static $internalModelName = 'appidentification';
	protected static $internalModelClass = '\OPNsense\AppIdentification\AppIdentification';

	private const IMPORT_FIELDS = ['enabled', 'description', 'match_type', 'match_value', 'app_label'];
	private const MATCH_TYPES = ['domain', 'ip', 'cidr', 'port', 'protocol'];
	private const IMPORT_LIMIT = 5000;
	private const PAYLOAD_LIMIT = 5242880;

	public function searchRulesAction()
	{
		return $this->searchBase('rules.rule', ['enabled', 'description', 'match_type', 'match_value', 'app_label']);
	}

	public function searchLibraryAction(): array
	{
		$source = $this->request->getPost('source', null, 'all');
		$custom = $this->collectRules();
		$builtin = Catalog::load()['applications'];
		$rows = [];
		if ($source !== 'builtin') {
			foreach ($custom as $rule) {
				$rows[] = $rule + ['source' => 'custom'];
			}
		}
		if ($source !== 'custom') {
			foreach ($builtin as $app) {
				$values = array_column($app['domains'], 'value');
				$rows[] = [
					'uuid' => 'builtin:' . $app['id'],
					'catalog_id' => $app['id'],
					'source' => 'builtin',
					'app_label' => $app['name'],
					'match_type' => 'domain',
					'match_value' => implode("\n", $values),
					'match_values' => $values,
					'enabled' => '1'
				];
			}
		}
		$result = $this->searchRecordsetBase(
			$rows,
			['app_label', 'description', 'catalog_id', 'match_type', 'match_value'],
			'app_label'
		);
		foreach ($result['rows'] as &$rule) {
			$rule['match_count'] = count($rule['match_values']);
			$rule['example'] = $rule['match_values'][0] ?? '';
			unset($rule['match_values'], $rule['match_value']);
		}
		unset($rule);
		return $result + ['library_count' => count($custom) + count($builtin)];
	}

	public function builtinAction(): array
	{
		$id = $this->request->get('id', null, '');
		foreach (Catalog::load()['applications'] as $app) {
			if ($app['id'] === $id) {
				return ['status' => 'ok', 'rule' => $app];
			}
		}
		return ['status' => 'error', 'message' => '未找到该内置规则。'];
	}

	public function getRuleAction($uuid = null)
	{
		return $this->getBase('rule', 'rules.rule', $uuid);
	}

	public function addRuleAction()
	{
		$validation = $this->validateRulePayloadFromRequest();
		if (!empty($validation)) {
			return ['result' => 'failed', 'validations' => $validation];
		}
		if ($this->request->isPost()) {
			Config::getInstance()->lock();
			if (count($this->collectRules()) >= self::IMPORT_LIMIT) {
				return ['result' => 'failed', 'validations' => ['rule.match_value' => '规则总数已达到 5000 条上限。']];
			}
		}
		return $this->addBase('rule', 'rules.rule');
	}

	public function setRuleAction($uuid)
	{
		$validation = $this->validateRulePayloadFromRequest();
		if (!empty($validation)) {
			return ['result' => 'failed', 'validations' => $validation];
		}
		return $this->setBase('rule', 'rules.rule', $uuid);
	}

	public function delRuleAction($uuid)
	{
		return $this->delBase('rules.rule', $uuid);
	}

	public function toggleRuleAction($uuid)
	{
		return $this->toggleBase('rules.rule', $uuid);
	}

	public function listAction(): array
	{
		$rules = array_values(array_filter($this->collectRules(), function ($rule) {
			return (string)$rule['enabled'] === '1';
		}));
		return ['rules' => $rules];
	}

	public function statsAction(): array
	{
		$rules = $this->collectRules();
		$enabled = 0;
		foreach ($rules as $rule) {
			if ((string)$rule['enabled'] === '1') {
				$enabled++;
			}
		}

		return [
			'status' => 'ok',
			'total' => count($rules),
			'enabled' => $enabled,
			'limit' => self::IMPORT_LIMIT
		];
	}

	public function importAction(): array
	{
		return $this->handleImport(false);
	}

	public function previewAction(): array
	{
		return $this->handleImport(true);
	}

	private function handleImport(bool $preview): array
	{
		if (!$this->request->isPost()) {
			return ['status' => 'error', 'message' => 'Import requires a POST request.'];
		}

		$format = $this->request->getPost('format', null, '');
		$mode = $this->request->getPost('mode', null, 'append');
		if (!is_string($format) || !is_string($mode)) {
			return ['status' => 'error', 'message' => '导入格式和模式必须为文本。'];
		}
		$format = strtolower(trim($format));
		$mode = strtolower(trim($mode));
		if (!in_array($format, ['csv', 'json'], true)) {
			return ['status' => 'error', 'message' => 'Import format must be csv or json.'];
		}
		if (!in_array($mode, ['append', 'replace'], true)) {
			return ['status' => 'error', 'message' => 'Import mode must be append or replace.'];
		}

		try {
			$payload = $this->readImportPayload();
		} catch (\InvalidArgumentException $error) {
			return ['status' => 'error', 'message' => $error->getMessage(), 'errors' => [$error->getMessage()]];
		}
		if (trim($payload) === '') {
			return ['status' => 'error', 'message' => 'Import data is empty.', 'errors' => ['Import data is empty.']];
		}

		$parsed = $format === 'csv' ? $this->parseCsvPayload($payload) : $this->parseJsonPayload($payload);
		if (!empty($parsed['errors'])) {
			return ['status' => 'error', 'message' => 'Import data is invalid.', 'errors' => $parsed['errors']];
		}

		$rows = $parsed['rows'];
		if (count($rows) === 0) {
			return ['status' => 'error', 'message' => 'Import data does not contain any rules.', 'errors' => ['Import data does not contain any rules.']];
		}
		if (count($rows) > self::IMPORT_LIMIT) {
			return ['status' => 'error', 'message' => sprintf('Import is limited to %d rules.', self::IMPORT_LIMIT)];
		}

		$validated = $this->validateImportRows($rows);
		if (!empty($validated['errors'])) {
			return ['status' => 'error', 'message' => 'Import data is invalid.', 'errors' => $validated['errors']];
		}

		if (!$preview) {
			$this->throwReadOnly();
			Config::getInstance()->lock();
		}
		$model = $this->getModel();
		$existingCount = count($this->collectRules());
		$existingKeys = $mode === 'append' ? $this->ruleKeys($this->collectRules()) : [];
		$seenKeys = [];
		$skipped = 0;
		$duplicates = [];
		$rulesToImport = [];
		foreach ($validated['rows'] as $row) {
			$key = $this->ruleKey($row);
			if (isset($seenKeys[$key]) || isset($existingKeys[$key])) {
				$skipped++;
				if (count($duplicates) < 20) {
					$duplicates[] = ['app_label' => $row['app_label'],
						'kept_app_label' => $existingKeys[$key] ?? $seenKeys[$key]];
				}
				continue;
			}
			$seenKeys[$key] = $row['app_label'];
			$rulesToImport[] = $row;
		}
		$resultTotal = ($mode === 'append' ? $existingCount : 0) + count($rulesToImport);
		if ($resultTotal > self::IMPORT_LIMIT) {
			return ['status' => 'error', 'message' => sprintf('规则总数不能超过 %d 条，请减少导入数量。', self::IMPORT_LIMIT)];
		}

		if ($mode === 'replace') {
			$uuids = [];
			foreach ($model->rules->rule->iterateItems() as $uuid => $rule) {
				$uuids[] = $uuid;
			}
			foreach ($uuids as $uuid) {
				$model->rules->rule->del($uuid);
			}
		}

		foreach ($rulesToImport as $row) {
			$node = $model->rules->rule->add();
			$node->enabled = $row['enabled'];
			$node->description = $row['description'];
			$node->match_type = $row['match_type'];
			$node->match_value = $row['match_value'];
			$node->app_label = $row['app_label'];
		}

		$validationMessages = $model->performValidation();
		if ($validationMessages->count() > 0) {
			$errors = [];
			foreach ($validationMessages as $message) {
				$errors[] = $message->getField() . ': ' . $message->getMessage();
			}
			return ['status' => 'error', 'message' => 'Imported rules failed model validation.', 'errors' => $errors];
		}

		if ($preview) {
			return ['status' => 'ok', 'preview' => true, 'mode' => $mode,
				'input' => count($rows), 'to_import' => count($rulesToImport), 'skipped' => $skipped,
				'existing' => $existingCount, 'total' => $resultTotal, 'duplicates' => $duplicates,
				'rows' => array_slice($validated['rows'], 0, 5)];
		}
		$this->setSaveAuditMessage(sprintf('AppIdentification: imported %d custom rules (%s)', count($rulesToImport), $mode));
		$this->save();
		if ($mode === 'replace') {
			syslog(LOG_NOTICE, sprintf('AppIdentification: replaced custom rules via bulk import, imported=%d skipped=%d', count($rulesToImport), $skipped));
		}

		return [
			'status' => 'ok',
			'imported' => count($rulesToImport),
			'skipped' => $skipped,
			'total' => count($this->collectRules()),
			'message' => sprintf('Successfully imported %d rules.', count($rulesToImport))
		];
	}

	public function templateAction(string $format = ''): array|string
	{
		$format = strtolower(trim($format));
		if ($format === 'csv') {
			return $this->downloadText($this->csvTemplate(), 'app_rules_template.csv', 'text/csv; charset=utf-8');
		}
		if ($format === 'json') {
			return $this->downloadText($this->jsonTemplate(), 'app_rules_template.json', 'application/json; charset=utf-8');
		}
		return ['status' => 'error', 'message' => 'Template format must be csv or json.'];
	}

	public function exportAction(string $format = ''): array|string
	{
		$format = strtolower(trim($format));
		$rules = $this->collectRules();
		$stamp = date('Ymd_His');
		if ($format === 'csv') {
			return $this->downloadText($this->rulesToCsv($rules), "app_rules_{$stamp}.csv", 'text/csv; charset=utf-8');
		}
		if ($format === 'json') {
			$json = json_encode(array_map([$this, 'exportRule'], $rules), JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
			return $this->downloadText($json . "\n", "app_rules_{$stamp}.json", 'application/json; charset=utf-8');
		}
		return ['status' => 'error', 'message' => 'Export format must be csv or json.'];
	}

	private function collectRules(): array
	{
		$model = $this->getModel();
		$rules = [];

		foreach ($model->rules->rule->iterateItems() as $uuid => $rule) {
			$rawMatchValue = (string)$rule->match_value;
			$rules[] = [
				'uuid' => (string)$uuid,
				'enabled' => (string)$rule->enabled,
				'description' => (string)$rule->description,
				'match_type' => (string)$rule->match_type,
				'match_value' => $rawMatchValue,
				'match_values' => $this->splitMatchValues($rawMatchValue),
				'app_label' => (string)$rule->app_label
			];
		}

		return $rules;
	}

	private function readImportPayload(): string
	{
		$payload = $this->request->getPost('payload', null, '');
		if (!is_string($payload) || strlen($payload) > self::PAYLOAD_LIMIT) {
			throw new \InvalidArgumentException('导入内容必须为文本，文件大小不能超过 5 MB。');
		}
		if ($payload !== '') {
			return $payload;
		}

		// The native MVC Request does not expose Phalcon's getUploadedFiles().
		foreach ($_FILES as $file) {
			if (is_array($file) && ($file['error'] ?? null) === UPLOAD_ERR_OK &&
				is_string($file['tmp_name'] ?? null) && is_uploaded_file($file['tmp_name'])) {
				if (filesize($file['tmp_name']) > self::PAYLOAD_LIMIT) {
					throw new \InvalidArgumentException('导入文件不能超过 5 MB。');
				}
				return (string)file_get_contents($file['tmp_name']);
			}
		}

		return '';
	}

	private function parseCsvPayload(string $payload): array
	{
		$payload = preg_replace('/^\xEF\xBB\xBF/', '', $payload);
		$handle = fopen('php://temp', 'r+');
		fwrite($handle, $payload);
		rewind($handle);

		$header = null;
		$rows = [];
		$errors = [];
		$line = 0;
		while (($fields = fgetcsv($handle, 0, ',', '"', '')) !== false) {
			$line++;
			if ($fields === [null] || $fields === false) {
				continue;
			}
			if ($header === null) {
				$header = array_map('trim', $fields);
				$missing = array_diff(['match_type', 'match_value', 'app_label'], $header);
				if (!empty($missing)) {
					$errors[] = 'CSV header is missing required fields: ' . implode(', ', $missing);
					break;
				}
				continue;
			}
			if (count($fields) !== count($header)) {
				$errors[] = sprintf('Line %d: column count does not match the header.', $line);
				continue;
			}
			$row = array_combine($header, $fields);
			if (isset($row['match_value'])) {
				$row['match_value'] = $this->normalizeImportedMatchValue($row['match_value']);
			}
			$row['_line'] = $line;
			$rows[] = $row;
		}
		fclose($handle);

		if ($header === null) {
			$errors[] = 'CSV file is empty.';
		}

		return ['rows' => $rows, 'errors' => $errors];
	}

	private function parseJsonPayload(string $payload): array
	{
		$payload = preg_replace('/^\xEF\xBB\xBF/', '', $payload);
		$data = json_decode($payload, true);
		if (json_last_error() !== JSON_ERROR_NONE) {
			return ['rows' => [], 'errors' => ['JSON parse error: ' . json_last_error_msg()]];
		}
		if (!is_array($data) || !array_is_list($data)) {
			return ['rows' => [], 'errors' => ['JSON root must be an array of rule objects.']];
		}

		$rows = [];
		$errors = [];
		foreach ($data as $idx => $row) {
			if (!is_array($row) || array_is_list($row)) {
				$errors[] = sprintf('Item %d: rule must be an object.', $idx + 1);
				continue;
			}
			if (isset($row['match_value']) && !is_string($row['match_value']) &&
				(!is_array($row['match_value']) || array_filter($row['match_value'], static fn($v) => !is_string($v)))) {
				$errors[] = sprintf('第 %d 条：匹配内容必须为文本或文本数组。', $idx + 1);
				continue;
			}
			if (array_key_exists('match_value', $row)) {
				$row['match_value'] = $this->normalizeImportedMatchValue($row['match_value']);
			}
			$row['_line'] = $idx + 1;
			$rows[] = $row;
		}
		return ['rows' => $rows, 'errors' => $errors];
	}

	private function validateImportRows(array $rows): array
	{
		$cleanRows = [];
		$errors = [];
		foreach ($rows as $idx => $row) {
			$line = (int)($row['_line'] ?? ($idx + 1));
			$clean = [];
			foreach (self::IMPORT_FIELDS as $field) {
				if (isset($row[$field]) && !is_scalar($row[$field])) {
					$errors[] = sprintf('第 %d 条：%s 必须为文本或标量值。', $line, $field);
					continue 2;
				}
				$clean[$field] = $field === 'enabled' && is_bool($row[$field] ?? null)
					? ($row[$field] ? '1' : '0') : trim((string)($row[$field] ?? ''));
			}
			$clean['match_type'] = strtolower($clean['match_type']);
			$clean['enabled'] = $this->normalizeEnabled($clean['enabled']);

			foreach (['match_type', 'match_value', 'app_label'] as $required) {
				if ($clean[$required] === '') {
					$errors[] = sprintf('Line %d: %s is required.', $line, $required);
				}
			}
			if ($clean['match_type'] !== '' && !in_array($clean['match_type'], self::MATCH_TYPES, true)) {
				$errors[] = sprintf('Line %d: match_type is invalid.', $line);
			}
			if (strlen($clean['match_value']) > 65536 || mb_strlen($clean['app_label']) > 255 || mb_strlen($clean['description']) > 255) {
				$errors[] = sprintf('第 %d 条：名称、描述最多 255 个字符，匹配内容最多 64 KB。', $line);
			}
			$valueErrors = $this->validateMatchValues($clean['match_type'], $clean['match_value']);
			foreach ($valueErrors as $valueError) {
				$errors[] = sprintf('Line %d: %s', $line, $valueError);
			}
			$cleanRows[] = $clean;
		}

		return ['rows' => $cleanRows, 'errors' => $errors];
	}

	private function normalizeEnabled(string $enabled): string
	{
		$value = strtolower($enabled);
		if ($value === '' || in_array($value, ['1', 'true', 'yes', 'on', 'enabled'], true)) {
			return '1';
		}
		return '0';
	}

	private function validateRulePayloadFromRequest(): array
	{
		$rule = $this->request->getPost('rule', null, []);
		if (!is_array($rule)) {
			return [];
		}

		if (!is_string($rule['match_type'] ?? null) || !in_array($rule['match_type'], self::MATCH_TYPES, true)) {
			return ['rule.match_type' => '请选择有效的匹配方式。'];
		}
		if (!is_string($rule['match_value'] ?? null)) {
			return ['rule.match_value' => '匹配内容必须为文本，每行填写一个值。'];
		}
		$type = $rule['match_type'];
		$matchValue = $rule['match_value'];
		$errors = $this->validateMatchValues($type, $matchValue);
		if (empty($errors)) {
			return [];
		}

		return ['rule.match_value' => implode(' ', $errors)];
	}

	private function validateMatchValues(string $type, string $value): array
	{
		$errors = [];
		$values = $this->splitMatchValues($value);
		if (empty($values)) {
			return ['match_value is required.'];
		}

		foreach ($values as $lineNo => $item) {
			$line = $lineNo + 1;
			if ($type === 'domain') {
				if (preg_match('/\s/', $item)) {
					$errors[] = sprintf('match_value line %d must not contain spaces.', $line);
				}
				continue;
			}

			if ($type === 'ip') {
				if (filter_var($item, FILTER_VALIDATE_IP) === false) {
					$errors[] = sprintf('match_value line %d must be a valid IP address.', $line);
				}
				continue;
			}

			if ($type === 'cidr') {
				if (!$this->isValidCidr($item)) {
					$errors[] = sprintf('match_value line %d must be a valid CIDR notation.', $line);
				}
				continue;
			}

			if ($type === 'port') {
				if (!ctype_digit($item) || (int)$item < 1 || (int)$item > 65535) {
					$errors[] = sprintf('match_value line %d must be a port between 1 and 65535.', $line);
				}
				continue;
			}

			if ($type === 'protocol' && $item === '') {
				$errors[] = sprintf('match_value line %d must not be empty.', $line);
			}
		}

		return $errors;
	}

	private function isValidCidr(string $value): bool
	{
		$parts = explode('/', $value, 2);
		if (count($parts) !== 2 || !ctype_digit((string)$parts[1])) {
			return false;
		}

		$ip = $parts[0];
		$prefix = (int)$parts[1];
		if (filter_var($ip, FILTER_VALIDATE_IP, FILTER_FLAG_IPV4) !== false) {
			return $prefix >= 0 && $prefix <= 32;
		}
		if (filter_var($ip, FILTER_VALIDATE_IP, FILTER_FLAG_IPV6) !== false) {
			return $prefix >= 0 && $prefix <= 128;
		}
		return false;
	}

	private function splitMatchValues(string $value): array
	{
		$parts = preg_split('/\r\n|\r|\n/', (string)$value) ?: [];
		$values = [];
		foreach ($parts as $part) {
			$item = trim((string)$part);
			if ($item !== '') {
				$values[] = $item;
			}
		}
		return $values;
	}

	private function normalizeImportedMatchValue($rawValue): string
	{
		if (is_array($rawValue)) {
			$items = [];
			foreach ($rawValue as $part) {
				$value = trim((string)$part);
				if ($value !== '') {
					$items[] = $value;
				}
			}
			return implode("\n", $items);
		}

		$value = str_replace(['\r\n', '\r'], "\n", (string)$rawValue);
		if (strpos($value, '|') !== false) {
			$items = [];
			foreach (explode('|', $value) as $part) {
				$item = trim((string)$part);
				if ($item !== '') {
					$items[] = $item;
				}
			}
			return implode("\n", $items);
		}

		return implode("\n", $this->splitMatchValues($value));
	}

	private function ruleKeys(array $rules): array
	{
		$keys = [];
		foreach ($rules as $rule) {
			$keys[$this->ruleKey($rule)] ??= (string)$rule['app_label'];
		}
		return $keys;
	}

	private function ruleKey(array $rule): string
	{
		$values = [];
		foreach ($this->splitMatchValues((string)($rule['match_value'] ?? '')) as $item) {
			$values[] = strtolower($item);
		}
		$values = array_values(array_unique($values));
		sort($values, SORT_STRING);
		return strtolower(trim((string)$rule['match_type'])) . "\n" . implode('|', $values);
	}

	private function exportRule(array $rule): array
	{
		return array_intersect_key($rule, array_flip(self::IMPORT_FIELDS));
	}

	private function rulesToCsv(array $rules): string
	{
		$handle = fopen('php://temp', 'r+');
		fputcsv($handle, self::IMPORT_FIELDS, ',', '"', '');
		foreach ($rules as $rule) {
			$exported = $this->exportRule($rule);
			$exported['match_value'] = implode('|', $this->splitMatchValues((string)($exported['match_value'] ?? '')));
			fputcsv($handle, array_values($exported), ',', '"', '');
		}
		rewind($handle);
		$content = stream_get_contents($handle);
		fclose($handle);
		return $content;
	}

	private function csvTemplate(): string
	{
		return "enabled,description,match_type,match_value,app_label\n"
			. "1,微信流量,domain,weixin.qq.com|wechat.com|qpic.cn|gtimg.cn,微信\n"
			. "1,抖音流量,domain,douyin.com|snssdk.com|byteimg.com|amemv.com,抖音\n"
			. "1,办公网段,cidr,10.10.0.0/16|192.168.0.0/24,内网办公\n"
			. "0,临时停用,port,8080,测试服务\n";
	}

	private function jsonTemplate(): string
	{
		return "[\n"
			. "  {\"enabled\":\"1\",\"description\":\"微信流量\",\"match_type\":\"domain\",\"match_value\":[\"weixin.qq.com\",\"wechat.com\",\"qpic.cn\"],\"app_label\":\"微信\"},\n"
			. "  {\"enabled\":\"1\",\"description\":\"抖音流量\",\"match_type\":\"domain\",\"match_value\":\"douyin.com|snssdk.com|byteimg.com\",\"app_label\":\"抖音\"}\n"
			. "]\n";
	}

	private function downloadText(string $content, string $filename, string $contentType): string
	{
		$this->response->setHeader('Content-Type', $contentType);
		$this->response->setHeader('Content-Transfer-Encoding', 'binary');
		$this->response->setHeader('Pragma', 'no-cache');
		$this->response->setHeader('Expires', '0');
		$this->response->setHeader('Content-Disposition', 'attachment; filename="' . $filename . '"');
		return $content;
	}
}
