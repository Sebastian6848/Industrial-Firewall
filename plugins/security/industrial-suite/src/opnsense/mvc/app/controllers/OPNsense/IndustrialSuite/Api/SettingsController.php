<?php
// SPDX-License-Identifier: BSD-2-Clause
namespace OPNsense\IndustrialSuite\Api;

use OPNsense\Base\ApiMutableModelControllerBase;

class SettingsController extends ApiMutableModelControllerBase
{
    protected static $internalModelName = 'suite';
    protected static $internalModelClass = '\OPNsense\IndustrialSuite\IndustrialSuite';

    public function getAction()
    {
        return ['suite' => ['integrity' => $this->getModel()->integrity->getNodes(),
                            'isolation' => ['enabled' => (string)$this->getModel()->isolation->enabled,
                                            'management' => (string)$this->getModel()->isolation->management]]];
    }

    public function setAction()
    {
        if (!$this->request->isPost()) {
            return ['result' => 'failed'];
        }
        $data = $this->request->getPost('suite', null, []);
        foreach (['integrity' => ['enabled', 'files'], 'isolation' => ['enabled', 'management']] as $area => $fields) {
            foreach ($fields as $field) {
                if (isset($data[$area][$field]) && is_scalar($data[$area][$field])) {
                    $this->getModel()->$area->$field = (string)$data[$area][$field];
                }
            }
        }
        return $this->save();
    }

    public function searchGroupAction() { return $this->searchBase('isolation.groups.group', ['name', 'members'], 'name'); }
    public function getGroupAction($uuid = null) { return $this->getBase('group', 'isolation.groups.group', $uuid); }
    public function addGroupAction() { return $this->addBase('group', 'isolation.groups.group'); }
    public function setGroupAction($uuid) { return $this->setBase('group', 'isolation.groups.group', $uuid); }
    public function delGroupAction($uuid) { return $this->delBase('isolation.groups.group', $uuid); }
    public function toggleGroupAction($uuid) { return $this->toggleBase('isolation.groups.group', $uuid); }
    public function searchRuleAction() { return $this->searchBase('isolation.rules.rule', ['description', 'source', 'destination', 'protocol', 'ports', 'action'], 'description'); }
    public function getRuleAction($uuid = null) { return $this->getBase('rule', 'isolation.rules.rule', $uuid); }
    public function addRuleAction() { return $this->addBase('rule', 'isolation.rules.rule'); }
    public function setRuleAction($uuid) { return $this->setBase('rule', 'isolation.rules.rule', $uuid); }
    public function delRuleAction($uuid) { return $this->delBase('isolation.rules.rule', $uuid); }
    public function toggleRuleAction($uuid) { return $this->toggleBase('isolation.rules.rule', $uuid); }
    public function searchNodeAction() { return $this->searchBase('nodes.node', ['name', 'url', 'verify_tls'], 'name'); }
    public function getNodeAction($uuid = null) { return $this->getBase('node', 'nodes.node', $uuid); }
    public function addNodeAction() { return $this->addBase('node', 'nodes.node'); }
    public function setNodeAction($uuid) { return $this->setBase('node', 'nodes.node', $uuid); }
    public function delNodeAction($uuid) { return $this->delBase('nodes.node', $uuid); }
    public function toggleNodeAction($uuid) { return $this->toggleBase('nodes.node', $uuid); }
}
