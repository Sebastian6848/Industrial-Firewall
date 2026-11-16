# App Identification

The plugin includes an offline catalog of 1418 named application/service domain
lists. The source commit and MIT license accompany `catalog.json`. The catalog
does not count individual domains as applications and does not decrypt TLS.
User-defined flow rules retain priority over the catalog and nDPI fallback.
Equal-specificity catalog conflicts remain unidentified.

Rebuild the catalog from a pinned v2fly/domain-list-community checkout with
`python3 tools/build_catalog.py SOURCE_CHECKOUT src/opnsense/data/appidentification/catalog.json`.
Run `php tests/catalog_test.php` to check every catalog entry is independently
reachable and domain lookalikes do not match. `php tests/domain_match_test.php`
checks the existing custom rule behavior.

This OPNsense plugin presents ntopng flow and Layer-7 application data in a
native dashboard and manages custom application identification rules.

## Component boundary

- `os-ntopng` owns ntopng installation, configuration, Redis integration and
  service lifecycle.
- `os-app-identification` consumes the ntopng REST API. Dashboard custom rules
  are persisted in the AppIdentification configuration and take effect on the
  next flow query, without restarting ntopng.
- The separate advanced nDPI protocol-file editor manages
  `/var/db/ntopng/protos.txt`; changes to that file require the `ntopng restart`
  configd action provided by `os-ntopng`.

The plugin must not generate ntopng or Redis configuration files, register the
ntopng service, or invoke its rc script directly.

## Configuration

The App Identification model contains only REST connection/authentication
settings, the ntopng interface ID used by API calls, and custom rules. Configure
capture interfaces and service ports in the separate ntopng plugin.

## Main code

- `Api/GeneralController.php`: REST connection settings and health checks.
- `Api/FlowsController.php`: active flow queries and response normalization.
- `Api/ApplicationsController.php`: L7 statistics and custom rule application.
- `Backend/BackendCore.php`: privileged REST requests and `protos.txt` access.
- `Backend/BackendFacade.php`: configd bridge, including calls to `os-ntopng`.

## 自定义与批量导入规则

“应用识别 → 应用与识别库”中的“应用识别规则”统一列出内置与自定义规则，
支持按来源筛选、按名称或匹配条件搜索。内置项可查看全部域名与匹配范围，
自定义项可在同一张表中新增、批量导入、编辑、启停、删除及导出。
支持域名、IP 地址、网段、端口和应用协议，匹配内容每行一个，同行规则中
任一值匹配即可。自定义规则优先于内置域名库；域名规则按实际命中值的精度选择，精度相同时保留配置中靠前的规则；同一规则中未命中的更长域名不会提高优先级。
这些规则用于流量分类，不代表自动生成防火墙阻断策略或解密 TLS。

批量导入支持 JSON、CSV 文件及粘贴文本，选取文件后自动选择格式。
提交前由服务端校验并显示总数、待导入数、重复数和前五条预览，并可展开查看被跳过的名称与保留名称；预览不保存。
默认“追加”会跳过相同匹配方式与匹配值的规则，值的大小写、顺序及重复行
不影响重复判断，已有规则的名称与启用状态保持不变。更新已有规则请编辑，
或备份后使用“替换自定义规则”（需要再次确认）。导入与导出只针对自定义规则，
内置项随插件维护。任一记录无效时整个导入不保存。
每次最多 5000 条，保存后的规则总数最多 5000 条，输入最多 5 MiB。

JSON 使用对象数组，字段为 `enabled`、`description`、`match_type`、
`match_value`、`app_label`；CSV 使用相同字段作为首行表头。
`enabled` 为 `1` 或 `0`，`match_type` 为 `domain`、`ip`、`cidr`、
`port` 或 `protocol`，`app_label` 为应用名称。JSON 的 `match_value`
支持换行分隔字符串或字符串数组；CSV 多行字段需要双引号包围。
页面提供模板和 JSON/CSV 导出，可直接作为再次导入的数据。

示例：

```json
[
  {
    "enabled": "1",
    "description": "企业协作应用",
    "match_type": "domain",
    "match_value": ["work.weixin.qq.com", "wecom.qq.com"],
    "app_label": "企业微信"
  }
]
```

Run `php tests/import_payload_test.php /path/to/core` on the review VM to check
native request compatibility, malformed input and multiline CSV round trips.
