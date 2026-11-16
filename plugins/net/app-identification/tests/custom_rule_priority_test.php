<?php
// SPDX-License-Identifier: BSD-2-Clause
namespace OPNsense\AppIdentification\Api {
    class GeneralController {}
}
namespace {
    require __DIR__ . '/../src/opnsense/mvc/app/controllers/OPNsense/AppIdentification/Api/ApplicationsController.php';
    $class = new \ReflectionClass(\OPNsense\AppIdentification\Api\ApplicationsController::class);
    $controller = $class->newInstanceWithoutConstructor();
    $match = $class->getMethod('matchFlowRule');
    $rules = [
        ['match_type'=>'domain', 'match_value'=>"qq.com\nvery.deep.unrelated.example.invalid", 'app_label'=>'Broad'],
        ['match_type'=>'domain', 'match_value'=>"work.weixin.qq.com\nwecom.qq.com", 'app_label'=>'Specific'],
        ['match_type'=>'domain', 'match_value'=>"work.weixin.qq.com\nother.invalid", 'app_label'=>'Later tie'],
        ['match_type'=>'port', 'match_value'=>'443', 'app_label'=>'Port fallback']
    ];
    foreach (['work.weixin.qq.com'=>'Specific', 'sub.work.weixin.qq.com'=>'Specific',
              'wecom.qq.com'=>'Specific', 'other.qq.com'=>'Broad',
              'notqq.com'=>'Port fallback', 'qq.com.attacker.invalid'=>'Port fallback'] as $host=>$expected) {
        $flow = ['server'=>['name'=>$host, 'port'=>443]];
        $result = $match->invoke($controller, $flow, $rules);
        if (($result['app_label'] ?? null) !== $expected) {
            throw new \RuntimeException('Wrong rule for ' . $host);
        }
    }
    echo "PASS: actual classifier selects the matched domain, preserves equal-priority order and port fallback\n";
}
