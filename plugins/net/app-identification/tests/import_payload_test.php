<?php
// SPDX-License-Identifier: BSD-2-Clause
// Run with PHP and the matching core checkout path as the first argument.
namespace OPNsense\Base {
    class ApiMutableModelControllerBase
    {
        public object $request;
    }
}

namespace {
    $core = $argv[1] ?? dirname(__DIR__, 4) . '/core';
    require $core . '/src/opnsense/mvc/app/library/OPNsense/Mvc/Request.php';
    require __DIR__ . '/../src/opnsense/mvc/app/controllers/OPNsense/AppIdentification/Api/RuleController.php';

    set_error_handler(function ($level, $message, $file, $line) {
        throw new \ErrorException($message, 0, $level, $file, $line);
    });
    function check(bool $condition, string $message): void
    {
        if (!$condition) {
            throw new \RuntimeException($message);
        }
    }

    $_SERVER['REQUEST_METHOD'] = 'POST';
    $_POST = ['format' => 'csv', 'mode' => 'append'];
    $_FILES = [];
    $controller = new \OPNsense\AppIdentification\Api\RuleController();
    $controller->request = new \OPNsense\Mvc\Request();
    $result = $controller->importAction();
    check($result['status'] === 'error' && $result['message'] === 'Import data is empty.',
        'Empty import must return a validation response with the native MVC Request');

    // A client cannot select a readable server file by supplying a temporary path.
    $_FILES = ['file' => ['error' => UPLOAD_ERR_OK, 'tmp_name' => __FILE__]];
    check($controller->importAction()['message'] === 'Import data is empty.',
        'Non-uploaded server files must not be read');
    $_FILES = ['file' => ['error' => [UPLOAD_ERR_OK], 'tmp_name' => [__FILE__]]];
    check($controller->importAction()['message'] === 'Import data is empty.',
        'Array upload fields must not trigger a PHP error');

    $parse = new \ReflectionMethod($controller, 'parseCsvPayload');
    $csv = "description,match_type,match_value,app_label\n" .
        '"quoted ""name"", path \\ test",domain,example.invalid,Example' . "\n";
    $result = $parse->invoke($controller, $csv);
    check($result['errors'] === [] && count($result['rows']) === 1, 'Valid CSV must parse');
    check($result['rows'][0]['description'] === 'quoted "name", path \\ test',
        'CSV quoting and literal backslashes must survive parsing without warnings');

    $parseJson = new \ReflectionMethod($controller, 'parseJsonPayload');
    $validate = new \ReflectionMethod($controller, 'validateImportRows');
    foreach (['{"match_type":"domain"}', '[false]', '[[]]', '[{"match_value":[{"nested":"value"}]}]'] as $invalid) {
        check(!empty($parseJson->invoke($controller, $invalid)['errors']), 'Malformed JSON rule shapes must fail without PHP warnings');
    }
    $parsed = $parseJson->invoke($controller, json_encode([
        ['enabled' => false, 'description' => '含中文的规则', 'match_type' => 'domain',
         'match_value' => ['example.invalid', 'cdn.example.invalid'], 'app_label' => '测试应用']
    ]));
    $valid = $validate->invoke($controller, $parsed['rows']);
    check($valid['errors'] === [] && $valid['rows'][0]['enabled'] === '0', 'Boolean false stays disabled');
    check($valid['rows'][0]['match_value'] === "example.invalid\ncdn.example.invalid", 'JSON match arrays preserve each domain');
    foreach ([['match_type'=>'ip','match_value'=>'999.1.1.1','app_label'=>'x'],
              ['match_type'=>'cidr','match_value'=>'192.0.2.1/99','app_label'=>'x'],
              ['match_type'=>'port','match_value'=>'65536','app_label'=>'x'],
              ['match_type'=>'domain','match_value'=>'example.invalid','app_label'=>['nested']]] as $invalid) {
        check(!empty($validate->invoke($controller, [$invalid])['errors']), 'Invalid rule values must fail validation');
    }
    $key = new \ReflectionMethod($controller, 'ruleKey');
    check($key->invoke($controller, ['match_type'=>'domain','match_value'=>"a.invalid\nb.invalid"]) ===
          $key->invoke($controller, ['match_type'=>'domain','match_value'=>"B.INVALID\na.invalid\na.invalid"]),
          'Deduplication is independent of alternative ordering, duplicates and case');
    $parsed = $parse->invoke($controller, "match_type,match_value,app_label\ndomain,\"a.invalid\nb.invalid\",\"中文,标签\"\n");
    check(count($parsed['rows']) === 1 && $parsed['rows'][0]['app_label'] === '中文,标签', 'Native CSV parser supports quoted multiline values');
    echo "PASS: native Request import handling and CSV regression checks\n";
}
