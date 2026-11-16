import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

import generate_rules


def configuration(rules, default_action="block"):
    entries = "".join(rules)
    return ET.fromstring(
        "<IndProto><general><enabled>1</enabled><default_action>%s</default_action></general>"
        "<rules>%s</rules></IndProto>" % (default_action, entries)
    )


def modbus_rule(unit_range="", function_codes="", time_start="", time_end=""):
    return (
        "<rule><enabled>1</enabled><description>test</description><protocol>modbus</protocol>"
        "<src_ip>any</src_ip><dst_ip>any</dst_ip><dst_port>502</dst_port>"
        "<action>pass</action><access>readwrite</access>"
        "<function_codes>%s</function_codes><modbus_unit_id>%s</modbus_unit_id>"
        "<time_range_start>%s</time_range_start><time_range_end>%s</time_range_end>"
        "<log_only>0</log_only></rule>"
    ) % (function_codes, unit_range, time_start, time_end)


class GenerateRulesTest(unittest.TestCase):
    def test_protocol_allocator_does_not_collide_after_large_expansion(self):
        indproto = configuration([
            modbus_rule("1-20", "1,2,3,4,5,6,7,8"),
            modbus_rule("21", "1"),
        ])

        rules, protocols, _ = generate_rules.render_rules(indproto)
        sids = generate_rules.validate_unique_sids(rules)

        self.assertGreater(len(rules), 161)
        self.assertEqual(len(sids), len(rules))
        self.assertEqual(protocols, {"modbus"})
        self.assertFalse(any(rule.startswith('pass ') for rule in rules))
        self.assertTrue(any('modbus: unit 21, function 1' in rule for rule in rules))

    def test_default_block_remains_when_timed_rule_is_inactive(self):
        indproto = configuration([modbus_rule(time_start="08:00", time_end="09:00")])

        with patch.object(generate_rules, "in_time_range", return_value=False):
            rules, protocols, time_rules = generate_rules.render_rules(indproto)

        self.assertEqual(protocols, {"modbus"})
        self.assertTrue(time_rules)
        self.assertEqual(len(rules), 1)
        self.assertIn("IndProto default Modbus block", rules[0])

    def test_duplicate_sid_validation_fails_closed(self):
        rule = 'alert tcp any any -> any 502 (msg:"test"; sid:1000000; rev:1;)'
        with self.assertRaisesRegex(ValueError, "duplicate generated sid"):
            generate_rules.validate_unique_sids([rule, rule])

    def test_selected_modbus_codes_override_legacy_field(self):
        indproto = configuration([modbus_rule(function_codes="1")], default_action="pass")
        node = indproto.find("./rules/rule")
        ET.SubElement(node, "modbus_function_codes").text = "5,6"

        rules, _, _ = generate_rules.render_rules(indproto)

        self.assertEqual(len(rules), 2)
        self.assertTrue(any("fc 5" in rule for rule in rules))
        self.assertTrue(any("fc 6" in rule for rule in rules))
        self.assertFalse(any("fc 1" in rule for rule in rules))


if __name__ == "__main__":
    unittest.main()
