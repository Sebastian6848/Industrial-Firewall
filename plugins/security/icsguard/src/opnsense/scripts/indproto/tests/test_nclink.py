import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

import generate_rules
from generators import nclink


def nclink_config(operations="data_set", device_uuid="", action="block", default_action="pass"):
    return ET.fromstring(
        "<IndProto><general><enabled>1</enabled><default_action>%s</default_action></general>"
        "<rules><rule><enabled>1</enabled><description>nclink_test</description>"
        "<protocol>nclink</protocol><src_ip>any</src_ip><dst_ip>any</dst_ip>"
        "<dst_port>1883</dst_port><action>%s</action><log_only>0</log_only>"
        "<nclink_operations>%s</nclink_operations>"
        "<nclink_device_uuid>%s</nclink_device_uuid>"
        "</rule></rules></IndProto>" % (default_action, action, operations, device_uuid)
    )


class NCLinkGeneratorTest(unittest.TestCase):
    def test_data_set_block_uses_mqtt_publish_topic(self):
        rules, protocols, _ = generate_rules.render_rules(
            nclink_config(device_uuid="machine-01")
        )

        self.assertEqual(protocols, {"nclink"})
        self.assertEqual(len(rules), 2)
        self.assertIn("mqtt.type:PUBLISH", rules[0])
        self.assertIn("mqtt.publish.topic", rules[0])
        self.assertIn("BLOCK NC-LINK DATA_SET", rules[0])
        self.assertNotIn("mqtt.type:CONNECT", rules[0])
        self.assertNotIn("Set/Request/machine-01", rules[0])
        self.assertIn("flowbits:set,indproto.nclink.blocked", rules[0])
        self.assertIn("flowbits:isset,indproto.nclink.blocked", rules[1])

    def test_empty_device_matches_operation_prefix(self):
        rules, _, _ = generate_rules.render_rules(nclink_config())

        pattern = re.search(r'pcre:"/(.*)/s"', rules[0]).group(1)
        self.assertIsNotNone(re.search(pattern, 'Set/Request/machine-01/app-01'))
        self.assertIsNone(re.search(pattern, 'Set/Request/'))
        self.assertIsNone(re.search(pattern, 'Set/Request/device/app/extra'))

    def test_pass_is_audited_without_suricata_pass(self):
        rules, _, _ = generate_rules.render_rules(
            nclink_config(operations="model_query,data_query", action="pass")
        )

        self.assertEqual(len(rules), 2)
        self.assertTrue(all(rule.startswith("alert ") for rule in rules))
        self.assertTrue(all("PASS AUDIT NC-LINK" in rule for rule in rules))
        self.assertFalse(any(rule.startswith("pass ") for rule in rules))

    def test_default_block_is_complement_of_allowed_device(self):
        rules, _, _ = generate_rules.render_rules(
            nclink_config(
                operations="data_set", device_uuid="machine-01",
                action="pass", default_action="block",
            )
        )

        self.assertTrue(any("PASS AUDIT NC-LINK DATA_SET" in rule for rule in rules))
        other_devices = [
            rule for rule in rules
            if "default block unapproved PUBLISH" in rule
        ]
        self.assertEqual(len(other_devices), 1)
        pattern = re.search(r'pcre:"/(.*)/s"', other_devices[0]).group(1)
        self.assertIsNone(re.search(pattern, 'Set/Request/machine-01'))
        self.assertIsNone(re.search(pattern, 'Set/Request/machine-01/app-01'))
        self.assertIsNotNone(re.search(pattern, 'Set/Request/other-device/app-01'))
        self.assertIsNotNone(re.search(pattern, 'Method/Call/machine-01/app-01'))
        self.assertIsNotNone(re.search(pattern, 'Unknown/machine-01'))
        generate_rules.validate_unique_sids(rules)

    def test_registration_uses_exact_standard_topic(self):
        rules, _, _ = generate_rules.render_rules(
            nclink_config(operations="register", action="block")
        )

        pattern = re.search(r'pcre:"/(.*)/s"', rules[0]).group(1)
        self.assertIsNotNone(re.search(pattern, 'Register/Request'))
        self.assertIsNone(re.search(pattern, 'Register/Request/other'))

    def test_invalid_device_uuid_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "device UUID"):
            generate_rules.render_rules(nclink_config(device_uuid="machine/#"))


if __name__ == "__main__":
    unittest.main()
