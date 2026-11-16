<?php

/*
 * Copyright (C) 2026
 * All rights reserved.
 */

namespace OPNsense\NCLink\Api;

use OPNsense\Base\ApiControllerBase;
use OPNsense\Core\Backend;
use OPNsense\NCLink\Proxy;

class LogController extends ApiControllerBase
{
    private const LOG_MODULE = 'core';

    public function searchAction()
    {
        $response = [
            'rows' => [],
            'rowCount' => 0,
            'total' => 0,
            'current' => 1
        ];

        if (!$this->request->isPost()) {
            return $response;
        }

        $itemsPerPage = $this->request->getPost('rowCount', 'int', 50);
        $itemsPerPage = min($itemsPerPage == -1 ? 5000 : $itemsPerPage, 9999);
        if ($itemsPerPage < 1) {
            $itemsPerPage = 50;
        }
        $currentPage = max($this->request->getPost('current', 'int', 1), 1);
        $searchPhrase = $this->request->get('searchPhrase', null, '');
        $logPath = (string)(new Proxy())->general->log_file;
        $logFilename = pathinfo($logPath ?: '/var/log/nclink-proxy.log', PATHINFO_FILENAME);

        $backend = new Backend();
        $result = json_decode((string)$backend->configdpRun('system diag log', [
            $itemsPerPage,
            ($currentPage - 1) * $itemsPerPage,
            $searchPhrase,
            self::LOG_MODULE,
            $logFilename,
            '',
            0
        ]), true);

        if (is_array($result)) {
            foreach ($result['rows'] ?? [] as $row) {
                $response['rows'][] = $this->formatRow($row);
            }
            $response['rowCount'] = count($response['rows']);
            $response['total'] = $result['total_rows'] ?? 0;
            $response['current'] = $currentPage;
        }

        return $response;
    }

    private function formatRow(array $row): array
    {
        $line = $row['line'] ?? '';
        $row['level'] = $row['severity'] ?? '';
        $row['event'] = '';
        $row['direction'] = '';
        $row['peer'] = '';
        $row['message'] = $line;
        $row['details'] = $line;

        $decoded = json_decode($line, true);
        if (is_array($decoded)) {
            if (!empty($decoded['timestamp']) && is_numeric($decoded['timestamp'])) {
                $row['timestamp'] = date('Y-m-d H:i:s', (int)$decoded['timestamp']);
            }
            $row['level'] = !empty($decoded['level']) ? ucfirst($decoded['level']) : '';
            $row['event'] = $decoded['event'] ?? ($decoded['packet_type'] ?? '');
            $row['direction'] = $decoded['direction'] ?? '';
            $row['peer'] = $decoded['peer'] ?? '';
            $row['message'] = $decoded['message'] ?? $this->packetSummary($decoded);
            $row['details'] = json_encode($decoded, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
        }

        return $row;
    }

    private function packetSummary(array $record): string
    {
        if (!empty($record['decode_error'])) {
            return $record['decode_error'];
        }

        $parts = [];
        if (!empty($record['packet_type'])) {
            $parts[] = $record['packet_type'];
        }
        if (!empty($record['topic'])) {
            $parts[] = $record['topic'];
        }
        if (!empty($record['client_id'])) {
            $parts[] = sprintf('client_id=%s', $record['client_id']);
        }
        if (!empty($record['nclink_detected'])) {
            $parts[] = 'NC-Link detected';
        }

        return !empty($parts) ? implode(' | ', $parts) : json_encode($record, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    }
}
