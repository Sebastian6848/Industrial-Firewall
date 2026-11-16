<?php

function indproto_enabled()
{
    global $config;

    return isset($config['OPNsense']['IndProto']['general']['enabled']) &&
        (string)$config['OPNsense']['IndProto']['general']['enabled'] === '1';
}

function indproto_configure()
{
    return [
        'indproto_rules' => ['indproto_rules_generate', 0],
        'xmlrpc_sync' => ['indproto_synced:2'],
    ];
}

function indproto_xmlrpc_sync()
{
    return [['id' => 'indproto', 'description' => gettext('Industrial protocol policies'),
             'section' => 'OPNsense.IndProto', 'services' => ['suricata']]];
}

function indproto_synced($verbose, $sections)
{
    if (isset($sections['OPNsense']['IndProto'])) {
        $response = json_decode(configd_run('indproto apply'), true);
        if (($response['status'] ?? '') !== 'ok') {
            throw new \RuntimeException('Synchronized industrial protocol policy could not be applied');
        }
    }
}

function indproto_rules_generate($verbose = false)
{
    $response = configd_run('indproto apply');
    if ($verbose) {
        printf("indproto apply: %s\n", trim($response));
    }
}
