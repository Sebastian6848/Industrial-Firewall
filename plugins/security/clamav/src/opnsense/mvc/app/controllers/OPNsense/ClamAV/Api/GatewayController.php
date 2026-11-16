<?php
// SPDX-License-Identifier: BSD-2-Clause
namespace OPNsense\ClamAV\Api;
use OPNsense\Base\ApiControllerBase;
use OPNsense\ClamAV\Gateway;
use OPNsense\Core\Backend;

class GatewayController extends ApiControllerBase
{
    private function backend(string $action): array
    {
        $raw = (new Backend())->configdRun('clamav gateway_' . $action);
        $result = json_decode(trim($raw), true);
        return is_array($result) ? $result : ['status' => 'error', 'message' => '防病毒后台暂时不可用，请稍后重试。'];
    }

    public function getAction(): array
    {
        try {
            return ['status' => 'ok', 'settings' => Gateway::settings()];
        } catch (\Throwable $error) {
            return ['status' => 'error', 'message' => $error->getMessage()];
        }
    }

    public function statusAction(): array { return $this->backend('status'); }
    public function logsAction(): array { return $this->backend('logs'); }

    public function runAction(): array
    {
        if (!$this->request->isPost()) {
            return ['status' => 'error', 'message' => '操作必须使用 POST。'];
        }
        $this->throwReadOnly();
        $data = $this->request->getJsonRawBody();
        if (!is_array($data) || !in_array($data['operation'] ?? '', Gateway::OPERATIONS, true) ||
            !is_array($data['settings'] ?? [])) {
            return ['status' => 'error', 'message' => '请求格式无效。'];
        }
        $payload = base64_encode(json_encode($data['settings'] ?? [], JSON_THROW_ON_ERROR));
        if (strlen($payload) > 20000) {
            return ['status' => 'error', 'message' => '设置内容过长。'];
        }
        return $this->backend('start ' . $data['operation'] . ' ' . ($payload ?: 'e30='));
    }
}
