<?php

namespace OPNsense\AppIdentification\Backend;

use OPNsense\Core\Backend;

class BackendFacade
{
    public function run(array $request): array
    {
        $payload = base64_encode(json_encode($request, JSON_UNESCAPED_SLASHES));
        $response = trim((new Backend())->configdRun('appidentification backend ' . escapeshellarg($payload)));
        $decoded = json_decode($response, true);
        if (is_array($decoded)) {
            return $decoded;
        }
        return ['status' => 'error', 'message' => $response !== '' ? $response : 'empty backend response'];
    }

    public function ntopng(string $action): array
    {
        if (!in_array($action, ['restart', 'status'], true)) {
            return ['status' => 'error', 'message' => 'unsupported ntopng service action'];
        }
        $response = trim((new Backend())->configdRun('ntopng ' . $action));
        if ($action === 'status') {
            return [
                'status' => stripos($response, 'is running') !== false ? 'ok' : 'error',
                'message' => $response,
            ];
        }
        return [
            'status' => $response === '' || stripos($response, 'error') === false ? 'ok' : 'error',
            'message' => $response !== '' ? $response : 'ntopng ' . $action . ' requested',
        ];
    }
}
