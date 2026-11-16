<?php
// SPDX-License-Identifier: BSD-2-Clause
require_once __DIR__ . '/../src/opnsense/mvc/app/library/OPNsense/AppIdentification/Catalog.php';
use OPNsense\AppIdentification\Catalog;

$file = __DIR__ . '/../src/opnsense/data/appidentification/catalog.json';
$data = Catalog::load($file);
$checked = 0;
$failed = [];
foreach ($data['applications'] as $app) {
    $matched = false;
    foreach ($app['domains'] as $domain) {
        $result = Catalog::identify($domain['value']);
        if (($result['id'] ?? '') === $app['id']) {
            $matched = true;
            break;
        }
    }
    if ($matched) {
        $checked++;
    } else {
        $failed[] = $app['id'];
    }
}
if ($checked < 1000 || $failed) {
    fwrite(STDERR, json_encode(['matched' => $checked, 'unreachable_entries' => $failed]) . PHP_EOL);
    exit(1);
}
foreach (['github.com.attacker.invalid', 'notgithub.com', '192.168.1.1', 'unknown.invalid'] as $host) {
    if (Catalog::identify($host) !== null) {
        fwrite(STDERR, 'Unexpected match for ' . $host . PHP_EOL);
        exit(1);
    }
}
echo "Catalog verified: $checked independently reachable application/service entries; negative cases passed.\n";
