<?php

/*
 * Copyright (C) 2026 Deciso B.V.
 * All rights reserved.
 */

namespace OPNsense\AppIdentification\Api;

use OPNsense\Base\ApiControllerBase;
use OPNsense\Core\Config;
use OPNsense\AppIdentification\AppIdentification;
use OPNsense\AppIdentification\Backend\BackendFacade;

/**
 * Class GeneralController
 *
 * Provide a generic ntopng REST API proxy for App Identification.
 */
class GeneralController extends ApiControllerBase
{
	/**
	 * Cached model instance.
	 */
	private $model;
	private $backend;

	/**
	 * Read ntopng settings model.
	 *
	 * @return array
	 */
	public function getAction(): array
	{
		try {
			$model = $this->getModel();
			$nodes = $model->getNodes();
			if (empty($nodes['rest_host'])) {
				$nodes['rest_host'] = '127.0.0.1';
			}
			if (empty($nodes['ifid']) || (int)$nodes['ifid'] < 1) {
				$nodes['ifid'] = '1';
			}
			return [
				'general' => $nodes
			];
		} catch (\Throwable $e) {
			return [
				'status' => 'error',
				'message' => sprintf('Unable to load ntopng settings: %s', $e->getMessage())
			];
		}
	}

	/**
	 * Save ntopng REST API settings.
	 *
	 * @return array
	 */
	public function setAction(): array
	{
		$result = ['result' => 'failed'];

		try {
			if (!$this->request->isPost()) {
				$result['message'] = 'Invalid request method.';
				return $result;
			}

			$model = $this->getModel();
			$model->setNodes($this->request->getPost('general'));

			$valMsgs = $model->performValidation();
			foreach ($valMsgs as $msg) {
				if (!isset($result['validations'])) {
					$result['validations'] = [];
				}
				$result['validations']['general.' . $msg->getField()] = $msg->getMessage();
			}

			if ($valMsgs->count() > 0) {
				return $result;
			}

			$model->serializeToConfig();
			Config::getInstance()->save();

			return [
				'result' => 'saved',
				'status' => 'ok',
				'message' => 'REST API configuration saved.'
			];
		} catch (\Throwable $e) {
			return [
				'result' => 'failed',
				'status' => 'error',
				'message' => sprintf('Unable to save ntopng settings: %s', $e->getMessage())
			];
		}
	}

	/**
	 * Restart ntopng service.
	 *
	 * @return array
	 */
	public function ntopngrestartAction(): array
	{
		try {
			return $this->backend()->ntopng('restart');
		} catch (\Throwable $e) {
			return [
				'status' => 'error',
				'message' => sprintf('Unable to restart ntopng: %s', $e->getMessage())
			];
		}
	}

	/**
	 * Query ntopng REST API endpoint and return decoded JSON.
	 *
	 * @param string $endpoint Relative endpoint under /lua/rest/v2/
	 * @param array $params Query string parameters
	 * @return array
	 */
	protected function proxyRequest(string $endpoint, array $params = []): array
	{
		return $this->backend()->run([
			'action' => 'api_get',
			'settings' => $this->backendSettings(),
			'endpoint' => $endpoint,
			'params' => $params,
		]);
	}

	/**
	 * Get status information from ntopng.
	 *
	 * @return array
	 */
	public function statusAction(): array
	{
		try {
			$payload = $this->proxyRequest('flow/active.lua', [
				'ifid' => $this->getIfid(),
				'perPage' => 1
			]);
			if (($payload['status'] ?? '') === 'error') {
				return $payload;
			}

			$totalRows = (int)($payload['rsp']['totalRows'] ?? 0);

			return [
				'status' => 'ok',
				'message' => sprintf('连接成功，当前活动流 %d 条', $totalRows),
				'active_flows' => $totalRows,
				'running' => true,
				'data' => $payload
			];
		} catch (\Throwable $e) {
			return [
				'status' => 'error',
				'message' => sprintf('Unable to retrieve ntopng status: %s', $e->getMessage())
			];
		}
	}

	/**
	 * Return current plugin model.
	 *
	 * @return AppIdentification
	 */
	protected function getModel(): AppIdentification
	{
		if ($this->model === null) {
			$this->model = new AppIdentification();
		}

		return $this->model;
	}

	private function getRestScheme(): string
	{
		$scheme = strtolower(trim((string)($this->getModel()->rest_scheme ?? 'http')));
		if ($scheme !== 'https') {
			$scheme = 'http';
		}
		return $scheme;
	}

	private function getRestHost(): string
	{
		$host = trim((string)($this->getModel()->rest_host ?? ''));
		return $host !== '' ? $host : '127.0.0.1';
	}

	private function getRestPort(): string
	{
		$port = trim((string)($this->getModel()->rest_port ?? '3000'));
		return $port !== '' && is_numeric($port) ? $port : '3000';
	}

	protected function getIfid(): int
	{
		$ifid = (int)trim((string)($this->getModel()->ifid ?? '1'));
		return $ifid > 0 ? $ifid : 1;
	}

	protected function backend(): BackendFacade
	{
		if ($this->backend === null) {
			$this->backend = new BackendFacade();
		}
		return $this->backend;
	}

	protected function backendSettings(): array
	{
		$model = $this->getModel();
		return [
			'rest_scheme' => $this->getRestScheme(),
			'rest_host' => $this->getRestHost(),
			'rest_port' => $this->getRestPort(),
			'auth_token' => trim((string)($model->auth_token ?? '')),
			'ifid' => $this->getIfid(),
		];
	}
}
