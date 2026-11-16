<?php

namespace OPNsense\IndProto;

use OPNsense\Base\BaseModel;
use OPNsense\Base\Messages\Message;

class IndProto extends BaseModel
{
    public function performValidation($validateFullModel = false)
    {
        $messages = parent::performValidation($validateFullModel);
        foreach ($this->rules->rule->iterateItems() as $id => $rule) {
            if ((string)$rule->protocol !== 'nclink') {
                continue;
            }
            if (strlen((string)$rule->nclink_topic_root) > 255) {
                $messages->appendMessage(new Message(gettext('主题根前缀最多为 255 字节。'), 'rules.rule.' . $id . '.nclink_topic_root'));
            }
            $filters = trim((string)$rule->nclink_subscribe_filters);
            if ($filters === '') {
                continue;
            }
            $field = 'rules.rule.' . $id . '.nclink_subscribe_filters';
            if ((string)$rule->nclink_packets === 'publish') {
                $messages->appendMessage(new Message(gettext('额外订阅过滤器需要选择订阅或发布与订阅。'), $field));
            }
            foreach (explode(',', $filters) as $filter) {
                $filter = trim($filter);
                if ($filter === '' || strlen($filter) > 255 || str_starts_with($filter, '$share/')) {
                    $messages->appendMessage(new Message(gettext('请输入有效的订阅过滤器，不支持共享订阅。'), $field));
                    break;
                }
                $parts = explode('/', $filter);
                foreach ($parts as $index => $part) {
                    if (
                        $part === '' || (str_contains($part, '+') && $part !== '+') ||
                        (str_contains($part, '#') && ($part !== '#' || $index !== count($parts) - 1))
                    ) {
                        $messages->appendMessage(new Message(gettext('订阅通配符必须独占路径段，井号只能位于末尾。'), $field));
                        break 2;
                    }
                }
                if (
                    ((string)$rule->nclink_device_uuid !== '' || (string)$rule->nclink_endpoint !== '')
                ) {
                    $messages->appendMessage(new Message(gettext('额外订阅过滤器须单独建规则并留空设备与通道条件。'), $field));
                    break;
                }
            }
        }
        return $messages;
    }
}
