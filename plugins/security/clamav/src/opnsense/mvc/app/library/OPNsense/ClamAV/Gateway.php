<?php
// SPDX-License-Identifier: BSD-2-Clause
namespace OPNsense\ClamAV;

use OPNsense\Core\Config;

/** A single configuration transaction for the explicit HTTP antivirus gateway. */
class Gateway
{
    public const STATE = '/var/db/clamav-gateway';
    public const OPERATIONS = ['apply', 'configure', 'set_engine', 'save_updates', 'update', 'test'];
    private const SCAN_FIELDS = ['interfaces', 'port', 'networks', 'max_file_mb'];
    private const UPDATE_FIELDS = ['automatic_updates', 'update_proxy_host', 'update_proxy_port'];
    private const MODELS = [
        'clam' => '\\OPNsense\\ClamAV\\General',
        'icap' => '\\OPNsense\\CICAP\\General',
        'scan' => '\\OPNsense\\CICAP\\Antivirus',
        'proxy' => '\\OPNsense\\Proxy\\Proxy'
    ];

    private static function models(): array
    {
        $models = [];
        foreach (self::MODELS as $key => $class) {
            if (!class_exists($class)) {
                throw new \RuntimeException('防病毒依赖尚未安装，请安装或升级 os-clamav 及其依赖。');
            }
            $models[$key] = new $class();
        }
        return $models;
    }

    public static function settings(): array
    {
        $m = self::models();
        $interfaces = [];
        $assigned = Config::getInstance()->object()->interfaces;
        foreach ($m['proxy']->forward->interfaces->getNodeData() as $key => $option) {
            $iface = $assigned->{$key};
            $ipv4 = (string)$iface->ipaddr;
            $dhcp = $ipv4 === 'dhcp';
            if ($dhcp) {
                $device = (string)$iface->if;
                $ipv4 = '';
                if ($device !== '' && $device[0] !== '-') {
                    $output = [];
                    exec('/sbin/ifconfig ' . escapeshellarg($device) . ' inet 2>/dev/null', $output);
                    if (preg_match('/^\s*inet\s+(\S+)/m', implode("\n", $output), $match)) {
                        $ipv4 = $match[1];
                    }
                }
            }
            $ipv4 = filter_var($ipv4, FILTER_VALIDATE_IP, FILTER_FLAG_IPV4) && $ipv4 !== '0.0.0.0' ? $ipv4 : '';
            $ipv6 = (string)$iface->ipaddrv6;
            $ipv6 = filter_var($ipv6, FILTER_VALIDATE_IP, FILTER_FLAG_IPV6) && $ipv6 !== '::' ? $ipv6 : '';
            $interfaces[] = ['id' => $key, 'name' => $option['value'], 'address' => $ipv4 ?: $ipv6,
                'dhcp' => $dhcp, 'available' => !$dhcp || $ipv4 !== '' || $ipv6 !== ''];
        }
        $size = (string)$m['scan']->maxobjectsize;
        return ['enabled' => (string)$m['clam']->enabled === '1' && (string)$m['proxy']->forward->icap->enable === '1' ? '1' : '0',
            'interfaces' => (string)$m['proxy']->forward->interfaces,
            'port' => (string)$m['proxy']->forward->port,
            'networks' => str_replace(',', "\n", (string)$m['proxy']->forward->acl->allowedSubnets),
            'max_file_mb' => preg_match('/^(\d+)M$/iD', $size, $match) ? $match[1] : '5',
            'automatic_updates' => (string)$m['clam']->fc_enabled,
            'update_proxy_host' => (string)$m['clam']->fc_proxyhost,
            'update_proxy_port' => (string)$m['clam']->fc_proxyport,
            'interface_options' => $interfaces];
    }

    private static function fields(array $data, array $fields): array
    {
        if (array_diff(array_keys($data), $fields)) {
            throw new \InvalidArgumentException('请求包含未知设置。');
        }
        foreach ($fields as $field) {
            if (!isset($data[$field]) || !is_scalar($data[$field])) {
                throw new \InvalidArgumentException('缺少有效设置：' . $field);
            }
            $data[$field] = trim((string)$data[$field]);
        }
        return $data;
    }

    private static function updateFields(array $data): array
    {
        $data = self::fields($data, self::UPDATE_FIELDS);
        if (!in_array($data['automatic_updates'], ['0', '1'], true)) {
            throw new \InvalidArgumentException('自动更新开关必须为 0 或 1。');
        }
        $host = $data['update_proxy_host'];
        if ($host !== '' && !filter_var($host, FILTER_VALIDATE_IP) &&
            (!filter_var($host, FILTER_VALIDATE_DOMAIN, FILTER_FLAG_HOSTNAME) || strlen($host) > 253)) {
            throw new \InvalidArgumentException('病毒库代理请填写主机名或 IP，不要填写 URL 或认证信息。');
        }
        $port = $data['update_proxy_port'];
        if (!ctype_digit($port) || (int)$port < 1 || (int)$port > 65535) {
            throw new \InvalidArgumentException('病毒库更新代理端口须在 1 到 65535 之间。');
        }
        $data['update_proxy_port'] = (string)(int)$port;
        return $data;
    }

    public static function validate(array $data): array
    {
        $data = self::fields($data, array_merge(['enabled'], self::SCAN_FIELDS, self::UPDATE_FIELDS));
        $data = array_replace($data, self::updateFields(array_intersect_key($data, array_flip(self::UPDATE_FIELDS))));
        if (!in_array($data['enabled'], ['0', '1'], true)) {
            throw new \InvalidArgumentException('启用开关必须为 0 或 1。');
        }
        foreach (['port' => [1024, 65535], 'max_file_mb' => [1, 100]] as $field => $range) {
            if (!ctype_digit($data[$field]) || (int)$data[$field] < $range[0] || (int)$data[$field] > $range[1]) {
                throw new \InvalidArgumentException('数值超出允许范围：' . $field);
            }
            $data[$field] = (string)(int)$data[$field];
        }
        if (in_array((int)$data['port'], [1344, 3310], true)) {
            throw new \InvalidArgumentException('代理监听端口不能与内部扫描端口冲突。');
        }
        $networks = preg_split('/[\s,]+/', $data['networks'], -1, PREG_SPLIT_NO_EMPTY);
        if (count($networks) > 128 || ($data['enabled'] === '1' && !$networks)) {
            throw new \InvalidArgumentException('启用时需指定允许的客户端地址或网段，最多 128 个。');
        }
        foreach ($networks as $network) {
            $parts = explode('/', $network);
            if (count($parts) > 2 || !filter_var($parts[0], FILTER_VALIDATE_IP)) {
                throw new \InvalidArgumentException('无效客户端地址或网段：' . $network);
            }
            $max = str_contains($parts[0], ':') ? 128 : 32;
            if (isset($parts[1]) && (!ctype_digit($parts[1]) || (int)$parts[1] < 1 || (int)$parts[1] > $max)) {
                throw new \InvalidArgumentException('禁止任意来源网段，请填写具体客户端网络：' . $network);
            }
        }
        $data['networks'] = implode(',', array_unique($networks));
        $options = self::settings()['interface_options'];
        $selected = array_filter(explode(',', $data['interfaces']));
        if (($data['enabled'] === '1' && !$selected) || array_diff($selected, array_column($options, 'id'))) {
            throw new \InvalidArgumentException('请选择有效的代理监听接口。');
        }
        if ($data['enabled'] === '1' &&
            array_diff($selected, array_column(array_filter($options, fn ($option) => $option['available']), 'id'))) {
            throw new \InvalidArgumentException('所选 DHCP 接口尚未取得地址，请稍后重试或选用其他接口。');
        }
        $data['interfaces'] = implode(',', array_unique($selected));
        return $data;
    }

    public static function patches(array $d): array
    {
        return [
            'clam' => ['enabled' => $d['enabled'], 'enabletcp' => '1', 'fc_enabled' => $d['automatic_updates'],
                'fc_proxyhost' => $d['update_proxy_host'], 'fc_proxyport' => $d['update_proxy_port'],
                'maxfilesize' => $d['max_file_mb'] . 'M', 'maxscansize' => max(100, (int)$d['max_file_mb'] * 2) . 'M'],
            'icap' => ['enabled' => $d['enabled'], 'listenaddress' => '127.0.0.1', 'localSquid' => '1'],
            'scan' => ['enable_clamav' => $d['enabled'], 'passonerror' => '0', 'sendpercentdata' => '0',
                'maxobjectsize' => $d['max_file_mb'] . 'M'],
            'proxy' => ['general' => ['enabled' => $d['enabled']], 'forward' => [
                'interfaces' => $d['interfaces'], 'port' => $d['port'], 'addACLforInterfaceSubnets' => '0',
                'antivirusGateway' => '1',
                'acl' => ['allowedSubnets' => $d['networks'], 'unrestricted' => ''],
                'icap' => ['enable' => $d['enabled'], 'RequestURL' => 'icap://127.0.0.1:1344/avscan',
                    'ResponseURL' => 'icap://127.0.0.1:1344/avscan', 'exclude' => '']]]
        ];
    }

    private static function select(array $source, array $shape): array
    {
        $result = [];
        foreach ($shape as $key => $value) {
            $result[$key] = is_array($value) ? self::select($source[$key] ?? [], $value) : ($source[$key] ?? '');
        }
        return $result;
    }

    private static function save(array $patches, ?array $expected = null): array
    {
        $config = Config::getInstance()->lock();
        try {
            $models = self::models();
            $before = [];
            foreach ($patches as $key => $patch) {
                $before[$key] = self::select($models[$key]->getNodeContent(), $patch);
                if ($expected !== null && $before[$key] !== $expected[$key]) {
                    throw new \RuntimeException('配置已由其他操作修改，未覆盖这些修改。');
                }
                if ($expected === null && $key === 'proxy' &&
                    ((string)$models[$key]->forward->sslbump === '1' || (string)$models[$key]->forward->transparentMode === '1')) {
                    throw new \RuntimeException('现有代理启用了透明代理或 HTTPS 解密，请先在高级配置中确认切换到显式代理。');
                }
                $models[$key]->setNodes($patch);
                $errors = $models[$key]->performValidation();
                if ($errors->count()) {
                    $messages = [];
                    foreach ($errors as $error) {
                        $messages[] = $error->getField() . ': ' . $error->getMessage();
                    }
                    throw new \InvalidArgumentException(implode('; ', $messages));
                }
            }
            foreach ($patches as $key => $_) {
                $models[$key]->serializeToConfig();
            }
            $config->save(['description' => 'Apply unified antivirus gateway settings']);
            return $before;
        } finally {
            $config->unlock();
        }
    }

    private static function command(array $args, int $timeout = 30): string
    {
        $files = [1 => ['pipe', 'w'], 2 => ['redirect', 1]];
        $proc = proc_open($args, $files, $pipes, null, null, ['bypass_shell' => true]);
        if (!is_resource($proc)) {
            throw new \RuntimeException('无法启动后台操作。');
        }
        stream_set_blocking($pipes[1], false);
        $deadline = microtime(true) + $timeout;
        $output = '';
        do {
            $output .= stream_get_contents($pipes[1]);
            $status = proc_get_status($proc);
            if (!$status['running']) {
                break;
            }
            if (microtime(true) > $deadline) {
                proc_terminate($proc);
                fclose($pipes[1]);
                proc_close($proc);
                throw new \RuntimeException('操作超时：' . basename($args[0]) . ' ' . ($args[1] ?? ''));
            }
            usleep(100000);
        } while (true);
        $output .= stream_get_contents($pipes[1]);
        fclose($pipes[1]);
        proc_close($proc);
        if ($status['exitcode'] !== 0) {
            throw new \RuntimeException(substr(trim($output), -2000) ?: '操作失败：' . basename($args[0]));
        }
        return trim($output);
    }

    private static function service(string $name, bool $enabled, bool $restart = true): void
    {
        exec('/usr/sbin/service ' . escapeshellarg($name) . ' onestatus 2>/dev/null', $unused, $status);
        if ($enabled && ($status !== 0 || $restart)) {
            self::command(['/usr/sbin/service', $name, $status === 0 ? 'onerestart' : 'onestart'], 90);
        } elseif (!$enabled && $status === 0) {
            self::command(['/usr/sbin/service', $name, 'onestop'], 45);
        }
    }

    private static function ready(int $port, int $seconds): void
    {
        $deadline = time() + $seconds;
        do {
            $socket = @fsockopen('127.0.0.1', $port, $errno, $error, 1);
            if (is_resource($socket)) {
                fclose($socket);
                return;
            }
            usleep(250000);
        } while (time() < $deadline);
        throw new \RuntimeException('扫描服务尚未就绪，内部端口：' . $port . '。请查看诊断信息。');
    }

    private static function runtime(array $d, callable $progress): void
    {
        $progress('正在生成防病毒关联配置');
        foreach (['ClamAV', 'CICAP', 'Proxy'] as $template) {
            self::command(['/usr/local/sbin/configctl', 'template', 'reload', 'OPNsense/' . $template]);
        }
        $m = self::models();
        $on = (string)$m['proxy']->general->enabled === '1';
        // Restore each component's previous state independently during rollback.
        if (!$on) {
            self::service('squid', false);
        }
        if ((string)$m['clam']->enabled === '1') {
            $progress('正在启动病毒扫描引擎并等待病毒库加载');
            if (!self::hasDatabase()) {
                $progress('首次启用：正在下载病毒库，请等待下载完成');
                self::service('clamav_freshclam', false);
                self::command(['/usr/local/bin/freshclam', '--stdout'], 600);
            }
            self::service('clamav_clamd', true);
            self::ready(3310, 120);
        }
        if ((string)$m['icap']->enabled === '1') {
            $progress('正在连接扫描服务');
            self::service('c-icap', true);
            self::ready(1344, 20);
        } else {
            self::service('c-icap', false);
        }
        if ((string)$m['clam']->enabled !== '1') {
            self::service('clamav_clamd', false);
        }
        if ($on) {
            $progress('正在启动下载防病毒代理');
            $result = self::command(['/usr/local/sbin/configctl', 'proxy', 'restart'], 90);
            if (!str_ends_with(trim($result), '__ok__')) {
                throw new \RuntimeException('代理启动失败：' . substr($result, -1800));
            }
        }
        $progress('正在应用病毒库自动更新设置');
        self::service('clamav_freshclam', $d['automatic_updates'] === '1', false);
    }

    private static function hasDatabase(): bool
    {
        return (file_exists('/var/db/clamav/main.cvd') || file_exists('/var/db/clamav/main.cld')) &&
            (file_exists('/var/db/clamav/daily.cvd') || file_exists('/var/db/clamav/daily.cld'));
    }

    public static function apply(
        array $data,
        callable $progress,
        ?callable $runtime = null,
        bool $saveUpdates = true
    ): array
    {
        $data = self::validate($data);
        $patches = self::patches($data);
        if (!$saveUpdates) {
            unset($patches['clam']['fc_enabled'], $patches['clam']['fc_proxyhost'], $patches['clam']['fc_proxyport']);
        }
        return self::applyChanges(
            $patches,
            $data,
            $progress,
            $runtime ?? static function ($settings, $notify) use ($saveUpdates) {
                self::runtime($settings, $notify);
                if ($saveUpdates && $settings['automatic_updates'] === '1') {
                    self::service('clamav_freshclam', true);
                }
            },
            $data['enabled'] === '1' ?
                '防病毒设置已应用，关联服务已就绪。' : '防病毒设置已保存，扫描仍处于停止状态。',
            $data['enabled'] === '1' && $runtime === null
        );
    }

    private static function applyChanges(
        array $patches,
        array $data,
        callable $progress,
        callable $runtime,
        string $message,
        bool $probe = false
    ): array {
        $old = self::settings();
        $before = self::save($patches);
        try {
            $runtime($data, $progress);
            if ($probe) {
                $progress('正在验证正常下载与病毒测试样本的拦截链路');
                self::probe();
            }
            return ['status' => 'ok', 'message' => $message];
        } catch (\Throwable $error) {
            $progress('应用失败，正在恢复之前的设置和服务');
            try {
                self::save($before, $patches);
                $runtime($old, $progress);
                return ['status' => 'error', 'rolled_back' => true, 'message' => $error->getMessage() . ' 已恢复之前的设置。'];
            } catch (\Throwable $rollback) {
                return ['status' => 'error', 'rolled_back' => false,
                    'message' => $error->getMessage() . ' 回退未完成：' . $rollback->getMessage()];
            }
        }
    }

    private static function savedSettings(): array
    {
        $settings = self::settings();
        unset($settings['interface_options']);
        return $settings;
    }

    private static function setEngine(string $enabled, callable $progress): array
    {
        $settings = self::savedSettings();
        $settings['enabled'] = $enabled;
        if ($enabled === '1') {
            return self::apply($settings, $progress, null, false);
        }
        return self::applyChanges([
            'clam' => ['enabled' => '0'],
            'icap' => ['enabled' => '0'],
            'scan' => ['enable_clamav' => '0'],
            'proxy' => ['general' => ['enabled' => '0'], 'forward' => ['icap' => ['enable' => '0']]]
        ], $settings, $progress, [self::class, 'runtime'], '防病毒已停止。病毒库更新按现有设置运行。');
    }

    private static function saveUpdates(array $settings, callable $progress): array
    {
        $patch = ['clam' => ['fc_enabled' => $settings['automatic_updates'],
            'fc_proxyhost' => $settings['update_proxy_host'], 'fc_proxyport' => $settings['update_proxy_port']]];
        return self::applyChanges($patch, $settings, $progress, static function ($data, $notify) {
            $notify('正在应用病毒库更新设置');
            self::command(['/usr/local/sbin/configctl', 'template', 'reload', 'OPNsense/ClamAV']);
            self::service('clamav_freshclam', $data['automatic_updates'] === '1');
        }, '病毒库更新设置已保存。');
    }

    public static function state(array $data): void
    {
        $tmp = self::STATE . '/job.' . getmypid() . '.tmp';
        file_put_contents($tmp, json_encode($data, JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR));
        chmod($tmp, 0600);
        rename($tmp, self::STATE . '/job.json');
    }

    public static function job(): array
    {
        $job = json_decode(@file_get_contents(self::STATE . '/job.json') ?: '{}', true) ?: [];
        if (($job['running'] ?? false) && time() - ($job['updated_at'] ?? 0) > 900) {
            $job['running'] = false;
            $job['status'] = 'error';
            $job['message'] = '上一次操作未正常结束，请检查服务状态后重新应用。';
        }
        return $job;
    }

    public static function start(string $operation, array $payload): array
    {
        if (!is_dir(self::STATE)) {
            mkdir(self::STATE, 0700, true);
        }
        $lock = fopen(self::STATE . '/launch.lock', 'c');
        flock($lock, LOCK_EX);
        try {
            if (self::job()['running'] ?? false) {
                throw new \RuntimeException('防病毒操作正在进行，请等待完成。');
            }
            $payload = match ($operation) {
                'apply' => self::validate($payload),
                'configure' => self::fields($payload, self::SCAN_FIELDS),
                'save_updates' => self::updateFields($payload),
                'set_engine' => self::fields($payload, ['enabled']),
                'update', 'test' => self::fields($payload, []),
                default => throw new \InvalidArgumentException('不支持的防病毒操作。')
            };
            if ($operation === 'set_engine' && !in_array($payload['enabled'], ['0', '1'], true)) {
                throw new \InvalidArgumentException('启停操作必须指定有效的目标状态。');
            }
            $id = bin2hex(random_bytes(12));
            $state = ['id' => $id, 'operation' => $operation, 'running' => true, 'status' => 'running',
                'message' => '后台操作已排队', 'updated_at' => time()];
            self::state($state);
            try {
                self::command(['/usr/sbin/daemon', '-f', '/usr/local/bin/php',
                    '/usr/local/opnsense/scripts/OPNsense/ClamAV/gateway.php', 'worker', $id, $operation,
                    base64_encode(json_encode($payload, JSON_THROW_ON_ERROR))]);
            } catch (\Throwable $error) {
                self::state(array_merge($state, ['running' => false, 'status' => 'error', 'message' => $error->getMessage()]));
                throw $error;
            }
            return ['status' => 'accepted', 'id' => $id, 'message' => '防病毒操作已开始，请等待状态更新。'];
        } finally {
            flock($lock, LOCK_UN);
            fclose($lock);
        }
    }

    public static function worker(string $id, string $operation, array $payload): void
    {
        $lock = fopen(self::STATE . '/operation.lock', 'c');
        flock($lock, LOCK_EX);
        $progress = static function ($message) use ($id, $operation) {
            self::state(['id' => $id, 'operation' => $operation, 'running' => true,
                'status' => 'running', 'message' => $message, 'updated_at' => time()]);
        };
        try {
            if ($operation === 'apply') {
                $result = self::apply($payload, $progress);
            } elseif ($operation === 'configure') {
                $result = self::apply(array_replace(self::savedSettings(), $payload), $progress, null, false);
            } elseif ($operation === 'set_engine') {
                $result = self::setEngine($payload['enabled'], $progress);
            } elseif ($operation === 'save_updates') {
                $result = self::saveUpdates($payload, $progress);
            } elseif ($operation === 'test') {
                $progress('正在检查防病毒下载链路');
                $result = self::probe();
            } elseif ($operation === 'update') {
                $progress('正在更新病毒库，首次下载可能需要几分钟');
                // The daemon owns freshclam's database lock; stop it during a manual update.
                self::command(['/usr/local/sbin/configctl', 'template', 'reload', 'OPNsense/ClamAV']);
                self::service('clamav_freshclam', false);
                try {
                    self::command(['/usr/local/bin/freshclam', '--stdout'], 600);
                } finally {
                    self::service('clamav_freshclam', self::settings()['automatic_updates'] === '1');
                }
                $result = ['status' => 'ok', 'message' => '病毒库检查及更新已完成。'];
            } else {
                throw new \RuntimeException('无效操作。');
            }
        } catch (\Throwable $error) {
            $result = ['status' => 'error', 'message' => $error->getMessage()];
        }
        self::state(array_merge($result, ['id' => $id, 'operation' => $operation,
            'running' => false, 'updated_at' => time()]));
        flock($lock, LOCK_UN);
        fclose($lock);
    }

    public static function status(): array
    {
        $services = [];
        foreach (['clamav_clamd' => '病毒扫描', 'c-icap' => '扫描连接', 'squid' => '下载代理', 'clamav_freshclam' => '自动更新'] as $service => $name) {
            exec('/usr/sbin/service ' . escapeshellarg($service) . ' onestatus 2>/dev/null', $unused, $code);
            $services[] = ['name' => $name, 'running' => $code === 0];
        }
        $databases = [];
        foreach (['main', 'daily', 'bytecode'] as $name) {
            $path = file_exists('/var/db/clamav/' . $name . '.cld') ? '/var/db/clamav/' . $name . '.cld' : '/var/db/clamav/' . $name . '.cvd';
            $header = is_file($path) ? explode(':', file_get_contents($path, false, null, 0, 512)) : [];
            $databases[] = ['name' => $name, 'present' => ($header[0] ?? '') === 'ClamAV-VDB',
                'version' => $header[2] ?? '', 'signatures' => $header[3] ?? '', 'built_at' => $header[1] ?? ''];
        }
        $m = self::models();
        $warnings = [];
        if ((string)$m['clam']->enabled === '1') {
            $expected = ['icap' => ['enabled' => '1', 'listenaddress' => '127.0.0.1', 'localSquid' => '1'],
                'scan' => ['enable_clamav' => '1', 'passonerror' => '0', 'sendpercentdata' => '0'],
                'proxy' => ['general' => ['enabled' => '1'], 'forward' => ['icap' => ['enable' => '1',
                    'RequestURL' => 'icap://127.0.0.1:1344/avscan', 'ResponseURL' => 'icap://127.0.0.1:1344/avscan']]]];
            foreach ($expected as $key => $shape) {
                if (self::select($m[$key]->getNodeContent(), $shape) !== $shape) {
                    $warnings[] = '关联设置不一致，请在本页重新应用防病毒配置。';
                    break;
                }
            }
            if ((string)$m['clam']->enabletcp !== '1') {
                $warnings[] = '扫描引擎的内部连接未启用。';
            }
            if (!self::hasDatabase()) {
                $warnings[] = '病毒库尚未就绪，请应用防病毒配置或更新病毒库。';
            }
            if ((string)$m['scan']->maxobjectsize !== (string)$m['clam']->maxfilesize) {
                $warnings[] = '各组件的扫描文件大小不一致，请重新应用防病毒设置。';
            }
            if ((string)$m['proxy']->forward->icap->exclude !== '' ||
                (string)$m['proxy']->forward->acl->unrestricted !== '') {
                $warnings[] = '高级配置中存在绕过扫描的例外，请核对后重新应用。';
            }
            foreach (array_slice($services, 0, 3) as $service) {
                if (!$service['running']) {
                    $warnings[] = $service['name'] . '未运行，请应用配置或查看诊断日志。';
                }
            }
        }
        return ['status' => 'ok', 'engine_enabled' => (string)$m['clam']->enabled === '1' &&
            (string)$m['proxy']->forward->icap->enable === '1', 'services' => $services, 'databases' => $databases,
            'warnings' => $warnings, 'job' => self::job()];
    }

    private static function probe(): array
    {
        $result = json_decode(self::command(['/usr/local/bin/python3',
            '/usr/local/opnsense/scripts/OPNsense/ClamAV/probe.py'], 50), true);
        if (!is_array($result) || ($result['status'] ?? '') !== 'ok') {
            throw new \RuntimeException($result['message'] ?? '防病毒链路自检未完成。');
        }
        return $result;
    }

    public static function logs(): array
    {
        $rows = [];
        foreach (['扫描引擎与更新' => '/var/log/system/latest.log', '下载代理' => '/var/log/squid/cache.log',
            '扫描连接' => '/var/log/c-icap/server.log', '病毒扫描' => '/var/log/clamd/latest.log'] as $name => $path) {
            if (!is_readable($path)) {
                continue;
            }
            $file = fopen($path, 'r');
            $size = fstat($file)['size'];
            if ($size > 65536) {
                fseek($file, -65536, SEEK_END);
                fgets($file);
            }
            $lines = explode("\n", stream_get_contents($file));
            fclose($file);
            foreach (array_slice($lines, -120) as $line) {
                if ($line !== '' && ($name !== '扫描引擎与更新' || preg_match('/clam|c-icap|squid/i', $line))) {
                    $rows[] = ['component' => $name, 'message' => $line];
                }
            }
        }
        return ['status' => 'ok', 'rows' => array_slice($rows, -200)];
    }
}
