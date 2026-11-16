<?php
// SPDX-License-Identifier: BSD-2-Clause
namespace OPNsense\AppIdentification\Api;

use OPNsense\AppIdentification\Catalog;
use OPNsense\Base\ApiControllerBase;

class CatalogController extends ApiControllerBase
{
    public function searchAction(): array
    {
        $catalog = Catalog::load();
        $needle = strtolower(trim((string)$this->request->get('search', null, '')));
        $offset = max(0, (int)$this->request->get('offset', 'int', 0));
        $rows = array_values(array_filter($catalog['applications'], static function ($app) use ($needle) {
            return $needle === '' || strpos(strtolower($app['id'] . ' ' . $app['name']), $needle) !== false;
        }));
        return ['status' => 'ok', 'catalog_count' => count($catalog['applications']), 'total' => count($rows),
                'source' => $catalog['source'] ?? [], 'rows' => array_slice($rows, $offset, 50),
                'scope' => 'Domain-based application/service signatures; encrypted content is not decrypted'];
    }
}
