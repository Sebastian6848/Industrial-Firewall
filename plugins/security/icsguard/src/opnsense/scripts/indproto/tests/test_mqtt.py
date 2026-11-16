import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

import generate_rules


def mqtt_config(access="readwrite", topic="", qos="", tls="0", connect="1", action="pass"):
    return ET.fromstring(
        "<IndProto><general><enabled>1</enabled><default_action>block</default_action></general><rules><rule>"
        "<enabled>1</enabled><description>mqtt_test</description><protocol>mqtt</protocol>"
        "<src_ip>any</src_ip><dst_ip>any</dst_ip><dst_port>1883</dst_port>"
        "<action>%s</action><access>%s</access><log_only>0</log_only>"
        "<mqtt_allow_connect>%s</mqtt_allow_connect><mqtt_topic>%s</mqtt_topic>"
        "<mqtt_client_id></mqtt_client_id><mqtt_username></mqtt_username>"
        "<mqtt_qos>%s</mqtt_qos><mqtt_tls>%s</mqtt_tls>"
        "</rule></rules></IndProto>" % (action, access, connect, topic, qos, tls)
    )


class MqttGeneratorTest(unittest.TestCase):
    def test_readwrite_expands_connect_and_operations(self):
        rules, protocols, _ = generate_rules.render_rules(mqtt_config())

        self.assertEqual(protocols, {"mqtt"})
        self.assertEqual(len(rules), 4)
        for operation in ("CONNECT", "PUBLISH", "SUBSCRIBE", "UNSUBSCRIBE"):
            self.assertTrue(any("mqtt.type:%s" % operation in rule for rule in rules))
        self.assertTrue(all(rule.startswith("alert ") for rule in rules))
        self.assertTrue(all("PASS AUDIT" in rule for rule in rules))
        self.assertFalse(any(rule.startswith("pass ") for rule in rules))
        generate_rules.validate_unique_sids(rules)

    def test_write_topic_and_qos_use_native_mqtt_keywords(self):
        rules, _, _ = generate_rules.render_rules(
            mqtt_config(access="write", topic="factory/line1/status", qos="1", connect="0")
        )

        self.assertIn("mqtt.type:PUBLISH", rules[0])
        self.assertIn("mqtt.publish.topic", rules[0])
        self.assertIn("mqtt.qos:1", rules[0])
        self.assertIn("startswith", rules[0])
        self.assertNotIn("factory/line1/status", rules[0])

    def test_connect_can_match_client_id_and_username(self):
        indproto = mqtt_config(access="write", connect="1")
        node = indproto.find("./rules/rule")
        node.find("mqtt_client_id").text = "line1-gateway"
        node.find("mqtt_username").text = "operator"

        rules, _, _ = generate_rules.render_rules(indproto)

        connect = rules[0]
        self.assertIn("mqtt.connect.clientid", connect)
        self.assertIn("mqtt.connect.username", connect)
        self.assertNotIn("line1-gateway", connect)
        self.assertNotIn("operator", connect)

    def test_identity_constraints_require_connect_rule(self):
        indproto = mqtt_config(access="write", connect="0")
        indproto.find("./rules/rule/mqtt_client_id").text = "line1-gateway"

        with self.assertRaisesRegex(ValueError, "require Allow MQTT CONNECT"):
            generate_rules.render_rules(indproto)

    def test_required_username_blocks_missing_and_other_values(self):
        indproto = mqtt_config(access="write", connect="1")
        indproto.find("./rules/rule/mqtt_username").text = "operator"

        rules, _, _ = generate_rules.render_rules(indproto)

        self.assertTrue(any("CONNECT username" in rule and 'content:!"|' in rule for rule in rules))
        self.assertTrue(any("CONNECT missing username" in rule for rule in rules))

    def test_inactive_timed_allow_still_defaults_to_block(self):
        indproto = mqtt_config(access="write", connect="1")
        node = indproto.find("./rules/rule")
        ET.SubElement(node, "time_range_start").text = "08:00"
        ET.SubElement(node, "time_range_end").text = "09:00"

        from unittest.mock import patch
        with patch.object(generate_rules, "in_time_range", return_value=False):
            rules, _, _ = generate_rules.render_rules(indproto)

        self.assertFalse(any(rule.startswith("alert ") for rule in rules))
        for operation in ("CONNECT", "PUBLISH", "SUBSCRIBE", "UNSUBSCRIBE"):
            self.assertTrue(any("default block %s" % operation in rule for rule in rules))

    def test_tls_generates_network_policy_without_payload_claims(self):
        rules, _, _ = generate_rules.render_rules(mqtt_config(tls="1"))

        self.assertEqual(len(rules), 1)
        self.assertIn("TLS PASS AUDIT", rules[0])
        self.assertNotIn("app-layer-protocol:mqtt", rules[0])
        self.assertNotIn("mqtt.type", rules[0])

    def test_default_block_is_complement_of_allowed_publish_topic(self):
        rules, _, _ = generate_rules.render_rules(
            mqtt_config(access="write", topic="factory/line1/status", connect="1")
        )

        self.assertTrue(any(
            rule.startswith("alert ") and "mqtt.type:PUBLISH" in rule for rule in rules
        ))
        other_topics = [rule for rule in rules if "default block other PUBLISH topics" in rule]
        self.assertEqual(len(other_topics), 1)
        self.assertIn('content:!"|', other_topics[0])
        self.assertTrue(any("default block SUBSCRIBE" in rule for rule in rules))
        self.assertTrue(any("default block UNSUBSCRIBE" in rule for rule in rules))
        self.assertFalse(any("default block CONNECT" in rule for rule in rules))
        self.assertFalse(any(rule.startswith("pass ") for rule in rules))

    def test_publish_qos_complement_is_blocked(self):
        rules, _, _ = generate_rules.render_rules(
            mqtt_config(access="write", topic="factory/status", qos="1", connect="0")
        )

        qos_blocks = [rule for rule in rules if "default block other PUBLISH QoS" in rule]
        self.assertEqual(len(qos_blocks), 1)
        self.assertIn("mqtt.qos:!1", qos_blocks[0])

    def test_multiple_allowed_topics_share_one_complement_rule(self):
        indproto = mqtt_config(access="write", topic="factory/line1", connect="0")
        rules_node = indproto.find("rules")
        second = ET.fromstring(ET.tostring(rules_node.find("rule"), encoding="unicode"))
        second.find("mqtt_topic").text = "factory/line2"
        rules_node.append(second)

        rules, _, _ = generate_rules.render_rules(indproto)

        topic_blocks = [rule for rule in rules if "default block other PUBLISH topics" in rule]
        self.assertEqual(len(topic_blocks), 1)
        self.assertEqual(topic_blocks[0].count('content:!"|'), 2)
        self.assertEqual(sum("PASS AUDIT PUBLISH" in rule for rule in rules), 2)

    def test_topic_is_hex_encoded_to_prevent_rule_injection(self):
        rules, _, _ = generate_rules.render_rules(
            mqtt_config(access="write", topic='factory/";sid:1;', connect="0")
        )

        self.assertNotIn('factory/";sid:1;', rules[0])
        generate_rules.validate_unique_sids(rules)

    def test_topic_block_does_not_block_connect_when_connect_is_allowed(self):
        rules, _, _ = generate_rules.render_rules(
            mqtt_config(
                access="readwrite",
                topic="factory/line1/status",
                connect="1",
                action="block",
            )
        )

        self.assertTrue(any("BLOCK PUBLISH" in rule for rule in rules))
        self.assertTrue(any("BLOCK SUBSCRIBE" in rule for rule in rules))
        self.assertTrue(any("BLOCK UNSUBSCRIBE" in rule for rule in rules))
        self.assertFalse(any("BLOCK CONNECT" in rule for rule in rules))

    def test_block_rule_only_blocks_connect_when_explicitly_cleared(self):
        rules, _, _ = generate_rules.render_rules(
            mqtt_config(access="write", topic="factory/status", connect="0", action="block")
        )

        self.assertTrue(any("BLOCK CONNECT" in rule for rule in rules))

    def test_explicit_operations_replace_legacy_access_mapping(self):
        indproto = mqtt_config(access="read", connect="0", action="block")
        indproto.find("./general/default_action").text = "pass"
        ET.SubElement(indproto.find("./rules/rule"), "mqtt_operations").text = "publish"

        rules, _, _ = generate_rules.render_rules(indproto)

        self.assertTrue(any("BLOCK PUBLISH" in rule for rule in rules))
        self.assertFalse(any("BLOCK SUBSCRIBE" in rule for rule in rules))
        self.assertFalse(any("BLOCK UNSUBSCRIBE" in rule for rule in rules))

    def test_empty_explicit_operations_support_connect_only_policy(self):
        indproto = mqtt_config(access="readwrite", connect="0", action="block")
        indproto.find("./general/default_action").text = "pass"
        ET.SubElement(indproto.find("./rules/rule"), "mqtt_operations")

        rules, _, _ = generate_rules.render_rules(indproto)

        self.assertEqual(len(rules), 2)
        self.assertIn("BLOCK CONNECT", rules[0])
        self.assertIn("blocked flow guard", rules[1])

    def test_mqtt_drop_sets_flowbit_and_installs_retransmit_guard(self):
        indproto = mqtt_config(access="write", topic="factory/status", connect="1", action="block")
        indproto.find("./general/default_action").text = "pass"
        ET.SubElement(indproto.find("./rules/rule"), "mqtt_operations").text = "publish"

        rules, _, _ = generate_rules.render_rules(indproto)

        topic_drop = next(rule for rule in rules if "BLOCK PUBLISH" in rule)
        guard = next(rule for rule in rules if "blocked flow guard" in rule)
        self.assertIn("flowbits:set,indproto.mqtt.blocked", topic_drop)
        self.assertIn("flowbits:isset,indproto.mqtt.blocked", guard)
        self.assertIn("flow:to_server,established", guard)
        generate_rules.validate_unique_sids(rules)


if __name__ == "__main__":
    unittest.main()
