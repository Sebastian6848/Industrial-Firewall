<?php

namespace OPNsense\IndProto\Api;

use OPNsense\Base\ApiMutableModelControllerBase;
use OPNsense\Base\FieldTypes\PortField;
use OPNsense\Core\Config;
use OPNsense\Firewall\Alias;
use OPNsense\IndProto\Backend\BackendFacade;

class RulesController extends ApiMutableModelControllerBase
{
    protected static $internalModelName = 'indproto';
    protected static $internalModelClass = '\OPNsense\IndProto\IndProto';

    public function searchRuleAction()
    {
        return $this->searchBase(
            "rules.rule",
            array(
                "description",
                "protocol",
                "src_ip",
                "dst_ip",
                "action",
                "access",
                "mqtt_operations",
                "nclink_operations",
                "protocol_operations",
                "enip_services"
            ),
            "description"
        );
    }

    public function getRuleAction($uuid = null)
    {
        return $this->getBase("rule", "rules.rule", $uuid);
    }

    public function addRuleAction()
    {
        return $this->addBase("rule", "rules.rule");
    }

    public function setRuleAction($uuid)
    {
        return $this->setBase("rule", "rules.rule", $uuid);
    }

    public function delRuleAction($uuid)
    {
        return $this->delBase("rules.rule", $uuid);
    }

    public function toggleRuleAction($uuid, $enabled = null)
    {
        return $this->toggleBase("rules.rule", $uuid, $enabled);
    }

    public function listNetworkSelectOptionsAction()
    {
        $networks = [];
        $aliases = [];
        $result = [
            'single' => ['label' => gettext('Single host or Network')],
            'aliases' => ['label' => gettext('Aliases'), 'items' => []],
            'networks' => [
                'label' => gettext('Networks'),
                'items' => ['any' => gettext('any'), '(self)' => gettext('This Firewall')],
            ],
        ];

        foreach ((Config::getInstance()->object())->interfaces->children() as $ifname => $ifdetail) {
            $description = htmlspecialchars(!empty($ifdetail->descr) ? $ifdetail->descr : strtoupper($ifname));
            $networks[$ifname] = sprintf(gettext('%s network'), $description);
            if (!isset($ifdetail->virtual)) {
                $networks["{$ifname}ip"] = sprintf(gettext('%s address'), $description);
            }
        }
        foreach (Alias::getCachedData()['aliases']['alias'] ?? [] as $alias) {
            if (in_array($alias['type'], ['host', 'network'])) {
                $aliases[$alias['name']] = $alias['name'];
            }
        }
        natcasesort($networks);
        natcasesort($aliases);
        $result['networks']['items'] += $networks;
        $result['aliases']['items'] += $aliases;
        return $result;
    }

    public function listPortSelectOptionsAction()
    {
        $aliases = [];
        $result = [
            'single' => ['label' => gettext('Single port or range')],
            'aliases' => ['label' => gettext('Aliases'), 'items' => []],
            'ports' => ['label' => gettext('Ports'), 'items' => ['' => gettext('any')]],
        ];
        foreach (PortField::getWellKnown() as $service => $port) {
            $result['ports']['items'][$service] = sprintf('%s (%s)', strtoupper($service), $port);
        }
        foreach (Alias::getCachedData()['aliases']['alias'] ?? [] as $alias) {
            if ($alias['type'] === 'port') {
                $aliases[$alias['name']] = $alias['name'];
            }
        }
        natcasesort($aliases);
        $result['aliases']['items'] += $aliases;
        return $result;
    }

    public function protocolsAction()
    {
        return (new BackendFacade())->run('capabilities');
    }

    public function applyAction()
    {
        if (!$this->request->isPost()) {
            return array("status" => "error", "message" => "POST required");
        }

        $this->throwReadOnly();
        $backend = new BackendFacade();
        return $backend->run("apply");
    }
}
