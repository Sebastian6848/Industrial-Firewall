<?php

/*
 * Copyright (C) 2026
 * All rights reserved.
 */

namespace OPNsense\NCLink;

use OPNsense\Base\BaseModel;
use OPNsense\Base\Messages\Message;

class Proxy extends BaseModel
{
    public function performValidation($validateFullModel = false)
    {
        $messages = parent::performValidation($validateFullModel);

        if ($this->general->enabled->isEqual('1')) {
            if ($this->general->target_host->isEmpty()) {
                $messages->appendMessage(new Message(
                    gettext('A target MQTT broker is required when the NC-Link proxy is enabled.'),
                    'general.target_host'
                ));
            }
            if (
                (string)$this->general->listen_host === (string)$this->general->target_host &&
                (string)$this->general->listen_port === (string)$this->general->target_port
            ) {
                $messages->appendMessage(new Message(
                    gettext('The listener and target broker cannot use the same address and port.'),
                    'general.target_port'
                ));
            }
        }

        return $messages;
    }
}
