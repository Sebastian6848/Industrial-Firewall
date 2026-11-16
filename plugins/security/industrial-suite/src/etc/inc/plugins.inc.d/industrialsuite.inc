<?php
// SPDX-License-Identifier: BSD-2-Clause

function industrialsuite_firewall($fw)
{
    $path = '/var/db/industrial-suite/isolation-active.json';
    if (!is_file($path)) {
        return;
    }
    $rules = json_decode(file_get_contents($path), true);
    if (!is_array($rules)) {
        throw new \RuntimeException('Industrial isolation policy is unreadable');
    }
    foreach ($rules as $rule) {
        // After essential system rules and before floating/interface user rules.
        $fw->registerFilterRule(2, $rule);
    }
}

function industrialsuite_cron()
{
    return [['description' => gettext('Industrial software integrity check'),
             'parameters' => [], 'command' => 'industrialsuite integrity_check']];
}

function industrialsuite_xmlrpc_sync()
{
    return [['id' => 'industrialsuite', 'description' => gettext('Industrial isolation policies'),
             'section' => 'OPNsense.IndustrialSuite.isolation',
             'services' => ['industrial_suite']]];
}

function industrialsuite_configure()
{
    return ['xmlrpc_sync' => ['industrialsuite_synced:2']];
}

function industrialsuite_synced($verbose, $sections)
{
    if (isset($sections['OPNsense']['IndustrialSuite']['isolation'])) {
        $result = json_decode(configd_run('industrialsuite isolation_apply e30='), true);
        if (($result['status'] ?? '') !== 'ok') {
            throw new \RuntimeException('Synchronized isolation policy could not be applied');
        }
    }
}

function industrialsuite_services()
{
    return [['name' => 'industrial_suite', 'description' => gettext('Software integrity monitor'),
             'pidfile' => '/var/run/industrial_suite.pid',
             'configd' => ['start' => ['industrialsuite monitor_start'],
                          'stop' => ['industrialsuite monitor_stop'],
                          'restart' => ['industrialsuite monitor_restart']]]];
}
