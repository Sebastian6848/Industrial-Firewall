<?php

/*
 * Copyright (C) 2026
 * All rights reserved.
 */

namespace OPNsense\NCLink\Api;

use OPNsense\Base\ApiMutableModelControllerBase;

class SettingsController extends ApiMutableModelControllerBase
{
    protected static $internalModelName = 'nclink';
    protected static $internalModelClass = '\OPNsense\NCLink\Proxy';
}
