<?php
// SPDX-License-Identifier: BSD-2-Clause
namespace OPNsense\AppIdentification;

/** Offline domain catalog. Ambiguous equal-specificity matches remain unknown. */
class Catalog
{
    private static ?array $catalog = null;
    private static array $suffix = [];
    private static array $exact = [];
    private static array $names = [];

    public static function load(?string $path = null): array
    {
        if (self::$catalog === null || $path !== null) {
            $path = $path ?? '/usr/local/opnsense/data/appidentification/catalog.json';
            $data = is_file($path) ? json_decode(file_get_contents($path), true) : null;
            self::$catalog = is_array($data) && ($data['schema'] ?? 0) === 1 ? $data : ['applications' => []];
            self::$suffix = self::$exact = self::$names = [];
            foreach (self::$catalog['applications'] as $app) {
                self::$names[$app['id']] = $app['name'];
                foreach ($app['domains'] as $domain) {
                    if ($domain['mode'] === 'exact') {
                        self::$exact[$domain['value']][$app['id']] = true;
                    } else {
                        self::$suffix[$domain['value']][$app['id']] = true;
                    }
                }
            }
        }
        return self::$catalog;
    }

    public static function identify(string $host): ?array
    {
        self::load();
        $host = strtolower(trim($host));
        if (strpos($host, '://') !== false) {
            $host = (string)parse_url($host, PHP_URL_HOST);
        } elseif (substr_count($host, ':') === 1) {
            $host = explode(':', $host, 2)[0];
        }
        $host = rtrim($host, '.');
        if ($host === '' || filter_var($host, FILTER_VALIDATE_IP) || !preg_match('/^[a-z0-9.-]+$/D', $host)) {
            return null;
        }
        $parts = explode('.', $host);
        foreach ($parts as $offset => $_) {
            $domain = implode('.', array_slice($parts, $offset));
            $matches = self::$suffix[$domain] ?? [];
            if ($offset === 0) {
                $matches += self::$exact[$domain] ?? [];
            }
            if (count($matches) > 1) {
                return null;
            }
            if (count($matches) === 1) {
                $id = (string)array_key_first($matches);
                return ['id' => $id, 'name' => self::$names[$id], 'source' => 'domain_catalog', 'matched_domain' => $domain];
            }
        }
        return null;
    }
}
