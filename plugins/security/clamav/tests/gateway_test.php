<?php
// SPDX-License-Identifier: BSD-2-Clause
// Run on an isolated review appliance: php gateway_test.php
require_once('config.inc');
use OPNsense\ClamAV\Gateway;

function check($value, $message): void
{
    if (!$value) {
        throw new RuntimeException($message);
    }
}
$settings = Gateway::settings();
check(count($settings['interface_options']) > 0, 'Listener choices must contain actual interfaces');
unset($settings['interface_options']);
$valid = Gateway::validate($settings);
foreach ([['networks' => '0.0.0.0/0'], ['networks' => '::/0'], ['networks' => '127.0.0.1/999'],
    ['port' => '1344'], ['port' => '3310'], ['port' => '3128;id'], ['interfaces' => 'nonexistent'],
    ['max_file_mb' => '0'], ['update_proxy_host' => 'http://user:secret@proxy/'],
    ['networks' => ['bad']], ['unknown' => 'value']] as $invalid) {
    try {
        Gateway::validate(array_replace($settings, $invalid));
        throw new RuntimeException('Invalid settings accepted: ' . array_key_first($invalid));
    } catch (InvalidArgumentException $expected) {
        // Invalid input must fail before changing any configuration.
    }
}
check(Gateway::settings()['networks'] === $settings['networks'], 'Validation changed live settings');
$patches = Gateway::patches($valid);
check($patches['scan']['passonerror'] === '0' && $patches['scan']['sendpercentdata'] === '0',
    'Scanning failures and partial data must not bypass scanning');
check($patches['proxy']['forward']['acl']['unrestricted'] === '', 'Unrestricted clients must not bypass scanning');
check($patches['proxy']['forward']['addACLforInterfaceSubnets'] === '0', 'Interface subnets must not bypass the client allowlist');
$classes = ['OPNsense\\ClamAV\\General', 'OPNsense\\CICAP\\General', 'OPNsense\\CICAP\\Antivirus', 'OPNsense\\Proxy\\Proxy'];
$before = [];
foreach ($classes as $class) {
    $before[$class] = (new $class())->getNodeContent();
}
$changed = $settings;
$changed['max_file_mb'] = $settings['max_file_mb'] === '7' ? '8' : '7';
$calls = 0;
$result = Gateway::apply($changed, static function ($message) {}, function ($data, $progress) use (&$calls, $changed, $settings) {
    $calls++;
    if ($calls === 1) {
        check(Gateway::settings()['max_file_mb'] === $changed['max_file_mb'], 'Coordinated settings were not committed');
        throw new RuntimeException('Simulated service startup failure');
    }
    check($data['max_file_mb'] === $settings['max_file_mb'], 'Rollback used new settings');
});
check($result['status'] === 'error' && $result['rolled_back'] === true && $calls === 2,
    'Failed runtime application must roll back configuration and attempt service restoration');
foreach ($classes as $class) {
    check((new $class())->getNodeContent() === $before[$class], 'Rollback changed ' . $class);
}
echo "PASS: validation, scan policy and four-model rollback regression checks\n";
