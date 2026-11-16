<?php
// SPDX-License-Identifier: BSD-2-Clause
namespace OPNsense\IndustrialSuite\Api;

use OPNsense\Base\ApiControllerBase;
use OPNsense\IndustrialSuite\Backend;

class ServiceController extends ApiControllerBase
{
    public function statusAction() { return Backend::run('status'); }
    public function logsAction() { return Backend::run('logs'); }

    public function runAction()
    {
        $request = $this->request->getJsonRawBody(true);
        $allowed = ['integrity_baseline', 'integrity_check', 'isolation_preview', 'isolation_apply',
                    'isolation_rollback', 'fleet_status', 'fleet_logs', 'fleet_preview', 'fleet_deploy'];
        if (!$this->request->isPost() || !is_array($request) || !in_array($request['operation'] ?? '', $allowed, true)) {
            return ['status' => 'error', 'message' => 'POST a supported operation'];
        }
        if (in_array($request['operation'], ['integrity_baseline', 'isolation_apply', 'isolation_rollback', 'fleet_deploy'], true)) {
            $this->throwReadOnly();
        }
        return Backend::run($request['operation'], ['node_ids' => $request['node_ids'] ?? []]);
    }
}
