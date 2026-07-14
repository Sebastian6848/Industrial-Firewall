# NC-Link decoder and observer proxy

This directory contains an independent MQTT/NC-Link decoder. It can be used by
plugins, diagnostics, or a transparent observer proxy without depending on
Suricata.

## Decode raw MQTT packets

```
/usr/local/opnsense/scripts/nclink/decode.py --hex 100f00044d5154540402003c00036e632d
```

Input may also be supplied with `--base64`, `--file`, or stdin.

## Transparent observer proxy

```
/usr/local/opnsense/scripts/nclink/proxy.py \
  --listen-host 127.0.0.1 \
  --listen-port 11883 \
  --target-host 192.0.2.10 \
  --target-port 1883 \
  --log-file /var/log/nclink-proxy.log
```

The proxy forwards MQTT traffic unchanged and writes decoded JSON lines for
CONNECT, PUBLISH, SUBSCRIBE, and UNSUBSCRIBE packets. It marks NC-Link traffic
when topics, client IDs, or payloads contain NC-Link markers such as
`NC-Link`, `REGMSG`, `REMSG`, `PRK`, or `SPSK`.

Standard NC-Link interface topics are detected without requiring an explicit
`nclink` marker. Supported families include:

* `Register/Request` and `Register/Response/...`
* `Discovery/Request/...` and `Discovery/Response/...`
* `Probe/Version/...`, `Probe/Query/...`, and `Probe/Set/...`
* `Query/Request/...`, `Query/Response/...`, `Set/Request/...`, and `Set/Response/...`
* `Sample/...`, `Notify/State/...`, `Method/...`, and `Event/...`
* dynamic sample and event registration/unregistration topics

The observer decodes plaintext MQTT. MQTT over TLS can be forwarded, but its
application payload cannot be inspected unless TLS is terminated before the
observer.

## Business semantic extraction

Decoded records include `nclink_semantics` when an NC-Link payload can be
interpreted. The semantic extractor preserves raw MQTT details and adds a
normalized business view:

* message families: `REGMSG`, `REMSG`, `PRK`, and `SPSK`
* message class: registration, resource, process, or sample
* identities: device, machine, CNC, gateway, line, and workshop IDs
* timestamps, message sequences, commands, and state fields
* structured data points with name, value, unit, quality, and timestamp
* alarms, faults, and warnings

Unknown JSON payload members are not discarded; they remain available in the
original decoded payload and in message bodies under `nclink_semantics`.

The proxy limits an incomplete observer buffer to 4 MiB so malformed or very
large MQTT frames cannot grow memory without bound. Forwarding continues when
the observer drops such a buffer. JSON logs rotate at 10 MiB and retain five
backups.
