#!/usr/local/bin/php
<?php
// SPDX-License-Identifier: BSD-2-Clause
require_once('util.inc');
require_once('script/load_phalcon.php');

use OPNsense\Core\Config;
use OPNsense\Core\Firmware;

if (($argv[1] ?? '') === 'managed') {
    exit(in_array($argv[2] ?? '', Firmware::LOCAL_PLUGINS, true) ? 0 : 1);
}

$proxy = (string)(Config::getInstance()->object()->system->firmware->plugin_proxy ?? '');
if ($proxy !== '' && Firmware::validPluginProxy($proxy)) {
    echo $proxy;
}
