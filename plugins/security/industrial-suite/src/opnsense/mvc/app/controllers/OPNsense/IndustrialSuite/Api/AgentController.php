<?php
// SPDX-License-Identifier: BSD-2-Clause
namespace OPNsense\IndustrialSuite\Api;

use OPNsense\Base\ApiMutableModelControllerBase;
use OPNsense\IndustrialSuite\Backend;

/** Receiver ACL exposes only project policy, status and project audit logs. */
class AgentController extends ApiMutableModelControllerBase
{
    protected static $internalModelName = 'suite';
    protected static $internalModelClass = '\OPNsense\IndustrialSuite\IndustrialSuite';

    public function statusAction() { return Backend::run('status'); }
    public function logsAction() { return Backend::run('logs'); }

    public function previewAction()
    {
        if (!$this->request->isPost()) {
            return ['status' => 'error', 'message' => 'POST required'];
        }
        $request = $this->request->getJsonRawBody(true);
        if (!is_array($request) || !is_array($request['policy'] ?? null)) {
            return ['status' => 'error', 'message' => 'A policy is required'];
        }
        return Backend::run('isolation_preview', ['policy' => $request['policy']]);
    }

    public function deployAction()
    {
        $preview = $this->previewAction();
        if (($preview['status'] ?? '') !== 'ok') {
            return $preview;
        }
        $policy = $this->request->getJsonRawBody(true)['policy'];
        $model = $this->getModel();
        $original = $model->isolation->getNodeContent();
        foreach (['groups' => 'group', 'rules' => 'rule'] as $container => $item) {
            $array = $model->isolation->$container->$item;
            foreach (array_keys(iterator_to_array($array->iterateItems())) as $uuid) {
                $array->del($uuid);
            }
            foreach ($policy[$container] ?? [] as $entry) {
                if (!preg_match('/^[a-f0-9-]{36}$/D', (string)($entry['uuid'] ?? ''))) {
                    return ['status' => 'error', 'message' => 'Policy entry requires a UUID'];
                }
                $node = $array->add($entry['uuid']);
                unset($entry['uuid']);
                $node->setNodes($entry);
            }
        }
        $model->isolation->enabled = (string)($policy['enabled'] ?? '0');
        $model->isolation->management = (string)($policy['management'] ?? '');
        $saved = $this->save(true);
        if (($saved['result'] ?? '') !== 'saved') {
            return ['status' => 'error', 'message' => 'Policy validation failed', 'validation' => $saved];
        }
        $result = Backend::run('isolation_apply');
        if (($result['status'] ?? '') !== 'ok') {
            // Restore the previous configured policy as well as the active rules.
            foreach (['groups' => 'group', 'rules' => 'rule'] as $container => $item) {
                $array = $model->isolation->$container->$item;
                foreach (array_keys(iterator_to_array($array->iterateItems())) as $uuid) {
                    $array->del($uuid);
                }
            }
            $model->isolation->setNodes($original);
            $this->save(true);
        }
        return $result;
    }
}
