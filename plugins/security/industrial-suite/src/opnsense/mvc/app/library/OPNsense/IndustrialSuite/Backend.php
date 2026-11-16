<?php
// SPDX-License-Identifier: BSD-2-Clause
namespace OPNsense\IndustrialSuite;

class Backend
{
    public static function run(string $action, array $request = []): array
    {
        if (!preg_match('/^[a-z_]+$/D', $action)) {
            return ['status' => 'error', 'message' => 'Invalid operation'];
        }
        $payload = base64_encode(json_encode($request, JSON_THROW_ON_ERROR));
        if (strlen($payload) > 250000) {
            return ['status' => 'error', 'message' => 'Request exceeds policy size limit'];
        }
        $raw = (new \OPNsense\Core\Backend())->configdRun('industrialsuite ' . $action . ' ' . $payload);
        $result = json_decode(trim($raw), true);
        return is_array($result) ? $result : ['status' => 'error', 'message' => 'Backend returned no valid response'];
    }
}
