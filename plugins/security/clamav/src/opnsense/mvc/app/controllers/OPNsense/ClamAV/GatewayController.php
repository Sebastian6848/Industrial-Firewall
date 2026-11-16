<?php
// SPDX-License-Identifier: BSD-2-Clause
namespace OPNsense\ClamAV;
class GatewayController extends \OPNsense\Base\IndexController
{
    public function indexAction()
    {
        $this->view->pick('OPNsense/ClamAV/gateway');
    }
}
