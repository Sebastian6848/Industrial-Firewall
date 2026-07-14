# Plugin-only repository policy

This core tree uses the official signed OPNsense package repository for plugin discovery and installation while keeping normal system updates disabled.

## Effective policy

- The OPNsense repository is enabled with its official fingerprint verification.
- The web API accepts install, reinstall, remove, lock, and unlock operations only for package names beginning with `os-`.
- The Plugins page lists remote official plugins and locally installed plugins.
- Firmware check, package update, major upgrade, changelog download, automatic update, and console-triggered update actions remain disabled.
- The upstream pre-install check that required the local core package to match the newest repository core version is intentionally omitted.
- pkg signature, package ABI, dependency, and conflict validation remains active and must not be bypassed.

Installing a plugin can also install or update packages required by that plugin. Review the pkg transaction output before using the same procedure on a production firewall. A plugin built for a different FreeBSD ABI or a materially newer OPNsense release is not made compatible by skipping the core version gate.

## Maintained plugin source repository

The maintained source repository is checked out at `/home/sebastian/plugins`:

```text
origin    https://gitee.com/xwy6848/plugins.git
upstream  https://github.com/opnsense/plugins.git
```

The source workflow remains available for plugins that are not compatible with the frozen binary repository:

```sh
cd /home/sebastian/plugins/<category>/<plugin>
make package
pkg add /path/to/os-example.pkg
```

Local packages must still target the firewall's FreeBSD ABI and have compatible dependencies.

## Runtime verification

After installing this core build on a test firewall:

```sh
configctl firmware reload
service configd restart
pkg update
pkg rquery '%n-%v' 'os-*'
```

Use the Plugins page for normal installation. System update and upgrade endpoints should continue to report that updates are disabled.
