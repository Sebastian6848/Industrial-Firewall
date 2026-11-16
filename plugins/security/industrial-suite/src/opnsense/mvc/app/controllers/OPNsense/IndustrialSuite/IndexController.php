<?php
// SPDX-License-Identifier: BSD-2-Clause
namespace OPNsense\IndustrialSuite;
class IndexController extends \OPNsense\Base\IndexController
{
    public function indexAction()
    {
        $this->view->pick('OPNsense/IndustrialSuite/index');
        $this->view->general = $this->getForm('general');
        foreach (['group', 'rule', 'node'] as $name) {
            $this->view->$name = $this->getForm($name);
            $grid = $name . 'Grid';
            $this->view->$grid = $this->getFormGrid($name);
        }
    }
}
