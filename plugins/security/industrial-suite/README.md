# Industrial Suite

Source-available OPNsense plugin providing software integrity monitoring,
gateway microsegmentation and a basic API-driven fleet manager. See the core
repository's `docs/FEATURE_REVIEW.md` for the Chinese operator guide and current
acceptance boundaries.

The plugin is disabled for integrity and isolation until configured. New
network groups do not alter PF until an administrator applies the policy.
Explicit denies precede permissions; default denials apply only between
managed networks. Management exceptions target the firewall itself. Existing
PF states are not globally flushed. Applied records survive reboot; drafts
are kept separately in OPNsense configuration. The original manual rules are
not modified.

Integrity baselines are explicit, never automatically created by the monitor.
The monitor checks every five minutes when enabled. Baselines, last results
and bounded audit logs reside under root-only `/var/db/industrial-suite/`.
They have no hardware trust anchor.

The manager talks to HTTPS `/api/industrialsuite/agent/{status,logs,preview,deploy}`
with a dedicated `api-industrial-agent` ACL and OPNsense API Key/Secret.
Credentials are stored in the device's protected configuration and are not
included in distributed isolation policies. Environment HTTP proxies and
HTTP redirects are bypassed. Certificate verification defaults to enabled.
One node failing does not suppress results from other nodes.

The `page-industrial-suite` ACL governs administration and cannot be granted
to receiver accounts. Receivers can only replace project isolation settings.
The core's XMLRPC plugin notification hook is required for HA policy
materialization; monitor settings, baselines and manager credentials are not
synchronized.

Run unit tests on Ubuntu:

```sh
python3 -m unittest discover -s security/industrial-suite/tests
```

On a dedicated FreeBSD review node with the documented sample matrix applied:

```sh
sh security/industrial-suite/tests/vnet_isolation.sh
```

This creates and removes temporary VNET jails, not physical NICs. It verifies
permitted TCP/502 connectivity and actual TCP/503 blocking. No ISO is produced.
