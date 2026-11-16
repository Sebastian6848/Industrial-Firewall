<?php

/*
 * Copyright (C) 2026
 * All rights reserved.
 */

namespace OPNsense\NCLink;

class ProxyController extends \OPNsense\Base\IndexController
{
    public function indexAction()
    {
        $this->view->generalForm = $this->getForm("general");
        $this->view->pick('OPNsense/NCLink/proxy');
    }
}
