# SPDX-License-Identifier: BSD-2-Clause
import re
import sys
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import generate_rules
import log_query
from generators import extended, nclink
from protocols import PROFILES, catalog
from nclink_semantics import classify_topic


def rule(protocol, **kwargs):
    return dict(
        protocol=protocol,
        enabled="1",
        description="扩展协议审核",
        src_ip="any",
        dst_ip="any",
        dst_port=str(PROFILES[protocol]["port"]),
        action="pass",
        access="read",
        _active=True,
        **kwargs
    )


class ExtendedTest(unittest.TestCase):
    def test_catalog_has_eleven_protocols_and_real_command_choices(self):
        self.assertEqual(len(catalog()), 11)
        self.assertEqual(len({p["id"] for p in catalog()}), 11)
        for protocol, profile in PROFILES.items():
            self.assertTrue(profile["limit"])
            self.assertTrue(extended.codes(protocol, rule(protocol)))
            with self.assertRaises(ValueError):
                extended.codes(protocol, rule(protocol, protocol_operations="invalid"))

    def test_no_permission_can_bypass_later_inspection(self):
        for protocol in PROFILES:
            rules = extended.generate_policy(
                protocol, [rule(protocol)], 6000000, "block"
            )
            self.assertTrue(any(line.startswith("alert ") for line in rules))
            self.assertTrue(any(line.startswith("drop ") for line in rules))
            self.assertFalse(any(line.startswith("pass ") for line in rules))

    def test_log_only_is_not_a_permission_in_default_deny(self):
        for protocol in PROFILES:
            entries = extended.generate_policy(
                protocol, [rule(protocol, log_only="1")], 6000000, "block"
            )
            self.assertTrue(any("LOG_ONLY" in line for line in entries))
            self.assertTrue(any(line.startswith("drop ") for line in entries))

    def test_inactive_rules_keep_default_denial(self):
        for protocol in PROFILES:
            item = rule(protocol)
            item["_active"] = False
            entries = extended.generate_policy(protocol, [item], 6000000, "block")
            self.assertTrue(entries)
            self.assertTrue(all(line.startswith("drop ") for line in entries))

    def test_cip_service_permissions_do_not_leak_between_commands(self):
        first = rule("enip", protocol_operations="111", enip_services="14")
        second = rule("enip", protocol_operations="112", enip_services="16")
        entries = extended.generate_policy("enip", [first, second], 6000000, "block")
        self.assertTrue(
            any(
                line.startswith("drop ")
                and "enip_command:111;" in line
                and "cip_service:16;" in line
                for line in entries
            )
        )
        self.assertTrue(
            any(
                line.startswith("drop ")
                and "enip_command:112;" in line
                and "cip_service:14;" in line
                for line in entries
            )
        )

    def test_protocol_logs_classify_raw_tcp_and_udp_alerts(self):
        for protocol in PROFILES:
            self.assertEqual(
                log_query.effective_protocol(
                    {
                        "proto": "TCP",
                        "alert": {
                            "signature": "IndProto " + protocol + " default BLOCK"
                        },
                    }
                ),
                protocol,
            )

    def test_extended_xml_compiles_with_unique_ids(self):
        root = ET.fromstring(
            "<IndProto><general><default_action>block</default_action></general><rules/></IndProto>"
        )
        for protocol in PROFILES:
            node = ET.SubElement(root.find("rules"), "rule")
            for key, value in rule(protocol).items():
                if key != "_active":
                    ET.SubElement(node, key).text = value
        entries, protocols, _ = generate_rules.render_rules(root)
        self.assertEqual(protocols, set(PROFILES))
        self.assertEqual(
            len(generate_rules.validate_unique_sids(entries)), len(entries)
        )


class NCLinkExtensionTest(unittest.TestCase):
    def test_full_topic_preserves_device_endpoint_and_direction(self):
        for topic, op, direction in [
            ("Query/Request/machine/app", "data_query", "request"),
            ("Query/Response/machine/app", "data_query", "response"),
            ("Sample/machine/channel", "sample", "publish"),
            ("Method/Call/machine/app", "method_call", "request"),
            ("Event/machine/app", "event", "publish"),
        ]:
            result = classify_topic(topic)
            self.assertEqual(result["nclink_operation"], op)
            self.assertEqual(result["nclink_direction"], direction)
            self.assertEqual(result["nclink_device_uuid"], "machine")
            self.assertEqual(result["nclink_endpoint"], topic.split("/")[-1])

    def test_endpoint_must_not_escape_its_device(self):
        with self.assertRaises(ValueError):
            nclink.patterns({"nclink_operations": "sample", "nclink_endpoint": "app"})
        with self.assertRaises(ValueError):
            nclink.patterns({"nclink_device_uuid": "machine/#"})

    def test_directions_and_topic_subscriptions_do_not_allow_wildcards(self):
        data = {
            "nclink_operations": "data_query",
            "nclink_device_uuid": "machine",
            "nclink_endpoint": "app",
            "nclink_direction": "request",
            "nclink_packets": "both",
        }
        patterns = [item[3] for item in nclink.patterns(data)]
        self.assertTrue(
            any(
                re.fullmatch(pattern, "Query/Request/machine/app")
                for pattern in patterns
            )
        )
        for value in [
            "Query/Response/machine/app",
            "Query/Request/machine/other",
            "Query/Request/+/+",
            "Query/Request/machine/app/extra",
        ]:
            self.assertFalse(any(re.fullmatch(pattern, value) for pattern in patterns))
        self.assertEqual(nclink.packet_types(data), ("PUBLISH", "SUBSCRIBE"))

    def test_invalid_response_is_not_parsed_as_version_request(self):
        self.assertEqual(classify_topic("Probe/Version/Response"), {})
        patterns = [
            p[3] for p in nclink.patterns({"nclink_operations": "version_probe"})
        ]
        self.assertFalse(
            any(re.fullmatch(p, "Probe/Version/Response/machine") for p in patterns)
        )


if __name__ == "__main__":
    unittest.main()
