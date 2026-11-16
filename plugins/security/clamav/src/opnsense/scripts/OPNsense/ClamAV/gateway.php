#!/usr/local/bin/php
<?php
// SPDX-License-Identifier: BSD-2-Clause
require_once('config.inc');
use OPNsense\ClamAV\Gateway;
try {
    $action = $argv[1] ?? '';
    if ($action === 'status') {
        $result = Gateway::status();
    } elseif ($action === 'logs') {
        $result = Gateway::logs();
    } elseif ($action === 'start') {
        $raw = base64_decode($argv[3] ?? '', true);
        if ($raw === false || strlen($raw) > 20000) {
            throw new InvalidArgumentException('请求格式无效。');
        }
        $request = json_decode($raw, true, 32, JSON_THROW_ON_ERROR);
        if (!is_array($request)) {
            throw new InvalidArgumentException('请求格式无效。');
        }
        $result = Gateway::start($argv[2] ?? '', $request);
    } elseif ($action === 'worker') {
        Gateway::worker($argv[2], $argv[3], json_decode(base64_decode($argv[4], true), true, 32, JSON_THROW_ON_ERROR));
        exit(0);
    } else {
        throw new InvalidArgumentException('不支持的操作。');
    }
} catch (Throwable $error) {
    $result = ['status' => 'error', 'message' => $error->getMessage()];
}
echo json_encode($result, JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE) . PHP_EOL;
