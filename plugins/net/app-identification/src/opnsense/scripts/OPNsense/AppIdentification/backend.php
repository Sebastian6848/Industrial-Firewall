#!/usr/local/bin/php
<?php

require_once('/usr/local/opnsense/mvc/app/library/OPNsense/AppIdentification/Backend/BackendCore.php');

if (($argv[1] ?? '') === '--request') {
    $json = base64_decode((string)($argv[2] ?? ''), true);
    $request = json_decode((string)$json, true);
    if (!is_array($request)) {
        $request = ['action' => 'invalid'];
    }
} else {
    $request = ['action' => 'invalid'];
}

$result = (new OPNsense\AppIdentification\Backend\BackendCore())->dispatch($request);
echo json_encode($result, JSON_UNESCAPED_SLASHES) . PHP_EOL;
// configd discards script output for non-zero exits. Errors are represented by
// the JSON status so API callers can display the actual ntopng error message.
exit(0);
