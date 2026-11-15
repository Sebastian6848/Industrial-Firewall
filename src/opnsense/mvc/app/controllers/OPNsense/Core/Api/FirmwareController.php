<?php

/*
 * Copyright (c) 2015-2025 Franco Fichtner <franco@opnsense.org>
 * Copyright (c) 2015-2018 Deciso B.V.
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *
 * 1. Redistributions of source code must retain the above copyright notice,
 *    this list of conditions and the following disclaimer.
 *
 * 2. Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in the
 *    documentation and/or other materials provided with the distribution.
 *
 * THIS SOFTWARE IS PROVIDED ``AS IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES,
 * INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY
 * AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
 * AUTHOR BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY,
 * OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
 * SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
 * INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
 * CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
 * ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 * POSSIBILITY OF SUCH DAMAGE.
 */

namespace OPNsense\Core\Api;

use OPNsense\Base\ApiMutableModelControllerBase;
use OPNsense\Core\Backend;
use OPNsense\Core\Config;
use OPNsense\Core\Firmware;
use OPNsense\Core\SanitizeFilter;
use OPNsense\Core\Shell;

/**
 * Class FirmwareController
 * @package OPNsense\Core
 */
class FirmwareController extends ApiMutableModelControllerBase
{
    protected static $internalModelName = 'firmware';
    protected static $internalModelClass = 'OPNsense\Core\Firmware';

    /**
     * Sanitize and restrict mutable package operations to plugins.
     * @param string $pkgName package name supplied by the client
     * @return string|null
     */
    private function sanitizePluginName($pkgName)
    {
        $pkgName = (new SanitizeFilter())->sanitize($pkgName, 'pkgname');
        return strpos($pkgName, 'os-') === 0 ? $pkgName : null;
    }

    /**
     * return bytes in human-readable form
     * @param integer $bytes bytes to convert
     * @return string
     */
    protected function formatBytes($bytes)
    {
        if (preg_match('/[^0-9]/', $bytes)) {
            /* already processed */
            return $bytes;
        }
        if ($bytes >= 1024 ** 5) {
            return sprintf('%.1F%s', $bytes / (1024 ** 5), 'PiB');
        } elseif ($bytes >= 1024 ** 4) {
            return sprintf('%.1F%s', $bytes / (1024 ** 4), 'TiB');
        } elseif ($bytes >= 1024 ** 3) {
            return sprintf('%.1F%s', $bytes / (1024 ** 3), 'GiB');
        } elseif ($bytes >= 1024 ** 2) {
            return sprintf('%.1F%s', $bytes / (1024 ** 2), 'MiB');
        } elseif ($bytes >= 1024) {
            return sprintf('%.1F%s', $bytes / 1024, 'KiB');
        } else {
            return sprintf('%d%s', $bytes, 'B');
        }
    }

    /**
     * Run check for updates
     * @return array
     */
    public function checkAction()
    {
        return [
            'status' => 'disabled',
            'status_msg' => gettext('System update checks are disabled on this product.'),
        ];
    }

    /**
     * retrieve available updates
     * @return array
     */
    public function statusAction()
    {
        $active_array = [];
        $active_count = 0;
        $active_size = '';
        $active_status = '';
        $backend = new Backend();

        if ($this->request->isPost()) {
            /* run a synchronous check prior to the result fetch */
            $backend->configdRun('firmware probe');
        }

        $product = json_decode(trim($backend->configdRun('firmware product')), true);
        if ($product == null) {
            $response = [
                'status_msg' => gettext('Firmware status check was aborted internally. Please try again.'),
                'status' => 'error',
            ];
        } elseif ($product['product_check'] == null) {
            $response = [
                'product' => $product,
                'status_msg' => gettext('Firmware status requires to check for update first to provide more information.'),
                'status' => 'none',
            ];
        } else {
            $response = $product['product_check'];
            $response['product'] = $product;

            $download_size = !empty($response['download_size']) ? $response['download_size'] : 0;

            $upgrade_size = 0;
            $update_size = 0;

            if (!empty($response['upgrade_packages'])) {
                foreach ($response['upgrade_packages'] as $listing) {
                    if (!empty($listing['size']) && is_numeric($listing['size'])) {
                        $update_size += $listing['size'];
                    }
                }
            }

            foreach (explode(',', $download_size) as $size) {
                if (preg_match('/\s*(\d+)\s*([a-z])/i', $size, $matches)) {
                    $factor = 1;
                    switch (isset($matches[2]) ? strtolower($matches[2]) : 'b') {
                        case 'p':
                            $factor *= 1024;
                            /* FALLTHROUGH */
                        case 't':
                            $factor *= 1024;
                            /* FALLTHROUGH */
                        case 'g':
                            $factor *= 1024;
                            /* FALLTHROUGH */
                        case 'm':
                            $factor *= 1024;
                            /* FALLTHROUGH */
                        case 'k':
                            $factor *= 1024;
                            /* FALLTHROUGH */
                        default:
                            break;
                    }
                    $update_size += $factor * $matches[1];
                }
            }

            $sorted = [];

            foreach (
                array('new_packages', 'reinstall_packages', 'upgrade_packages',
                'downgrade_packages', 'remove_packages') as $pkg_type
            ) {
                if (isset($response[$pkg_type])) {
                    foreach ($response[$pkg_type] as $value) {
                        switch ($pkg_type) {
                            case 'downgrade_packages':
                                $sorted[$value['name']] = array(
                                    'reason' => gettext('downgrade'),
                                    'old' => $value['current_version'],
                                    'new' => $value['new_version'],
                                    'name' => $value['name'],
                                    'repository' => $value['repository'],
                                );
                                break;
                            case 'new_packages':
                                $sorted[$value['name']] = array(
                                    'new' => $value['version'],
                                    'reason' => gettext('new'),
                                    'name' => $value['name'],
                                    'repository' => $value['repository'],
                                    'old' => gettext('N/A'),
                                );
                                break;
                            case 'reinstall_packages':
                                $sorted[$value['name']] = array(
                                    'reason' => gettext('reinstall'),
                                    'new' => $value['version'],
                                    'old' => $value['version'],
                                    'repository' => $value['repository'],
                                    'name' => $value['name'],
                                );
                                break;
                            case 'remove_packages':
                                $sorted[$value['name']] = array(
                                    'reason' => gettext('obsolete'),
                                    'new' => gettext('N/A'),
                                    'old' => $value['version'],
                                    'name' => $value['name'],
                                    'repository' => $value['repository'],
                                );
                                break;
                            case 'upgrade_packages':
                                $sorted[$value['name']] = array(
                                    'reason' => gettext('upgrade'),
                                    'old' => empty($value['current_version']) ?
                                        gettext('N/A') : $value['current_version'],
                                    'new' => $value['new_version'],
                                    'repository' => $value['repository'],
                                    'name' => $value['name'],
                                );
                                break;
                            default:
                                /* undefined */
                                break;
                        }
                    }
                }
            }

            uksort($sorted, function ($a, $b) {
                return strnatcasecmp($a, $b);
            });

            $response['all_packages'] = $sorted;

            $active_count = count($response['all_packages']);
            $active_array = &$response['all_packages'];
            $active_size = $update_size;
            $active_status = 'update';
            $active_reboot = '0';

            $sorted = [];

            if (isset($response['upgrade_sets'])) {
                foreach ($response['upgrade_sets'] as $value) {
                    if (!empty($value['size']) && is_numeric($value['size'])) {
                        $upgrade_size += $value['size'];
                    }
                    $sorted[$value['name']] = array(
                        'reason' => gettext('upgrade'),
                        'old' => empty($value['current_version']) ?
                            gettext('N/A') : $value['current_version'],
                        'new' => $value['new_version'],
                        'repository' => $value['repository'],
                        'name' => $value['name'],
                    );
                }
            }

            uksort($sorted, function ($a, $b) {
                return strnatcasecmp($a, $b);
            });

            $response['all_sets'] = $sorted;

            if ($active_count == 0) {
                $active_count = count($response['all_sets']);
                $active_array = &$response['all_sets'];
                $active_size = $upgrade_size;
                $active_status = 'upgrade';
            }

            $subscription = strpos($response['product']['product_mirror'], '${SUBSCRIPTION}') !== false;

            if (array_key_exists('connection', $response) && $response['connection'] == 'unresolved') {
                $response['status_msg'] = gettext('No address record found for the selected mirror.');
                $response['status'] = 'error';
            } elseif (array_key_exists('connection', $response) && $response['connection'] == 'unauthenticated') {
                $response['status_msg'] = gettext('Could not authenticate the selected mirror.');
                $response['status'] = 'error';
            } elseif (array_key_exists('connection', $response) && $response['connection'] == 'misconfigured') {
                $response['status_msg'] = gettext('The current package configuration is invalid.');
                $response['status'] = 'error';
            } elseif (array_key_exists('connection', $response) && $response['connection'] != 'ok') {
                $response['status_msg'] = gettext('An error occurred while connecting to the selected mirror.');
                $response['status'] = 'error';
            } elseif (array_key_exists('repository', $response) && $response['repository'] == 'untrusted') {
                $response['status_msg'] = gettext('Could not verify the repository fingerprint.');
                $response['status'] = 'error';
            } elseif (array_key_exists('repository', $response) && $response['repository'] == 'forbidden') {
                $response['status_msg'] = $subscription ? gettext('The provided subscription is either invalid or expired. Please make sure the input is correct. Otherwise contact sales or visit the online shop to obtain a valid one.') : gettext('The repository did not grant access.');
                $response['status'] = 'error';
            } elseif (array_key_exists('repository', $response) && $response['repository'] == 'revoked') {
                $response['status_msg'] = gettext('The repository fingerprint has been revoked.');
                $response['status'] = 'error';
            } elseif (array_key_exists('repository', $response) && $response['repository'] == 'unsigned') {
                $response['status_msg'] = gettext('The repository has no fingerprint.');
                $response['status'] = 'error';
            } elseif (array_key_exists('repository', $response) && $response['repository'] == 'incomplete') {
                $response['status_msg'] = sprintf(gettext('The release type "%s" is not available on this repository.'), $response['product_target']);
                $response['status'] = 'error';
            } elseif (array_key_exists('repository', $response) && $response['repository'] != 'ok') {
                $response['status_msg'] = $subscription ? sprintf(gettext('The matching %s %s series does not yet exist. Images are available to switch this installation to the latest business edition.'), $response['product']['product_name'], $response['product_abi']) : gettext('Could not find the repository on the selected mirror.');
                $response['status'] = 'error';
            } elseif ($active_count) {
                if ($active_count == 1) {
                    /* keep this dynamic for template translation even though %s is always '1' */
                    $response['status_msg'] = sprintf(
                        gettext('There is %s update available, total download size is %s.'),
                        $active_count,
                        $this->formatBytes($active_size)
                    );
                } else {
                    $response['status_msg'] = sprintf(
                        gettext('There are %s updates available, total download size is %s.'),
                        $active_count,
                        $this->formatBytes($active_size)
                    );
                }
                if (
                    ($active_status == 'update' && $response['needs_reboot'] == 1) ||
                    ($active_status == 'upgrade' && $response['upgrade_needs_reboot'] == 1)
                ) {
                    $active_reboot = '1';
                    $response['status_msg'] = sprintf(
                        '%s %s',
                        $response['status_msg'],
                        gettext('This update requires a reboot.')
                    );
                }
                $response['status_reboot'] = $active_reboot;
                $response['status'] = $active_status;
            } elseif (!$active_count) {
                $response['status_msg'] = gettext('There are no updates available on the selected mirror.');
                $response['status'] = 'none';
            } else {
                $response['status_msg'] = gettext('Unknown firmware status encountered.');
                $response['status'] = 'error';
            }
        }

        return $response;
    }

    /**
     * Retrieve specific changelog in text and html format
     * @param string $version changelog to retrieve
     * @return array corresponding changelog in both formats
     * @throws \Exception
     */
    public function changelogAction($version)
    {
        $response = ['status' => 'failure'];

        if (!$this->request->isPost()) {
            return $response;
        }

        $version = (new SanitizeFilter())->sanitize($version, 'version');

        $backend = new Backend();
        $html = trim($backend->configdpRun('firmware changelog html', [$version]));
        $date = trim($backend->configdpRun('firmware changelog date', [$version]));

        if (!empty($html)) {
            $response['version'] = $version;
            $response['status'] = 'ok';
            $response['html'] = $html;
            $response['date'] = $date;
        }

        return $response;
    }

    /**
     * Retrieve upgrade log hidden in system
     * @return string with upgrade log
     * @throws \Exception
     */
    public function logAction($clear)
    {
        $backend = new Backend();
        $response = ['status' => 'failure'];

        if ($this->request->isPost()) {
            $text = trim($backend->configdRun('firmware log ' . (empty($clear) ? 'show' : 'clear')));
            $response['status'] = 'ok';
            if (!empty($text)) {
                $response['log'] = $text;
            }
        }

        return $response;
    }

    /**
     * Retrieve specific license for package in text format
     * @param string $package package to retrieve
     * @return array with all possible licenses
     * @throws \Exception
     */
    public function licenseAction($package)
    {
        $backend = new Backend();
        $response = [];

        if ($this->request->isPost()) {
            // sanitize package name
            $package = (new SanitizeFilter())->sanitize($package, 'pkgname');
            $text = trim($backend->configdRun(sprintf('firmware license %s', $package)));
            if (!empty($text)) {
                $response['license'] = $text;
            }
        }

        return $response;
    }

    /**
     * perform reboot
     * @return array status
     * @throws \Exception
     */
    public function rebootAction()
    {
        $backend = new Backend();
        $response = [];
        if ($this->request->isPost()) {
            $this->getLogger('audit')->notice(sprintf("[Firmware] User %s executed a reboot", $this->getUserName()));
            $response['status'] = 'ok';
            $response['msg_uuid'] = trim($backend->configdRun('firmware reboot', true));
        } else {
            $response['status'] = 'failure';
        }

        return $response;
    }

    /**
     * perform poweroff
     * @return array status
     * @throws \Exception
     */
    public function poweroffAction()
    {
        $backend = new Backend();
        $response = [];
        if ($this->request->isPost()) {
            $this->getLogger('audit')->notice(sprintf("[Firmware] User %s executed a poweroff", $this->getUserName()));
            $response['status'] = 'ok';
            $response['msg_uuid'] = trim($backend->configdRun('firmware poweroff', true));
        } else {
            $response['status'] = 'failure';
        }

        return $response;
    }

    /**
     * perform (stable) update
     * @return array status
     * @throws \Exception
     */
    public function updateAction()
    {
        return [
            'status' => 'disabled',
            'status_msg' => gettext('System updates are disabled on this product.'),
        ];
    }

    /**
     * perform (major) upgrade
     * @return array status
     * @throws \Exception
     */
    public function upgradeAction()
    {
        return [
            'status' => 'disabled',
            'status_msg' => gettext('System upgrades are disabled on this product.'),
        ];
    }

    /**
     * run an audit in the backend
     * @return array status
     * @throws \Exception
     */
    private function auditHelper(string $audit): array
    {
        $backend = new Backend();
        $response = [];

        if ($this->request->isPost()) {
            $response['status'] = 'ok';
            $response['msg_uuid'] = trim($backend->configdRun("firmware $audit", true));
        } else {
            $response['status'] = 'failure';
        }

        return $response;
    }

    /**
     * run a cleanup task
     * @return array status
     * @throws \Exception
     */
    public function cleanupAction()
    {
        return $this->auditHelper('cleanup');
    }

    /**
     * run a connection check
     * @return array status
     * @throws \Exception
     */
    public function connectionAction()
    {
        return $this->auditHelper('connection');
    }

    /**
     * run a health check
     * @return array status
     * @throws \Exception
     */
    public function healthAction()
    {
        return $this->auditHelper('health');
    }

    /*
     * run a security audit
     * @return array status
     * @throws \Exception
     */
    public function auditAction()
    {
        if ($this->request->isPost()) {
            $this->getLogger('audit')->notice(sprintf("[Firmware] User %s executed a security audit", $this->getUserName()));
        }

        return $this->auditHelper('audit');
    }

    /**
     * reinstall package
     * @param string $pkg_name package name to reinstall
     * @return array status
     * @throws \Exception
     */
    public function reinstallAction($pkg_name)
    {
        $backend = new Backend();
        $response = [];
        $pkg_name = $this->request->isPost() ? $this->sanitizePluginName($pkg_name) : null;

        if (in_array($pkg_name, Firmware::LOCAL_PLUGINS, true)) {
            return ['status' => 'failure', 'status_msg' => gettext('本地定制插件由项目部署流程维护，不能从上游重装。')];
        }

        if (!empty($pkg_name)) {
            $this->getLogger('audit')->notice(
                sprintf("[Firmware] User %s executed a reinstall of plugin %s", $this->getUserName(), $pkg_name)
            );
            $response['status'] = 'ok';
            $response['msg_uuid'] = trim($backend->configdpRun("firmware reinstall", [$pkg_name], true));
        } else {
            $response['status'] = 'failure';
            $response['status_msg'] = gettext('Only os-* plugin packages can be reinstalled.');
        }

        return $response;
    }

    /**
     * install missing configured plugins
     * @return array status
     * @throws \Exception
     */
    public function syncPluginsAction()
    {
        $backend = new Backend();
        $response = [];

        if ($this->request->isPost()) {
            $this->getLogger('audit')->notice(sprintf("[Firmware] User %s executed a plugins sync", $this->getUserName()));
            $response['status'] = strtolower(trim($backend->configdRun('firmware sync')));
        } else {
            $response['status'] = 'failure';
        }

        return $response;
    }

    /**
     * reset missing configured plugins
     * @return array status
     * @throws \Exception
     */
    public function resyncPluginsAction()
    {
        $backend = new Backend();
        $response = [];

        if ($this->request->isPost()) {
            $response['status'] = strtolower(trim($backend->configdRun('firmware resync')));
        } else {
            $response['status'] = 'failure';
        }

        return $response;
    }

    /**
     * install package
     * @param string $pkg_name package name to install
     * @return array status
     * @throws \Exception
     */
    public function installAction($pkg_name)
    {
        $backend = new Backend();
        $response = [];
        $pkg_name = $this->request->isPost() ? $this->sanitizePluginName($pkg_name) : null;

        if (in_array($pkg_name, Firmware::LOCAL_PLUGINS, true)) {
            return ['status' => 'failure', 'status_msg' => gettext('本地定制插件由项目部署流程维护。')];
        }

        if (!empty($pkg_name)) {
            $this->getLogger('audit')->notice(
                sprintf("[Firmware] User %s executed an install of plugin %s", $this->getUserName(), $pkg_name)
            );
            $response['status'] = 'ok';
            $response['msg_uuid'] = trim($backend->configdpRun("firmware install", [$pkg_name], true));
        } else {
            $response['status'] = 'failure';
            $response['status_msg'] = gettext('Only os-* plugin packages can be installed.');
        }

        return $response;
    }

    /**
     * remove package
     * @param string $pkg_name package name to remove
     * @return array status
     * @throws \Exception
     */
    public function removeAction($pkg_name)
    {
        $backend = new Backend();
        $response = [];

        $pkg_name = $this->request->isPost() ? $this->sanitizePluginName($pkg_name) : null;

        if (!empty($pkg_name)) {
            $this->getLogger('audit')->notice(
                sprintf("[Firmware] User %s executed an remove of package %s", $this->getUserName(), $pkg_name)
            );
            $response['status'] = 'ok';
            // execute action
            $response['msg_uuid'] = trim($backend->configdpRun("firmware remove", array($pkg_name), true));
        } else {
            $response['status'] = 'failure';
        }

        return $response;
    }

    /**
     * lock package
     * @param string $pkg_name package name to lock
     * @return array status
     * @throws \Exception
     */
    public function lockAction($pkg_name)
    {
        $backend = new Backend();
        $response = [];

        if ($this->request->isPost()) {
            $pkg_name = $this->sanitizePluginName($pkg_name);
            if (!empty($pkg_name)) {
                $this->getLogger('audit')->notice(
                    sprintf("[Firmware] User %s locked package %s", $this->getUserName(), $pkg_name)
                );
            }
        } else {
            $pkg_name = null;
        }

        if (!empty($pkg_name)) {
            $response['msg_uuid'] = trim($backend->configdpRun("firmware lock", array($pkg_name), true));
            $response['status'] = 'ok';
        } else {
            $response['status'] = 'failure';
        }

        return $response;
    }

    /**
     * unlock package
     * @param string $pkg_name package name to unlock
     * @return array status
     * @throws \Exception
     */
    public function unlockAction($pkg_name)
    {
        $backend = new Backend();
        $response = [];

        if ($this->request->isPost()) {
            $pkg_name = $this->sanitizePluginName($pkg_name);
            if (!empty($pkg_name)) {
                $this->getLogger('audit')->notice(
                    sprintf("[Firmware] User %s unlocked package %s", $this->getUserName(), $pkg_name)
                );
            }
        } else {
            $pkg_name = null;
        }

        if (!empty($pkg_name)) {
            $response['msg_uuid'] = trim($backend->configdpRun("firmware unlock", array($pkg_name), true));
            $response['status'] = 'ok';
        } else {
            $response['status'] = 'failure';
        }

        return $response;
    }

    /**
     * retrieve execution status
     */
    public function runningAction()
    {
        $backend = new Backend();

        $result = array(
            'status' => trim($backend->configdRun('firmware running'))
        );

        return $result;
    }

    /**
     * retrieve upgrade status (and log file of current process)
     */
    public function upgradestatusAction()
    {
        $backend = new Backend();
        $result = array('status' => 'running');
        $cmd_result = trim($backend->configdRun('firmware status'));

        $result['log'] = $cmd_result;

        if ($cmd_result == null) {
            $result['status'] = 'error';
        } elseif (strpos($cmd_result, '***ERROR***') !== false) {
            $result['status'] = 'error';
        } elseif (strpos($cmd_result, '***DONE***') !== false) {
            $result['status'] = 'done';
        } elseif (strpos($cmd_result, '***REBOOT***') !== false) {
            $result['status'] = 'reboot';
        }

        return $result;
    }

    /**
     * query package details
     * @return array
     * @throws \Exception
     */
    public function detailsAction($package)
    {
        $backend = new Backend();
        $response = [];

        if ($this->request->isPost()) {
            $package = (new SanitizeFilter())->sanitize($package, 'pkgname');
            $text = trim($backend->configdRun(sprintf('firmware details %s', $package)));
            if (!empty($text)) {
                $response['details'] = $text;
            }
        }

        return $response;
    }

    /**
     * list local packages and remotely available plugins
     * @return array
     */
    public function infoAction($refresh = null)
    {
        $config = Config::getInstance()->object();
        $configPlugins = [];
        if (!empty($config->system->firmware->plugins)) {
            $configPlugins = explode(",", $config->system->firmware->plugins);
        }

        $keys = ['name', 'version', 'comment', 'flatsize', 'locked', 'automatic', 'license', 'repository', 'origin'];
        $backend = new Backend();
        $response = [];

        $version = explode(' ', Shell::shell_safe('opnsense-version -nv'));
        foreach (['product_id' => 0, 'product_version' => 1] as $result => $index) {
            $response[$result] = !empty($version[$index]) ? $version[$index] : 'unknown';
        }

        /* allows us to select UI features based on product state */
        $devel = explode('-', $response['product_id']);
        $devel = count($devel) == 2 ? $devel[1] == 'devel' : false;

        $packages = [];
        $plugins = [];
        $tiers = [];
        $remotePluginCount = 0;
        $refreshOutput = '';

        /* regenerate repository configuration without running a firmware check */
        $backend->configdRun('firmware reload');
        if ($refresh === '1') {
            $refreshOutput = trim($backend->configdRun('firmware catalogue_refresh') ?? '');
        }

        /* package infos are flat lists with 3 pipes as delimiter */
        foreach (array('remote', 'local') as $type) {
            $current = $backend->configdRun("firmware {$type}");
            $current = explode("\n", trim($current ?? ''));

            foreach ($current as $line) {
                $expanded = explode('|||', $line);
                $translated = [];
                $index = 0;
                if (count($expanded) != count($keys)) {
                    continue;
                }
                foreach ($keys as $key) {
                    $translated[$key] = $expanded[$index++];
                    if (empty($translated[$key])) {
                        $translated[$key] = gettext('N/A');
                    } elseif ($key == 'flatsize') {
                        $translated[$key] = $this->formatBytes($translated[$key]);
                    }
                }

                /* mark remote packages as provided and local packages as installed */
                $translated['provided'] = $type == 'remote' ? '1' : '0';
                $translated['installed'] = $type == 'local' ? '1' : '0';
                $translated['remote_version'] = $type == 'remote' ? $translated['version'] : gettext('N/A');
                if (isset($packages[$translated['name']])) {
                    /* local iteration, retain the version offered by the plugin repository */
                    $translated['provided'] = '1';
                    $translated['remote_version'] = $packages[$translated['name']]['remote_version'];
                }
                $translated['path'] = "{$translated['repository']}/{$translated['origin']}";
                $translated['configured'] = in_array($translated['name'], $configPlugins) || $translated['automatic'] == '1' ? '1' : '0';
                $packages[$translated['name']] = $translated;

                /* select local and remotely available plugins */
                $plugin = explode('-', $translated['name']);
                if (count($plugin)) {
                    if ($plugin[0] == 'os') {
                        if ($type == 'remote') {
                            $remotePluginCount++;
                        }
                        if (
                            $type == 'local' || ($type == 'remote' &&
                            ($devel || end($plugin) != 'devel'))
                        ) {
                            $plugins[$translated['name']] = $translated;
                        }
                    }
                }
            }
        }

        /* query annotations after remote refreshed the catalogue */
        $current = $backend->configdRun('firmware tiers');
        $current = explode("\n", trim($current ?? ''));
        foreach ($current as $line) {
            $expanded = explode('|||', $line);
            if (count($expanded) == 3) {
                $tiers[$expanded[0]] = $expanded[2];
            }
        }

        if ($remotePluginCount > 0) {
            $response['catalogue_status'] = $refresh !== '1' || str_contains($refreshOutput, 'CATALOGUE_REFRESH_OK') ? 'ok' : 'stale';
            $response['catalogue_message'] = sprintf(
                $response['catalogue_status'] === 'ok'
                    ? gettext('已加载软件源目录，共 %d 个插件。')
                    : gettext('联网刷新失败，继续显示缓存目录中的 %d 个插件；请检查镜像与代理配置。'),
                $remotePluginCount
            );
        } else {
            $response['catalogue_status'] = 'error';
            $response['catalogue_message'] = gettext('尚未取得插件目录，请检查镜像与代理配置后点击刷新。');
        }

        foreach ($configPlugins as $missing) {
            if (!array_key_exists($missing, $plugins)) {
                $plugins[$missing] = [];
                foreach ($keys as $key) {
                    $plugins[$missing][$key] = gettext('N/A');
                }
                $plugins[$missing]['path'] = gettext('N/A');
                $plugins[$missing]['configured'] = '1';
                $plugins[$missing]['installed'] = '0';
                $plugins[$missing]['provided'] = '0';
                $plugins[$missing]['remote_version'] = gettext('N/A');
                $plugins[$missing]['name'] = $missing;
            }
        }

        uasort($plugins, function ($a, $b) {
            return strnatcasecmp(
                ($a['configured'] && !$a['installed'] ? '0' : '1') . ($a['installed'] ? '0' : '1') . $a['name'],
                ($b['configured'] && !$b['installed'] ? '0' : '1') . ($b['installed'] ? '0' : '1') . $b['name']
            );
        });

        $response['plugin'] = [];
        foreach ($plugins as $plugin) {
            $plugin['local_custom'] = in_array($plugin['name'], Firmware::LOCAL_PLUGINS, true) ? '1' : '0';
            $plugin['catalogue_known'] = $remotePluginCount > 0 ? '1' : '0';
            if ($plugin['local_custom'] === '1') {
                $plugin['repository'] = gettext('本地构建');
            }
            /* for any community repository, orphaned package or otherwise unknown force the lowest tier */
            $plugin['tier'] = '4';

            if (
                in_array($plugin['repository'], ['OPNsense', 'SunnyValley']) &&
                $plugin['provided'] == '1' &&
                isset($tiers[$plugin['name']])
            ) {
                $plugin['tier'] = $tiers[$plugin['name']];
            }

            $response['plugin'][] = $plugin;
        }

        return $response;
    }

    /** Connection settings for plugin repositories, independent of system updates. */
    public function pluginSettingsAction()
    {
        $model = $this->getModel();
        $options = $model->getRepositoryOptions();
        if (!$this->request->isPost()) {
            $mirrors = [];
            foreach ($options['mirrors'] as $url => $label) {
                if (str_starts_with($url, 'https://') && !in_array($url, $options['mirrors_has_subscription'], true)) {
                    $mirrors[$url] = $label;
                }
            }
            return ['mirror' => (string)$model->mirror, 'plugin_proxy' => (string)$model->plugin_proxy, 'mirrors' => $mirrors];
        }
        $values = $this->request->getPost('connection');
        if (!is_array($values)) {
            return ['status' => 'failure'];
        }
        $mirror = $values['mirror'] ?? '';
        $proxy = $values['plugin_proxy'] ?? '';
        if (
            !is_string($mirror) || !isset($options['mirrors'][$mirror]) || !str_starts_with($mirror, 'https://') ||
            in_array($mirror, $options['mirrors_has_subscription'], true) || !is_string($proxy) || !Firmware::validPluginProxy($proxy)
        ) {
            return ['status' => 'failure', 'status_msg' => gettext('请选择 HTTPS 镜像；代理应为 http://主机:端口，留空直接连接。')];
        }
        $model->mirror = $mirror;
        $model->plugin_proxy = $proxy;
        $validation = $this->validate();
        if (!empty($validation['result'])) {
            return ['status' => 'failure', 'status_msg' => implode(' ', array_values($validation['validations'] ?? []))];
        }
        $this->save();
        (new Backend())->configdRun('firmware reload');
        return ['status' => 'ok'];
    }

    /**
     * list firmware mirror and flavour options
     * @return array
     */
    public function getOptionsAction()
    {
        return $this->getModel()->getRepositoryOptions();
    }

    /**
     * set firmware configuration options
     * @return array status
     */
    public function setAction()
    {
        $response = ['status' => 'failure'];

        if (!$this->request->isPost()) {
            return $response;
        }

        $values = $this->request->getPost(static::$internalModelName);

        foreach ($values as $key => &$value) {
            if ($key == 'plugins') {
                /* discards plugins on purpose for the time being */
                unset($values[$key]);
            } else {
                $value = filter_var($value, FILTER_SANITIZE_URL);
            }
        }

        $mdl = $this->getModel();
        $mdl->setNodes($values);

        $ret = $this->validate();
        if (!empty($ret['result'])) {
            $response['status_msg'] = array_values($ret['validations'] ?? [gettext('Unkown firmware validation error')]);
            return $response;
        }

        $response['status'] = 'ok';
        $this->save();

        $backend = new Backend();
        $backend->configdRun('firmware flush');
        $backend->configdRun('firmware reload');

        return $response;
    }
}
