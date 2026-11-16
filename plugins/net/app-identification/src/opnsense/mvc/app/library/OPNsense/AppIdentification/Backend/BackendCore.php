<?php

namespace OPNsense\AppIdentification\Backend;

class BackendResult
{
    public static function ok(array $data = [], string $message = 'ok'): array
    {
        return array_merge(['status' => 'ok', 'message' => $message], $data);
    }

    public static function error(string $message, array $data = []): array
    {
        return array_merge(['status' => 'error', 'message' => $message], $data);
    }
}

class CapabilityProbe
{
    public function probe(array $settings = []): array
    {
        $items = [
            'ntopng_binary' => $this->command('ntopng') || is_executable('/usr/local/bin/ntopng'),
            'rules_dir_writable' => $this->dirWritable('/var/db/ntopng'),
        ];
        if (!empty($settings)) {
            $client = new NtopngClient($settings);
            $items['ntopng_api'] = ($client->get('flow/active.lua', ['ifid' => $settings['ifid'] ?? 1, 'perPage' => 1])['status'] ?? '') !== 'error';
        }
        return [
            'available' => $items,
            'missing' => array_keys(array_filter($items, static fn($ok) => !$ok)),
        ];
    }

    private function command(string $command): bool
    {
        return trim((string)shell_exec('command -v ' . escapeshellarg($command) . ' 2>/dev/null')) !== '';
    }

    private function dirWritable(string $path): bool
    {
        return is_dir($path) ? is_writable($path) : is_writable(dirname($path));
    }
}

class RuleStore
{
    private const RULES_FILE = '/var/db/ntopng/protos.txt';
    private const RULES_BAK = '/var/db/ntopng/protos.txt.bak';

    public function read(): array
    {
        $rules = [];
        if (is_file(self::RULES_FILE)) {
            foreach (file(self::RULES_FILE, FILE_IGNORE_NEW_LINES) ?: [] as $line) {
                $line = trim((string)$line);
                if ($line !== '') {
                    $rules[] = $line;
                }
            }
        }
        return BackendResult::ok(['data' => $rules, 'file' => self::RULES_FILE], 'rules read');
    }

    public function write(array $rules): array
    {
        $dir = dirname(self::RULES_FILE);
        if (!is_dir($dir) && !mkdir($dir, 0755, true)) {
            return BackendResult::error('failed to create ' . $dir);
        }
        $lines = [];
        foreach ($rules as $rule) {
            if (is_scalar($rule)) {
                $line = trim((string)$rule);
                if ($line !== '') {
                    $lines[] = $line;
                }
            }
        }
        if (is_file(self::RULES_FILE)) {
            @copy(self::RULES_FILE, self::RULES_BAK);
        }
        if (file_put_contents(self::RULES_FILE, implode("\n", $lines) . (empty($lines) ? '' : "\n")) === false) {
            return BackendResult::error('failed to write ' . self::RULES_FILE);
        }
        @chown(self::RULES_FILE, 'ntopng');
        @chgrp(self::RULES_FILE, 'ntopng');
        @chmod(self::RULES_FILE, 0640);
        return BackendResult::ok(['data' => ['written' => count($lines), 'file' => self::RULES_FILE, 'backup' => self::RULES_BAK]], 'rules written');
    }
}

class NtopngClient
{
    private array $settings;

    public function __construct(array $settings)
    {
        $this->settings = $settings;
    }

    public function get(string $endpoint, array $params = []): array
    {
        $endpoint = ltrim($endpoint, '/');
        $url = $this->baseUrl() . $endpoint;
        if (!empty($params)) {
            $url .= (strpos($url, '?') === false ? '?' : '&') . http_build_query($params);
        }
        $headers = ['Accept: application/json'];
        $token = trim((string)($this->settings['auth_token'] ?? ''));
        if ($token === '') {
            return BackendResult::error('ntopng API token is required');
        }
        $token = preg_replace('/^Token\s+/i', '', $token);
        $headers[] = 'Authorization: Token ' . $token;
        $ch = curl_init($url);
        if ($ch === false) {
            return BackendResult::error('unable to initialize cURL client');
        }
        curl_setopt_array($ch, [
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_CONNECTTIMEOUT => 5,
            CURLOPT_TIMEOUT => 5,
            CURLOPT_FAILONERROR => false,
            CURLOPT_FOLLOWLOCATION => false,
            CURLOPT_HTTPHEADER => $headers,
        ]);
        $body = curl_exec($ch);
        $httpCode = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
        $curlErr = curl_error($ch);
        curl_close($ch);
        if ($body === false || $httpCode === 0) {
            return BackendResult::error($curlErr !== '' ? $curlErr : 'unable to connect to ntopng', ['http_code' => $httpCode]);
        }
        if ($httpCode === 302) {
            return BackendResult::error('ntopng authentication failed', ['http_code' => $httpCode]);
        }
        if ($httpCode >= 400) {
            return BackendResult::error("ntopng returned HTTP error {$httpCode}", ['http_code' => $httpCode]);
        }
        $decoded = json_decode((string)$body, true);
        if (!is_array($decoded)) {
            return BackendResult::error('invalid JSON returned by ntopng', ['http_code' => $httpCode]);
        }
        return $decoded;
    }

    private function baseUrl(): string
    {
        return sprintf('%s://%s:%s/lua/rest/v2/get/', $this->scheme(), $this->host(), $this->port());
    }

    private function scheme(): string
    {
        return strtolower((string)($this->settings['rest_scheme'] ?? 'http')) === 'https' ? 'https' : 'http';
    }

    private function host(): string
    {
        $host = trim((string)($this->settings['rest_host'] ?? ''));
        return $host !== '' ? $host : 'localhost';
    }

    private function port(): string
    {
        $port = trim((string)($this->settings['rest_port'] ?? '3000'));
        return $port !== '' && is_numeric($port) ? $port : '3000';
    }
}

class BackendCore
{
    public function dispatch(array $request): array
    {
        try {
            $action = (string)($request['action'] ?? 'status');
            $settings = is_array($request['settings'] ?? null) ? $request['settings'] : [];
            switch ($action) {
                case 'capabilities':
                    return BackendResult::ok(['capabilities' => (new CapabilityProbe())->probe($settings)]);
                case 'read_rules':
                    return (new RuleStore())->read();
                case 'write_rules':
                    return (new RuleStore())->write(is_array($request['rules'] ?? null) ? $request['rules'] : []);
                case 'api_get':
                    return (new NtopngClient($settings))->get((string)($request['endpoint'] ?? ''), is_array($request['params'] ?? null) ? $request['params'] : []);
                default:
                    return BackendResult::error('unsupported action');
            }
        } catch (\Throwable $e) {
            return BackendResult::error($e->getMessage());
        }
    }
}
