<?php

/*
 * Copyright (C) 2026
 * All rights reserved.
 */

namespace OPNsense\NCLink\Api;

use OPNsense\Base\ApiMutableServiceControllerBase;

class ServiceController extends ApiMutableServiceControllerBase
{
    protected static $internalServiceClass = '\OPNsense\NCLink\Proxy';
    protected static $internalServiceTemplate = 'OPNsense/NCLink';
    protected static $internalServiceEnabled = 'general.enabled';
    protected static $internalServiceName = 'nclink';
}
