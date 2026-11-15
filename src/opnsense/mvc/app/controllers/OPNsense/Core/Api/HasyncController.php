<?php

/*
 * Copyright (c) 2024 Deciso B.V.
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

/**
 * Class HasyncController
 * @package OPNsense\Core
 */
class HasyncController extends ApiMutableModelControllerBase
{
    protected static $internalModelName = 'hasync';
    protected static $internalModelClass = 'OPNsense\Core\Hasync';

    public function getAction()
    {
        $result = parent::getAction();
        $labels = [
            'Aliases' => '地址与端口别名',
            'Authentication Servers' => '认证服务器',
            'Captive Portal' => '认证门户',
            'Certificates and Authorities' => '证书与证书机构',
            'Cron' => '定时任务',
            'DHCRelay' => 'DHCP 中继',
            'Dnsmasq DNS/DHCP' => 'DNS 与 DHCP 服务',
            'Firewall Categories' => '防火墙分类',
            'Firewall Groups' => '防火墙组',
            'Firewall Log Templates' => '防火墙日志模板',
            'Firewall Rules' => '防火墙规则',
            'Firewall Schedules' => '防火墙时间计划',
            'Host discovery service' => '主机发现服务',
            'Industrial isolation policies' => '工业隔离策略',
            'Industrial protocol policies' => '工业协议策略',
            'Intrusion Detection' => '入侵检测',
            'Monit System Monitoring' => '系统监控',
            'Netflow / Insight' => '流量统计与分析',
            'Network Time' => '网络时间',
            'Router Advertisements' => '路由通告',
            'Shaper' => '流量整形',
            'Squid Web Proxy' => 'Web 代理',
            'Static Routes' => '静态路由',
            'System logging' => '系统日志',
            'System Tunables' => '系统调优参数',
            'Users and Groups' => '用户与用户组',
            'Virtual IPs' => '虚拟地址',
            'Web GUI' => '管理界面',
        ];
        foreach ($result['hasync']['syncitems'] ?? [] as $key => $option) {
            if (isset($option['value'])) {
                $result['hasync']['syncitems'][$key]['value'] = $labels[$option['value']] ?? gettext($option['value']);
            }
        }
        return $result;
    }

    public function reconfigureAction()
    {
        $result = ["status" => "failed"];
        if ($this->request->isPost()) {
            $result['status'] = strtolower(trim((new Backend())->configdRun('interface pfsync configure')));
        }
        return $result;
    }
}
